"""NASA POWER monthly gridded products over a selected area."""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import rasterio
from rasterio.io import MemoryFile

from .environmental_series import area_bounds, selected_geometry, series
from .precipitation import read_grid
from .public_sources import request_json
from .regional_layers import temporal_layer

SOLAR_ROUTE = "nasa.power.solar.area"
TEMPERATURE_ROUTE = "nasa.power.temperature.area"
NASA_IMAGES = "https://gis.earthdata.nasa.gov/portal/rest/services/POWER"
MAX_MONTHS = 600


@dataclass(frozen=True)
class PowerGrid:
    name: str
    service: str
    field: str
    native_unit: str
    unit: str
    grid: tuple[float, float, float, float]
    minimum: float
    resolution: str

    @property
    def endpoint(self):
        return f"{NASA_IMAGES}/{self.service}/ImageServer"


PRODUCTS = {
    SOLAR_ROUTE: PowerGrid("POWER Monthly Radiation", "POWER_MONTHLY_RADIATION_LST",
                           "ALLSKY_SFC_SW_DWN", "W m-2", "W/m²", (-180, -90, 1, 1), 0, "1°"),
    TEMPERATURE_ROUTE: PowerGrid("POWER Monthly Meteorology", "POWER_MONTHLY_METEOROLOGY_LST",
                                 "T2M", "C", "°C", (-180.3125, -90.25, .625, .5), -100, "0,625° × 0,5°"),
}


def monthly_slices(product):
    payload, _ = request_json(product.endpoint + "/multiDimensionalInfo", "NASA POWER", f="json")
    variable = next((entry for entry in payload.get("multidimensionalInfo", {}).get("variables", [])
                     if entry["name"] == product.field), None)
    if not variable or variable.get("unit") != product.native_unit:
        raise ValueError("NASA POWER no devolvió el catálogo esperado para esta variable.")
    time = next((dimension for dimension in variable.get("dimensions", [])
                 if dimension["name"] == "StdTime"), {})
    return {datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m"): value
            for value in time.get("values", [])}


def grid_month(product, stamp, bounds, area):
    west, south, east, north = bounds
    _, _, dx, dy = product.grid
    size = f"{round((east - west) / dx)},{round((north - south) / dy)}"
    rule = {"multidimensionalDefinition": [{"variableName": product.field, "dimensionName": "StdTime",
                                           "values": [stamp], "isSlice": True}]}
    parameters = {
        "bbox": ",".join(map(str, bounds)), "bboxSR": 4326, "imageSR": 4326,
        "size": size, "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_NearestNeighbor", "mosaicRule": json.dumps(rule), "f": "image",
    }
    with urlopen(product.endpoint + "/exportImage?" + urlencode(parameters), timeout=35) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("NASA POWER devolvió un ráster mayor al esperado.")
    with MemoryFile(data) as memory, memory.open() as dataset:
        return read_grid(dataset, area, True, minimum=product.minimum)


def fetch_power_area(source, investigation, start, end):
    product = PRODUCTS[source["access"]]
    if source["upstream"]["variableId"] != product.field:
        raise ValueError("La variable no coincide con el producto regional de NASA POWER.")
    geometry = selected_geometry(source, investigation, {"Polygon", "MultiPolygon"})
    west, south, east, north = area_bounds(geometry)
    x, y, dx, dy = product.grid
    bounds = (x + math.floor((west - x) / dx) * dx, y + math.floor((south - y) / dy) * dy,
              x + math.ceil((east - x) / dx) * dx, y + math.ceil((north - y) / dy) * dy)
    years = set(investigation["time"].get("years") or range(start.year, end.year + 1))
    months = [f"{year:04d}-{month:02d}" for year in sorted(years) for month in range(1, 13)
              if (start.year, start.month) <= (year, month) <= (end.year, end.month)]
    if not months:
        raise ValueError("La consulta regional de NASA POWER requiere al menos un mes.")
    if len(months) > MAX_MONTHS:
        raise ValueError(f"Elegí hasta {MAX_MONTHS} meses para la consulta regional de NASA POWER.")
    slices = monthly_slices(product)

    def load(period):
        stamp = slices.get(period)
        if stamp is None:
            return None, []
        try:
            return grid_month(product, stamp, bounds, geometry)
        except (OSError, URLError, rasterio.errors.RasterioError, ValueError):
            return None, []

    points, events = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for month, (value, cells) in zip(months, pool.map(load, months)):
            stamp = month + "-01"
            points.append({"month": stamp, "value": value})
            events.extend({"id": f"{month}:{i}", "date": stamp, **cell} for i, cell in enumerate(cells))
    available = sum(point["value"] is not None for point in points)
    if not available:
        raise ValueError("NASA POWER no devolvió valores para el área y los meses elegidos.")
    result = series(source, "NASA POWER", product.name, product.unit, points,
                    "Promedio espacial del área", product.endpoint, "monthly")
    result["selectedYears"] = sorted(years) if investigation["time"].get("years") else []
    result["map"] = temporal_layer(
        "grid", geometry, start.replace(day=1), end, "value", events=events,
        unit=product.unit, cadence="monthly", nativeCadence="monthly",
        note=f"Grilla NASA POWER de {product.resolution}. Ponderación por superficie y fracción dentro del área.",
        periods=[point["month"] for point in points],
    )
    if available != len(months):
        result["mapMessage"] = f"NASA POWER devolvió valores para {available} de {len(months)} meses seleccionados."
    return result
