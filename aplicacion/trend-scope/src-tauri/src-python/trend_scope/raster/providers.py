"""Native grid registry. No scientific transformations are performed here."""
from datetime import date, timedelta, datetime, timezone
import numpy as np
from .contract import GridField

def variable(name, unit, aggregation):
    return dict(name=name, unit=unit, aggregation=aggregation, kind="reanalysis")

PROVIDERS = {
    "nasa.power.regional.monthly": dict(
        id="nasa.power.regional.monthly", title="NASA POWER MERRA-2 mensual",
        cadences=["monthly"], native_resolution_deg=(0.5, 0.625),
        notes="Una variable por solicitud regional. PRECTOTCORR es tasa, no acumulado.",
        variables={
            "T2M": variable("Temperatura del aire a 2 m", "C", "monthly mean"),
            "PRECTOTCORR": variable("Precipitación corregida", "mm/day", "monthly mean daily rate"),
            "RH2M": variable("Humedad relativa a 2 m", "%", "monthly mean"),
            "WS2M": variable("Velocidad del viento a 2 m", "m/s", "monthly mean")}),
    "openmeteo.era5.daily": dict(
        id="openmeteo.era5.daily", title="Open-Meteo ERA5 diario",
        cadences=["daily"], native_resolution_deg=(0.25, 0.25),
        notes="ERA5 explícito; UTC; nearest; elevation=nan; unidades originales de la API.",
        variables={
            "temperature_2m_mean": variable("Temperatura del aire a 2 m", "°C", "daily mean"),
            "precipitation_sum": variable("Precipitación", "mm", "daily sum"),
            "relative_humidity_2m_mean": variable("Humedad relativa a 2 m", "%", "daily mean"),
            "wind_speed_10m_max": variable("Velocidad del viento a 10 m", "km/h", "daily maximum")})}

def times_for(request):
    start, end = date.fromisoformat(request.start), date.fromisoformat(request.end)
    result = []
    if request.cadence == "monthly":
        start = start.replace(day=1)
    while start <= end:
        result.append(start.isoformat())
        start = (date(start.year + (start.month == 12), start.month % 12 + 1, 1)
                 if request.cadence == "monthly" else start + timedelta(days=1))
    return result

def check_size(request, cells, count):
    if cells > request.max_cells or cells * count > request.max_values:
        raise ValueError(f"La grilla requiere {cells} celdas y {cells * count} valores; "
                         f"reducí el área a {request.max_cells} celdas y/o el período "
                         f"hasta {request.max_values} valores como máximo.")

def make_field(request, times, lats, lons, values, urls, unit):
    from ..services.environmental_series import inside_area
    p = PROVIDERS[request.provider]
    v = p["variables"][request.variable_id]
    mask = np.array([[request.polygon is None or inside_area(x, y, request.polygon)
                      for x in lons] for y in lats], dtype=bool)
    check_size(request, len(lats) * len(lons), len(times))
    return GridField(provider=request.provider, product=p["title"], kind=v["kind"],
        variable_id=request.variable_id, variable_name=v["name"], unit=unit,
        cadence=request.cadence, times=times, lats=lats, lons=lons, values=values,
        mask=mask, native_resolution_deg=p["native_resolution_deg"], urls=urls,
        retrieved_at=datetime.now(timezone.utc).isoformat(), aggregation=v["aggregation"]).validate()

def fetch_grid(request):
    try:
        request.validate()
        date.fromisoformat(request.start)
        date.fromisoformat(request.end)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Pedido de grilla inválido: {error}") from error
    p = PROVIDERS.get(request.provider)
    if not p or request.variable_id not in p["variables"] or request.cadence not in p["cadences"]:
        raise ValueError("Proveedor, variable o cadencia no admitidos.")
    if any(type(n) is not int or n <= 0 for n in (request.max_cells, request.max_values)):
        raise ValueError("max_cells y max_values deben ser enteros positivos.")
    if request.polygon is not None and request.polygon.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("La geometría debe ser Polygon o MultiPolygon.")
    if request.provider == "nasa.power.regional.monthly":
        from .power_regional import fetch
    else:
        from .openmeteo_grid import fetch
    return fetch(request).validate()
