"""W05: lagged and partial Pearson correlation with an effective sample size.

Both functions measure linear association, never causation. Lags are always
given explicitly; nothing here searches for, or ranks by, the "best" lag.
"""
import numpy as np
from scipy import stats

from ..numeric import array, finite, integer, temporal

VERSION = '1.0.0-candidate'
MIN_PAIRS = 4


def _lag1(sample: np.ndarray) -> float:
    """Lag-1 autocorrelation of one segment; a constant segment is rejected."""
    centered = sample - sample.mean()
    denominator = float(np.dot(centered, centered))
    if denominator == 0:
        raise ValueError('Constant series has undefined correlation')
    return float(np.dot(centered[:-1], centered[1:]) / denominator)


def _effective_size(n: int, first_r1: float, second_r1: float) -> float:
    """Bretherton et al. (1999): n (1 - r1x r1y) / (1 + r1x r1y), never larger than n.

    Capping at n is conservative: negative serial correlation does not buy extra
    degrees of freedom. AR(1) is an approximation of the dependence structure.
    """
    product = first_r1 * second_r1
    if product <= -1.0:
        return float(n)
    return float(min(n, n * (1.0 - product) / (1.0 + product)))


def _p_value(r: float, effective: float, extra: int = 0):
    """Two-sided t test of r = 0 with (effective - 2 - extra) degrees of freedom.

    Returns (p, testable). When fewer than one degree of freedom remains the test
    is not performed: p is reported as 1.0 (no evidence) and testable is False.
    """
    df = effective - 2.0 - extra
    if df < 1.0:
        return 1.0, False
    if abs(r) >= 1.0:
        return 0.0, True
    statistic = r * np.sqrt(df / (1.0 - r * r))
    return float(2.0 * stats.t.sf(abs(statistic), df)), True


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        raise ValueError('Constant series has undefined correlation')
    r = float(np.corrcoef(a, b)[0, 1])
    finite([r])
    return float(np.clip(r, -1.0, 1.0))


def lagged_correlation(times, first, second, *, lags) -> dict:
    """Pearson correlation of `first` and `second` at each explicit lag.

    A positive lag k pairs first[i] with second[i + k] (`first` precedes
    `second` by k steps); a negative lag pairs first[i + |k|] with second[i].
    Lags count observation steps of a regular grid, not calendar units. For
    every lag the result has `r`, `n` (pairs), `n_effective`, `p_value`,
    `testable` and the lag-1 autocorrelation of each overlapping segment.

    `n_effective` = n (1 - r1x r1y) / (1 + r1x r1y), capped at n (Bretherton et
    al. 1999); the p-value is a two-sided t test with n_effective - 2 degrees of
    freedom. Where fewer than one degree of freedom remains, `testable` is False
    and `p_value` is 1.0 (no evidence), not a measured value.

    Limits: linear association only; correlation is not causation; shared
    trends or seasonal cycles inflate it, so remove them explicitly beforehand;
    with several lags the p-values need multiple-testing control (W06). No best
    lag is selected or ranked. Needs a regular grid and at least 4 pairs per
    lag. O(n) per lag.
    """
    t, x = temporal(times, first, regular=True, minimum=MIN_PAIRS)
    _, y = temporal(times, second, regular=True, minimum=MIN_PAIRS)
    n = len(x)
    if isinstance(lags, (str, bytes)) or not hasattr(lags, '__iter__'):
        raise ValueError('lags must be an explicit list of integers')
    steps = [integer(lag, 'lag', -n) for lag in lags]
    if not steps or len(set(steps)) != len(steps):
        raise ValueError('lags must be a nonempty list without repeated values')
    reach = n - MIN_PAIRS
    if any(abs(lag) > reach for lag in steps):
        raise ValueError(f'Each |lag| must leave at least {MIN_PAIRS} pairs (max {reach} for this series)')
    r, count, effective, p_values, testable, r1_first, r1_second = [], [], [], [], [], [], []
    for lag in steps:
        a, b = (x[:n - lag], y[lag:]) if lag >= 0 else (x[-lag:], y[:n + lag])
        r.append(_correlation(a, b))
        count.append(len(a))
        ra, rb = _lag1(a), _lag1(b)
        r1_first.append(ra)
        r1_second.append(rb)
        size = _effective_size(len(a), ra, rb)
        effective.append(size)
        p, ok = _p_value(r[-1], size)
        p_values.append(p)
        testable.append(ok)
    return {'lags': np.asarray(steps, dtype=np.int64), 'r': np.asarray(r), 'n': np.asarray(count, dtype=np.int64),
            'n_effective': np.asarray(effective), 'p_value': np.asarray(p_values), 'testable': np.asarray(testable),
            'r1_first': np.asarray(r1_first), 'r1_second': np.asarray(r1_second),
            'lag_convention': 'positive lag: first precedes second', 'uncertainty': 'p_values_only',
            'warnings': ['Correlation is not causation; shared trends or seasonality can create association.',
                         'With several lags the p-values require multiple-testing control (fdr_bh).',
                         'Effective sample size assumes AR(1) serial dependence in both series.']}


