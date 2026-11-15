"""Public station, surface-water, and Argentine place lookups."""

import csv
import io
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from unicodedata import combining, normalize
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def request_json(endpoint, provider, **parameters):
    url = endpoint + "?" + urlencode(parameters)
    try:
        with urlopen(url, timeout=25) as response:
            return json.load(response), url
    except HTTPError as error:
        if error.code == 429:
            raise ValueError(f"{provider} alcanzó el límite de consultas. Volvé a intentar más tarde.") from error
        raise ValueError(f"{provider} rechazó la solicitud (HTTP {error.code}). Revisá el identificador y las fechas.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo obtener una respuesta válida de {provider}.") from error


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result not in (-999, -9999, -999999999999) else None


def fetch_public_series(source, period):
    route = source["access"]
    upstream = source.get("upstream") or {}
    variable = upstream.get("variableId")
    selectors = upstream.get("selectors") or {}
    start, end = (date.fromisoformat(period[key]) for key in ("start", "end"))
    if start > end:
        raise ValueError("La fecha inicial debe ser anterior o igual a la final.")

    if route in {"noaa.ncei.station", "noaa.ncei.daily"}:
        provider = "NOAA NCEI"
        station = selectors.get("stationId", "").strip().upper()
        daily = route == "noaa.ncei.daily"
        units = {"PRCP": "mm", "TAVG": "°C", "TMAX": "°C", "TMIN": "°C", "SNOW": "mm", "SNWD": "mm"}
        if not re.fullmatch(r"[A-Z0-9]{11}", station) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", variable or ""):
            raise ValueError("Ingresá un ID de estación NOAA de 11 caracteres y una variable admitida.")
        rows, url = request_json(
            "https://www.ncei.noaa.gov/access/services/data/v1", provider,
            dataset="daily-summaries" if daily else "global-summary-of-the-month", stations=station,
            startDate=(start if daily else start.replace(day=1)).isoformat(),
            endDate=end.isoformat(), dataTypes=variable, units="metric", format="json",
        )
        by_date = {row["DATE"]: number(row.get(variable)) for row in rows}
        if daily:
            dates = ((start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1))
        else:
            dates = (f"{year:04d}-{month:02d}" for year in range(start.year, end.year + 1)
                     for month in range(1, 13)
                     if (start.year, start.month) <= (year, month) <= (end.year, end.month))
        points = [{"month": key, "value": by_date.get(key)} for key in dates]
        location = f"Estación {station}"
    else:
        provider = "NASA SWOT / Hydrocron"
        feature = selectors.get("featureType")
        identifier = selectors.get("featureId", "").strip()
        if feature not in ("Reach", "PriorLake") or not re.fullmatch(r"[0-9]{10,11}", identifier):
            raise ValueError("Ingresá el ID oficial de un tramo de río o lago SWOT.")
        units = {"wse": "m", "area_total": "km²"}
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", variable or ""):
            raise ValueError("La variable elegida no corresponde al tipo de río o lago.")
        field = "reach_id" if feature == "Reach" else "lake_id"
        payload, url = request_json(
            "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries", provider,
            feature=feature, feature_id=identifier, fields=f"{field},time_str,{variable}",
            output="csv", start_time=f"{start}T00:00:00Z", end_time=f"{end}T23:59:59Z",
            collection_name="SWOT_L2_HR_RiverSP_D" if feature == "Reach" else "SWOT_L2_HR_LakeSP_D",
        )
        rows = list(csv.DictReader(io.StringIO(payload.get("results", {}).get("csv") or "")))
        unit = next((row[f"{variable}_units"] for row in rows if row.get(f"{variable}_units")), None)
        if unit:
            units[variable] = unit.replace("km^2", "km²")
        points = sorted(
            ({"month": row["time_str"], "value": number(row.get(variable))}
             for row in rows if row.get("time_str") and row["time_str"] != "no_data"),
            key=lambda point: point["month"],
        )
        location = f"{'Tramo de río' if feature == 'Reach' else 'Lago'} {identifier}"

    return {
        "id": source["id"], "provider": provider, "variable": variable, "points": points,
        "unit": units.get(variable, "Unidad sin verificar"), "location": location, "url": url,
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "cadence": {"nasa.swot.hydrocron": "overpass", "noaa.ncei.daily": "daily"}.get(route, "monthly"),
    }


