"""Rank compatible, configured data products by native spatial resolution."""

import math
import os
from datetime import date
from pathlib import Path

from rasterio.features import geometry_mask
from rasterio.transform import from_origin

from .environmental_series import area_bounds, inside_area, selected_geometry
from .era5_land_monthly import VARIABLES, fetch_era5_land, monthly_periods
from .power import ROUTE as POWER_POINT_ROUTE
from .power_grid import SOLAR_ROUTE, TEMPERATURE_ROUTE
from .precipitation import CHIRPS_ROUTE, PMRA_ROUTE, fetch_precipitation, monthly_assets
from .public_sources import world_countries


def cds_configured():
    config = Path(os.environ.get("CDSAPI_RC") or (Path.home() / ".cdsapirc"))
    return bool(os.environ.get("CDSAPI_KEY", "").strip() or config.is_file())


def argentina_selection(geometry):
    if geometry["type"] == "Point":
        west, south = geometry["coordinates"][:2]
        east, north = west, south
    else:
        west, south, east, north = area_bounds(geometry)
    if not (-74 <= west <= east <= -52 and -56 <= south <= north <= -21):
        return False
    argentina = world_countries().get("ARG")
    if not argentina:
        return False
    if geometry["type"] == "Point":
        return inside_area(west, south, argentina["geometry"])
    step = .025
    grid = from_origin(west, north, step, step)
    shape = (math.ceil((north - south) / step), math.ceil((east - west) / step))
    selected = geometry_mask([geometry], shape, grid, invert=True)
    inside = geometry_mask([argentina["geometry"]], shape, grid, invert=True)
    if not selected.any():
        return inside_area((west + east) / 2, (south + north) / 2, argentina["geometry"])
    return not (selected & ~inside).any()


def precipitation_candidate(source, geometry, periods, *, fallback=False):
    route = source["access"]
    alternative = CHIRPS_ROUTE if route == PMRA_ROUTE else PMRA_ROUTE
    if not periods:
        return None
    if geometry["type"] == "Point":
        south = north = geometry["coordinates"][1]
    else:
        _, south, _, north = area_bounds(geometry)
    chirps_area_km2 = (111.195 * .05) ** 2 * math.cos(math.radians((south + north) / 2))
    if alternative == PMRA_ROUTE:
        if chirps_area_km2 <= 25 or periods[0] < "2000-01" or periods[-1] > "2023-12" or not argentina_selection(geometry):
            return None
    elif (not fallback and chirps_area_km2 >= 25 and "2000-01" <= periods[0] <= periods[-1] <= "2023-12"
          and argentina_selection(geometry)):
        return None
    if south < -60 or north > 60:
        return None
    if not set(periods).issubset(monthly_assets(alternative)):
        return None
    name, resolution = ("PMRAv1", "5 km × 5 km") if alternative == PMRA_ROUTE else ("CHIRPS v3", "0,05° × 0,05°")
    return {**source, "access": alternative}, name, resolution


def complete_precipitation(choice, investigation, start, end):
    alternative, name, resolution = choice
    result = fetch_precipitation(alternative, investigation, start, end)
    if not result["points"] or any(point["value"] is None for point in result["points"]):
        raise ValueError(f"{name} no devolvió datos para todos los meses solicitados.")
    return {**result, "sourceSelection": f"{name} · {resolution}"}


def has_era5_alternative(source):
    return (source["access"] in {SOLAR_ROUTE, TEMPERATURE_ROUTE, POWER_POINT_ROUTE}
            and source["upstream"]["variableId"] in VARIABLES)


def with_best_spatial_resolution(source, investigation, start, end, fetch_original):
    route = source["access"]
    variable = source["upstream"]["variableId"]
    reason = None
    tried_precipitation_alternative = False
    native = {SOLAR_ROUTE: "NASA POWER · 1° × 1°", TEMPERATURE_ROUTE: "NASA POWER · 0,625° × 0,5°",
              CHIRPS_ROUTE: "CHIRPS v3 · 0,05° × 0,05°", PMRA_ROUTE: "PMRAv1 · 5 km × 5 km"}
    if route == POWER_POINT_ROUTE and has_era5_alternative(source):
        native[route] = native[SOLAR_ROUTE if variable == "ALLSKY_SFC_SW_DWN" else TEMPERATURE_ROUTE]
    if has_era5_alternative(source) and start.year >= 1950:
        if not cds_configured():
            reason = "Se usó NASA POWER. Para consultar ERA5-Land (0,1°) configurá CDSAPI_KEY o .cdsapirc y aceptá los términos de CDS."
        else:
            area = selected_geometry(source, investigation, {"Polygon", "MultiPolygon", "Point"})
            if area["type"] == "Point":
                west, south = area["coordinates"][:2]
                east, north = west, south
            else:
                west, south, east, north = area_bounds(area)
            periods = monthly_periods(start, end, investigation["time"].get("years"))
            # Bound the requested raster before submitting it to CDS.
            size = (math.ceil((east - west) * 10) + 3) * (math.ceil((north - south) * 10) + 3) * len(periods)
            if end.replace(day=1) >= date.today().replace(day=1):
                reason = "ERA5-Land mensual requiere meses completos ya publicados."
            elif size > 20_000_000:
                reason = "El área y el período superan el tamaño admitido para la consulta ERA5-Land de 0,1°."
            else:
                try:
                    result = fetch_era5_land(source, investigation, start, end)
                except (OSError, ValueError, RuntimeError, KeyError) as error:
                    reason = f"No se pudo usar ERA5-Land (0,1°). {error}"
                else:
                    return {**result, "sourceSelection": "ERA5-Land mensual · 0,1° × 0,1°"}
    elif route in {CHIRPS_ROUTE, PMRA_ROUTE} and variable == "precipitation":
        geometry = selected_geometry(source, investigation, {"Polygon", "MultiPolygon", "Point"})
        periods = monthly_periods(start, end, investigation["time"].get("years"))
        if periods:
            try:
                choice = precipitation_candidate(source, geometry, periods)
                if choice:
                    tried_precipitation_alternative = True
                    return complete_precipitation(choice, investigation, start, end)
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                reason = f"No se pudo verificar o consultar una grilla alternativa. {error}"
    original_error = None
    try:
        result = fetch_original()
    except (OSError, ValueError) as error:
        original_error = error
        result = None
    if route == PMRA_ROUTE and variable == "precipitation" and not tried_precipitation_alternative:
        if result is None or any(point["value"] is None for point in result["points"]):
            try:
                choice = precipitation_candidate(source, geometry, periods, fallback=True)
                if choice:
                    replacement = complete_precipitation(choice, investigation, start, end)
                    replacement["mapMessage"] = "Se usó CHIRPS porque PMRA no cubrió toda la consulta."
                    return replacement
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                reason = f"No se pudo completar la consulta alternativa con CHIRPS. {error}"
    if original_error:
        if reason:
            raise ValueError(f"{reason} {original_error}") from original_error
        raise original_error
    if route in native:
        result["sourceSelection"] = native[route]
    if reason:
        result["mapMessage"] = " ".join(filter(None, (reason, result.get("mapMessage"))))
    return result
