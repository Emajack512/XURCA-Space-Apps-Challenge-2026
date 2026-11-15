"""Monthly ERA5-Land fields on their published 0.1-degree grid."""

import hashlib
import json
from collections import defaultdict
from datetime import date
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
from netCDF4 import Dataset, num2date
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from ..configuration import directory
from .climate_store import retrieve_archive
from .environmental_series import area_bounds, selected_geometry, series
from .grid_layers import monthly_map_cell_limit
from .precipitation import read_grid
from .regional_layers import temporal_layer

DATASET = "reanalysis-era5-land-monthly-means"
REFERENCE = f"https://cds.climate.copernicus.eu/datasets/{DATASET}"
VARIABLES = {
    "ALLSKY_SFC_SW_DWN": ("surface_solar_radiation_downwards", "ssrd", "W/m²"),
    "T2M": ("2m_temperature", "t2m", "°C"),
}


def monthly_periods(start, end, selected_years=()):
    years = selected_years or range(start.year, end.year + 1)
    return [f"{year:04d}-{month:02d}" for year in sorted(years) for month in range(1, 13)
            if (start.year, start.month) <= (year, month) <= (end.year, end.month)]


def archive_for(variable, periods, bounds):
    west, south, east, north = bounds
    orders = defaultdict(list)
    for period in periods:
        orders[period[:4]].append(period[5:])
    years_by_months = defaultdict(list)
    for year, months in orders.items():
        years_by_months[tuple(months)].append(year)
    base = {"variable": [variable], "product_type": ["monthly_averaged_reanalysis"],
            "time": ["00:00"], "area": [round(north, 4), round(west, 4), round(south, 4), round(east, 4)],
            "data_format": "netcdf", "download_format": "unarchived"}
    queries = [(years[0], {**base, "year": years, "month": list(months)})
               for months, years in years_by_months.items()]
    manifest = {"dataset": DATASET, "requests": queries}
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:24]
    folder = directory() / "downloads" / "cds"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{key}.zip"
    if not target.exists():
        retrieve_archive(DATASET, queries, manifest, target)
    return target


def monthly_grids(path, code):
    with Dataset(path) as dataset:
        latitude = dataset["latitude"]
        longitude = dataset["longitude"]
        time = dataset.variables.get("valid_time", dataset.variables.get("time"))
        variable = dataset.variables.get(code)
        if time is None or variable is None:
            raise ValueError("El archivo ERA5-Land no contiene la variable o el tiempo esperado.")
        dims = (time.dimensions[0], latitude.dimensions[0], longitude.dimensions[0])
        if set(variable.dimensions) != set(dims) or variable.ndim != 3:
            raise ValueError("El archivo ERA5-Land no tiene una grilla mensual bidimensional.")
        unit = str(getattr(variable, "units", "")).lower().replace(" ", "").replace("*", "").replace("^", "")
        if unit not in ({"jm-2", "j/m2"} if code == "ssrd" else {"k", "kelvin"}):
            raise ValueError("ERA5-Land devolvió unidades distintas de las esperadas.")
        xs = (np.asarray(longitude[:], dtype=float) + 180) % 360 - 180
        ys = np.asarray(latitude[:], dtype=float)
        rows, cols = np.argsort(-ys), np.argsort(xs)
        if len(rows) < 2 or len(cols) < 2 or not np.allclose(np.diff(xs[cols]), .1) or not np.allclose(np.diff(ys[rows]), -.1):
            raise ValueError("ERA5-Land no devolvió la grilla regional esperada de 0,1°.")
        transform = from_origin(xs[cols[0]] - .05, ys[rows[0]] + .05, .1, .1)
        spatial = [dim for dim in variable.dimensions if dim != dims[0]]
        stamps = num2date(time[:], time.units, calendar=getattr(time, "calendar", "standard"))
        for index, stamp in enumerate(stamps):
            key = tuple(index if dim == dims[0] else slice(None) for dim in variable.dimensions)
            values = np.ma.asarray(variable[key], dtype=np.float32).filled(np.nan)
            if spatial != list(dims[1:]):
                values = values.T
            values = values[np.ix_(rows, cols)]
            # The monthly means of daily means use an average daily accumulation.
            values = values / 86_400 if code == "ssrd" else values - 273.15
            yield stamp.strftime("%Y-%m"), transform, values


def fetch_era5_land(source, investigation, start, end):
    variable, code, unit = VARIABLES[source["upstream"]["variableId"]]
    area = selected_geometry(source, investigation, {"Polygon", "MultiPolygon", "Point"})
    regional = area["type"] != "Point"
    if regional:
        west, south, east, north = area_bounds(area)
    else:
        west, south = area["coordinates"][:2]
        east, north = west, south
    if east - west > 180:
        raise ValueError("La grilla ERA5-Land requiere un área que no cruce el antimeridiano.")
    periods = monthly_periods(start, end, investigation["time"].get("years"))
    bounds = (max(-180, west - .11), max(-90, south - .11),
              min(180, east + .11), min(90, north + .11))
    path = archive_for(variable, periods, bounds)
    requested = set(periods)
    cell_limit = monthly_map_cell_limit(len(periods))
    frames = {}
    with TemporaryDirectory(dir=path.parent) as folder, ZipFile(path) as archive:
        for entry in archive.infolist():
            if not entry.filename.endswith(".nc"):
                continue
            local = archive.extract(entry, folder)
            for month, transform, values in monthly_grids(local, code):
                if month not in requested:
                    continue
                with MemoryFile() as memory:
                    with memory.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                                     dtype="float32", crs="EPSG:4326", transform=transform, nodata=np.nan) as grid:
                        grid.write(values, 1)
                        frames[month] = read_grid(grid, area, regional, minimum=0 if code == "ssrd" else -100,
                                                  cell_limit=cell_limit)
    if any(not frames.get(month) or frames[month][0] is None for month in periods):
        raise ValueError("ERA5-Land no devolvió celdas válidas para todos los meses seleccionados.")
    points, events = [], []
    for month in periods:
        stamp = month + "-01"
        value, cells = frames[month]
        points.append({"month": stamp, "value": value})
        events.extend({"id": f"{month}:{index}", "date": stamp, **cell} for index, cell in enumerate(cells))
    location = "Promedio espacial del área" if regional else "Celda del punto seleccionado"
    result = series(source, "Copernicus · ECMWF", "ERA5-Land mensual", unit, points, location, REFERENCE, "monthly")
    if not regional:
        return {**result, "coordinates": area["coordinates"][:2]}
    result["map"] = temporal_layer(
        "grid", area, start.replace(day=1), end, "value", events=events, unit=unit,
        cadence="monthly", nativeCadence="monthly", periods=[point["month"] for point in points],
        note="Resolución nativa: 0,1° × 0,1°. En áreas grandes se agrupan celdas para el mapa.",
    )
    return result
