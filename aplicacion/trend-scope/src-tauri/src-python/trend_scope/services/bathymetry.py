"""Static ETOPO1 bathymetry sampled on a common grid across regional blocks."""

import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import quote
from urllib.request import urlopen

from .environmental_series import area_bounds, inside_area, selected_geometry, series
from .regional_layers import spatial_blocks, temporal_layer

ROUTE = "noaa.etopo.area"
ENDPOINT = "https://data.pmel.noaa.gov/socat/erddap/griddap/etopo180"
MODEL_DATE = date(2009, 1, 1)


def grid_limits(low, high, spacing=1):
    first = (math.floor(low / spacing + 1e-9) + 0.5) * spacing
    last = (math.ceil(high / spacing - 1e-9) - 0.5) * spacing
    return first, max(first, last)


def etopo_block(bounds, stride=60):
    west, south, east, north = bounds
    low_lat, high_lat = grid_limits(south, north, stride / 60)
    low_lon, high_lon = grid_limits(west, east, stride / 60)
    query = (f"altitude[({low_lat:.8f}):{stride}:({high_lat:.8f})]"
             f"[({low_lon:.8f}):{stride}:({high_lon:.8f})]")
    with urlopen(ENDPOINT + ".csv?" + quote(query, safe=""), timeout=30) as response:
        content = response.read(250_001)
    if len(content) > 250_000:
        raise ValueError("NOAA devolvió un bloque de batimetría mayor al esperado.")
    rows = csv.DictReader(io.StringIO(content.decode("utf-8")))
    if set(rows.fieldnames or ()) != {"altitude", "latitude", "longitude"}:
        raise ValueError("NOAA no devolvió una grilla ETOPO1 válida.")
    next(rows, None)  # CSV includes field units on the first data row.
    return [(float(row["longitude"]), float(row["latitude"]), float(row["altitude"])) for row in rows]


def regional_samples(rows, area, stride):
    if stride == 60:
        return [(lon, lat, value) for lon, lat, value in rows if inside_area(lon, lat, area)]
    if not rows:
        return []
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    lons = sorted({lon for lon, _, _ in rows})
    lats = sorted({lat for _, lat, _ in rows}, reverse=True)
    columns = {lon: index for index, lon in enumerate(lons)}
    lines = {lat: index for index, lat in enumerate(lats)}
    spacing = stride / 60
    mask = geometry_mask([area], (len(lats), len(lons)),
                         from_origin(lons[0] - spacing / 2, lats[0] + spacing / 2, spacing, spacing),
                         invert=True)
    return [(lon, lat, value) for lon, lat, value in rows if mask[lines[lat], columns[lon]]]


def fetch_bathymetry(source, investigation, _start, _end):
    if source["upstream"]["variableId"] != "depth":
        raise ValueError("ETOPO1 admite profundidad submarina en esta consulta.")
    area = selected_geometry(source, investigation, {"Polygon", "MultiPolygon"})
    bounds = area_bounds(area)
    features = investigation["geography"]["selection"]["features"]
    distance = next((feature.get("properties", {}).get("coastDistanceKm") for feature in features
                     if feature["geometry"] is area), None)
    stride = 60
    if isinstance(distance, (float, int)) and 1 <= distance <= 500:
        stride = max(value for value in (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
                     if value <= max(1, distance / 3.7))
    spacing = stride / 60
    blocks = spatial_blocks(area, bounds, tile=30 * spacing)
    if len(blocks) > 256:
        raise ValueError("La batimetría de esta franja requiere muchos bloques. Elegí un tramo de costa más corto.")
    samples = {}
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for rows in pool.map(lambda block: etopo_block(block, stride), blocks):
                for lon, lat, altitude in regional_samples(rows, area, stride):
                    if math.isfinite(altitude) and altitude < 0:
                        samples[lon, lat] = -altitude
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("No se pudo consultar toda la grilla de batimetría NOAA. Probá de nuevo.") from error
    if not samples:
        raise ValueError(f"La grilla de {stride} minutos de arco no encontró celdas submarinas dentro del área.")
    bins = [0.0] * 8
    total, weighted_depth = 0.0, 0.0
    events = []
    for (lon, lat), depth in samples.items():
        weight = math.cos(math.radians(lat))
        total += weight
        weighted_depth += depth * weight
        bins[min(int(depth // 1000), 7)] += weight
        w, e = lon - spacing / 2, lon + spacing / 2
        s, n = lat - spacing / 2, lat + spacing / 2
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        events.append({"id": f"{lon}:{lat}", "date": MODEL_DATE.isoformat(), "value": depth,
                       "geometry": {"type": "Polygon", "coordinates": [ring]}})
    points = [{"month": f"{i * 1000}–<{(i+1) * 1000} m" if i < 7 else "≥ 7000 m",
               "value": weight / total * 100} for i, weight in enumerate(bins)]
    result = series(source, "NOAA", "ETOPO1", "%", points, "Área de estudio", ENDPOINT + ".html", "distribution")
    result["message"] = (f"Profundidad media ponderada: {weighted_depth / total:.0f} m. "
                         f"{len(samples)} celdas submarinas en {len(blocks)} bloques.")
    result["statistics"] = {"weightedMeanDepthM": weighted_depth / total, "sampledCells": len(samples),
                            "maximumSampledDepthM": max(samples.values()), "blocks": len(blocks)}
    result["map"] = temporal_layer(
        "grid", area, MODEL_DATE, MODEL_DATE, "value", events=events, unit="m", static=True,
        note=f"ETOPO1 es un modelo estático. Muestra de {stride} minutos de arco, con profundidad positiva bajo el nivel del mar.",
    )
    return result