GEOREF = "https://apis.datos.gob.ar/georef/api/v2.0/"
BOUNDARY_KINDS = {"provincias", "localidades-censales"}


def find_places(query, kind, language="es"):
    if kind not in BOUNDARY_KINDS | {"localidades", "regiones", "paises", "continentes", "oceanos", "physical"} or not 2 <= len(query.strip()) <= 100:
        raise ValueError("Ingresá entre 2 y 100 caracteres para buscar un lugar.")
    if kind == "physical":
        return find_physical_region(query)
    if kind == "regiones":
        return find_world_regions(query)
    if kind == "oceanos":
        return find_ocean(query)
    if kind == "continentes":
        return find_continent(query)
    if kind == "paises":
        return find_country(query)
    if kind == "localidades":
        return find_world_cities(query, language)
    payload, _ = request_json(
        GEOREF + kind,
        "Georef Argentina", nombre=query.strip(), max=8,
    )
    return [
        {"id": item["id"], "name": item["nombre"], "country": "Argentina",
         "province": item["nombre"] if kind == "provincias" else (item.get("provincia") or {}).get("nombre"),
         "coordinates": [item["centroide"]["lon"], item["centroide"]["lat"]]}
        for item in payload[kind.replace("-", "_")]
        if (item.get("centroide") or {}).get("lon") is not None and item["centroide"].get("lat") is not None
    ]


@lru_cache(maxsize=2)
def georef_boundaries(kind):
    payload, _ = request_json(GEOREF + kind + ".geojson", "Georef Argentina")
    return {item["properties"]["id"]: item["geometry"] for item in payload["features"]
            if item.get("geometry") and item["geometry"]["type"] in {"Polygon", "MultiPolygon"}}


def region_key(name):
    return "".join(char for char in normalize("NFD", name.casefold()) if not combining(char)).strip()


@lru_cache(maxsize=1)
def world_countries():
    endpoint = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
                "geojson/ne_50m_admin_0_countries.geojson")
    payload, _ = request_json(endpoint, "Natural Earth")
    countries = {}
    for item in payload["features"]:
        props = item["properties"]
        code = next((value for value in (props.get("ISO_A3"), props.get("ISO_A3_EH"))
                     if value and re.fullmatch(r"[A-Z]{3}", value)), None)
        if code and (code not in countries or props.get("ADM0_A3") == code):
            countries[code] = item
    return countries


def country_match(name):
    key = region_key(name)
    if not key:
        return None
    matches = []
    for code, item in world_countries().items():
        props = item["properties"]
        names = [code, *(props.get(field) for field in ("ISO_A2", "ADMIN", "NAME", "NAME_LONG", "NAME_ES", "NAME_EN"))]
        if key in {region_key(value) for value in names if value}:
            matches.append(code)
    return matches[0] if len(matches) == 1 else None


def boundary_result(identifier, name, item, country=None):
    geometry = item["geometry"]
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    vertices = [point[:2] for polygon in polygons for point in polygon[0]]
    center = [(min(values) + max(values)) / 2 for values in zip(*vertices)]
    return {"id": identifier, "name": name.strip(), "country": country, "coordinates": center}


def find_country(query):
    code = country_match(query)
    return [boundary_result(code, query, world_countries()[code])] if code else []


