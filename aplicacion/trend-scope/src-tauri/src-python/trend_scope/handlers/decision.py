"""Decision layer: turns step results into findings and a verdict on the hypothesis.

Deterministic rules, no language model. The challenge questions are answered
literally in every finding: what changes (`what`), where (`where`), how much
(`how_much`) and whether it is significant (`significant`, `p_value`).

Fixed rules:
  * p >= alpha, or a confidence interval that includes 0 -> "inconclusive"
    ("no hay evidencia suficiente"); never "sin cambios".
  * Anomalies, trends and events are different findings.
  * No "percentage of certainty" is ever produced: closeness to a hypothesis
    is expressed through the p-value, the interval and the sign.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Optional

import numpy as np

from ..models.stats.multiple_testing import fdr_bh
from ..services.station_catalogs import ENTITY_ROUTES

SPI_DEFICIT = -1.0   # documented SPI state thresholds (plan: -1 / +1)
SPI_EXCESS = 1.0
OPERATORS = {">": lambda a, b: a > b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b}


def _f(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _step(steps: list, prefix: str, completed: bool = True):
    for item in steps:
        if item.step_id == prefix or item.step_id.startswith(prefix + ":"):
            if not completed or item.status == "completed":
                return item
    return None


def _what(series: dict, prepared) -> dict:
    return {"variable": series.get("variable"), "family": prepared.meta["family"], "source_id": series.get("id"),
            "provider": series.get("provider"), "product": series.get("product"), "unit": prepared.meta["unit"]}


def _where(series: dict, source: Optional[dict]) -> dict:
    coordinates = series.get("coordinates")
    entity = (source or {}).get("access") in ENTITY_ROUTES
    mode = "entity" if entity else ("point" if coordinates else "unknown")
    return {"mode": mode, "coordinates": coordinates, "label": series.get("location")}


def _when(prepared) -> dict:
    dates = prepared.meta["dates"]
    return {"start": dates[0], "end": dates[-1], "cadence": prepared.profile["cadence"], "n": prepared.profile["n"]}


def _finding(kind: str, series, source, prepared, **fields) -> dict:
    base = {"type": kind, "what": _what(series, prepared), "where": _where(series, source), "when": _when(prepared),
            "how_much": None, "significant": None, "p_value": None, "alpha": None, "test": None,
            "conclusiveness": "not_tested", "statement_key": f"{kind}.descriptive", "notes": [], "limitations": []}
    base.update(fields)
    return base


def _gap(kind: str, series, source, prepared, steps: list, why: str) -> dict:
    failed = [f"{s.step_id}: {s.reason}" for s in steps if s.status != "completed" and not s.optional and s.reason]
    return _finding(kind, series, source, prepared, conclusiveness="insufficient_data",
                    statement_key=f"{kind}.insufficient_data", notes=[why] + failed)


# ----------------------------------------------------------------------------- per struct

def _describe(ctx) -> dict:
    step = _step(ctx["steps"], "summary")
    if step is None:
        return {"findings": [_gap("descriptive", ctx["series"], ctx["source"], ctx["prepared"], ctx["steps"],
                                  "No se pudo calcular el resumen.")], "verdict": None, "charts": []}
    p = step.payload
    unit = ctx["prepared"].meta["unit"]
    finding = _finding("descriptive", ctx["series"], ctx["source"], ctx["prepared"],
                       how_much={"n": p["n"], "mean": _f(p["mean"]), "std": _f(p["std"]), "minimum": _f(p["minimum"]),
                                 "maximum": _f(p["maximum"]), "unit": unit,
                                 "quantiles": {f"{q:g}": _f(v) for q, v in zip(p["quantile_levels"], p["quantile_values"])}},
                       statement_key="descriptive.summary",
                       limitations=["Describe las observaciones recibidas; no es un promedio de área ni un total anual."])
    return {"findings": [finding], "verdict": None,
            "charts": [{"kind": "timeseries", "series_ref": ctx["series"].get("id")}]}


def _trend(ctx) -> dict:
    steps, params, prepared = ctx["steps"], ctx["params"], ctx["prepared"]
    slope = _step(steps, "slope")
    test = _step(steps, "test_modified") or _step(steps, "test")
    if slope is None or test is None:
        why = "No se pudo estimar la tendencia o su significancia."
        return {"findings": [_gap("trend", ctx["series"], ctx["source"], prepared, steps, why)],
                "verdict": _verdict_trend(ctx["hypothesis"], None), "charts": []}
    s, alpha = slope.payload, params["alpha"]
    estimate, lower, upper = float(s["slope"]), float(s["lower"]), float(s["upper"])
    p_value = float(test.payload["p_value"])
    significant = p_value < alpha
    excludes_zero = lower > 0 or upper < 0
    conclusive = significant and excludes_zero
    direction = "increasing" if estimate > 0 else "decreasing" if estimate < 0 else "none"
    unit = prepared.meta["unit"]
    span = prepared.profile["span_years"]
    notes = []
    if significant != excludes_zero:
        notes.append("El valor p y el intervalo de confianza no coinciden (la prueba y el intervalo usan supuestos "
                     "distintos); se trata como no concluyente.")
    if _step(steps, "deseason") is None:
        notes.append("La serie no se desestacionalizó antes de estimar la pendiente.")
    base = prepared.derived.get("baseline")
    if base and base.get("note"):
        notes.append(base["note"])
    if prepared.profile["cadence"] == "irregular":
        notes.append("Serie irregular: no se corrigió por muestreo desigual.")
    finding = _finding(
        "trend", ctx["series"], ctx["source"], prepared,
        how_much={"per_year": estimate, "per_decade": estimate * 10, "unit": f"{unit}/decade",
                  "unit_per_year": f"{unit}/year",
                  "interval": {"lower": lower * 10, "upper": upper * 10, "level": float(s["confidence"]),
                               "unit": f"{unit}/decade"},
                  "total_change": estimate * span, "total_change_unit": unit, "span_years": span,
                  "direction": direction},
        significant=significant, p_value=p_value, alpha=alpha, test=test.method_id,
        conclusiveness="conclusive" if conclusive else "inconclusive",
        statement_key=f"trend.significant.{direction}" if conclusive else "trend.inconclusive",
        notes=notes,
        limitations=["La significancia no establece causalidad ni importancia física.",
                     "El intervalo de la pendiente supone independencia serial; con autocorrelación es demasiado angosto.",
                     "Un solo punto o estación no representa el promedio de una región."])
    charts = [{"kind": "timeseries_trend", "series_ref": ctx["series"].get("id"),
               "overlays": [{"type": "trend_slope", "step": "slope", "per_year": estimate,
                             "lower_per_year": lower, "upper_per_year": upper, "level": float(s["confidence"])}]}]
    return {"findings": [finding], "verdict": _verdict_trend(ctx["hypothesis"], finding), "charts": charts}


def _verdict_trend(hypothesis: Optional[dict], finding: Optional[dict]) -> Optional[dict]:
    if hypothesis is None:
        return None
    base = {"hypothesis": hypothesis}
    if finding is None or finding["conclusiveness"] == "insufficient_data":
        return {**base, "status": "not_testable", "reason_key": "verdict.not_testable", "evidence": {}}
    how = finding["how_much"]
    evidence = {"p_value": finding["p_value"], "alpha": finding["alpha"],
                "interval_excludes_zero": how["interval"]["lower"] > 0 or how["interval"]["upper"] < 0,
                "observed_direction": how["direction"], "per_decade": how["per_decade"], "unit": how["unit"]}
    if finding["conclusiveness"] != "conclusive":
        return {**base, "status": "inconclusive", "reason_key": "verdict.inconclusive", "evidence": evidence}
    wanted = hypothesis.get("direction", "any")
    matches = wanted == "any" or wanted == how["direction"]
    evidence["direction_matches"] = matches
    if matches and hypothesis.get("min_rate") is not None and abs(how["per_year"]) < hypothesis["min_rate"]:
        evidence["min_rate"] = hypothesis["min_rate"]
        return {**base, "status": "not_supported", "reason_key": "verdict.trend.below_min_rate", "evidence": evidence}
    status = "supported" if matches else "not_supported"
    return {**base, "status": status, "reason_key": f"verdict.trend.{status}", "evidence": evidence}


def _anomaly(ctx) -> dict:
    step = _step(ctx["steps"], "anomalies")
    prepared = ctx["prepared"]
    if step is None:
        return {"findings": [_gap("anomaly", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudieron calcular las anomalías.")],
                "verdict": _verdict_threshold(ctx["hypothesis"], None), "charts": []}
    values = np.asarray(step.payload["values"], dtype=float)
    dates = prepared.meta["dates"]
    kind = ctx["params"]["kind"]
    unit = prepared.meta["unit"] if kind == "absolute" else "%" if kind == "percent" else "1"
    peak = int(np.argmax(np.abs(values)))
    base = prepared.derived.get("baseline")
    finding = _finding(
        "anomaly", ctx["series"], ctx["source"], prepared,
        how_much={"kind": kind, "unit": unit, "last": float(values[-1]), "last_date": dates[-1],
                  "mean": float(values.mean()), "largest": float(values[peak]), "largest_date": dates[peak],
                  "n": int(values.size)},
        statement_key="anomaly.descriptive", notes=[base["note"]] if base and base.get("note") else [],
        limitations=["La adecuación del período de referencia la decide quien consulta.",
                     "Una anomalía no es una tendencia ni un evento: son resultados distintos."])
    finding["baseline"] = base
    charts = [{"kind": "anomaly_bars", "series_ref": ctx["series"].get("id"), "values_step": "anomalies", "unit": unit}]
    return {"findings": [finding], "verdict": _verdict_threshold(ctx["hypothesis"], values), "charts": charts}


def _verdict_threshold(hypothesis: Optional[dict], values) -> Optional[dict]:
    if hypothesis is None:
        return None
    base = {"hypothesis": hypothesis}
    if values is None or len(values) == 0:
        return {**base, "status": "not_testable", "reason_key": "verdict.not_testable", "evidence": {}}
    statistic = hypothesis.get("statistic", "last")
    observed = {"last": values[-1], "max": values.max(), "min": values.min(), "mean": values.mean()}[statistic]
    met = OPERATORS[hypothesis["operator"]](float(observed), float(hypothesis["value"]))
    return {**base, "status": "supported" if met else "not_supported",
            "reason_key": "verdict.threshold.met" if met else "verdict.threshold.unmet",
            "evidence": {"statistic": statistic, "observed": float(observed), "operator": hypothesis["operator"],
                         "value": hypothesis["value"], "descriptive_only": True}}


def _spi(ctx) -> dict:
    prepared = ctx["prepared"]
    dates = prepared.meta["dates"]
    findings, used = [], []
    for step in ctx["steps"]:
        if not step.step_id.startswith("spi:") or step.status != "completed":
            continue
        p = step.payload
        spi, valid = np.asarray(p["spi"], dtype=float), np.asarray(p["valid"], dtype=bool)
        if not valid.any():
            continue
        v = spi[valid]
        position = np.flatnonzero(valid)
        findings.append(_finding(
            "index", ctx["series"], ctx["source"], prepared,
            how_much={"scale_months": int(p["scale"]), "n_valid": int(valid.sum()),
                      "deficit_fraction": float(np.mean(v <= SPI_DEFICIT)),
                      "excess_fraction": float(np.mean(v >= SPI_EXCESS)),
                      "last": float(v[-1]), "last_date": dates[int(position[-1])],
                      "minimum": float(v.min()), "unit": "1",
                      "thresholds": {"deficit": SPI_DEFICIT, "excess": SPI_EXCESS}},
            statement_key="spi.descriptive",
            notes=([f"Meses con calibración de menos de 20 años (baja robustez): {w}" for w in p["warnings"] if "Low robustness" in w]),
            limitations=["No se suman SPI de distintas escalas.", "El SPI no es humedad del suelo.",
                         "La bondad de ajuste de la distribución gamma no se evaluó."]))
        used.append(step.step_id)
    if not findings:
        return {"findings": [_gap("index", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudo calcular el SPI en ninguna escala.")], "verdict": None, "charts": []}
    return {"findings": findings, "verdict": None,
            "charts": [{"kind": "spi_states", "series_ref": ctx["series"].get("id"), "steps": used}]}


def _fit(ctx) -> dict:
    step = _step(ctx["steps"], "fit")
    prepared = ctx["prepared"]
    if step is None:
        return {"findings": [_gap("fit", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudo ajustar el modelo.")], "verdict": None, "charts": []}
    p = step.payload
    unit = prepared.meta["unit"]
    how = {"model": step.method_id, "parameters": _plain(p.get("parameters", {})), "metrics": _plain(p.get("metrics", {})),
           "time_unit": "year", "unit": unit}
    parameters = p.get("parameters", {})
    if step.method_id == "linear" and _f(parameters.get("slope")) is not None:
        how["slope_per_year"] = float(parameters["slope"])
        how["slope_unit"] = f"{unit}/year"
    finding = _finding("fit", ctx["series"], ctx["source"], prepared, how_much=how, statement_key="fit.descriptive",
                       limitations=["Ajuste descriptivo dentro de la muestra: no evalúa significancia ni es un pronóstico validado."])
    return {"findings": [finding], "verdict": None,
            "charts": [{"kind": "timeseries", "series_ref": ctx["series"].get("id"), "fit_step": "fit"}]}


def _add_months(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _forecast(ctx) -> dict:
    step = _step(ctx["steps"], "forecast")
    prepared, hypothesis = ctx["prepared"], ctx["hypothesis"]
    if step is None:
        return {"findings": [_gap("forecast", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudo generar el pronóstico.")],
                "verdict": _verdict_forecast(hypothesis, None), "charts": [], "forecast": None}
    p = step.payload
    unit = prepared.meta["unit"]
    last = date.fromisoformat(prepared.meta["dates"][-1])
    central = [float(v) for v in p["central"]]
    times = [_add_months(last, i).isoformat() for i in range(1, len(central) + 1)]
    lower = [_f(v) for v in p["lower"]]
    upper = [_f(v) for v in p["upper"]]
    has_interval = any(v is not None for v in lower)
    interval = p["interval"]
    block = {
        "mode": p["mode"], "model": p["model"], "delivered": p["delivered"], "unit": unit,
        "issue_date": prepared.meta["dates"][-1], "times": times, "central": central, "central_kind": "point_forecast",
        "interval": ({"level": interval["level"], "lower": lower, "upper": upper,
                      "empirical_coverage": interval["empirical_coverage"], "calibrated": interval["calibrated"],
                      "coverage_floor": interval.get("coverage_floor"), "kind": "predictive"} if has_interval else None),
        "min_skill": p.get("min_skill"),
        "baseline": {"name": p["best_baseline"], "values": [float(v) for v in p["baseline_values"]]},
        "skill_vs_baseline": [_f(v) for v in p["skill_vs_best_baseline"]],
        "horizon_requested": p["horizon_requested"], "horizon_validated": p["horizon_validated"],
        "not_superior_to_baseline": p["not_superior_to_baseline"],
        "backtest": {"n_origins": p["backtest"]["n_origins"], "initial_train": p["backtest"]["initial_train"],
                     "design": p["backtest"]["design"]},
        "uncertainty": p["uncertainty"],
        "assumptions": ["Pronóstico estadístico de la serie; no incluye predictores físicos ni escenarios."],
    }
    finding = _finding(
        "forecast", ctx["series"], ctx["source"], prepared,
        how_much={"horizon_steps": len(central), "unit": unit, "first": central[0], "last": central[-1],
                  "model": p["model"], "delivered": p["delivered"], "mode": p["mode"],
                  "horizon_validated": p["horizon_validated"]},
        conclusiveness="validated" if p["mode"] == "validated_forecast" else "exploratory",
        statement_key=f"forecast.{p['mode']}", notes=list(p["warnings"]),
        limitations=["Es un pronóstico estadístico de una sola serie.",
                     "El intervalo es predictivo (valores futuros), no un intervalo de confianza de un parámetro.",
                     "El desempeño pasado no garantiza el futuro."])
    finding["not_superior_to_baseline"] = p["not_superior_to_baseline"]
    return {"findings": [finding], "verdict": _verdict_forecast(hypothesis, block), "forecast": block,
            "charts": [{"kind": "forecast_fan", "series_ref": ctx["series"].get("id")}]}


def _verdict_forecast(hypothesis: Optional[dict], block: Optional[dict]) -> Optional[dict]:
    if hypothesis is None:
        return None
    base = {"hypothesis": hypothesis}
    if block is None:
        return {**base, "status": "not_testable", "reason_key": "verdict.not_testable", "evidence": {}}
    index = hypothesis["at_step"] - 1
    compare = OPERATORS[hypothesis["operator"]]
    value = float(hypothesis["value"])
    central = block["central"][index]
    evidence = {"central": central, "operator": hypothesis["operator"], "value": value, "at_step": hypothesis["at_step"],
                "date": block["times"][index], "mode": block["mode"]}
    interval = block["interval"]
    if interval and interval["lower"][index] is not None and interval["upper"][index] is not None:
        inside = [compare(interval["lower"][index], value), compare(interval["upper"][index], value)]
        evidence.update({"lower": interval["lower"][index], "upper": interval["upper"][index],
                         "interval_calibrated": interval["calibrated"]})
        status = "supported" if all(inside) else "not_supported" if not any(inside) else "inconclusive"
    else:
        status = "supported" if compare(central, value) else "not_supported"
        evidence["descriptive_only"] = True
    if block["mode"] != "validated_forecast" and status == "supported":
        evidence["caveat"] = "pronóstico no validado: la condición se cumple solo en la estimación central"
    return {**base, "status": status, "reason_key": f"verdict.forecast.{status}", "evidence": evidence}


def _plain(mapping) -> dict:
    return {str(k): _f(v) if isinstance(v, (int, float)) else v for k, v in dict(mapping).items()}


# ----------------------------------------------------------------------------- phase 2

CHART_LIMIT = 5000


def _listed(array, limit: int = CHART_LIMIT):
    """Plain list of finite floats for a chart overlay; None when the array is too long."""
    values = np.asarray(array, dtype=float)
    if values.size > limit:
        return None
    return [_f(v) for v in values]


def _seasonality(ctx) -> dict:
    steps, prepared = ctx["steps"], ctx["prepared"]
    harmonic = _step(steps, "harmonic")
    if harmonic is None:
        return {"findings": [_gap("seasonality", ctx["series"], ctx["source"], prepared, steps,
                                  "No se pudo ajustar el ciclo anual.")], "verdict": None, "charts": []}
    unit = prepared.meta["unit"]
    parameters, metrics = harmonic.payload.get("parameters", {}), harmonic.payload.get("metrics", {})
    how = {"unit": unit, "period": "1 año", "harmonics": ctx["params"]["harmonics"],
           "coefficients": {k: _f(v) for k, v in parameters.items() if k.startswith(("cos_", "sin_"))},
           "r2": _f(metrics.get("r2")), "seasonal_strength": prepared.profile.get("seasonal_strength"),
           "annual_bin": None, "stl_seasonal_range": None}
    notes = []
    spectrum = _step(steps, "spectrum")
    if spectrum is not None:
        frequencies = np.asarray(spectrum.payload["frequencies"], dtype=float)   # cycles per year
        amplitude = np.asarray(spectrum.payload["amplitude"], dtype=float)
        if frequencies.size > 1:
            k = int(np.argmin(np.abs(frequencies - 1.0)))
            how["annual_bin"] = {"frequency_per_year": _f(frequencies[k]), "amplitude": _f(amplitude[k]), "unit": unit}
    else:
        notes.append("El espectro de amplitud no se calculó.")
    decomposition = _step(steps, "decomposition")
    chart = {"kind": "decomposition", "series_ref": ctx["series"].get("id"), "dates": prepared.meta["dates"]}
    if decomposition is not None:
        seasonal = np.asarray(decomposition.payload["seasonal"], dtype=float)
        how["stl_seasonal_range"] = _f(seasonal.max() - seasonal.min())
        chart.update({"trend": _listed(decomposition.payload["trend"]), "seasonal": _listed(seasonal),
                      "residual": _listed(decomposition.payload["residuals"])})
    else:
        notes.append("La descomposición STL no está disponible (falta statsmodels o la serie es corta).")
    fitted = harmonic.payload.get("y_pred")
    if fitted is not None:
        chart["harmonic_fit"] = _listed(fitted)
    finding = _finding("seasonality", ctx["series"], ctx["source"], prepared, how_much=how,
                       statement_key="seasonality.descriptive", notes=notes,
                       limitations=["Describe el ciclo de la muestra; no prueba que sea estadísticamente significativo.",
                                    "El espectro tiene fugas espectrales; la descomposición STL usa todo el período."])
    return {"findings": [finding], "verdict": None, "charts": [chart]}


def _verdict_change_point(hypothesis: Optional[dict], finding: Optional[dict]) -> Optional[dict]:
    if hypothesis is None:
        return None
    base = {"hypothesis": hypothesis}
    if finding is None or finding["conclusiveness"] == "insufficient_data":
        return {**base, "status": "not_testable", "reason_key": "verdict.not_testable", "evidence": {}}
    changes = finding["how_much"]["changes"]
    window = hypothesis.get("window")
    inside = [c for c in changes if not window or window["start"] <= c["date"] <= window["end"]]
    evidence = {"n_changes": len(changes), "dates_in_window": [c["date"] for c in inside], "window": window,
                "caveat": "detección por penalización: no es una prueba de significancia"}
    if inside:
        return {**base, "status": "supported", "reason_key": "verdict.change_point.detected", "evidence": evidence}
    # A detector that finds nothing does not prove that nothing changed.
    return {**base, "status": "inconclusive", "reason_key": "verdict.inconclusive", "evidence": evidence}


def _change_point(ctx) -> dict:
    steps, prepared = ctx["steps"], ctx["prepared"]
    segments_step = _step(steps, "segments")
    if segments_step is None:
        return {"findings": [_gap("change_point", ctx["series"], ctx["source"], prepared, steps,
                                  "No se pudieron detectar cambios.")],
                "verdict": _verdict_change_point(ctx["hypothesis"], None), "charts": []}
    dates = prepared.meta["dates"]
    deseason = _step(steps, "deseason")
    # Segment means on the same series PELT segmented: with the seasonal cycle removed, a segment that
    # covers more summers than winters does not fake a level shift.
    if deseason is not None and isinstance(deseason.payload, dict) and deseason.payload.get("values") is not None:
        values, basis = np.asarray(deseason.payload["values"], dtype=float), "anomalies"
    else:
        values, basis = prepared.dataset.variables["y"].values, "original"
    unit = prepared.meta["unit"]
    is_cusum = segments_step.method_id == "cusum_reference"
    key = "event_indices" if is_cusum else "change_indices"
    indices = [int(i) for i in np.asarray(segments_step.payload[key]).tolist()]
    bounds = [0] + indices + [len(values)]
    segments = [{"start": dates[a], "end": dates[b - 1], "n": b - a, "mean": float(values[a:b].mean())}
                for a, b in zip(bounds[:-1], bounds[1:])]
    changes = [{"date": dates[i], "index": i, "mean_before": segments[k]["mean"], "mean_after": segments[k + 1]["mean"],
                "shift": segments[k + 1]["mean"] - segments[k]["mean"]} for k, i in enumerate(indices)]
    if is_cusum:
        # The accumulators reset at every alarm, so means between alarms say nothing about the alarm:
        # report only when and on which side of the reference each alarm fired.
        directions = [int(d) for d in np.asarray(segments_step.payload["event_directions"]).tolist()]
        changes = [{"date": dates[i], "index": i, "direction": "above_reference" if d > 0 else "below_reference"}
                   for i, d in zip(indices, directions)]
    notes = (["CUSUM respecto de la base de referencia: cada alarma marca cuándo el apartamiento acumulado superó "
              "el umbral, no cuándo empezó el cambio."] if is_cusum
             else ["Aproximación con PELT (costo cuadrático); no es BFAST."])
    if basis == "anomalies":
        notes.append("Las medias por tramo son medias de las anomalías (sin ciclo estacional), en la unidad de la variable.")
    else:
        notes.append("La serie no se desestacionalizó: las medias por tramo son de la serie original y pueden reflejar "
                     "la estación del año que cubre cada tramo.")
    finding = _finding(
        "change_point", ctx["series"], ctx["source"], prepared,
        how_much={"n_changes": len(changes), "changes": changes, "segments": segments, "unit": unit, "basis": basis,
                  "method": "cusum" if is_cusum else "pelt",
                  **({"k": segments_step.payload["k"], "h": segments_step.payload["h"],
                      "reference_mean": segments_step.payload["reference_mean"],
                      "reference_std": segments_step.payload["reference_std"]} if is_cusum else {}),
                  "penalty": segments_step.payload.get("penalty", ctx["params"]["penalty"]),
                  "penalty_rule": segments_step.payload.get("penalty_rule", "manual"),
                  "min_size": ctx["params"]["min_size"], "deseasonalized": deseason is not None},
        conclusiveness="descriptive", statement_key="change_point.detected" if changes else "change_point.none_detected",
        test="cusum" if is_cusum else "pelt", notes=notes,
        limitations=["Detección por penalización: no es una prueba de significancia y depende de la penalización elegida.",
                     "El instante detectado no es el inicio del cambio.",
                     "Si no se detecta ningún cambio, no hay evidencia suficiente: no significa que no haya cambios."])
    charts = [{"kind": "change_points", "series_ref": ctx["series"].get("id"), "dates": [c["date"] for c in changes]}]
    return {"findings": [finding], "verdict": _verdict_change_point(ctx["hypothesis"], finding), "charts": charts}


def _smoothing(ctx) -> dict:
    step = _step(ctx["steps"], "smooth")
    prepared = ctx["prepared"]
    if step is None:
        return {"findings": [_gap("smoothing", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudo suavizar la serie.")], "verdict": None, "charts": []}
    values = np.asarray(step.payload["values"], dtype=float)
    dates = prepared.meta["dates"]
    dates = dates[len(dates) - len(values):]
    unit = prepared.meta["unit"]
    causal = step.payload.get("causal")
    finding = _finding(
        "smoothing", ctx["series"], ctx["source"], prepared,
        how_much={"method": step.method_id, "window": ctx["params"]["window"], "n_input": prepared.profile["n"],
                  "n_smoothed": int(values.size), "causal": causal, "unit": unit, "first": _f(values[0]),
                  "last": _f(values[-1]), "minimum": _f(values.min()), "maximum": _f(values.max())},
        statement_key="smoothing.descriptive",
        notes=([] if causal else ["SSA usa toda la serie (no causal): sirve para describir, no para validar ni pronosticar."]),
        limitations=["Suavizar no es detectar tendencias ni probar nada.",
                     "La media móvil causal acorta la serie y desplaza la señal hacia atrás."])
    overlay = {"type": "smoothed", "step": "smooth", "dates": dates, "values": _listed(values)}
    return {"findings": [finding], "verdict": None,
            "charts": [{"kind": "timeseries", "series_ref": ctx["series"].get("id"), "overlays": [overlay]}]}


def _events(ctx) -> dict:
    step = _step(ctx["steps"], "events")
    prepared = ctx["prepared"]
    series = prepared.dataset.variables["y"].values
    if step is None:
        return {"findings": [_gap("event", ctx["series"], ctx["source"], prepared, ctx["steps"],
                                  "No se pudieron detectar eventos.")],
                "verdict": _verdict_threshold(ctx["hypothesis"], None), "charts": []}
    p = step.payload
    dates = prepared.meta["dates"]
    unit = prepared.meta["unit"]
    limit = 200
    starts, ends = np.asarray(p["start_indices"]).tolist(), np.asarray(p["end_indices"]).tolist()
    durations, peaks = np.asarray(p["durations"]).tolist(), np.asarray(p["peak_values"]).tolist()
    peak_at, excess = np.asarray(p["peak_indices"]).tolist(), np.asarray(p["mean_exceedance"]).tolist()
    events = [{"start": dates[a], "end": dates[b], "duration_steps": int(d), "peak_value": _f(v), "peak_date": dates[k],
               "mean_exceedance": _f(e)} for a, b, d, v, k, e in zip(starts, ends, durations, peaks, peak_at, excess)]
    thresholds = np.asarray(p["reference"]["thresholds"], dtype=float)
    base = prepared.derived.get("baseline")
    finding = _finding(
        "event", ctx["series"], ctx["source"], prepared,
        how_much={"n_events": int(p["n_events"]), "q": ctx["params"]["q"], "direction": p["direction"],
                  "min_duration_steps": int(p["min_duration"]), "exceedance_fraction": _f(p["exceedance_fraction"]),
                  "threshold_min": _f(thresholds.min()), "threshold_max": _f(thresholds.max()), "unit": unit,
                  "events": events[:limit], "truncated": len(events) > limit},
        conclusiveness="descriptive", statement_key="event.found" if events else "event.none_found",
        notes=[base["note"]] if base and base.get("note") else [],
        limitations=["Un evento no es una tendencia ni una anomalía: son resultados distintos.",
                     "El umbral sale solo del período de referencia y tiene incertidumbre de muestreo que no se estima."])
    finding["baseline"] = base
    charts = [{"kind": "table", "series_ref": ctx["series"].get("id"),
               "overlays": [{"type": "event_spans", "spans": [{"start": e["start"], "end": e["end"]} for e in events[:limit]]}]}]
    return {"findings": [finding], "verdict": _verdict_threshold(ctx["hypothesis"], series), "charts": charts}


def _verdict_relationship(hypothesis: Optional[dict], rows: Optional[list], alpha: float) -> Optional[dict]:
    if hypothesis is None:
        return None
    base = {"hypothesis": hypothesis}
    if not rows:
        return {**base, "status": "not_testable", "reason_key": "verdict.not_testable", "evidence": {}}
    wanted = hypothesis.get("lags")
    sign = hypothesis.get("sign", "any")
    tested = [row for row in rows if wanted is None or row["lag"] in wanted]
    matching = [row["lag"] for row in tested if row["significant_fdr"]
                and (sign == "any" or (sign == "positive") == (row["r"] > 0))]
    evidence = {"lags_tested": [row["lag"] for row in tested], "lags_significant_matching": matching, "sign": sign,
                "alpha": alpha, "kind": "association", "caveat": "asociación estadística, no causa"}
    if matching:
        return {**base, "status": "supported", "reason_key": "verdict.relationship.supported", "evidence": evidence}
    return {**base, "status": "inconclusive", "reason_key": "verdict.inconclusive", "evidence": evidence}


def _relationship(ctx) -> dict:
    steps, prepared, params = ctx["steps"], ctx["prepared"], ctx["params"]
    step = _step(steps, "lags")
    if step is None:
        return {"findings": [_gap("association", ctx["series"], ctx["source"], prepared, steps,
                                  "No se pudo calcular la correlación.")],
                "verdict": _verdict_relationship(ctx["hypothesis"], None, params["alpha"]), "charts": []}
    p = step.payload
    alpha = params["alpha"]
    lags = np.asarray(p["lags"]).tolist()
    p_values, testable = np.asarray(p["p_value"], dtype=float), np.asarray(p["testable"], dtype=bool)
    q_values = [None] * len(lags)
    rejected = [False] * len(lags)
    if testable.any():
        adjusted = fdr_bh(p_values[testable], alpha=alpha)
        for position, q, flag in zip(np.flatnonzero(testable).tolist(), adjusted["q_values"], adjusted["rejected"]):
            q_values[position], rejected[position] = float(q), bool(flag)
    rows = [{"lag": int(lag), "r": _f(r), "n": int(n), "n_effective": _f(neff), "p_value": _f(pv), "q_value": q,
             "significant_fdr": flag, "testable": bool(ok)}
            for lag, r, n, neff, pv, q, flag, ok in zip(lags, np.asarray(p["r"]).tolist(), np.asarray(p["n"]).tolist(),
                                                        np.asarray(p["n_effective"]).tolist(), p_values.tolist(),
                                                        q_values, rejected, testable.tolist())]
    roles = prepared.meta["roles"]
    partial = None
    partial_step = _step(steps, "partial")
    if partial_step is not None:
        q = partial_step.payload
        partial = {"r": _f(q["r"]), "n": int(q["n"]), "n_effective": _f(q["n_effective"]), "p_value": _f(q["p_value"]),
                   "testable": bool(q["testable"]), "significant": bool(q["testable"] and q["p_value"] < alpha),
                   "controls": [role["variable"] for role in roles[2:]], "lag": 0,
                   "note": "Correlación parcial en desfase 0, sin corrección por pruebas múltiples (una sola prueba)."}
    elif roles[2:]:
        partial = {"unavailable": True, "reason": next((s.reason for s in steps if s.step_id == "partial" and s.reason), "")}
    n_hits = sum(rejected)
    notes = ["Asociación estadística: no establece causa ni dirección causal."]
    if prepared.meta.get("deseasonalized"):
        notes.append("Se quitó el ciclo mensual de cada serie antes de correlacionar.")
    else:
        notes.append("No se quitó el ciclo estacional: tendencias o ciclos compartidos pueden inflar la asociación.")
    finding = _finding(
        "association", ctx["series"], ctx["source"], prepared,
        how_much={"lags": rows, "n_tests": len(rows), "n_significant_fdr": n_hits, "alpha": alpha, "unit": "1",
                  "lag_convention": "desfase positivo: la primera variable antecede a la segunda",
                  "step_unit": prepared.meta["time_unit"], "partial": partial,
                  "deseasonalized": bool(prepared.meta.get("deseasonalized"))},
        alpha=alpha, test="pearson_lagged_fdr_bh", conclusiveness="conclusive" if n_hits else "inconclusive",
        statement_key="association.fdr_significant" if n_hits else "association.inconclusive", notes=notes,
        limitations=["Correlación no implica causalidad.",
                     "El tamaño efectivo supone dependencia serial de orden 1 en ambas series.",
                     "No se elige un «mejor desfase»: se informan todos los evaluados."])
    finding["what"] = {"first": roles[0], "second": roles[1], "controls": roles[2:]}
    charts = [{"kind": "scatter_lag", "series_refs": [role["id"] for role in roles], "lags": lags}]
    return {"findings": [finding], "verdict": _verdict_relationship(ctx["hypothesis"], rows, alpha), "charts": charts}


def _precipitation_indices(ctx) -> dict:
    steps, prepared = ctx["steps"], ctx["prepared"]
    unit = prepared.meta["unit"]
    labels = {"rx1day": ("Rx1day", "Máxima precipitación en 1 día", unit),
              "rx5day": ("Rx5day", "Máxima precipitación en 5 días consecutivos", unit),
              "sdii": ("SDII", "Intensidad media de los días húmedos", f"{unit}/día húmedo"),
              "cdd": ("CDD", "Máxima racha de días secos", "días"),
              "r95ptot": ("R95pTOT", "Precipitación total en días sobre el percentil de la base", unit)}
    findings = []
    base = prepared.derived.get("baseline")
    for name, (short, title, index_unit) in labels.items():
        step = _step(steps, name)
        if step is None:
            findings.append(_gap("climate_index", ctx["series"], ctx["source"], prepared, steps,
                                 f"No se pudo calcular {short}."))
            continue
        p = step.payload
        years = np.asarray(p["group_ids"]).astype(int).tolist()
        raw = np.asarray(p["values"], dtype=float)
        valid = np.asarray(p["valid"], dtype=bool)
        good = raw[valid]
        if good.size == 0:
            findings.append(_gap("climate_index", ctx["series"], ctx["source"], prepared, steps, f"{short} no tiene años válidos."))
            continue
        position = np.flatnonzero(valid)
        how = {"index": short, "title": title, "unit": index_unit, "years": years,
               "values": [_f(v) if ok else None for v, ok in zip(raw, valid)], "n_years": int(valid.sum()),
               "mean": _f(good.mean()), "minimum": _f(good.min()), "maximum": _f(good.max()),
               "maximum_year": years[int(position[int(np.argmax(good))])], "last": _f(good[-1]),
               "last_year": years[int(position[-1])], "wet_threshold": ctx["params"]["wet_threshold"]}
        notes = []
        if name == "r95ptot":
            how.update({"percentile": ctx["params"]["percentile"], "threshold": _f(p.get("threshold")),
                        "n_reference_wet_days": int(p.get("n_reference_wet_days", 0))})
            if base and base.get("note"):
                notes.append(base["note"])
        if int(valid.sum()) < 10:
            notes.append("Hay menos de 10 años: no alcanza para hablar de tendencia ni de variabilidad interanual.")
        finding = _finding("climate_index", ctx["series"], ctx["source"], prepared, how_much=how,
                           statement_key=f"climate_index.{name}", conclusiveness="descriptive", notes=notes,
                           limitations=["Cada índice se informa por separado.",
                                        "Solo se usaron años calendario completos, sin días faltantes.",
                                        "Un punto no representa el promedio de una región."])
        finding["baseline"] = base if name == "r95ptot" else None
        findings.append(finding)
    return {"findings": findings, "verdict": None,
            "charts": [{"kind": "table", "series_ref": ctx["series"].get("id"), "indices": list(labels)}]}


BUILDERS = {"precipitation_indices": _precipitation_indices, "describe": _describe, "trend_significance": _trend, "anomaly": _anomaly,
            "drought_spi": _spi, "regression_fit": _fit, "forecast": _forecast,
            "seasonality": _seasonality, "change_point": _change_point, "smoothing": _smoothing,
            "extreme_events": _events, "relationship": _relationship}


def build(struct, params: dict, steps: list, prepared, series: dict, source: Optional[dict],
          hypothesis: Optional[dict]) -> dict:
    """Findings, verdict and chart descriptors for one analysis."""
    builder = BUILDERS.get(struct.struct_id)
    if builder is None:
        return {"findings": [], "verdict": None, "charts": []}
    return builder({"struct": struct, "params": params, "steps": steps, "prepared": prepared, "series": series,
                    "source": source, "hypothesis": hypothesis})
