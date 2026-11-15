
"""Build approximate coastal corridors from published country and land polygons."""

import math
from functools import lru_cache

import numpy as np
from rasterio.features import bounds, rasterize, shapes
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from scipy.ndimage import binary_dilation, binary_propagation, distance_transform_edt

from .public_sources import (NATURAL_EARTH, OCEAN_NAMES, country_match, marine_polygons,
                             orient_boundary, region_key, request_json, world_countries)


@lru_cache(maxsize=1)
def land_polygons():
    payload, _ = request_json(NATURAL_EARTH + "ne_50m_land.geojson", "Natural Earth")
    return [part for feature in payload["features"] for part in parts(feature["geometry"])]


def parts(geometry):
    if geometry["type"] == "Polygon":
        return [geometry]
    return [{"type": "Polygon", "coordinates": polygon} for polygon in geometry["coordinates"]]


def extent_area(geometry):
    west, south, east, north = bounds(geometry)
    return (east - west) * (north - south) * math.cos(math.radians((south + north) / 2))


def named_waters(name):
    if name is None:
        return []
    key = region_key(name)
    catalog = marine_polygons()
    names = [name]
    for labels, aliases in OCEAN_NAMES.values():
        if key in {region_key(alias) for alias in (*labels, *aliases)}:
            names = list(labels) if key not in catalog else [name]
            break
    if key in {"atlantico", "oceano atlantico", "atlantic", "atlantic ocean", "atlantico norte", "north atlantic ocean"}:
        names += ["North Atlantic Ocean", "Bay of Biscay", "Gulf of Cadiz"]
    elif key in {"mediterraneo", "mar mediterraneo", "mediterranean", "mediterranean sea"}:
        names = ["Mediterranean Sea", "Western Mediterranean", "Eastern Mediterranean",
                 "Alboran Sea", "Balearic Sea", "Adriatic Sea", "Aegean Sea",
                 "Ionian Sea", "Ligurian Sea", "Tyrrhenian Sea"]
    matches = [catalog[region_key(label)]["geometry"] for label in names if region_key(label) in catalog]
    if not matches:
        raise ValueError("No encontré ese mar o sector en Natural Earth. Precisá el nombre o elegí toda la costa.")
    return matches


def coastal_band(country, land, distance_km, side, water=()):
    west, south, east, north = bounds(country)
    if east - west > 70 or north - south > 55 or south < -80 or north > 80:
        raise ValueError("La costa cubre una extensión muy grande. Indicá un tramo más acotado.")
    lon, lat = (west + east) / 2, (south + north) / 2
    crs = f"+proj=aeqd +lon_0={lon} +lat_0={lat} +datum=WGS84 +units=m +no_defs"

    def project(geometry):
        return transform_geom("EPSG:4326", crs, geometry)

    national = project(country)
    left, bottom, right, top = bounds(national)
    distance = distance_km * 1000
    step = min(2000, distance / 4)
    pad = distance + step * 3
    shape = (math.ceil((top - bottom + 2 * pad) / step), math.ceil((right - left + 2 * pad) / step))
    if math.prod(shape) > 4_000_000:
        raise ValueError("Esa distancia requiere una grilla muy grande. Acotá la costa o elegí una franja más ancha.")
    grid = from_origin(left - pad, top + pad, step, step)

    def mask(geometries):
        if not geometries:
            return np.zeros(shape, dtype=bool)
        return rasterize(geometries, out_shape=shape, transform=grid, dtype="uint8").astype(bool)

    # Cull offshore islands and land masses too far from the padded study window.
    latitude_margin = pad / 100_000 + 1
    longitude_margin = latitude_margin / max(.1, math.cos(math.radians(max(abs(south), abs(north)))))

    def nearby(geometry):
        x0, y0, x1, y1 = bounds(geometry)
        return (x1 >= west - longitude_margin and x0 <= east + longitude_margin
                and y1 >= south - latitude_margin and y0 <= north + latitude_margin)

    national_mask = mask([national])
    land_mask = mask([project(part) for part in land if nearby(part)]) | national_mask
    wet = ~land_mask
    exterior = np.zeros(shape, dtype=bool)
    exterior[0, :] = exterior[-1, :] = True
    exterior[:, 0] = exterior[:, -1] = True
    sea = binary_propagation(exterior & wet, mask=wet)
    shoreline = national_mask & binary_dilation(sea)
    if water:
        sector = mask([project(part) for region in water for part in parts(region) if nearby(part)]) & sea
        if not sector.any():
            raise ValueError("Ese mar o sector no coincide con la costa seleccionada.")
        # The marine and land outlines are generalized independently at 1:50m scale.
        shoreline &= distance_transform_edt(~sector, sampling=step) <= 12_000
    if not shoreline.any():
        raise ValueError("No encontré un tramo de costa para esa selección.")
    band = distance_transform_edt(~shoreline, sampling=step) <= distance
    if side == "sea":
        band &= sea
    elif side == "land":
        band &= national_mask
    else:
        band &= sea | national_mask
    polygons = [geometry["coordinates"] for geometry, _ in shapes(band.astype("uint8"), mask=band, transform=grid)]
    if not polygons:
        raise ValueError("La franja es demasiado angosta para la resolución del catálogo.")
    geometry = transform_geom(crs, "EPSG:4326", {"type": "MultiPolygon", "coordinates": polygons}, precision=5)
    return orient_boundary(geometry)


def coastal_regions(countries, territory, side, distance_km, waters=None):
    codes = [country_match(name) for name in countries]
    if None in codes or len(set(codes)) != len(codes):
        raise ValueError("Precisá los países costeros sin repetirlos.")
    waters = None if waters == "all" else waters
    water = named_waters(waters)
    result = []
    for name, code in zip(countries, codes):
        country = world_countries()[code]["geometry"]
        if territory == "mainland":
            country = max(parts(country), key=extent_area)
        geometry = coastal_band(country, land_polygons(), distance_km, side, water)
        result.append({"name": f"{name} · {distance_km:g} km" + (f" · {waters}" if waters else ""),
                       "geometry": geometry})
    return result
