# CLAUDE.md — Traspaso de contexto (2026-11-15, tras la fusión con el asistente de JP)

Proyecto: **Earth Detective / XURCA** (NASA Space Apps 2026). App de escritorio Tauri + SvelteKit + Python (PyTauri) en `aplicacion/trend-scope/`. Idioma de trabajo: español rioplatense. Lee también `AGENTS.md` (raíz) y `aplicacion/trend-scope/src-tauri/src-python/trend_scope/models/CLAUDE.md` (reglas del motor científico).

## Arquitectura (implementada según `Mapa_frontend.png`)

`request.json` → **Data Handler** → **Analysis Handler** (devuelve un **Analysis Struct**) → **Algorithm Handler** (librerías de cálculo y predictivas) → Data Handler arma `response.json` → frontend (panel «Análisis estadístico») / chatbot (`analysisDigest`).

- Especificación: `docs/plan-maestro/23_ARQUITECTURA_HANDLERS.md`.
- Orden de trabajo y estado de handlers: `PY/handlers/AGENTS.md`. Cola de funciones científicas (W01–W20): `PY/models/AGENTS.md` §6.
- El Data Handler no usa CSV (el diagrama lo menciona): pasa arreglos en memoria. No hay exportación a CSV para el usuario.

## Estado de `main` (commit `831a2b3`)

`main` es la fusión del trabajo de Ema (motor estadístico, handlers, panel de análisis, D-06) con el de JP Marsi (asistente de IA). La rama `ema_workspace` está alineada con `main`.

**Cambios de JP que hay que conocer** (no pisarlos):
- `src/lib/services/acquisition.js::prepareInvestigation(data)` reemplaza al viejo `buildInvestigation` de `+page.svelte`: valida fechas (no futuras), filtra fuentes por alcance y asigna `geometryId` solo si hay **una** geometría compatible (si no, error «Elegí una geometría de consulta compatible…»). `+page.svelte` la envuelve en `buildInvestigation()` y se la pasa a `AnalysisPanel` y a `Assistant`: el panel, «Procesar» y el botón «Ejecutar análisis» del chat usan el mismo camino.
- Chat: `readyToProcess` en el contrato (la app consulta datos sola cuando el modelo tiene todo resuelto; con `changes.analysis` va en `false`: un análisis **nunca** se ejecuta solo). `acquisitionError` se muestra en el chat. Mascota (`src/lib/assets/mascot/*`). Lugares por nombre resueltos automáticamente: comando `load_place_boundary` en `desktop.py` + `public_sources.place_boundary` (localidades, localidades censales, provincias de Argentina).
- `sources.js::providerGeometries(route)`; nuevas fuentes en `source-coverage.json`: CHIRPS diario (`maxDays`) y USGS sismos (conteo, magnitud, profundidad; selección `Area`). `coverage.py` admite `Area` y `period_limit`.
- Panel de configuración: estado `settingsOpen` (no se persiste; `cfg_visual.json` arranca con `settings:false`); se quitó del menú Datos/Visualización.

## Verificado a mano (2026-11-15, Windows)

- La app arranca con la fusión. Backend: `list_analyses` devuelve 13 structs; un `run_analysis` con POWER T2M + PRECTOTCORR (Villa Mercedes, 2000–2024, mensual) da `completed` en los 10 structs de serie, antes y después de la fusión. `trend_significance`: +0,36 °C/década, p 0,003, IC [0,16; 0,56]; pronóstico con SARIMA (intervalo solo en el horizonte validado).
- Panel desde la interfaz (antes de la fusión): `trend_significance` en Mina Clavero → +0,32 °C/década, p 0,0077, Mann-Kendall modificado; muestra veredicto, hallazgos, avisos y «Cómo se calculó».
- **Sin probar todavía:** panel con `prepareInvestigation` de JP, chat → «Ejecutar análisis» → explicación con `analysisDigest`, gráfica de pronóstico en pantalla.

## Cómo arrancar la app (Windows, PowerShell, desde `aplicacion/trend-scope`)

