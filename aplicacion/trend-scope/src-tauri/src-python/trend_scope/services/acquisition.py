"""Dispatch selected variables through their supported access routes."""

import json
from datetime import date

from .reanalysis import ROUTE as REANALYSIS, fetch_reanalysis
from .power import ROUTE, fetch_series
from .public_sources import fetch_public_series

PUBLIC_ROUTES = {"noaa.ncei.station", "nasa.swot.hydrocron"}


def validate_investigation(investigation):
    """Reject incomplete or malformed configurations before calling any data source."""
    try:
        json.dumps(investigation, allow_nan=False)
        if investigation.get("schemaVersion") != 1:
            raise ValueError()
        period = investigation["time"]
        start, end = (date.fromisoformat(period[key]) for key in ("start", "end"))
        if start > end or end > date.today():
            raise ValueError()
        if investigation.get("methods"):
            raise ValueError("Los métodos personalizados todavía no están conectados a Procesar.")
        features = investigation["geography"]["selection"]["features"]
        points = {}
        for feature in features:
            if feature["geometry"]["type"] != "Point":
                continue
            lon, lat = feature["geometry"]["coordinates"]
            if type(lon) not in (int, float) or type(lat) not in (int, float) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError()
            if feature["id"] in points:
                raise ValueError()
            points[feature["id"]] = feature
        sources = investigation["sources"]
        if not 1 <= len(sources) <= 25 or len({s["id"] for s in sources}) != len(sources):
            raise ValueError()
        for source in sources:
            access = source["access"]
            upstream = source["upstream"]
            if access not in PUBLIC_ROUTES | {ROUTE, REANALYSIS} or not upstream.get("variableId"):
                raise ValueError()
            if access in {ROUTE, REANALYSIS} and upstream.get("geometryId") not in points:
                raise ValueError()
            selectors = upstream.get("selectors", {})
            if access == "noaa.ncei.station" and not selectors.get("stationId"):
                raise ValueError()
            if access == "nasa.swot.hydrocron" and not selectors.get("featureId"):
                raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError("Revisá la investigación: fechas históricas en orden, variables admitidas y un punto o identificador por fuente. Los métodos personalizados aún no se ejecutan.") from None


def acquire(investigation):
    validate_investigation(investigation)
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
