from datetime import date
from zipfile import ZipFile

from netCDF4 import Dataset
import pytest
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from .grid_layers import with_grid_map
from . import firms
from . import station_catalogs
from .precipitation import read_precipitation
from .station_catalogs import regional_entities


AREA = {"type": "Polygon", "coordinates": [[[-0.4, -0.4], [1.4, -0.4], [1.4, 1.4], [-0.4, 1.4], [-0.4, -0.4]]]}
START, END = date(2025, 1, 1), date(2025, 1, 2)


def test_precipitation_keeps_zero_and_clips_to_valid_cells():
    with MemoryFile() as image:
        with image.open(driver="GTiff", width=2, height=2, count=1, dtype="float32",
                        crs="EPSG:4326", transform=from_origin(0, 2, 1, 1)) as raster:
            raster.write(np.array([[0, 12], [24, -9999]], dtype="float32"), 1)
            point = {"type": "Point", "coordinates": [0.1, 1.9]}
            assert read_precipitation(raster, point, False) == (0, [])
            point["coordinates"] = [1.1, 0.1]
            assert read_precipitation(raster, point, False) == (None, [])
            tiny = {"type": "Polygon", "coordinates": [
                [[1.1, 1.1], [1.2, 1.1], [1.2, 1.2], [1.1, 1.2], [1.1, 1.1]]
            ]}
            average, cells = read_precipitation(raster, tiny, True)
            assert average == pytest.approx(12)
            assert [cell["value"] for cell in cells] == pytest.approx([12])


def test_download_to_map_preserves_native_values_and_missing_cells(tmp_path):
    path = tmp_path / "fields.nc"
    with Dataset(path, "w") as data:
        for axis, values, units in [
            ("lat", [0, 1], "degrees_north"),
            ("lon", [0, 1], "degrees_east"),
            ("time", [0, 12, 24], "hours since 2025-01-01 00:00:00"),
        ]:
            data.createDimension(axis, len(values))
            coord = data.createVariable(axis, "f4", (axis,))
            coord.units = units
            coord[:] = values
        rainfall = data.createVariable("precipitation", "f4", ("time", "lat", "lon"), fill_value=-9999)
        rainfall.units = "mm"
        rainfall[:] = [[[800, 800], [800, 800]], [[2, -9999], [3, 4]], [[5, 6], [7, 8]]]
        unrelated = data.createVariable("temperature", "f4", ("time", "lat", "lon"))
        unrelated.units = "K"
    archive_path = tmp_path / "grid.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(path, path.name)
    source = {"id": "rain", "access": "nasa.earthdata",
              "upstream": {"geometryId": "p", "variableId": "all", "selectors": {"mapVariable": "precipitation"}}}
    investigation = {"geography": {"selection": {"features": [{"id": "p", "geometry": AREA}]}}}
    result = with_grid_map({"downloadPath": str(archive_path)}, source, investigation, START, END)
    layer = result["map"]
    assert layer["kind"] == "grid"
    assert layer["unit"] == "mm"
    assert [row["value"] for row in layer["events"]] == [2, 3, 4, 5, 6, 7, 8]
    assert layer["events"][0]["date"] == "2025-01-01T12:00:00"
    source["upstream"]["selectors"]["mapVariable"] = "unknown"
    missing = with_grid_map({"downloadPath": str(archive_path)}, source, investigation, START, END)
    assert "map" not in missing
    assert "mapMessage" in missing


def test_station_area_keeps_each_feature_and_can_skip_a_failed_candidate():
    candidates = [(0, key, key, {"type": "Point", "coordinates": [x, x]})
                  for key, x in [("first", 0), ("failed", 0.4), ("third", 1)]]

    def fetch(candidate):
        if candidate[1] == "failed":
            raise ValueError("Provider unavailable")
        return {"unit": "m", "cadence": "monthly", "points": [{"month": "2025-01", "value": candidate[3]["coordinates"][0]}]}

    result = regional_entities({"id": "water", "upstream": {"variableId": "level"}}, AREA, START, END, candidates, fetch)
    layer = result["map"]
    assert layer["cadence"] == "monthly"
    assert layer["failures"] == 1
    assert [row["entityId"] for row in layer["events"]] == ["first", "third"]
    assert [row["value"] for row in layer["events"]] == [0, 1]


