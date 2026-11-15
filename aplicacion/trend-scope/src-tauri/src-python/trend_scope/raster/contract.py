"""Frozen contract between the grid connectors (Codex de Ema) and the grid analyses (Claude).

DO NOT CHANGE THIS FILE without agreement between both agents (see raster/AGENTS.md).
Connectors PRODUCE `GridField`; handlers CONSUME it. Nothing here downloads or computes science.

Conventions (all mandatory):
  * `lats` ascending (south -> north), `lons` ascending (west -> east), both cell CENTERS in degrees WGS 84.
  * `values` has shape (time, lat, lon), float64. Missing / cloud / out-of-coverage = NaN. NEVER 0.
  * No interpolation, regridding, gap filling or unit conversion inside a connector. If the provider
    delivers a rate (e.g. mm/day) the unit says so; it is not turned into an accumulation.
  * `mask` (lat, lon) is True for cells whose center lies inside the requested polygon (all True for a bbox).
  * `times` are the validity instants of each slice: ISO dates ("YYYY-MM-DD"; monthly = first day of month).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

CADENCES = ("daily", "monthly")
KINDS = ("reanalysis", "satellite", "model", "station_interpolated", "observed")
MAX_CELLS_DEFAULT = 2500          # lat x lon cells per request (provisional; protects memory and the provider)
MAX_VALUES_DEFAULT = 2_000_000    # time x lat x lon values per request (provisional)


@dataclass(frozen=True)
class GridRequest:
    provider: str                   # connector id, e.g. "nasa.power.regional.monthly"
    variable_id: str                # provider variable code, e.g. "T2M", "PRECTOTCORR", "temperature_2m_mean"
    start: str                      # ISO date, inclusive
    end: str                        # ISO date, inclusive
    cadence: str                    # one of CADENCES
    bbox: tuple                     # (west, south, east, north) in degrees; always given
    polygon: Optional[dict] = None  # GeoJSON Polygon/MultiPolygon geometry; None = the bbox itself
    max_cells: int = MAX_CELLS_DEFAULT
    max_values: int = MAX_VALUES_DEFAULT

    def validate(self) -> None:
        if self.cadence not in CADENCES:
            raise ValueError(f"cadence must be one of {CADENCES}")
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox must be (west, south, east, north) with west < east and south < north")
        if self.start > self.end:
            raise ValueError("start must not be after end")


@dataclass
class GridField:
    provider: str
    product: str                    # human product name, e.g. "NASA POWER MERRA-2 (monthly)"
    kind: str                       # one of KINDS
    variable_id: str
    variable_name: str              # unambiguous name, e.g. "Temperatura del aire a 2 m"
    unit: str                       # e.g. "C", "mm/day", "mm", "m/s", "%"
    cadence: str                    # one of CADENCES
    times: list                     # ISO dates, one per slice
    lats: np.ndarray                # (n_lat,) ascending cell centers
    lons: np.ndarray                # (n_lon,) ascending cell centers
    values: np.ndarray              # (n_time, n_lat, n_lon) float64, NaN = no data
    mask: np.ndarray                # (n_lat, n_lon) bool, True = inside the requested area
    native_resolution_deg: tuple    # (dlat, dlon) of the PROVIDER grid, not of the request
    urls: list                      # every request URL used (provenance)
    retrieved_at: str               # ISO datetime UTC
    aggregation: str = "native"     # what the provider value represents, e.g. "monthly mean of daily values"
    depth_range: Optional[str] = None   # e.g. "0-7 cm" for soil layers (ingeniera, spec B3/E2)
    sensor: Optional[str] = None        # satellite sensor and overpass if any (spec B2)
    warnings: list = field(default_factory=list)

    def validate(self) -> "GridField":
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if self.cadence not in CADENCES:
            raise ValueError(f"cadence must be one of {CADENCES}")
        if not self.unit or not self.variable_name:
            raise ValueError("unit and variable_name are mandatory")
        self.lats = np.asarray(self.lats, dtype=np.float64)
        self.lons = np.asarray(self.lons, dtype=np.float64)
        self.values = np.asarray(self.values, dtype=np.float64)
        self.mask = np.asarray(self.mask, dtype=bool)
        n_time, n_lat, n_lon = len(self.times), self.lats.size, self.lons.size
        if self.values.shape != (n_time, n_lat, n_lon):
            raise ValueError(f"values must have shape (time, lat, lon) = {(n_time, n_lat, n_lon)}, got {self.values.shape}")
        if self.mask.shape != (n_lat, n_lon):
            raise ValueError("mask must have shape (lat, lon)")
        if n_time == 0 or n_lat == 0 or n_lon == 0:
            raise ValueError("empty grid")
        if np.any(np.diff(self.lats) <= 0) or np.any(np.diff(self.lons) <= 0):
            raise ValueError("lats and lons must be strictly ascending")
        if np.isinf(self.values).any():
            raise ValueError("values must not contain infinities; use NaN for missing data")
        if list(self.times) != sorted(self.times) or len(set(self.times)) != len(self.times):
            raise ValueError("times must be strictly increasing")
        if not self.urls:
            raise ValueError("urls (provenance) are mandatory")
        return self

    def coverage_fraction(self) -> np.ndarray:
        """Per time slice: share of in-mask cells with a finite value."""
        inside = self.mask.sum()
        if inside == 0:
            return np.zeros(len(self.times))
        return np.isfinite(self.values[:, self.mask]).sum(axis=1) / inside