```
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path; $env:PATH = "$env:VIRTUAL_ENV\Scripts;$env:PATH"; .\node_modules\.bin\tauri.cmd dev
```
Sin `VIRTUAL_ENV` falla con «activate the python virtual environment first». `pnpm` no está en el PATH de Ema (sí en el Linux de Eze: `pnpm tauri dev` con el venv activado). Tras un `git pull` con dependencias nuevas: `pip install` en `.venv` lo que declare `src-tauri/pyproject.toml`.

## Decisión del equipo

**No hacer benchmarks ni pruebas automáticas.** Se prueba a mano. Las verificaciones de arriba son llamadas manuales al backend y uso de la interfaz, no una suite. Ante errores de ejecución: corregir sin rediseñar.

## Estado por fase

| Fase | Contenido | Estado |
|---|---|---|
| 0 | `robust_z` de W01 con factor 1,4826 | Hecha |
| 1 | `handlers/` completos, comandos `run_analysis` y `list_analyses`, W17 y W18 | Hecha y verificada |
| 2 | W05 (`stats/lagged.py`), W04 (`climate/events.py`) + structs `seasonality`, `change_point`, `smoothing`, `extreme_events`, `relationship` | Hecha y verificada (corren sin error) |
| 3 | Pronóstico: W07–W09, W13, W20 + `forecast_backtest`; W06; structs `forecast` y `spatial_pattern`; `spatial.py` | Hecha; `forecast` verificado |
| 4 | W19, W10, W11, W12, W14, W15, W16 como API de Python | Solo W10 registrada (struct `precipitation_indices`); W11, W12, W14, W15, W16, W19 y la convolución 2D (`signal/convolution2d.py`, el «FIR 2D» del diagrama) siguen sin registrar: necesitan ráster o varias variables diarias que los conectores no entregan |

Structs (13): `describe`, `trend_significance`, `anomaly`, `drought_spi`, `regression_fit`, `forecast`, `spatial_pattern`, `seasonality`, `change_point`, `smoothing`, `extreme_events`, `relationship`, `precipitation_indices`. No verificados aún: `drought_spi`, `spatial_pattern`, `precipitation_indices`.

**Parámetros obligatorios sin valor por defecto** (`ParamSpec.required=True`, `INVALID_REQUEST` si faltan): `penalty` (change_point), `window` (smoothing), `q` y `min_duration` (extreme_events), `lags` (relationship). Provisionales: `harmonics` 2, `min_size` 6, `components` [0].

## Mapa de archivos (PY = `aplicacion/trend-scope/src-tauri/src-python/trend_scope/`)

- `PY/handlers/contracts.py` — Pydantic del request/response, códigos de error, `request_hash`, `export_schemas()`.
- `PY/handlers/analysis_structs.py` — catálogo declarativo (`STRUCTS`, `BY_ID`); agregar un análisis = agregar una entrada.
- `PY/handlers/analysis_handler.py` — `resolve`, `check`, `capabilities`, topes provisionales de horizonte.
- `PY/handlers/preparation.py` — series → `ScientificDataset`; `prepare_group` alinea 2–4 series para `relationship`.
- `PY/handlers/algorithm_handler.py` — ejecuta pasos con `catalog_registry()` + `analyze()`; sin fórmulas.
- `PY/handlers/decision.py` — hallazgos y veredicto; reglas deterministas.
- `PY/handlers/data_handler.py` — `run(request) -> response`; usa `services.acquisition.acquire` y `services.evidence.with_evidence`.
- `PY/handlers/spatial.py` — puntos dentro de un polígono (nunca promedio zonal).
- `PY/models/` — motor científico (39 métodos en `catalog_registry.py`).
- `PY/services/environmental_series.py::read_text` — si un servidor no responde, el error nombra el host y sugiere quitar la variable.
- Frontend de análisis: `src/lib/services/acquisition.js` (`prepareInvestigation`, `runAnalysis`, `listAnalyses`, `analysisRequest`), `analysisText.js` (textos; `unit()` muestra °C/década y `testLabels` nombres de prueba, solo visualización), `analysisRunner.js` + `stores/analysis.js`, `components/AnalysisPanel.svelte`, `ForecastChart.svelte`. Estilos globales en `src/lib/styles/dashboard.css` (los radio y checkbox no heredan `width:100%`).

## Reglas que hay que respetar