def test_noaa_area_checks_nearby_stations_and_preserves_zero_rainfall(monkeypatch):
    monkeypatch.setattr(station_catalogs, "noaa_stations", lambda: (
        ("outside", "Too far", 4, 0),
        ("nearby", "Nearby", 2.2, 0),
        ("inside", "Inside", 1, 0),
    ))
    source = {"id": "rain", "access": "noaa.ncei.daily", "product": "NOAA daily",
              "upstream": {"variableId": "PRCP", "geometryId": "p"}}
    investigation = {"geography": {"selection": {"features": [{"id": "p", "geometry": AREA}]}}}
    calls = []

    def fetch(candidate):
        station = candidate["upstream"]["selectors"]["stationId"]
        calls.append(station)
        return {"unit": "mm", "cadence": "daily", "points": [
            {"month": "2025-01-01", "value": 0 if station == "nearby" else None}
        ]}

    result = station_catalogs.fetch_for_selection(source, investigation, START, END, fetch)
    assert sorted(calls) == ["inside", "nearby"]
    assert result["map"]["stationSurface"]
    assert result["map"]["events"][0]["entityId"] == "nearby"
    assert result["map"]["events"][0]["value"] == 0
    with pytest.raises(ValueError, match="no devolvió datos de PRCP"):
        station_catalogs.fetch_for_selection(source, investigation, START, END,
                                             lambda _: {"points": []})


def test_firms_emits_detections_and_keeps_original_csv(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRMS_MAP_KEY", "fixture")
    monkeypatch.setattr(firms, "directory", lambda: tmp_path)
    monkeypatch.setattr(firms, "read_text", lambda *_:
                        "latitude,longitude,acq_date,acq_time,frp,confidence\n"
                        "0,0,2025-01-01,0830,15,nominal\n"
                        "4,4,2025-01-01,0930,80,high\n")
    source = {"id": "frp", "upstream": {"variableId": "frp", "productId": "VIIRS_SNPP_SP", "geometryId": "p"}}
    investigation = {"geography": {"selection": {"features": [{"id": "p", "geometry": AREA}]}}}
    result = firms.fetch_firms(source, investigation, START, END)
    assert result["map"]["eventType"] == "fire"
    [detection] = result["map"]["events"]
    assert detection["date"] == "2025-01-01T08:30:00Z"
    assert detection["frp"] == 15
    assert "fixture" not in str(result)

def test_regional_daily_mean_uses_calendar_days_and_keeps_missing_months(monkeypatch):
    from . import precipitation
    monkeypatch.setattr(precipitation, "monthly_assets", lambda route: {"2024-02": "february"})
    monkeypatch.setattr(precipitation, "read_period",
                        lambda *args: (58, [{"value": 29, "geometry": AREA}]))
    source = {"id": "rain", "access": precipitation.CHIRPS_ROUTE,
              "upstream": {"geometryId": "area", "variableId": "precipitation_daily_mean"}}
    config = {"geography": {"selection": {"features": [{"id": "area", "geometry": AREA}]}}}
    result = precipitation.fetch_precipitation(source, config, date(2024, 2, 1), date(2024, 3, 31))
    assert result["unit"] == result["map"]["unit"] == "mm/día"
    assert [row["value"] for row in result["points"]] == [2, None]
    assert result["map"]["events"][0]["value"] == 1
    assert "1 de 2" in result["mapMessage"]

def test_large_grid_combines_blocks_with_cell_weights():
    from .precipitation import read_nonnegative_grid
    with MemoryFile() as image:
        with image.open(driver="GTiff", width=600, height=2, count=1, dtype="float32",
                        crs="EPSG:4326", transform=from_origin(-60, 1, .1, .1)) as raster:
            data = np.full((2, 600), 10, dtype="float32")
            data[:, 480:] = 60
            raster.write(data, 1)
            area = {"type": "Polygon", "coordinates": [[[-60,.8],[0,.8],[0,1],[-60,1],[-60,.8]]]}
            value, cells = read_nonnegative_grid(raster, area, True)
    assert value == pytest.approx(20)
    assert len(cells) == 1200
    assert len({str(cell["geometry"]) for cell in cells}) == len(cells)


def test_earthquake_blocks_deduplicate_shared_events(monkeypatch):
    from . import environmental_series as es
    event = {"id": "shared", "geometry": {"coordinates": [0, 0, 5]},
             "properties": {"time": 1735689600000, "mag": 4}}
    monkeypatch.setattr(es, "spatial_blocks", lambda *args: [(-1,-1,0,1),(0,-1,1,1)])
    monkeypatch.setattr(es, "earthquake_window", lambda *args: [event])
    source = {"id": "quakes", "upstream": {"variableId": "count", "geometryId": "area", "selectors": {}}}
    config = {"geography": {"selection": {"features": [{"id": "area", "geometry": AREA}]}}}
    result = es.fetch_earthquakes(source, config, START, END)
    assert len(result["map"]["events"]) == 1
    assert [point["value"] for point in result["points"]] == [1, 0]



def test_temperature_grid_keeps_negative_values_and_excludes_fill():
    from .precipitation import read_grid
    with MemoryFile() as image:
        with image.open(driver="GTiff", width=3, height=1, count=1, dtype="float32",
                        crs="EPSG:4326", transform=from_origin(0, 1, 1, 1)) as raster:
            raster.write(np.array([[-6, 4, -999]], dtype="float32"), 1)
            geometry = {"type": "Polygon", "coordinates": [[[0,0],[3,0],[3,1],[0,1],[0,0]]]}
            value, cells = read_grid(raster, geometry, True, minimum=-100)
    assert value == pytest.approx(-1)
    assert [cell["value"] for cell in cells] == [-6, 4]


def test_power_regional_keeps_all_months_and_maps_for_a_long_period(monkeypatch):
    from datetime import date
    from . import power_grid

    geometry = {"type": "Polygon", "coordinates": [[[-48, -16], [-47, -16], [-47, -15], [-48, -16]]]}
    months = {f"{year}-{month:02d}": 1 for year in range(1994, 2011) for month in range(1, 13)}
    monkeypatch.setattr(power_grid, "selected_geometry", lambda *args: geometry)
    monkeypatch.setattr(power_grid, "monthly_slices", lambda product: months)
    monkeypatch.setattr(power_grid, "grid_month", lambda *args: (200, [{"value": 200}]))
    source = {"id": "solar", "access": power_grid.SOLAR_ROUTE, "upstream": {"variableId": "ALLSKY_SFC_SW_DWN"}}
    result = power_grid.fetch_power_area(source, {"time": {}}, date(1994, 1, 1), date(2010, 12, 31))

    expected = [month + "-01" for month in months]
    assert [point["month"] for point in result["points"]] == expected
    assert result["map"]["periods"] == expected
    assert [cell["date"] for cell in result["map"]["events"]] == expected



def test_coastal_buffer_uses_the_sea_and_excludes_the_land_border():
    from .coastal_regions import coastal_band
    from .environmental_series import inside_area

    def rectangle(west, south, east, north):
        return {"type": "Polygon", "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south]
        ]]}

    country = rectangle(0, -0.5, 1, 0.5)
    land = [rectangle(0, -3, 3, 3)]
    offshore = coastal_band(country, land, 25, "sea")
    inland = coastal_band(country, land, 25, "land")
    assert inside_area(-0.1, 0, offshore)
    assert not inside_area(-0.4, 0, offshore)
    assert not inside_area(0.1, 0, offshore)
    assert inside_area(0.1, 0, inland)
    assert not inside_area(0.95, 0, inland)