def partial_correlation(first, second, controls) -> dict:
    """Correlation of `first` and `second` after removing the linear effect of `controls`.

    Both series are regressed (least squares, with intercept) on the controls and
    the residuals are correlated. `controls` is an (n, k) array or a 1D array
    for a single control. Observations are assumed to be in time order on a
    regular grid: the effective size uses the lag-1 autocorrelation of the two
    residual series (as in `lagged_correlation`) and the t test has
    n_effective - 2 - k degrees of freedom. `testable` and `p_value` follow the
    same convention as `lagged_correlation`.

    Limits: linear and additive control only; omitted or nonlinear confounders
    remain; correlation is not causation; collinear controls raise ValueError.
    O(n k^2).
    """
    x = array(first, 'first', minimum=MIN_PAIRS + 1)
    y = array(second, 'second', minimum=MIN_PAIRS + 1)
    raw = np.asarray(controls)
    c = array(raw.reshape(-1, 1) if raw.ndim == 1 else raw, 'controls', ndim=2)
    n = len(x)
    if y.shape != x.shape or c.shape[0] != n:
        raise ValueError('first, second and controls must have the same number of observations')
    k = c.shape[1]
    if n - k - 2 < 3:
        raise ValueError('Too few observations for the number of controls')
    design = np.column_stack([np.ones(n), c])
    if np.linalg.matrix_rank(design) < k + 1:
        raise ValueError('Controls are collinear or constant')
    with np.errstate(over='raise', invalid='raise'):
        res_x = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
        res_y = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    finite(res_x)
    finite(res_y)
    scale_x, scale_y = np.max(np.abs(x - x.mean())), np.max(np.abs(y - y.mean()))
    if np.ptp(res_x) <= 1e-12 * max(scale_x, 1e-300) or np.ptp(res_y) <= 1e-12 * max(scale_y, 1e-300):
        raise ValueError('A series is fully explained by the controls; the partial correlation is undefined')
    r = _correlation(res_x, res_y)
    ra, rb = _lag1(res_x), _lag1(res_y)
    effective = _effective_size(n, ra, rb)
    p, ok = _p_value(r, effective, extra=k)
    return {'r': r, 'n': int(n), 'n_controls': int(k), 'n_effective': effective, 'p_value': p, 'testable': ok,
            'uncertainty': 'p_values_only',
            'warnings': ['Correlation is not causation; unmeasured or nonlinear confounders are not removed.',
                         'Effective sample size assumes AR(1) serial dependence in the residuals.']}


def _aux(data, name: str):
    if not isinstance(name, str) or name not in data.variables:
        raise ValueError('Specify other series as dataset variable IDs')
    item = data.variables[name]
    if item.dimensions != ('time',) or (item.invalid is not None and item.invalid.any()):
        raise ValueError('Other series must be unmasked time variables')
    return item


def _result(data, request, method, payload, units, variable):
    from ..contracts import AnalysisResult

    t = data.time.values
    return AnalysisResult(
        request.analysis_id, method, VERSION, data.dataset_id, request.variable, 'completed', 'estimate',
        dict(request.parameters), payload, units, tuple(payload['warnings']), data.provenance,
        {'n_observations': len(t), 'time_start': t[0], 'time_end': t[-1], 'time_origin': data.time.origin,
         'time_unit': data.time.unit, 'calendar': data.time.calendar, 'value_unit': variable.unit,
         'quality': data.quality}, data.transformations, uncertainty=payload['uncertainty'])


def analyze_lagged_correlation(data, request):
    """Registry adapter. `second_variable` is a dataset variable ID; `lags` is explicit."""
    variable = data.variables[request.variable]
    if data.time is None or (variable.invalid is not None and variable.invalid.any()):
        raise ValueError('Explicit time coordinates and unmasked observations are required')
    parameters = dict(request.parameters)
    other = _aux(data, parameters.pop('second_variable', None))
    if 'lags' not in parameters:
        raise ValueError('Specify lags explicitly')
    payload = lagged_correlation(data.time.values, variable.values, other.values, lags=parameters['lags'])
    units = {key: '1' for key in ('r', 'n', 'n_effective', 'p_value', 'testable', 'r1_first', 'r1_second')}
    units['lags'] = 'steps'
    return _result(data, request, 'lagged_correlation', payload, units, variable)


def analyze_partial_correlation(data, request):
    """Registry adapter. `second_variable` and `controls` (a list) are dataset variable IDs."""
    variable = data.variables[request.variable]
    if data.time is None or (variable.invalid is not None and variable.invalid.any()):
        raise ValueError('Explicit time coordinates and unmasked observations are required')
    parameters = dict(request.parameters)
    other = _aux(data, parameters.pop('second_variable', None))
    names = parameters.pop('controls', None)
    if not isinstance(names, (list, tuple)) or not names:
        raise ValueError('Specify controls as a nonempty list of dataset variable IDs')
    columns = [_aux(data, name).values for name in names]
    temporal(data.time.values, variable.values, regular=True, minimum=MIN_PAIRS + 1)
    payload = partial_correlation(variable.values, other.values, np.column_stack(columns))
    units = {key: '1' for key in ('r', 'n', 'n_controls', 'n_effective', 'p_value', 'testable')}
    return _result(data, request, 'partial_correlation', payload, units, variable)