@lru_cache(maxsize=12)
def world_regions(code, level):
    layer = f"ADM{level}"
    try:
        meta, _ = request_json(f"https://www.geoboundaries.org/api/current/gbOpen/{code}/{layer}/", "geoBoundaries")
    except ValueError as error:
        if isinstance(error.__cause__, HTTPError) and error.__cause__.code == 404:
            return {}
        raise
    if not isinstance(meta, dict):
        return {}
    url = meta.get("simplifiedGeometryGeoJSON", "")
    path = re.fullmatch(r"https://github\.com/wmgeolab/geoBoundaries/raw/[a-f0-9]+/releaseData/gbOpen/"
                        + code + "/" + layer + "/geoBoundaries-" + code + "-" + layer + r"_simplified\.geojson", url)
    if not path:
        raise ValueError("geoBoundaries no devolvió un archivo de límites compatible.")
    payload, _ = request_json(url, "geoBoundaries")
    return {str(index): item for index, item in enumerate(payload.get("features", []))
            if item.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"}}


def find_world_regions(query):
    name, _, country = query.partition(",")
    code = country_match(country)
    if not code:
        return []
    key = region_key(name)
    if code == "PRY" and key in {"distrito capital", "asuncion del paraguay"}:
        key = "asuncion"
    for level in (1, 2):
        matches = [boundary_result(f"{code}:{level}:{identifier}", name, item, country.strip())
                   for identifier, item in world_regions(code, level).items()
                   if region_key(item["properties"]["shapeName"]) == key]
        if matches:
            return matches
    return []


CONTINENT_NAMES = {
    "south-america": ("South America", "América del Sur", "Sudamérica", "Suramérica"),
    "north-america": ("North America", "América del Norte", "Norteamérica"),
    "europe": ("Europe", "Europa"),
    "africa": ("Africa", "África"),
    "asia": ("Asia",),
    "oceania": ("Oceania", "Oceanía"),
    "antarctica": ("Antarctica", "Antártida"),
}


@lru_cache(maxsize=len(CONTINENT_NAMES))
def continent_boundary(identifier):
    continent = CONTINENT_NAMES[identifier][0]
    parts = []
    for item in world_countries().values():
        geometry = item["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        if item["properties"].get("CONTINENT") == continent:
            parts.extend(polygons)
        elif identifier == "south-america" and item["properties"].get("ADMIN") == "France":
            # Natural Earth groups French Guiana with France in its country layer.
            parts.extend(polygon for polygon in polygons
                         if all(-62 < x < -48 and 0 < y < 10 for x, y, *_ in polygon[0]))
    return {"type": "MultiPolygon", "coordinates": parts}


def find_continent(query):
    key = region_key(query)
    for identifier, names in CONTINENT_NAMES.items():
        if key in {region_key(name) for name in names}:
            return [boundary_result(identifier, query, {"geometry": continent_boundary(identifier)})]
    return []


OCEAN_NAMES = {
    "atlantic": (("North Atlantic Ocean", "South Atlantic Ocean"), ("Atlántico", "Océano Atlántico", "Atlantic Ocean")),
    "north-atlantic": (("North Atlantic Ocean",), ("Atlántico Norte", "Océano Atlántico Norte")),
    "south-atlantic": (("South Atlantic Ocean",), ("Atlántico Sur", "Océano Atlántico Sur")),
    "pacific": (("North Pacific Ocean", "South Pacific Ocean"), ("Pacífico", "Océano Pacífico", "Pacific Ocean")),
    "indian": (("Indian Ocean",), ("Índico", "Océano Índico")),
    "arctic": (("Arctic Ocean",), ("Ártico", "Océano Ártico")),
    "southern": (("Southern Ocean",), ("Antártico", "Océano Antártico", "Océano Austral")),
}


@lru_cache(maxsize=1)
def marine_polygons():
    endpoint = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
                "geojson/ne_50m_geography_marine_polys.geojson")
    payload, _ = request_json(endpoint, "Natural Earth")
    return {region_key(item["properties"]["name"]): item for item in payload["features"]
            if item.get("geometry") and item["properties"].get("name")}


def ocean_boundary(identifier):
    names, _ = OCEAN_NAMES[identifier]
    parts = []
    for name in names:
        item = marine_polygons().get(region_key(name))
        if not item:
            raise ValueError("No encontré el límite publicado para toda la cuenca oceánica.")
        geom = item["geometry"]
        parts.extend([geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"])
    return {"type": "MultiPolygon", "coordinates": parts}


def find_ocean(query):
    key = region_key(query)
    for identifier, (names, aliases) in OCEAN_NAMES.items():
        lookup = (*aliases, *names) if len(names) == 1 else aliases
        if key in {region_key(name) for name in lookup}:
            return [boundary_result(identifier, query, {"geometry": ocean_boundary(identifier)})]
    return []



NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"


@lru_cache(maxsize=1)
def physical_regions():
    payload, _ = request_json(NATURAL_EARTH + "ne_50m_geography_regions_polys.geojson", "Natural Earth")
    return {str(index): item for index, item in enumerate(payload["features"])
            if (item.get("geometry") or {}).get("type") in {"Polygon", "MultiPolygon"}}


def find_physical_region(query):
    aliases = {"himalaya": "himalayas", "cordillera del himalaya": "himalayas",
               "desierto del sahara": "sahara", "atacama": "desierto de atacama", "atacama desert": "desierto de atacama",
               "gobi": "gobi desert", "desierto del gobi": "gobi desert"}
    key = region_key(query)
    key = aliases.get(key, key)
    return [boundary_result(identifier, query, item) for identifier, item in physical_regions().items()
            if key in {region_key(value) for field, value in item["properties"].items()
                       if field.lower().startswith(("name", "namealt")) and isinstance(value, str)}]


def place_boundary(kind, identifier):
    if kind == "physical" and identifier in physical_regions():
        return orient_boundary(physical_regions()[identifier]["geometry"])
    if kind == "oceanos" and identifier in OCEAN_NAMES:
        return orient_boundary(ocean_boundary(identifier))
    if kind == "continentes" and identifier in CONTINENT_NAMES:
        return orient_boundary(continent_boundary(identifier))
    if kind == "paises" and re.fullmatch(r"[A-Z]{3}", identifier):
        region = world_countries().get(identifier)
        if region:
            return orient_boundary(region["geometry"])
    if kind == "regiones" and re.fullmatch(r"[A-Z]{3}:[12]:[0-9]{1,5}", identifier):
        code, level, index = identifier.split(":")
        region = world_regions(code, int(level)).get(index)
        if region:
            return orient_boundary(region["geometry"])
    if kind not in BOUNDARY_KINDS or not re.fullmatch(r"[0-9]{2,12}", identifier):
        raise ValueError("El lugar seleccionado no tiene un identificador de área válido.")
    geometry = georef_boundaries(kind).get(identifier)
    if geometry is None:
        raise ValueError("No hay un límite publicado para este lugar.")
    return orient_boundary(geometry)


def orient_boundary(geometry):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    oriented = []
    for polygon in polygons:
        rings = []
        for index, ring in enumerate(polygon):
            area = sum(a[0]*b[1] - a[1]*b[0] for a, b in zip(ring, ring[1:]))
            rings.append(ring if (area > 0) == (index == 0) else list(reversed(ring)))
        oriented.append(rings)
    return {"type": geometry["type"], "coordinates": oriented[0] if geometry["type"] == "Polygon" else oriented}


def find_world_cities(query, language):
    payload, _ = request_json(
        "https://photon.komoot.io/api/", "Photon",
        q=query.strip(), layer="city", limit=8, lang="en" if language == "en" else "default",
    )
    # Photon can return administrative boundaries alongside the actual town.
    # Prefer a place feature only within the same named province and country.
    features = payload.get("features", [])
    def identity(props):
        return tuple((props.get(key) or "").casefold() for key in ("name", "state", "country"))
    towns = {identity(feature["properties"]) for feature in features
             if feature["properties"].get("osm_key") == "place"}
    places = []
    for feature in features:
        props = feature["properties"]
        if props.get("osm_key") == "boundary" and identity(props) in towns:
            continue
        if not props.get("name") or feature["geometry"]["type"] != "Point":
            continue
        places.append({
            "id": f'{props["osm_type"]}{props["osm_id"]}',
            "name": props["name"], "province": props.get("state"),
            "country": props.get("country"), "coordinates": feature["geometry"]["coordinates"],
        })
    return places
