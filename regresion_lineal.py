"""
Regresión lineal múltiple por mínimos cuadrados para un número fijo de entradas.

Modelo:  y = b0 + b1*x1 + b2*x2 + ... + bn*xn

Uso:
    python regresion_lineal.py            # modo interactivo
    python regresion_lineal.py --demo     # ejemplo con datos sintéticos
"""

import sys

import numpy as np


def regresion_lineal(X, y):
    """
    Ajusta una regresión lineal por mínimos cuadrados.

    Parámetros
    ----------
    X : array de forma (m, n)  -> m muestras, n entradas
    y : array de forma (m,)    -> salidas observadas

    Devuelve
    --------
    coef : array de forma (n+1,)  -> [b0, b1, ..., bn] (b0 es el intercepto)
    r2   : coeficiente de determinación R²
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()

    if X.ndim == 1:
        X = X.reshape(-1, 1)

    m, n = X.shape
    if y.shape[0] != m:
        raise ValueError("X e y deben tener el mismo número de muestras.")
    if m < n + 1:
        raise ValueError(f"Se necesitan al menos {n + 1} muestras para {n} entradas.")

    # Matriz de diseño con columna de unos para el intercepto
    A = np.hstack([np.ones((m, 1)), X])

    # Mínimos cuadrados: minimiza ||A·b - y||².
    # Equivale a resolver la ecuación normal (AᵀA)b = Aᵀy, pero lstsq
    # es más estable numéricamente.
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)

    # R² = 1 - SS_res / SS_tot
    y_pred = A @ coef
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    return coef, r2


def predecir(coef, X_nuevo):
    """Calcula las predicciones y = b0 + b1*x1 + ... + bn*xn."""
    X_nuevo = np.asarray(X_nuevo, dtype=float)
    if X_nuevo.ndim == 1:
        X_nuevo = X_nuevo.reshape(1, -1)
    return coef[0] + X_nuevo @ coef[1:]


def mostrar_resultado(coef, r2, n):
    """Imprime coeficientes, ecuación y R²."""
    print("\n=== Resultados ===")
    print(f"Intercepto b0 = {coef[0]:.6f}")
    for i in range(n):
        print(f"b{i + 1} = {coef[i + 1]:.6f}")

    terminos = [f"{coef[0]:.4f}"] + [
        f"{coef[i + 1]:+.4f}*x{i + 1}" for i in range(n)
    ]
    print("Ecuación: y = " + " ".join(terminos))
    print(f"R² = {r2:.6f}")


def leer_datos_interactivo():
    """Pide al usuario el número de entradas y las muestras por consola."""
    while True:
        try:
            n = int(input("Número de entradas (variables x): "))
            if n >= 1:
                break
            print("Debe ser un entero mayor o igual a 1.")
        except ValueError:
            print("Introduce un entero válido.")

    while True:
        try:
            m = int(input(f"Número de muestras (mínimo {n + 1}): "))
            if m >= n + 1:
                break
            print(f"Necesitas al menos {n + 1} muestras.")
        except ValueError:
            print("Introduce un entero válido.")

    X = np.zeros((m, n))
    y = np.zeros(m)
    print(f"\nIntroduce {n} valores de x seguidos del valor de y, separados por espacios:")
    for k in range(m):
        while True:
            fila = input(f"Muestra {k + 1}: ").split()
            if len(fila) == n + 1:
                try:
                    valores = [float(v) for v in fila]
                    X[k] = valores[:n]
                    y[k] = valores[n]
                    break
                except ValueError:
                    pass
            print(f"Se esperaban {n + 1} números.")

    return X, y


def demo():
    """Genera datos con coeficientes conocidos y comprueba que se recuperan."""
    rng = np.random.default_rng(42)
    n = 2
    m = 50
    X = rng.uniform(-10, 10, size=(m, n))
    b_real = np.array([2.0, 3.0, -1.0])
    y = b_real[0] + X @ b_real[1:] + rng.normal(0, 0.5, size=m)

    print(f"Demo: {m} muestras, {n} entradas.")
    print(f"Coeficientes reales: {b_real}")
    coef, r2 = regresion_lineal(X, y)
    mostrar_resultado(coef, r2, n)

    nuevo = [[1.0, 1.0], [5.0, -2.0]]
    print("\nPredicciones para nuevos puntos:")
    for punto, pred in zip(nuevo, predecir(coef, nuevo)):
        print(f"  x = {punto} -> y = {pred:.4f}")


def main():
    if "--demo" in sys.argv:
        demo()
        return

    X, y = leer_datos_interactivo()
    coef, r2 = regresion_lineal(X, y)
    mostrar_resultado(coef, r2, X.shape[1])


if __name__ == "__main__":
    main()
