"""ERA5 native centers, batched locations, no elevation downscaling.

Quota (free tier, https://open-meteo.com/en/pricing): 600 calls/minute, 5000/hour, 10000/day. A request
is counted as several calls when it covers several locations or more than two weeks, so the weighted
cost is approximated as locations x ceil(days / 14). The connector refuses requests above
MAX_WEIGHTED_CALLS (with a message on how much to shrink) and paces batches below the per-minute limit.
"""
import math
import time
from collections import deque

import numpy as np
from ..services.public_sources import request_json
from .providers import times_for, check_size, make_field

DAYS_PER_CALL = 14                # Open-Meteo counts more than two weeks of data as extra calls
MINUTE_BUDGET = 550               # stay under the 600 calls/minute free limit
MAX_WEIGHTED_CALLS = 1100         # per grid request: the FWI asks 4 grids, 4 x 1100 < 5000 calls/hour
_RECENT: deque = deque()          # (timestamp, weighted cost) of recent batches in this process


def weighted_cost(n_cells: int, n_days: int) -> int:
    return n_cells * max(1, math.ceil(n_days / DAYS_PER_CALL))


def _pace(cost: int) -> None:
    """Sleep until the batches of the last 60 s plus `cost` fit in MINUTE_BUDGET."""
    while True:
        now = time.monotonic()
        while _RECENT and now - _RECENT[0][0] > 60:
            _RECENT.popleft()
        used = sum(item[1] for item in _RECENT)
        if used + cost <= MINUTE_BUDGET or not _RECENT:
            _RECENT.append((now, cost))
            return
        time.sleep(max(0.5, 60 - (now - _RECENT[0][0])))


def fetch(request):
    w, s, e, n = request.bbox
    lats = np.arange(np.ceil(s * 4), np.floor(n * 4) + 1) / 4
    lons = np.arange(np.ceil(w * 4), np.floor(e * 4) + 1) / 4
    times = times_for(request)
    check_size(request, len(lats) * len(lons), len(times))
    per_location = weighted_cost(1, len(times))
    total = weighted_cost(len(lats) * len(lons), len(times))
    if total > MAX_WEIGHTED_CALLS:
        raise ValueError(f"La grilla de Open-Meteo costaría unas {total} llamadas de la cuota gratuita "
                         f"({len(lats) * len(lons)} celdas × {len(times)} días); el máximo por pedido es "
                         f"{MAX_WEIGHTED_CALLS}. Achicá el área o el período (por ejemplo, unos "
                         f"{max(1, MAX_WEIGHTED_CALLS // per_location)} celdas para este período).")
    values = np.full((len(times), len(lats), len(lons)), np.nan)
    cells = [(i, j) for i in range(len(lats)) for j in range(len(lons))]
    urls, unit = [], None
    batch_size = max(1, min(100, MINUTE_BUDGET // per_location))
    for offset in range(0, len(cells), batch_size):
        batch = cells[offset:offset + batch_size]
        _pace(weighted_cost(len(batch), len(times)))
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
