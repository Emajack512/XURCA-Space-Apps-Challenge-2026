"""Grid analyses on (time, lat, lon) arrays. Version 1.0.0-candidate.

Conventions (same as `raster/contract.py`): lats/lons ascending cell centers, NaN = no data
(never filled or interpolated), `mask` (lat, lon) True = inside the requested area.
Every function works cell by cell on the provider's native grid: no regridding.
"""
from __future__ import annotations

import numpy as np

from ..numeric import integer, scalar
from ..stats.multiple_testing import fdr_bh
from ..stats.trends import mann_kendall, sen_slope
from ..signal.convolution2d import convolve2d

VERSION = '1.0.0-candidate'


def _months(times) -> np.ndarray:
    return np.array([int(str(t)[5:7]) for t in times], dtype=int)


def _years(times) -> np.ndarray:
    """Decimal years from ISO dates (mid-month not assumed: the date as given)."""
    out = []
    for t in times:
        y, m, d = (int(part) for part in str(t)[:10].split('-'))
        out.append(y + (m - 1) / 12 + (d - 1) / 365.25)
    return np.asarray(out, dtype=float)


def monthly_anomalies(values: np.ndarray, times, *, min_count: int = 3) -> tuple:
    """Per cell, subtract the mean of each calendar month (all years). Returns (anomalies, months_ok mask).

    A cell-month with fewer than `min_count` finite values gets NaN anomalies for that month.
    """
    months = _months(times)
    anomalies = np.full(values.shape, np.nan)
    for month in range(1, 13):
        rows = months == month
        if not rows.any():
            continue
        block = values[rows]
        count = np.isfinite(block).sum(axis=0)
        with np.errstate(invalid='ignore'):
            mean = np.where(count >= min_count, np.nansum(block, axis=0) / np.maximum(count, 1), np.nan)
        anomalies[rows] = block - mean
    return anomalies


def grid_trends(times, values, mask, *, cadence: str, alpha: float = 0.05, min_points: int = 10,
                min_count: int = 3) -> dict:
    """Sen slope + Mann-Kendall per in-mask cell, with Benjamini-Hochberg FDR across the tested cells.

    Monthly grids are deseasonalized per cell (monthly anomalies) before both tests, so the
    annual cycle neither biases Sen's slope nor inflates MK. Slopes are reported per decade.
    """
    if cadence != 'monthly':
        raise ValueError('Grid trends need a monthly grid (daily grids: aggregate first or use a longer period)')
    v = np.asarray(values, dtype=float)
    m = np.asarray(mask, dtype=bool)
    level = scalar(alpha, 'alpha')
    needed = integer(min_points, 'min_points', 3)
    series = monthly_anomalies(v, times, min_count=min_count)
    t = _years(times)
    n_lat, n_lon = m.shape
    slope = np.full((n_lat, n_lon), np.nan)
    p_value = np.full((n_lat, n_lon), np.nan)
    n_obs = np.zeros((n_lat, n_lon), dtype=int)
    for i in range(n_lat):
        for j in range(n_lon):
            if not m[i, j]:
                continue
            y = series[:, i, j]
            ok = np.isfinite(y)
            n_obs[i, j] = int(ok.sum())
            if n_obs[i, j] < needed or np.ptp(y[ok]) == 0:
                continue
            slope[i, j] = sen_slope(t[ok], y[ok])['slope'] * 10
            p_value[i, j] = mann_kendall(t[ok], y[ok])['p_value']
    tested = np.isfinite(p_value)
    q_value = np.full_like(p_value, np.nan)
    significant = np.zeros((n_lat, n_lon), dtype=bool)
    if tested.any():
        result = fdr_bh(p_value[tested], alpha=level)
        q_value[tested] = result['q_values']
        significant[tested] = result['rejected']
    return {'slope_per_decade': slope, 'p_value': p_value, 'q_value': q_value, 'significant_fdr': significant,
            'n_obs': n_obs, 'n_tested': int(tested.sum()), 'n_significant_fdr': int(significant.sum()),
            'n_positive': int((slope[tested] > 0).sum()), 'n_negative': int((slope[tested] < 0).sum()),
            'alpha': level, 'uncertainty': 'not_estimated',
            'warnings': ['Per-cell tests assume serial independence; neighbouring cells are spatially correlated, '
                         'so the false discovery control is approximate.',
                         'Cells with fewer valid months than min_points are not tested (shown as no data).']}


def grid_anomaly(times, values, mask, *, base_start: str, base_end: str, period_start: str, period_end: str,
                 min_count: int = 3) -> dict:
    """Mean anomaly of a period against the per-cell monthly climatology of a base period (monthly grids)."""
    v = np.asarray(values, dtype=float)
    m = np.asarray(mask, dtype=bool)
    stamps = np.array([str(t)[:10] for t in times])
    base = (stamps >= base_start) & (stamps <= base_end)
    period = (stamps >= period_start) & (stamps <= period_end)
    if not period.any():
        raise ValueError('The requested period has no time slices in the grid')
    if not base.any():
        raise ValueError('The base period has no time slices in the grid')
    months = _months(times)
    anomalies = np.full((int(period.sum()),) + v.shape[1:], np.nan)
    missing_months = []
    for k, index in enumerate(np.flatnonzero(period)):
        month = months[index]
        reference = v[base & (months == month)]
        count = np.isfinite(reference).sum(axis=0)
        if (count < min_count).all():
            missing_months.append(int(month))
        with np.errstate(invalid='ignore'):
            climatology = np.where(count >= min_count, np.nansum(reference, axis=0) / np.maximum(count, 1), np.nan)
        anomalies[k] = v[index] - climatology
    finite = np.isfinite(anomalies)
    count = finite.sum(axis=0)
    with np.errstate(invalid='ignore'):
        mean = np.where(count > 0, np.nansum(anomalies, axis=0) / np.maximum(count, 1), np.nan)
    mean[~m] = np.nan
    warnings = ['Anomaly against the per-cell monthly mean of the base period; base suitability is caller-defined.']
    if missing_months:
        warnings.append(f'Months without enough base years (min_count={min_count}): {sorted(set(missing_months))}.')
    return {'anomaly': mean, 'n_slices': count, 'n_period_slices': int(period.sum()),
            'n_base_slices': int(base.sum()), 'uncertainty': 'not_estimated', 'warnings': warnings}


