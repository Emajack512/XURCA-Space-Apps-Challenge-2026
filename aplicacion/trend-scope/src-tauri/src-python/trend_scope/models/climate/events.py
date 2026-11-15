"""W04: percentile thresholds, threshold-exceedance events and event composites.

An event is not a trend and not an anomaly: the three are different results
and are never merged. Thresholds are computed only from the baseline period.
"""
import numpy as np

from ..numeric import array, finite, integer, scalar, temporal

VERSION = '1.0.0-candidate'


def _labels(groups, shape) -> np.ndarray:
    if np.ma.isMaskedArray(groups):
        raise ValueError('groups must not be masked')
    labels = np.asarray(groups)
    if labels.shape != shape or labels.dtype.kind not in 'iu':
        raise ValueError('groups must contain one integer label per observation')
    return labels


def percentile_thresholds(values, groups, baseline, *, q, min_count) -> dict:
    """Per-group q-quantile of the baseline observations only (linear interpolation).

    `q` (strictly between 0 and 1) and `min_count` are explicit: the research
    does not fix them. `groups` are integer labels (e.g. calendar month); each
    group needs at least `min_count` baseline observations or ValueError names
    it. Observations outside `baseline` never influence the result. The
    threshold keeps the unit of the variable. The caller decides whether the
    baseline is adequate. O(n log n) time, O(n) memory.
    """
    y = array(values, 'values')
    labels = _labels(groups, y.shape)
    level = scalar(q, 'q')
    if not 0 < level < 1:
        raise ValueError('q must be strictly between 0 and 1')
    minimum = integer(min_count, 'min_count')
    if np.ma.isMaskedArray(baseline):
        raise ValueError('baseline must not be masked')
    mask = np.asarray(baseline)
    if mask.shape != y.shape or mask.dtype.kind != 'b':
        raise ValueError('baseline must be a boolean mask matching values')
    ids = np.unique(labels)
    thresholds, counts = np.empty(len(ids)), np.empty(len(ids), dtype=np.int64)
    for i, label in enumerate(ids):
        sample = y[mask & (labels == label)]
        if len(sample) < minimum:
            raise ValueError(f'Group {label} has fewer than min_count={minimum} baseline observations')
        thresholds[i], counts[i] = np.quantile(sample, level), len(sample)
    finite(thresholds, 'thresholds')
    return {'group_ids': ids, 'thresholds': thresholds, 'count': counts, 'q': level,
            'uncertainty': 'not_estimated',
            'warnings': ['Baseline suitability is caller-defined; thresholds carry sampling uncertainty that is not estimated.']}


def expand_thresholds(groups, reference) -> np.ndarray:
    """One threshold per observation, looked up by group label in `reference`."""
    labels = np.asarray(groups)
    if labels.ndim != 1 or labels.dtype.kind not in 'iu':
        raise ValueError('groups must contain one integer label per observation')
    ids, thresholds = np.asarray(reference['group_ids']), np.asarray(reference['thresholds'])
    position = np.searchsorted(ids, labels)
    if np.any(position >= len(ids)) or np.any(ids[np.minimum(position, len(ids) - 1)] != labels):
        raise ValueError('A group has no threshold in the reference')
    return thresholds[position]


def detect_events(times, values, thresholds, *, direction, min_duration) -> dict:
    """Maximal runs of consecutive steps beyond the threshold, at least `min_duration` long.

    `direction` is 'above' (value > threshold) or 'below' (value < threshold);
    equality is not an exceedance. `thresholds` has one value per observation.
    `min_duration` (in steps) is explicit: the research does not fix it. Start
    and end indices are inclusive; durations count steps; `peak_values` is the
    maximum ('above') or minimum ('below') inside the event; `mean_exceedance`
    is the mean distance beyond the threshold, always >= 0 and in the unit of
    the variable. The series must be regular and complete: a gap would merge or
    split events. An event is a threshold crossing, not a trend or a
    statistically tested anomaly. O(n).
    """
    t, y = temporal(times, values, regular=True)
    limit = array(thresholds, 'thresholds')
    if limit.shape != y.shape:
        raise ValueError('thresholds must have one value per observation')
    if direction not in ('above', 'below'):
        raise ValueError("direction must be 'above' or 'below'")
    minimum = integer(min_duration, 'min_duration')
    sign = 1.0 if direction == 'above' else -1.0
    with np.errstate(over='raise', invalid='raise'):
        excess = sign * (y - limit)
    finite(excess)
    beyond = excess > 0
    edges = np.diff(np.concatenate(([0], beyond.astype(np.int8), [0])))
    starts, stops = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
    keep = (stops - starts + 1) >= minimum
    starts, stops = starts[keep], stops[keep]
    peaks, peak_at, mean_excess = [], [], []
    for a, b in zip(starts, stops):
        window = excess[a:b + 1]
        offset = int(np.argmax(window))
        peak_at.append(a + offset)
        peaks.append(float(y[a + offset]))
        mean_excess.append(float(window.mean()))
    return {'start_indices': starts.astype(np.int64), 'end_indices': stops.astype(np.int64),
            'start_times': t[starts], 'end_times': t[stops], 'durations': (stops - starts + 1).astype(np.int64),
            'peak_values': np.asarray(peaks), 'peak_indices': np.asarray(peak_at, dtype=np.int64),
            'mean_exceedance': np.asarray(mean_excess), 'n_events': int(len(starts)),
            'exceedance_fraction': float(beyond.mean()), 'direction': direction, 'min_duration': minimum,
            'uncertainty': 'not_estimated',
            'warnings': ['An event is a threshold crossing, not a trend or a tested anomaly.',
                         'Events shorter than min_duration are discarded, not merged.']}