- No tocar `web app/`. No tocar `services/` ni el frontend sin pedido. No modificar archivos de `models/PRESERVATION.json`. **No pisar el trabajo de JP en el asistente** (`Assistant.svelte`, `assistantConfiguration.js`, `assistant-contract.json`, `services/assistant*.py`); D-15: JP es dueño, Ema revisora.
- Los handlers **no contienen fórmulas**: todo cálculo sale de un método del motor.
- Nada de interpolación, orden ni conversión de unidades implícitos; toda transformación va en `transformations`.
- Nunca un «porcentaje de certeza»; p ≥ α o intervalo con 0 → «no hay evidencia suficiente», jamás «sin cambios».
- Valores provisionales (sin respaldo de la investigación): `min_points` 10, topes de horizonte (mensual 12, diario 14, anual 5), `max_origins` 24, `min_residuals` 10, `baseline_min_count` 3, `mk_lag` 1, `n_points` 9.
- Git: no hacer commit ni push sin pedido explícito. No incluir en commits `package.json` (agrega `pnpm` como dependencia), `package-lock.json` ni `src-tauri/Cargo.toml`: están modificados en la copia de Ema y no son parte del trabajo.

## Decisiones (`docs/plan-maestro/21_RIESGOS_Y_DECISIONES.md`)

- **D-06 decidida:** `statsmodels`, `pymannkendall`, `ruptures` en `pyproject.toml` (compilan en Windows y en el Linux de Eze).
- **D-03 pendiente:** valores de los parámetros obligatorios y de los provisionales; los define la ingeniera química. Ejemplo del problema: `change_point` con `penalty` 10 sobre la serie mensual cruda marca 7 cortes porque pesa el ciclo estacional.
- **D-21 pendiente:** tolerancias del pronóstico (orígenes, cobertura, habilidad); se fijan después de los primeros backtests reales.

## Pendientes y riesgos conocidos

1. **Probar desde la interfaz** lo que la fusión tocó: panel con `prepareInvestigation`, chat → propuesta → «Ejecutar análisis» → explicación sin inventar, error de adquisición visible en el chat.
2. **Pulir el formulario de análisis:** los parámetros se ven por su id («baseline», «alpha», «confidence»); la barra de estado dice «1 variables».
3. **CHIRPS** (`data.chc.ucsb.edu`) no responde desde la red de Ema (DNS resuelve, la conexión da timeout); POWER y Open-Meteo sí. Es de red, no de código.
4. **Datos espaciales:** la convolución 2D y W11–W19 necesitan un conector de ráster; decidir si entra en esta versión.
5. **Auditoría independiente** pendiente de W01–W03 y de todo lo nuevo; todo está en estado `candidate`.
6. Sin generar los JSON Schema ni fixtures (`contracts.export_schemas()` los produce bajo demanda).
7. `fire/fwi.py`: rechaza |lat| < 30° y no se comparó con tablas de referencia.
8. `tests/test_climatology.py` y `services/test_assistant.py` no se corrieron tras los cambios; tests que cuenten métodos del registro pueden fallar.
9. Desvíos de la fase 2: el paso `fdr` de `relationship` lo hace `decision.py` con `fdr_bh` (W06); `seasonality` informa coeficientes armónicos, amplitud espectral anual y rango STL; `change_point` calcula medias por tramo con NumPy (descriptivo); no hay `cusum`; `extreme_events` con hipótesis `threshold` compara un estadístico de la serie.
10. Desvíos respecto del plan 23: sin paso `lttb` en `describe`; `lag1_autocorrelation` acepta `groups`; código de error `CADENCE_INCOMPATIBLE`; el pronóstico es un único método registrado (`forecast_backtest`).
11. Avisos de Git sobre LF/CRLF: inofensivos.

## Cómo seguir

1. Arrancar la app (comando de arriba) y que el usuario pruebe el punto 1 de pendientes; corregir lo que falle sin rediseñar y sin tocar el asistente de JP salvo pedido.
2. Pulir el formulario (punto 2).
3. Con D-03 resuelta, cargar los valores por defecto en `analysis_structs.py`.
4. Auditoría independiente. Respetar el protocolo de una función por solicitud de `models/AGENTS.md`.
