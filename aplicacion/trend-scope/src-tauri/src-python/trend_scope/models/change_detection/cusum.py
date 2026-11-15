"""Two-sided tabular CUSUM with explicit physical baseline and thresholds."""
import numpy as np
from numba import njit
from ..numeric import array, finite, scalar


@njit(cache=True)
def _cusum(y, baseline, allowance, threshold):
    high = np.zeros(len(y))
    low = np.zeros(len(y))
    events = np.zeros(len(y), dtype=np.int8)
    upper = lower = 0.
    for i in range(len(y)):
        delta = y[i]-baseline
        upper = max(0., upper+delta-allowance)
        lower = max(0., lower-delta-allowance)
        high[i], low[i] = upper, lower
        if upper > threshold:
            events[i] = 1
            upper = lower = 0.
        elif lower > threshold:
            events[i] = -1
            upper = lower = 0.
    return high, low, events


def cusum(values, *, baseline: float, allowance: float, threshold: float) -> dict:
    """Reset both accumulators after a crossing; detection time is not onset time."""
    y = array(values, 'values')
    baseline = scalar(baseline, 'baseline')
    allowance = scalar(allowance, 'allowance')
    threshold = scalar(threshold, 'threshold', positive=True)
    if allowance < 0:
        raise ValueError('allowance must be nonnegative')
    high, low, events = _cusum(y, baseline, allowance, threshold)
    finite(high); finite(low)
    return {'upper': high, 'lower': low, 'event_indices': np.flatnonzero(events),
            'event_directions': events[events != 0],
            'warnings': ['Thresholds require domain calibration; crossings are not certified emergency alerts.',
                         'Baseline must be specified without using future evaluation data.']}


VERSION = '1.0.0-candidate'


def cusum_reference(times, values, reference, *, k: float = 0.5, h: float = 5.0, min_reference: int = 24) -> dict:
    """Tabular CUSUM in units of the reference period's standard deviation.

    mu0 and sigma0 come only from observations where `reference` is True; the series is
    standardized z = (y - mu0) / sigma0 and `cusum` runs with allowance k and threshold h
    (Montgomery, Introduction to Statistical Quality Control: k = 0.5 detects a 1-sigma shift,
    h = 5 gives an in-control average run length of about 465 independent observations).
    """
    from ..numeric import integer, temporal
    t, y = temporal(times, values, regular=True)
    mask = np.asarray(reference, dtype=bool)
    if mask.shape != y.shape:
        raise ValueError('reference must have one flag per observation')
    needed = integer(min_reference, 'min_reference', 2)
    if mask.sum() < needed:
        raise ValueError(f'The reference period has {int(mask.sum())} observations; at least {needed} are needed')
    k = scalar(k, 'k')
    h = scalar(h, 'h', positive=True)
    if k < 0:
        raise ValueError('k must be nonnegative')
    mu0 = float(np.mean(y[mask]))
    sigma0 = float(np.std(y[mask], ddof=1))
    if not np.isfinite(sigma0) or sigma0 <= 0:
        raise ValueError('The reference period has no variability: CUSUM cannot be standardized')
    output = cusum((y - mu0) / sigma0, baseline=0.0, allowance=k, threshold=h)
    output['event_times'] = t[output['event_indices']]
    output.update({'reference_mean': mu0, 'reference_std': sigma0, 'k': k, 'h': h,
                   'n_reference': int(mask.sum()), 'units_of_upper_lower': 'reference standard deviations'})
    output['warnings'] = list(output['warnings']) + [
        'CUSUM assumes independent observations; autocorrelation (common in monthly anomalies) raises false alarms.',
        'An alarm marks when the accumulated departure from the reference crossed h, not when the change began.']
    return output


def analyze_cusum_reference(data, request):
    """Registry adapter: `baseline` is a dataset variable ID coded 0/1 (the reference period)."""
    from ..contracts import AnalysisResult

    variable = data.variables[request.variable]
    if data.time is None or (variable.invalid is not None and variable.invalid.any()):
        raise ValueError('Explicit time coordinates and unmasked observations are required')
    parameters = dict(request.parameters)
    identifier = parameters.pop('baseline', None)
    if not isinstance(identifier, str) or identifier not in data.variables:
        raise ValueError('Specify baseline as a dataset variable ID')
    flags = np.asarray(data.variables[identifier].values)
    if not np.isin(flags, [0, 1]).all():
        raise ValueError('baseline variable must encode False/True as 0/1')
    payload = cusum_reference(data.time.values, variable.values, flags.astype(bool), **parameters)
    unit = variable.unit
    units = {'upper': '1', 'lower': '1', 'event_indices': '1', 'event_directions': '1', 'event_times': data.time.unit,
             'reference_mean': unit, 'reference_std': unit, 'k': '1', 'h': '1', 'n_reference': '1'}
    return AnalysisResult(
        request.analysis_id, 'cusum_reference', VERSION, data.dataset_id, request.variable, 'completed', 'events',
        dict(request.parameters), payload, units, tuple(payload['warnings']), data.provenance,
        {'n_observations': len(data.time.values), 'time_start': data.time.values[0], 'time_end': data.time.values[-1],
         'time_origin': data.time.origin, 'time_unit': data.time.unit, 'calendar': data.time.calendar,
         'value_unit': unit, 'quality': data.quality},
        data.transformations, uncertainty='not_estimated')
