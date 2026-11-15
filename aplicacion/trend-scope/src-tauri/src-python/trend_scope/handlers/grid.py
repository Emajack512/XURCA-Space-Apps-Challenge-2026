"""Grid analyses (stage D): build a GridRequest, fetch it through raster/, run models/spatial/grid.py.

No formulas here. Maps go in the block's `grids` list (for the map views, JP's side); findings keep
only compact numbers so `assistant_digest` never carries arrays.

`grids` layer format (frontier with the frontend; tell JP before changing it):
  {"id", "title", "role": "value"|"anomaly"|"trend"|"significance"|"smoothed",
   "variable": {"id", "name", "unit", "kind", "product", "provider", "depth_range", "sensor"},
   "valid": {"start", "end"}, "lats", "lons", "values" (rows = lats ascending; null = no data),
   "mask" (rows of booleans), "color_scale_type": "sequential"|"divergent"|"categorical",
   "center" (0 for divergent, else null), "value_min", "value_max" (recommended, never colours),
   "coverage_fraction", "native_resolution_deg", "provenance": {"urls", "retrieved_at"}}
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..models.spatial import grid as engine
from .contracts import INVALID_REQUEST, METHOD_NOT_AVAILABLE, SOURCE_ERROR, HandlerError, error_item

GRID_STRUCTS = {"grid_trend_map", "grid_anomaly_map", "grid_smoothing", "grid_area_summary", "grid_fire_weather"}
POLYGONS = {"Polygon", "MultiPolygon"}
CADENCE_BY_ROUTE = {"nasa.power.monthly": "monthly", "openmeteo.archive.daily": "daily"}


def connector_reason() -> Optional[str]:
    """None when raster/providers.py is installed; otherwise why grid analyses are unavailable."""
    try:
        from ..raster import providers  # noqa: F401
    except ImportError:
        return "El conector de grillas (raster/providers.py) todavía no está instalado."
    return None


def _area(investigation: dict, wanted: Optional[str], scope: dict) -> dict:
    features = (investigation.get("geography") or {}).get("selection", {}).get("features") or []
    areas = [f for f in features if isinstance(f, dict) and (f.get("geometry") or {}).get("type") in POLYGONS
             and (wanted is None or f.get("id") == wanted)]
    if len(areas) != 1:
        raise HandlerError(INVALID_REQUEST, "Los análisis de mapa necesitan exactamente un polígono seleccionado "
                           "(o indicá area_feature_id).", scope)
    return areas[0]


def _provider_for(variable_id: str, cadence: str, scope: dict) -> str:
    from ..raster.providers import PROVIDERS
    for provider_id, item in PROVIDERS.items():
        if cadence in item.get("cadences", ()) and variable_id in item.get("variables", {}):
            return provider_id
    raise HandlerError(METHOD_NOT_AVAILABLE, f"Ningún conector de grillas ofrece {variable_id} con cadencia {cadence}.", scope)


def _fetch(spec, params: dict, sources: dict, investigation: dict):
    scope = {"analysis_id": spec.id}
    reason = connector_reason()
    if reason:
        raise HandlerError(METHOD_NOT_AVAILABLE, reason, scope)
    from ..raster.contract import GridRequest
    from ..raster.providers import fetch_grid
    from ..services.environmental_series import area_bounds
    source = sources[spec.targets[0]]
    cadence = CADENCE_BY_ROUTE.get(source.get("access"))
    if cadence is None:
        raise HandlerError(METHOD_NOT_AVAILABLE, "Los mapas necesitan una variable de NASA POWER u Open-Meteo como plantilla.", scope)
    area = _area(investigation, params.get("area_feature_id"), scope)
    variable_id = (source.get("upstream") or {}).get("variableId")
    period = investigation.get("time") or {}
    request = GridRequest(provider=_provider_for(variable_id, cadence, scope), variable_id=variable_id,
                          start=period.get("start"), end=period.get("end"), cadence=cadence,
                          bbox=tuple(area_bounds(area["geometry"])), polygon=area["geometry"])
    try:
        request.validate()
        return fetch_grid(request).validate()
    except ValueError as error:
        raise HandlerError(SOURCE_ERROR, str(error), scope) from None


def _matrix(array: np.ndarray) -> list:
    return [[None if not np.isfinite(v) else float(v) for v in row] for row in np.asarray(array, dtype=float)]


def _range(array: np.ndarray, divergent: bool) -> tuple:
    finite = np.asarray(array, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None, None
    if divergent:
        bound = float(np.percentile(np.abs(finite), 98)) or float(np.max(np.abs(finite)))
        return -bound, bound
    return float(np.percentile(finite, 2)), float(np.percentile(finite, 98))


def _layer(field, layer_id: str, title: str, role: str, values: np.ndarray, *, start: str, end: str,
           scale: str = "sequential", unit: Optional[str] = None) -> dict:
    divergent = scale == "divergent"
    low, high = (0.0, 1.0) if scale == "categorical" else _range(values, divergent)
    inside = field.mask.sum()
    coverage = float((np.isfinite(values) & field.mask).sum() / inside) if inside else 0.0
    return {"id": layer_id, "title": title, "role": role,
            "variable": {"id": field.variable_id, "name": field.variable_name, "unit": unit or field.unit,
                         "kind": field.kind, "product": field.product, "provider": field.provider,
                         "depth_range": field.depth_range, "sensor": field.sensor},
            "valid": {"start": start, "end": end}, "lats": [float(v) for v in field.lats],
            "lons": [float(v) for v in field.lons], "values": _matrix(values),
            "mask": [[bool(v) for v in row] for row in field.mask], "color_scale_type": scale,
            "center": 0.0 if divergent else None, "value_min": low, "value_max": high,
            "coverage_fraction": coverage, "native_resolution_deg": list(field.native_resolution_deg),
            "provenance": {"urls": list(field.urls), "retrieved_at": field.retrieved_at}}


def _what(field) -> dict:
    return {"variable": field.variable_id, "name": field.variable_name, "unit": field.unit,
            "provider": field.provider, "product": field.product, "kind": field.kind}


def _where(field, n_cells: int) -> dict:
    return {"mode": "grid", "n_cells_inside": int(field.mask.sum()), "n_cells_analyzed": int(n_cells),
            "native_resolution_deg": list(field.native_resolution_deg),
            "bbox": [float(field.lons[0]), float(field.lats[0]), float(field.lons[-1]), float(field.lats[-1])],
            "label": "Celdas de la grilla del proveedor dentro del polígono (no es un promedio zonal exacto)"}


def _finding(kind: str, field, how_much: dict, *, n_cells: int, notes: list, limitations: list,
             test: Optional[str] = None, conclusiveness: str = "descriptive") -> dict:
    return {"type": kind, "what": _what(field), "where": _where(field, n_cells),
            "when": {"start": field.times[0], "end": field.times[-1], "cadence": field.cadence},
            "how_much": how_much, "significant": None, "p_value": None, "alpha": how_much.get("alpha"),
            "test": test, "conclusiveness": conclusiveness, "statement_key": f"{kind}.result",
            "notes": notes, "limitations": limitations}


def _trend(field, params) -> tuple:
    result = engine.grid_trends(field.times, field.values, field.mask, cadence=field.cadence,
                                alpha=params["alpha"], min_points=params["min_points"])
    tested = np.isfinite(result["slope_per_decade"])
    slopes = result["slope_per_decade"][tested]
    unit = f"{field.unit}/decade"
    how_much = {"unit": unit, "n_tested": result["n_tested"], "n_significant_fdr": result["n_significant_fdr"],
                "n_positive": result["n_positive"], "n_negative": result["n_negative"], "alpha": result["alpha"],
                "median_per_decade": float(np.median(slopes)) if slopes.size else None,
                "min_per_decade": float(slopes.min()) if slopes.size else None,
                "max_per_decade": float(slopes.max()) if slopes.size else None}
    start, end = field.times[0], field.times[-1]
    layers = [_layer(field, "trend", "Tendencia por década (Sen, sin ciclo anual)", "trend", result["slope_per_decade"],
                     start=start, end=end, scale="divergent", unit=unit),
              _layer(field, "significance", "Celdas con tendencia significativa tras FDR", "significance",
                     np.where(tested, result["significant_fdr"].astype(float), np.nan), start=start, end=end,
                     scale="categorical", unit="1")]
    finding = _finding("grid_trend", field, how_much, n_cells=result["n_tested"], test="mann_kendall+fdr_bh",
                       notes=["Tendencia de Sen y prueba de Mann-Kendall por celda sobre anomalías mensuales; "
                              "falsos descubrimientos controlados con Benjamini-Hochberg."],
                       limitations=["Celdas vecinas están correlacionadas: el control de FDR es aproximado.",
                                    "No hay evidencia suficiente en una celda no significativa: no significa que no cambie.",
                                    "Una celda es la grilla nativa del proveedor; no representa un punto exacto."],
                       conclusiveness="statistical")
    return [finding], layers, result["warnings"]


def _anomaly(field, params) -> tuple:
    base = params.get("baseline") or {"start": "1991-01-01", "end": "2020-12-31"}
    period = params.get("period") or {"start": field.times[-12] if len(field.times) >= 12 else field.times[0],
                                      "end": field.times[-1]}
    warnings = []
    if field.times[0] > base["start"] or field.times[-1] < base["end"]:
        base = {"start": field.times[0], "end": field.times[-1]}
        warnings.append("La base 1991-2020 no está cubierta por la grilla: se usó todo el período descargado como base.")
    result = engine.grid_anomaly(field.times, field.values, field.mask, base_start=base["start"], base_end=base["end"],
                                 period_start=period["start"], period_end=period["end"],
                                 min_count=params["baseline_min_count"])
    finite = result["anomaly"][np.isfinite(result["anomaly"])]
    how_much = {"unit": field.unit, "baseline": base, "period": period, "n_period_slices": result["n_period_slices"],
                "mean": float(finite.mean()) if finite.size else None,
                "min": float(finite.min()) if finite.size else None, "max": float(finite.max()) if finite.size else None}
    layers = [_layer(field, "anomaly", "Anomalía media del período respecto de la base", "anomaly", result["anomaly"],
                     start=period["start"], end=period["end"], scale="divergent")]
    finding = _finding("grid_anomaly", field, how_much, n_cells=int(finite.size),
                       notes=[f"Base {base['start']} a {base['end']}; período {period['start']} a {period['end']}."],
                       limitations=["Anomalía descriptiva: no es una prueba de significancia.",
                                    "Una anomalía no es una tendencia."])
    return [finding], layers, warnings + result["warnings"]


def _smoothing(field, params) -> tuple:
    complete = [k for k in range(len(field.times)) if np.isfinite(field.values[k]).all()]
    if not complete:
        raise ValueError("Ningún paso de la grilla está completo: no se suaviza para no inventar las celdas faltantes.")
    k = complete[-1]
    date = field.times[k]
    result = engine.smooth_slices(field.values[k:k + 1], field.mask, size=params["size"])
    layers = [_layer(field, "smoothed", f"{date} suavizado ({params['size']}×{params['size']} celdas)", "smoothed",
                     result["values"][0], start=date, end=date),
              _layer(field, "value", f"{date} (sin suavizar)", "value", field.values[k], start=date, end=date)]
    how_much = {"unit": field.unit, "kernel_size": result["kernel_size"], "boundary": result["boundary"],
                "date": date, "skipped_recent_incomplete": len(field.times) - 1 - k}
    finding = _finding("grid_smoothing", field, how_much, n_cells=int(np.isfinite(result["values"][0]).sum()),
                       notes=[f"Convolución 2D (media de caja) sobre {date}, el paso más reciente sin celdas faltantes; "
                              "los bordes sin ventana completa se descartan."],
                       limitations=["Suavizar no agrega información ni resolución: es solo para ver el patrón general."])
    return [finding], layers, result["warnings"]


def _area_summary(field, params) -> tuple:
    result = engine.area_mean(field.values, field.lats, field.mask)
    mean = result["mean"]
    finite = np.isfinite(mean)
    how_much = {"unit": field.unit, "n_cells_inside": result["n_cells_inside"],
                "mean_of_period": float(mean[finite].mean()) if finite.any() else None,
                "min_coverage": float(result["coverage_fraction"].min()),
                "series": [{"date": t, "value": None if not math.isfinite(v) else float(v), "coverage": float(c)}
                           for t, v, c in zip(field.times[-24:], mean[-24:], result["coverage_fraction"][-24:])]}
    layers = [_layer(field, "value", "Último mes", "value", field.values[-1], start=field.times[-1], end=field.times[-1])]
    finding = _finding("grid_area_summary", field, how_much, n_cells=result["n_cells_inside"],
                       notes=["Media ponderada por cos(latitud) de las celdas con dato cuyo centro cae en el polígono "
                              "(se muestran los últimos 24 pasos)."],
                       limitations=["No es un promedio zonal exacto: las celdas parcialmente cubiertas cuentan enteras.",
                                    "Cuando la cobertura es baja, la media representa solo las celdas con dato."])
    return [finding], layers, result["warnings"]


FWI_VARIABLES = {"temperature": "temperature_2m_mean", "humidity": "relative_humidity_2m_mean",
                 "wind": "wind_speed_10m_max", "precipitation": "precipitation_sum"}
FWI_UNITS = {"temperature": {"C", "°C"}, "humidity": {"%"}, "wind": {"km/h"}, "precipitation": {"mm"}}
FWI_SPINUP_DAYS = 30


def _fetch_fwi_inputs(spec, params, sources, investigation) -> dict:
    """The four daily grids of the FWI, same area and period; units checked, never converted here."""
    scope = {"analysis_id": spec.id}
    reason = connector_reason()
    if reason:
        raise HandlerError(METHOD_NOT_AVAILABLE, reason, scope)
    from ..raster.contract import GridRequest
    from ..raster.providers import fetch_grid
    from ..services.environmental_series import area_bounds
    area = _area(investigation, params.get("area_feature_id"), scope)
    period = investigation.get("time") or {}
    fields = {}
    for role, variable_id in FWI_VARIABLES.items():
        request = GridRequest(provider=_provider_for(variable_id, "daily", scope), variable_id=variable_id,
                              start=period.get("start"), end=period.get("end"), cadence="daily",
                              bbox=tuple(area_bounds(area["geometry"])), polygon=area["geometry"])
        try:
            request.validate()
            field = fetch_grid(request).validate()
        except ValueError as error:
            raise HandlerError(SOURCE_ERROR, str(error), scope) from None
        if field.unit not in FWI_UNITS[role]:
            label = {"temperature": "la temperatura", "humidity": "la humedad", "wind": "el viento",
                     "precipitation": "la lluvia"}[role]
            raise HandlerError(INVALID_REQUEST, f"El FWI necesita {label} en {'/'.join(sorted(FWI_UNITS[role]))} y la "
                               f"grilla trae {field.unit}: no se convierte en silencio.", scope)
        fields[role] = field
    first = fields["temperature"]
    for role, field in fields.items():
        if field.times != first.times or field.values.shape != first.values.shape:
            raise HandlerError(INVALID_REQUEST, "Las cuatro grillas del FWI no comparten fechas ni celdas.", scope)
    if len(first.times) <= FWI_SPINUP_DAYS + 30:
        raise HandlerError(INVALID_REQUEST, f"El FWI necesita más de {FWI_SPINUP_DAYS + 30} días: los primeros "
                           f"{FWI_SPINUP_DAYS} se descartan como arranque de los códigos de humedad.", scope)
    return fields


def _fire_weather(fields, params) -> tuple:
    t = fields["temperature"]
    result = engine.grid_fwi(t.times, t.values, fields["humidity"].values, fields["wind"].values,
                             fields["precipitation"].values, t.lats, t.mask)
    fwi = result["fwi"][FWI_SPINUP_DAYS:]
    times = t.times[FWI_SPINUP_DAYS:]
    last30 = fwi[-30:]
    with np.errstate(invalid="ignore"):
        mean_last30 = np.where(np.isfinite(last30).any(axis=0), np.nanmean(np.where(np.isfinite(last30), last30, np.nan), axis=0), np.nan)
    finite_last = fwi[-1][np.isfinite(fwi[-1])]
    how_much = {"unit": "1", "date": times[-1], "spinup_days": FWI_SPINUP_DAYS,
                "last_day_median": float(np.median(finite_last)) if finite_last.size else None,
                "last_day_max": float(finite_last.max()) if finite_last.size else None,
                "last30_mean_max": float(np.nanmax(mean_last30)) if np.isfinite(mean_last30).any() else None,
                "n_skipped_cells": result["n_skipped_cells"], "initial_state": result["initial_state"]}
    fwi_field = t  # geometry and provenance of the temperature grid; the FWI is dimensionless
    layers = [_layer(fwi_field, "fwi_last", f"FWI del {times[-1]}", "value", fwi[-1], start=times[-1], end=times[-1], unit="1"),
              _layer(fwi_field, "fwi_mean30", f"FWI medio de los últimos 30 días hasta {times[-1]}", "value", mean_last30,
                     start=times[-30], end=times[-1], unit="1")]
    for layer in layers:
        layer["variable"].update({"id": "fwi", "name": "Índice meteorológico de peligro de incendio (FWI, adimensional)"})
        layer["provenance"]["urls"] = [u for f in fields.values() for u in f.urls]
    finding = _finding("grid_fire_weather", fwi_field, how_much, n_cells=int(np.isfinite(fwi[-1]).sum()),
                       notes=["Sistema canadiense FWI (Van Wagner 1987), verificado contra xclim; factores de duración "
                              "del día según la latitud de cada celda."],
                       limitations=["Es peligro meteorológico relativo: no es probabilidad de incendio, ni ubicación, "
                                    "ni superficie quemada; no mostrar como porcentaje.",
                                    "Usa medias diarias en lugar de valores de mediodía (aproximación).",
                                    "Las clases de peligro (bajo, alto, extremo) no están calibradas para la región."])
    finding["what"].update({"variable": "fwi", "name": "FWI", "unit": "1"})
    return [finding], layers, result["warnings"]


RUNNERS = {"grid_trend_map": _trend, "grid_anomaly_map": _anomaly, "grid_smoothing": _smoothing,
           "grid_area_summary": _area_summary}


def analyze(spec, resolved, sources: dict, investigation: dict) -> dict:
    """Run one grid analysis. Never raises: errors go into the block."""
    struct = resolved.struct
    block = {"id": spec.id, "struct": struct.struct_id, "kind": struct.kind, "status": "failed",
             "targets": list(spec.targets), "parameters_effective": resolved.params, "data_profile": None,
             "transformations": [], "steps": [], "findings": [], "verdict": None, "forecast": None,
             "charts": [{"kind": "map"}], "grids": [], "warnings": [], "errors": []}
    try:
        if struct.struct_id == "grid_fire_weather":
            fields = _fetch_fwi_inputs(spec, resolved.params, sources, investigation)
            field = fields["temperature"]
            findings, layers, warnings = _fire_weather(fields, resolved.params)
        else:
            field = _fetch(spec, resolved.params, sources, investigation)
            findings, layers, warnings = RUNNERS[struct.struct_id](field, resolved.params)
    except HandlerError as error:
        block["errors"].append(error.to_dict())
        return block
    except ValueError as error:
        block["errors"].append(error_item(INVALID_REQUEST, str(error), {"analysis_id": spec.id}))
        return block
    block["data_profile"] = {"cadence": field.cadence, "n_times": len(field.times), "n_lat": int(field.lats.size),
                             "n_lon": int(field.lons.size), "n_cells_inside": int(field.mask.sum()),
                             "coverage_min": float(field.coverage_fraction().min())}
    block["findings"], block["grids"] = findings, layers
    block["warnings"] = [{"step": "grid", "message": text} for text in list(field.warnings) + list(warnings)]
    block["status"] = "completed"
    return block