def event_composite(times, response, event_indices, *, before, after) -> dict:
    """Mean of `response` at each offset from -before to +after around the events.

    `event_indices` are positions in the series (for example the start indices
    of `detect_events`). Offsets that fall outside the series are skipped for
    that event, so `n` can differ between offsets and is reported per offset.
    The result describes the sample of events given; it has no significance
    test and does not show that the events caused the response. Offsets are in
    steps of a regular grid. O(events x window).
    """
    t, y = temporal(times, response, regular=True)
    low, high = integer(before, 'before', 0), integer(after, 'after', 0)
    positions = np.asarray(event_indices)
    if positions.ndim != 1 or positions.size == 0 or positions.dtype.kind not in 'iu':
        raise ValueError('event_indices must be a nonempty list of integer positions')
    if positions.min() < 0 or positions.max() >= len(y):
        raise ValueError('event_indices must lie inside the series')
    offsets = np.arange(-low, high + 1)
    means, counts = np.full(len(offsets), np.nan), np.zeros(len(offsets), dtype=np.int64)
    for i, offset in enumerate(offsets):
        target = positions + offset
        inside = (target >= 0) & (target < len(y))
        counts[i] = int(inside.sum())
        if counts[i]:
            means[i] = float(y[target[inside]].mean())
    available = counts > 0
    return {'offsets': offsets, 'mean': np.where(available, means, 0.0), 'n': counts, 'valid': available,
            'n_events': int(len(positions)), 'uncertainty': 'not_estimated',
            'warnings': ['Composite of a sample of events: no significance test, no causal claim.',
                         'Offsets with valid=False have no observations; their mean is a 0 placeholder.']}


def _auxiliary(data, parameters: dict, names: tuple) -> dict:
    selected = {}
    for name in names:
        identifier = parameters.pop(name, None)
        if not isinstance(identifier, str) or identifier not in data.variables:
            raise ValueError(f'Specify {name} as a dataset variable ID')
        item = data.variables[identifier]
        if item.dimensions != ('time',) or item.unit != '1' or (item.invalid is not None and item.invalid.any()):
            raise ValueError(f'{name} must be an unmasked dimensionless time variable')
        selected[name] = item.values
    return selected


def analyze_detect_events(data, request):
    """Registry adapter: baseline thresholds (percentile_thresholds) + events (detect_events).

    `groups` and `baseline` are dataset variable IDs (unit 1; baseline coded 0/1).
    `q`, `min_count`, `direction` and `min_duration` are required and have no default.
    """
    from ..contracts import AnalysisResult

    variable = data.variables[request.variable]
    if data.time is None or (variable.invalid is not None and variable.invalid.any()):
        raise ValueError('Explicit time coordinates and unmasked observations are required')
    parameters = dict(request.parameters)
    selected = _auxiliary(data, parameters, ('groups', 'baseline'))
    missing = [key for key in ('q', 'min_count', 'direction', 'min_duration') if key not in parameters]
    if missing:
        raise ValueError('Specify ' + ', '.join(missing) + ' explicitly')
    if not np.isin(selected['baseline'], [0, 1]).all():
        raise ValueError('baseline variable must encode False/True as 0/1')
    t, y = temporal(data.time.values, variable.values, regular=True)
    reference = percentile_thresholds(y, selected['groups'], selected['baseline'].astype(bool),
                                      q=parameters['q'], min_count=parameters['min_count'])
    per_observation = expand_thresholds(selected['groups'], reference)
    payload = detect_events(t, y, per_observation, direction=parameters['direction'],
                            min_duration=parameters['min_duration'])
    payload['reference'] = reference
    payload['thresholds'] = per_observation
    payload['warnings'] = list(payload['warnings']) + list(reference['warnings'])
    unit = variable.unit
    units = {'start_indices': '1', 'end_indices': '1', 'start_times': data.time.unit, 'end_times': data.time.unit,
             'durations': 'steps', 'peak_values': unit, 'peak_indices': '1', 'mean_exceedance': unit,
             'n_events': '1', 'exceedance_fraction': '1', 'thresholds': unit,
             'reference.group_ids': '1', 'reference.thresholds': unit, 'reference.count': '1', 'reference.q': '1'}
    return AnalysisResult(
        request.analysis_id, 'detect_events', VERSION, data.dataset_id, request.variable, 'completed', 'events',
        dict(request.parameters), payload, units, tuple(payload['warnings']), data.provenance,
        {'n_observations': len(t), 'time_start': t[0], 'time_end': t[-1], 'time_origin': data.time.origin,
         'time_unit': data.time.unit, 'calendar': data.time.calendar, 'value_unit': unit, 'quality': data.quality},
        data.transformations, uncertainty=payload['uncertainty'])
