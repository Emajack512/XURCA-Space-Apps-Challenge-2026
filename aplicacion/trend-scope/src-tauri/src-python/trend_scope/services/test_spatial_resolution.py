from datetime import date
from zipfile import ZipFile

import pytest
from netCDF4 import Dataset

from . import era5_land_monthly, spatial_resolution
from .power_grid import SOLAR_ROUTE
from .precipitation import CHIRPS_ROUTE, PMRA_ROUTE


def example():
    area = {"type": "Polygon", "coordinates": [[
        [-66.35, -33.35], [-66.15, -33.35], [-66.15, -33.15], [-66.35, -33.15], [-66.35, -33.35],
    ]]}
    request = {"time": {}, "geography": {"selection": {"features": [{"id": "sl", "geometry": area}]}}}
    source = {"id": "solar", "access": SOLAR_ROUTE,
              "upstream": {"variableId": "ALLSKY_SFC_SW_DWN", "geometryId": "sl"}}
    return source, request, area


def test_monthly_regional_solar_prefers_the_finer_grid_at_acquisition(tmp_path, monkeypatch):
    source, request, _ = example()
    data = tmp_path / "fixture.nc"
    with Dataset(data, "w") as grid:
        for name, count in (("valid_time", 1), ("latitude", 2), ("longitude", 2)):
            grid.createDimension(name, count)
        time = grid.createVariable("valid_time", "i4", ("valid_time",))
        time.units = "days since 2000-01-01"
        time[:] = [0]
        grid.createVariable("latitude", "f8", ("latitude",))[:] = [-33.2, -33.3]
        grid.createVariable("longitude", "f8", ("longitude",))[:] = [-66.3, -66.2]
        ssrd = grid.createVariable("ssrd", "f4", ("valid_time", "latitude", "longitude"))
        ssrd.units = "J m**-2"
        ssrd[:] = 100 * 86_400
    path = tmp_path / "monthly.zip"
    with ZipFile(path, "w") as archive:
        archive.write(data, "2000.nc")
    monkeypatch.setattr(era5_land_monthly, "archive_for", lambda *args: path)
    monkeypatch.setattr(spatial_resolution, "cds_configured", lambda: True)
    result = spatial_resolution.with_best_spatial_resolution(
        source, request, date(2000, 1, 1), date(2000, 1, 31),
        lambda: pytest.fail("The coarse product should not be called"),
    )
    assert result["id"] == source["id"]
    assert result["unit"] == "W/m²"
    assert result["points"][0]["value"] == pytest.approx(100)
    assert len(result["map"]["events"]) == 4
    assert result["sourceSelection"] == "ERA5-Land mensual · 0,1° × 0,1°"


def test_reports_unconfigured_cds_before_using_power(monkeypatch):
    source, request, _ = example()
    monkeypatch.setattr(spatial_resolution, "cds_configured", lambda: False)
    result = spatial_resolution.with_best_spatial_resolution(
        source, request, date(2000, 1, 1), date(2000, 1, 31), lambda: {"provider": "NASA POWER"}
    )
    assert result["sourceSelection"] == "NASA POWER · 1° × 1°"
    assert "CDSAPI_KEY" in result["mapMessage"]


def test_precipitation_prefers_pmra_only_if_every_month_and_the_area_are_covered(monkeypatch):
    _, _, area = example()
    source = {"access": CHIRPS_ROUTE}
    monkeypatch.setattr(spatial_resolution, "argentina_selection", lambda geometry: True)
    monkeypatch.setattr(spatial_resolution, "monthly_assets", lambda route: {"2000-01": "file"})
    assert spatial_resolution.precipitation_candidate(source, area, ["2000-01"])[0]["access"] == PMRA_ROUTE
    assert spatial_resolution.precipitation_candidate(source, area, ["2000-01", "2000-02"]) is None
    monkeypatch.setattr(spatial_resolution, "argentina_selection", lambda geometry: False)
    assert spatial_resolution.precipitation_candidate(source, area, ["2000-01"]) is None




def test_grid_keeps_more_native_cells_per_short_map_series():
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    from .grid_layers import MAX_DISPLAY_CELLS, monthly_map_cell_limit
    from .precipitation import read_grid

    area = {"type": "Polygon", "coordinates": [[
        [-67, -34], [-64.5, -34], [-64.5, -31.5], [-67, -31.5], [-67, -34]
    ]]}
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=50, height=50, count=1, dtype="float32",
                         crs="EPSG:4326", transform=from_origin(-67, -31.5, .05, .05)) as dataset:
            dataset.write(np.arange(2500, dtype=np.float32).reshape(50, 50), 1)
            before, coarse = read_grid(dataset, area, True, cell_limit=MAX_DISPLAY_CELLS)
            after, native = read_grid(dataset, area, True, cell_limit=monthly_map_cell_limit(12))
    assert len(native) == 2500 > len(coarse)
    assert before == pytest.approx(after)


def test_era5_failure_is_reported_before_coarse_fallback(monkeypatch):
    source, request, _ = example()
    monkeypatch.setattr(spatial_resolution, "cds_configured", lambda: True)

    def failed(*args):
        raise ValueError("ERA5-Land no devolvió todos los meses.")

    monkeypatch.setattr(spatial_resolution, "fetch_era5_land", failed)
    result = spatial_resolution.with_best_spatial_resolution(
        source, request, date(2000, 1, 1), date(2000, 1, 31), lambda: {"provider": "NASA POWER"},
    )
    assert result["provider"] == "NASA POWER"
    assert "no devolvió todos los meses" in result["mapMessage"]



def test_pmra_partial_result_uses_chirps_for_the_whole_period(monkeypatch):
    source, request, _ = example()
    source["access"] = PMRA_ROUTE
    source["upstream"]["variableId"] = "precipitation"
    monkeypatch.setattr(spatial_resolution, "argentina_selection", lambda area: True)
    monkeypatch.setattr(spatial_resolution, "monthly_assets", lambda route: {"2000-01": "file", "2000-02": "file"})

    def rainfall(alternative, *_args):
        assert alternative["access"] == CHIRPS_ROUTE
        return {"provider": "UCSB Climate Hazards Center", "points": [{"value": 10}, {"value": 13}]}

    monkeypatch.setattr(spatial_resolution, "fetch_precipitation", rainfall)
    result = spatial_resolution.with_best_spatial_resolution(
        source, request, date(2000, 1, 1), date(2000, 2, 29),
        lambda: {"provider": "PMRAv1", "points": [{"value": 10}, {"value": None}]},
    )
    assert result["sourceSelection"].startswith("CHIRPS")
    assert "PMRA" in result["mapMessage"]
