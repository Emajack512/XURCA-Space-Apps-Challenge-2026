"""Point series from the public Open-Meteo historical API."""

import math
from collections import defaultdict
from statistics import mean
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from .catalog import acquisition_gaps
from .public_sources import request_json

ROUTE = "openmeteo.archive.daily"
ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
VARIABLE_MODELS = {
    "soil_moisture_0_to_7cm_mean": "era5_land",
    "soil_moisture_7_to_28cm_mean": "era5_land",
    "soil_moisture_28_to_100cm_mean": "era5_land",
    "soil_moisture_100_to_255cm_mean": "era5_land",
    "temperature_2m_max": "era5_land",
    "temperature_2m_min": "era5_land",
    "precipitation_sum": "era5",
    "temperature_2m_mean": "era5",
    "relative_humidity_2m_mean": "era5",
    "wind_speed_10m_mean": "era5",
    "shortwave_radiation_sum": "era5",
    "pressure_msl_mean": "era5",
    "snowfall_sum": "era5",
    "cloud_cover_mean": "era5",
    "snow_depth": "era5_land",
    "et0_fao_evapotranspiration": "era5",
}


def archive_data(longitude, latitude, start, end, variables, model):
    daily = [variable for variable in variables if variable != "snow_depth"]
    params = {"daily": ",".join(daily)} if daily else {}
    if "snow_depth" in variables:
        params["hourly"] = "snow_depth"
    return request_json(
        ENDPOINT, "Open-Meteo", longitude=longitude, latitude=latitude,
        start_date=start, end_date=end, **params,
        models=model, timezone="GMT", cell_selection="land",
    )


cached_archive_data = lru_cache(maxsize=8)(archive_data)


def fetch_reanalysis(sources, investigation):
    if not sources:
        return []
    period = investigation.get("time") or {}
    if not period.get("start") or not period.get("end"):
        raise ValueError("Ingresá las dos fechas para Open-Meteo.")
    start, end = (date.fromisoformat(period[key]) for key in ("start", "end"))
    if start > end or end > date.today():
        raise ValueError("Open-Meteo requiere fechas históricas en orden.")
    features = investigation["geography"]["selection"]["features"]
    groups = {}
    for source in sources:
        gaps = acquisition_gaps(source, investigation)
        if gaps:
            raise ValueError("Completá los campos de Open-Meteo: " + ", ".join(gaps))
        upstream = source["upstream"]
        variable = upstream["variableId"]
        model = VARIABLE_MODELS.get(variable)
        if not model:
            raise ValueError("La variable no está habilitada para el producto de reanálisis.")
        if start.year < (1950 if model == "era5_land" else 1940):
            raise ValueError("El intervalo empieza antes de la cobertura del producto.")
        longitude, latitude = next(
            item["geometry"]["coordinates"][:2] for item in features if item["id"] == upstream["geometryId"]
        )
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("Las coordenadas están fuera del rango WGS 84.")
        groups.setdefault((longitude, latitude, model), []).append(source)

    results = []
    for (longitude, latitude, model), group in groups.items():
        product = "ECMWF ERA5-Land" if model == "era5_land" else "ECMWF ERA5"
        variables = tuple(sorted({item["upstream"]["variableId"] for item in group}))
        load = cached_archive_data if end < date.today() - timedelta(days=120) else archive_data
        payload, url = load(longitude, latitude, start, end, variables, model)
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        for source in group:
            variable = source["upstream"]["variableId"]
            values = daily.get(variable)
            unit = (payload.get("daily_units") or {}).get(variable)
            if variable == "snow_depth":
                unit, by_date = daily_snow_depth(payload)
            else:
                if not unit or not isinstance(values, list) or len(values) != len(dates):
                    raise ValueError(f"Open-Meteo no devolvió una serie válida para {variable}.")
                by_date = dict(zip(dates, values))
            points = []
            for offset in range((end - start).days + 1):
                day = (start + timedelta(days=offset)).isoformat()
                value = by_date.get(day)
                if not isinstance(value, (float, int)) or not math.isfinite(value):
                    value = None
                points.append({"month": day, "value": value})
            if all(point["value"] is None for point in points):
                raise ValueError("Open-Meteo no devolvió valores para una de las variables en este lugar y período.")
            cell = [payload["longitude"], payload["latitude"]]
            results.append({
                "id": source["id"], "provider": "Open-Meteo", "product": product,
                "variable": variable, "unit": unit, "points": points, "cadence": "daily",
                "coordinates": [longitude, latitude],
                "location": f"Punto {longitude:.4f}, {latitude:.4f} · celda {cell[0]:.4f}, {cell[1]:.4f} (lon, lat)",
                "url": url, "retrievedAt": datetime.now(timezone.utc).isoformat(),
            })
    return results


def daily_snow_depth(payload):
    hourly = payload.get("hourly") or {}
    stamps = hourly.get("time") or []
    values = hourly.get("snow_depth")
    unit = (payload.get("hourly_units") or {}).get("snow_depth")
    if not unit or not isinstance(values, list) or len(values) != len(stamps):
        raise ValueError("Open-Meteo no devolvió una serie válida de espesor de nieve.")
    samples = defaultdict(dict)
    for stamp, value in zip(stamps, values):
        if isinstance(value, (int, float)) and math.isfinite(value):
            samples[stamp[:10]][stamp] = value
    return unit, {day: mean(hours.values()) for day, hours in samples.items() if len(hours) == 24}
