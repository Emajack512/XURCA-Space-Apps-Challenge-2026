"""ERA5 native centers, batched locations, no elevation downscaling."""
import numpy as np
from ..services.public_sources import request_json
from .providers import times_for, check_size, make_field

# Operational batch size, NOT the API maximum (1000 locations).
BATCH_SIZE = 10

def fetch(request):
    w, s, e, n = request.bbox
    lats = np.arange(np.ceil(s * 4), np.floor(n * 4) + 1) / 4
    lons = np.arange(np.ceil(w * 4), np.floor(e * 4) + 1) / 4
    times = times_for(request)
    check_size(request, len(lats) * len(lons), len(times))
    values = np.full((len(times), len(lats), len(lons)), np.nan)
    cells = [(i, j) for i in range(len(lats)) for j in range(len(lons))]
    urls, unit = [], None
    for offset in range(0, len(cells), BATCH_SIZE):
        batch = cells[offset:offset + BATCH_SIZE]
        data, url = request_json("https://archive-api.open-meteo.com/v1/archive",
            "archive-api.open-meteo.com (revisá conexión y cuota; reintentá más tarde)",
            latitude=",".join(str(lats[i]) for i, j in batch),
            longitude=",".join(str(lons[j]) for i, j in batch),
            start_date=request.start, end_date=request.end, daily=request.variable_id,
            models="era5", timezone="GMT", elevation="nan", cell_selection="nearest")
        urls.append(url)
        rows = data if isinstance(data, list) else [data]
        if len(rows) != len(batch):
            raise ValueError("Open-Meteo devolvió una cantidad de celdas inesperada.")
        for row, (i, j) in zip(rows, batch):
            if not (np.isclose(row["latitude"], lats[i], atol=1e-5, rtol=0)
                    and np.isclose(row["longitude"], lons[j], atol=1e-5, rtol=0)):
                raise ValueError("Open-Meteo devolvió otra celda; no se permite regrillar.")
            if row["daily"]["time"] != times:
                raise ValueError("Open-Meteo devolvió fechas incompletas o inesperadas.")
            returned_unit = row["daily_units"][request.variable_id]
            if unit is not None and unit != returned_unit:
                raise ValueError("Open-Meteo cambió las unidades entre celdas.")
            unit = returned_unit
            values[:, i, j] = [np.nan if v is None else v for v in row["daily"][request.variable_id]]
    return make_field(request, times, lats, lons, values, urls, unit)