def test_physical_regions_use_catalog_polygons(monkeypatch):
    from . import public_sources

    geometry = {"type": "Polygon", "coordinates": [[
        [76, 30], [77, 30], [77, 31], [76, 30]
    ]]}
    monkeypatch.setattr(public_sources, "physical_regions", lambda: {
        "5": {"geometry": geometry, "properties": {"name": "HIMALAYAS"}}
    })
    result = public_sources.find_places("Himalaya", "physical")
    assert [item["id"] for item in result] == ["5"]
    assert public_sources.place_boundary("physical", "5") == geometry


def test_bathymetry_samples_a_thin_coastal_strip(monkeypatch):
    from datetime import date
    from . import bathymetry

    geometry = {"type": "Polygon", "coordinates": [[
        [-9.2, 39.9], [-9.1, 39.9], [-9.1, 40.1], [-9.2, 40.1], [-9.2, 39.9]
    ]]}
    source = {"id": "depth", "upstream": {"variableId": "depth", "geometryId": "coast"}}
    workspace = {"geography": {"selection": {"features": [{
        "id": "coast", "geometry": geometry, "properties": {"coastDistanceKm": 20}
    }]}}}

    def fetch(block, stride):
        assert stride == 5
        return [(-9.15, 40.0, -100)]

    monkeypatch.setattr(bathymetry, "etopo_block", fetch)
    result = bathymetry.fetch_bathymetry(source, workspace, date.today(), date.today())
    assert result["map"]["events"][0]["value"] == 100
