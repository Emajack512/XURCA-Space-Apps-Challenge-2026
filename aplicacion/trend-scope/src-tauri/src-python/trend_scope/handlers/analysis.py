from typing import Any, Dict, List
from trend_scope.models.stats import regression
from trend_scope.models.types import FitOutput

def run_regression_analysis(
    algorithm: str,
    x: List[float],
    y: List[float],
    options: Dict[str, Any] | None = None
) -> FitOutput:
    """
    Despachador central para las análisis de regresión según el algoritmo solicitado.
    """
    options = options or {}

    match algorithm:
        case "linear":
            return regression.linear_regression(x, y)
        case "polynomial":
            degree = options.get("degree", 2)
            return regression.polynomial_regression(x, y, degree=degree)
        case "ridge":
            degree = options.get("degree", 3)
            alpha = options.get("alpha", 1.0)
            return regression.ridge_regression(x, y, degree=degree, alpha=alpha)
        case "exponential":
            return regression.exponential_regression(x, y)
        case "logarithmic":
            return regression.logarithmic_regression(x, y)
        case "power":
            return regression.power_regression(x, y)
        case "harmonic":
            period = options.get("period", 1.0)
            harmonics = options.get("harmonics", 2)
            trend_degree = options.get("trend_degree", 1)
            return regression.harmonic_regression(
                x, y, period=period, harmonics=harmonics, trend_degree=trend_degree
            )
        case _:
            raise ValueError(f"Algoritmo de regresión desconocido: '{algorithm}'")