def area_mean(values, lats, mask) -> dict:
    """cos(latitude)-weighted mean of the finite in-mask cells, per time slice, with coverage.

    It is a mean over grid cells whose centers fall inside the area (not an exact zonal mean:
    partially covered cells count fully).
    """
    v = np.asarray(values, dtype=float)
    m = np.asarray(mask, dtype=bool)
    weights = np.cos(np.deg2rad(np.asarray(lats, dtype=float)))[:, None] * np.ones(m.shape)
    weights = np.where(m, weights, 0.0)
    finite = np.isfinite(v) & m[None]
    w = np.where(finite, weights[None], 0.0)
    total = w.sum(axis=(1, 2))
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = np.where(total > 0, np.nansum(np.where(finite, v, 0.0) * w, axis=(1, 2)) / total, np.nan)
    inside = max(int(m.sum()), 1)
    coverage = finite.sum(axis=(1, 2)) / inside
    return {'mean': mean, 'coverage_fraction': coverage, 'n_cells_inside': int(m.sum()), 'uncertainty': 'not_estimated',
            'warnings': ['Mean of grid cells whose centers are inside the area (cos-latitude weights); '
                         'partially covered cells count fully.']}


FWI_STARTUP = {'ffmc': 85.0, 'dmc': 6.0, 'dc': 15.0}   # Van Wagner (1987) standard start-up values


def grid_fwi(times, temperature, humidity, wind_kmh, precipitation, lats, mask, *, initial_state=None) -> dict:
    """Canadian FWI system per in-mask cell from DAILY grids (fire/fwi.py, verified against xclim).

    Cells with any missing day are skipped (the moisture codes carry memory: a gap cannot be bridged
    without inventing weather). Each cell uses its own latitude for the day-length factors.
    """
    from ..fire.fwi import fire_weather_index
    t, h, w, p = (np.asarray(a, dtype=float) for a in (temperature, humidity, wind_kmh, precipitation))
    m = np.asarray(mask, dtype=bool)
    if not (t.shape == h.shape == w.shape == p.shape) or t.shape[1:] != m.shape:
        raise ValueError('The four daily grids must share the same (time, lat, lon) shape')
    months = _months(times)
    state = dict(initial_state or FWI_STARTUP)
    fwi = np.full(t.shape, np.nan)
    skipped = 0
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if not m[i, j]:
                continue
            cell = [a[:, i, j] for a in (t, h, w, p)]
            if not all(np.isfinite(c).all() for c in cell):
                skipped += 1
                continue
            result = fire_weather_index(cell[0], np.clip(cell[1], 0, 100), cell[2], cell[3], months,
                                        latitude=float(lats[i]), initial_state=state)
            fwi[:, i, j] = result['fwi']
    return {'fwi': fwi, 'n_skipped_cells': skipped, 'initial_state': state, 'uncertainty': 'not_estimated',
            'warnings': ['FWI is defined with local-noon weather; daily mean temperature and humidity, daily '
                         'maximum wind and 24 h precipitation are used as an approximation.',
                         'Moisture codes start from standard start-up values: discard the first weeks (spin-up).',
                         'Relative meteorological danger only: not ignition probability, location or burned area.']}


def smooth_slices(values, mask, *, size: int = 3, boundary: str = 'reflect') -> dict:
    """Box smoothing (size x size, weights 1/size^2) of each time slice with `convolve2d`.

    A slice with ANY missing cell is not smoothed (NaN output) because filling gaps would invent
    data; only cells whose full kernel footprint lies inside the grid are kept.
    """
    v = np.asarray(values, dtype=float)
    m = np.asarray(mask, dtype=bool)
    side = integer(size, 'size', 3)
    if side % 2 == 0:
        raise ValueError('size must be odd')
    kernel = np.full((side, side), 1.0 / side ** 2)
    out = np.full(v.shape, np.nan)
    skipped = 0
    valid = None
    for k in range(v.shape[0]):
        if not np.isfinite(v[k]).all():
            skipped += 1
            continue
        result = convolve2d(v[k], kernel, boundary=boundary)
        valid = result['valid']
        out[k] = np.where(valid & m, result['values'], np.nan)
    warnings = ['Box smoothing of cell values (no area weighting); border cells without a full kernel are dropped.']
    if skipped:
        warnings.append(f'{skipped} time slice(s) had missing cells and were not smoothed (gaps are never filled).')
    return {'values': out, 'n_skipped_slices': skipped, 'kernel_size': side, 'boundary': boundary,
            'uncertainty': 'not_estimated', 'warnings': warnings}
