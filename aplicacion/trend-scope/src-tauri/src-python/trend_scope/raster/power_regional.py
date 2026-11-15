"""POWER monthly native MERRA-2 cells; annual month 13 is excluded."""
import numpy as np
from ..services.public_sources import request_json
from .providers import times_for, check_size, make_field

def fetch(request):
    w, s, e, n = request.bbox
    times = times_for(request)
    lats = np.arange(np.ceil(s / .5), np.floor(n / .5) + 1) * .5
    lons = np.arange(np.ceil(w / .625), np.floor(e / .625) + 1) * .625
    check_size(request, len(lats) * len(lons), len(times))
    data, url = request_json("https://power.larc.nasa.gov/api/temporal/monthly/regional",
        "power.larc.nasa.gov (revisá conexión, área y fechas; reintentá más tarde)",
        **{"parameters": request.variable_id, "community": "AG", "format": "JSON",
           "longitude-min": w, "longitude-max": e, "latitude-min": s, "latitude-max": n,
           "start": request.start[:4], "end": request.end[:4]})
    values = np.full((len(times), len(lats), len(lons)), np.nan)
    seen = set()
    for feature in data["features"]:
        x, y = feature["geometry"]["coordinates"][:2]
        if not (w <= x <= e and s <= y <= n):
            continue
        if x not in lons or y not in lats or (x, y) in seen:
            raise ValueError("POWER devolvió centros inesperados o duplicados.")
        seen.add((x, y))
        series = feature["properties"]["parameter"][request.variable_id]
        for t, instant in enumerate(times):
            value = series.get(instant[:7].replace("-", ""))
            if value is not None and value != data["header"]["fill_value"]:
                values[t, np.searchsorted(lats, y), np.searchsorted(lons, x)] = value
    if len(seen) != len(lats) * len(lons):
        raise ValueError("POWER devolvió una región incompleta; reducí el bbox y reintentá.")
    return make_field(request, times, lats, lons, values, [url],
                      data["parameters"][request.variable_id]["units"])
