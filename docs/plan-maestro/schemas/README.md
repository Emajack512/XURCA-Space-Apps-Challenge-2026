# Contratos de `request.json` y `response.json`

Generados con `trend_scope.handlers.contracts.export_schemas()` (Pydantic). Si cambia `contracts.py`, regenerarlos.

| Archivo | Qué es |
|---|---|
| `request.schema.json` | JSON Schema del pedido de análisis (`earth-detective/request`, versión 1) |
| `response.schema.json` | JSON Schema de la respuesta (`earth-detective/response`, versión 1) |
| `fixture.request.trend.json` | Pedido real: `trend_significance` sobre NASA POWER T2M, Villa Mercedes, 2000–2024, mensual, hipótesis «aumenta» |
| `fixture.response.trend.json` | Su respuesta real (`completed`, arreglos recortados a 50 puntos) |
| `fixture.request.invalid-request.json` | Pedido de `relationship` con una sola variable (requiere 2 a 4) |
| `fixture.response.invalid-request.json` | Su respuesta: `failed` con `INVALID_REQUEST` |

Los cuatro fixtures validan contra su schema (`jsonschema.validate`). La respuesta de tendencia depende de los datos de NASA POWER del día en que se generó (2026-11-15): sirve como ejemplo de forma, no como valor de referencia científico.
