"""W10: ETCCDI-style indices from regular daily series.

Inputs: a regular daily series in chronological order and `groups`, one
integer label per day (the year). Each index is reported separately and per
group; they are not combined. Daily precipitation in mm, no missing values.
Definitions follow the ETCCDI index descriptions (Zhang et al., 2011); the
wet-day threshold is an explicit argument (the standard value is 1 mm).
"""
import numpy as np

from ..numeric import array, finite, integer, scalar, temporal

VERSION = '1.0.0-candidate'


def _prepare(values, groups, *, precipitation=True):
    y = array(values, 'values')
    labels = np.asarray(groups)
    if labels.shape != y.shape or labels.dtype.kind not in 'iu':
        raise ValueError('groups must be one integer year label per day')
    if precipitation and np.any(y < 0):
        raise ValueError('precipitation must be nonnegative')
    return y, labels, np.unique(labels)


def _result(ids, output, valid=None, **extra):
    finite(output[~np.isnan(output)])
    return {'group_ids': ids, 'values': output,
            'valid': np.ones(len(ids), dtype=bool) if valid is None else valid,
            'uncertainty': 'not_estimated',
            'warnings': ['Index computed per group from daily data; no missing days are tolerated.'], **extra}


def rx1day(values, groups) -> dict:
    """Maximum 1-day precipitation per year (mm)."""
    y, labels, ids = _prepare(values, groups)
    return _result(ids, np.array([y[labels == g].max() for g in ids]))


def rx5day(values, groups) -> dict:
    """Maximum 5-consecutive-day precipitation total per year (mm), windows inside the year."""
    y, labels, ids = _prepare(values, groups)
    output = np.full(len(ids), np.nan)
    for position, g in enumerate(ids):
        sample = y[labels == g]
        if sample.size >= 5:
            output[position] = np.convolve(sample, np.ones(5), mode='valid').max()
    valid = ~np.isnan(output)
    return _result(ids, output, valid)


def sdii(values, groups, *, wet_threshold) -> dict:
    """Simple daily intensity index: mean precipitation on wet days (>= threshold), mm/day."""
    y, labels, ids = _prepare(values, groups)
    limit = scalar(wet_threshold, 'wet_threshold', True)
    output = np.full(len(ids), np.nan)
    for position, g in enumerate(ids):
        wet = y[(labels == g) & (y >= limit)]
        if wet.size:
            output[position] = wet.mean()
    return _result(ids, output, ~np.isnan(output))


def cdd(values, groups, *, wet_threshold) -> dict:
    """Maximum number of consecutive dry days (< threshold) per year."""
    y, labels, ids = _prepare(values, groups)
    limit = scalar(wet_threshold, 'wet_threshold', True)
    output = np.zeros(len(ids))
    for position, g in enumerate(ids):
        best = run = 0
        for dry in (y[labels == g] < limit):
            run = run + 1 if dry else 0
            best = max(best, run)
        output[position] = best
    return _result(ids, output)


def r95ptot(values, groups, baseline, *, wet_threshold, percentile=95.0) -> dict:
    """Total precipitation on days above the base-period percentile of wet days (mm).

    The threshold is the `percentile` of wet-day amounts (>= wet_threshold)
    computed ONLY on days where the boolean `baseline` mask is true.
    """
    y, labels, ids = _prepare(values, groups)
    limit = scalar(wet_threshold, 'wet_threshold', True)
    q = scalar(percentile, 'percentile', True)
    mask = np.asarray(baseline)
    if mask.shape != y.shape or mask.dtype != np.bool_:
        raise ValueError('baseline must be a boolean mask with one entry per day')
    reference = y[mask & (y >= limit)]
    if reference.size < 2:
        raise ValueError('The baseline has too few wet days to estimate the percentile')
    threshold = float(np.percentile(reference, q))
    output = np.array([y[(labels == g) & (y > threshold)].sum() for g in ids])
    return _result(ids, output, threshold=threshold, n_reference_wet_days=int(reference.size))


def warm_spell_days(values, thresholds, groups, *, min_duration) -> dict:
    """Days per year inside spells of >= min_duration consecutive days above `thresholds`.

    `thresholds` is an array with one (e.g. calendar-day percentile) threshold
    per day, calculated by the caller on a base period.
    """
    y, labels, ids = _prepare(values, groups, precipitation=False)
    limit = array(thresholds, 'thresholds')
    if limit.shape != y.shape:
        raise ValueError('thresholds must have one entry per day')
    needed = integer(min_duration, 'min_duration')
    output = np.zeros(len(ids))
    for position, g in enumerate(ids):
        hot = y[labels == g] > limit[labels == g]
        run = 0
        for flag in np.append(hot, False):
            if flag:
                run += 1
            else:
                if run >= needed:
                    output[position] += run
                run = 0
    return _result(ids, output)


def analyze_etccdi(method, data, request):
    """Registry adapter for rx1day, rx5day, sdii, cdd and r95ptot (one method each).

    `groups` is a dataset variable ID (unit 1) holding the calendar year of each
    day; r95ptot also takes `baseline` (0/1). The series must be regular daily
    precipitation depth with complete years: the caller (handler) keeps only
    complete years. `wet_threshold` is required by sdii, cdd and r95ptot.
    """
    from ..contracts import AnalysisResult
    from .events import _auxiliary

    variable = data.variables[request.variable]
    if data.time is None or (variable.invalid is not None and variable.invalid.any()):
        raise ValueError('Explicit time coordinates and unmasked observations are required')
    t, y = temporal(data.time.values, variable.values, regular=True, minimum=365)
    parameters = dict(request.parameters)
    names = ('groups', 'baseline') if method == 'r95ptot' else ('groups',)
    selected = _auxiliary(data, parameters, names)
    groups = selected['groups']
    if method in ('sdii', 'cdd', 'r95ptot') and 'wet_threshold' not in parameters:
        raise ValueError('Specify wet_threshold explicitly')
    if method == 'rx1day':
        payload = rx1day(y, groups)
    elif method == 'rx5day':
        payload = rx5day(y, groups)
    elif method == 'sdii':
        payload = sdii(y, groups, wet_threshold=parameters['wet_threshold'])
    elif method == 'cdd':
        payload = cdd(y, groups, wet_threshold=parameters['wet_threshold'])
    else:
        if not np.isin(selected['baseline'], [0, 1]).all():
            raise ValueError('baseline variable must encode False/True as 0/1')
        extra = {'percentile': parameters['percentile']} if 'percentile' in parameters else {}
        payload = r95ptot(y, groups, selected['baseline'].astype(bool),
                          wet_threshold=parameters['wet_threshold'], **extra)
    unit = 'days' if method == 'cdd' else variable.unit
    units = {'group_ids': '1', 'values': unit, 'valid': '1'}
    if method == 'r95ptot':
        units.update(threshold=variable.unit, n_reference_wet_days='1')
    return AnalysisResult(
        request.analysis_id, method, VERSION, data.dataset_id, request.variable, 'completed', 'index',
        dict(request.parameters), payload, units, tuple(payload['warnings']), data.provenance,
        {'n_observations': len(t), 'time_start': t[0], 'time_end': t[-1], 'time_origin': data.time.origin,
         'time_unit': data.time.unit, 'calendar': data.time.calendar, 'value_unit': variable.unit,
         'quality': data.quality}, data.transformations, uncertainty=payload['uncertainty'])
