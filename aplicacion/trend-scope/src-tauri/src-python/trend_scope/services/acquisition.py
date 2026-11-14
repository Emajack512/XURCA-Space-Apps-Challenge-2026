"""Dispatch selected variables through their supported access routes."""

from .reanalysis import ROUTE as REANALYSIS, fetch_reanalysis
from .power import ROUTE, fetch_series
from .public_sources import fetch_public_series

PUBLIC_ROUTES = {"noaa.ncei.station", "nasa.swot.hydrocron"}


def acquire(investigation):
    sources = investigation.get("sources") or []
    if not sources:
        raise ValueError("Agregá al menos una variable.")
    if any(source.get("access") not in PUBLIC_ROUTES | {ROUTE, REANALYSIS} for source in sources):
        raise ValueError("Quitá las fuentes que todavía no están disponibles para consulta.")
    monthly_points = [source for source in sources if source["access"] == ROUTE]
    results = fetch_series({**investigation, "sources": monthly_points}) if monthly_points else []
    for source in sources:
        if source["access"] in PUBLIC_ROUTES:
            results.append(fetch_public_series(source, investigation["time"]))

    results.extend(fetch_reanalysis([source for source in sources if source["access"] == REANALYSIS], investigation))
    by_id = {result["id"]: result for result in results}
    return [by_id[source["id"]] for source in sources]
