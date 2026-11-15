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

## Etapa D (mapas) en paralelo con el Codex de Ema — desde 2026-11-15

- **Codex de Ema** (worktree `C:\Users\Victus\Desktop\nasa-hackathon\XURCA-codex-raster`, rama `ema_codex_raster`): conectores de grillas en `PY/raster/` (`providers.py::fetch_grid`, `power_regional.py`, `openmeteo_grid.py`, `chirps_cog.py`, `manual_check.py`, `fixtures/`, `NOTES.md`). Reglas en `PY/raster/AGENTS.md`. No toca nada fuera de `PY/raster/`.
- **Frontera congelada:** `PY/raster/contract.py` (`GridRequest`, `GridField`: ejes ascendentes, `values` (time, lat, lon) con NaN = sin dato, `mask`, unidad, procedencia). Solo se cambia de común acuerdo.
- **Claude (este agente), en paralelo, sin tocar `PY/raster/`:** structs sobre grillas en `handlers/` y `models/`, desarrollados con `GridField` sintéticos hasta que existan los fixtures reales:
  1. `grid_trend_map`: tendencia (Sen + Mann-Kendall) por celda dentro de la máscara + FDR (Benjamini-Hochberg) sobre las celdas.
  2. `grid_anomaly_map`: anomalía de un período contra la base, por celda (paleta divergente centrada en 0 la decide el frontend).
  3. `grid_smoothing`: convolución 2D (`signal/convolution2d.py`) por intervalo, sin rellenar NaN.
  4. `grid_area_summary`: media de área ponderada por cos(lat) de las celdas con dato, rotulada como promedio de grilla (no zonal exacto) con cobertura.
  5. Bloque `grids` en `response.json` (contracts.py + schemas) con los metadatos que pide el documento de la ingeniera (`variable`, `kind`, `unit`, `valid_at`, `value_min/max` recomendados, `color_scale_type` secuencial/divergente, `coverage_fraction`, `nodata`, `native_resolution`, procedencia); los colores los elige el frontend (JP).
  6. Struct `fire_weather` (FWI) sobre un punto con 4 variables diarias de ERA5 (temperatura, humedad, viento, lluvia), si el tiempo alcanza.
- **Estado del lado de Claude (2026-11-15, commits `147992a` y siguiente):** HECHO 1–4 y 6 (`grid_fire_weather`, FWI por celda con las 4 grillas diarias de ERA5; exige viento en km/h, lluvia en mm, humedad en %, temperatura en °C y no convierte; descarta 30 días de arranque). En lugar de cambiar `contracts.py`, las capas van en `block["grids"]` (formato documentado en `handlers/grid.py`); `assistant_digest` no las incluye. Los 5 structs `grid_*` figuran `available: false` hasta que exista `raster/providers.py`; probados con un conector simulado (todos `completed`). Motor en `models/spatial/grid.py`; handler en `handlers/grid.py`. El frontend de mapas (dibujar `grids`) es de JP: avisarle el formato.
- **Integración:** cuando el Codex termine, Ema (o Claude a pedido) hace merge de `ema_codex_raster` en `ema_workspace`, se corre `manual_check.py` y los structs de grilla con datos reales, y recién entonces se sube a `main`.

## Fronteras con JP (detalle completo en `AGENTS.md` de la raíz, sección «Fronteras de trabajo»)

- **Lado de Ema (este agente):** `PY/handlers/`, `PY/models/`, `AnalysisPanel.svelte`, `ForecastChart.svelte`, `analysisText.js`, `docs/plan-maestro/schemas/`.
- **Lado de JP (Codex):** `Assistant.svelte`, `assistantConfiguration.js`, mascota, `assistant-contract.json`, `services/assistant*.py` (salvo `analysis_catalog()` y `check_analysis()`), `+page.svelte`, mapa, geografía, fuentes y cobertura, comandos de `desktop.py` que no sean de análisis.
- **Frontera (solo de común acuerdo):** `changes.analysis`, `analysisCatalog`, `analysisDigest`/`assistant_digest`, `prepareInvestigation()`, `executeAnalysis()` + `stores/analysis.js`, `request.json`/`response.json`.
- Si cambio la forma de `assistant_digest`, de `capabilities()` o de `request`/`response`, avisar a JP antes de subir. Presupuesto del prompt: ~14 800 caracteres libres para contexto; el catálogo de análisis ocupa ~2 500 (no inflarlo).

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

Structs (13): `describe`, `trend_significance`, `anomaly`, `drought_spi`, `regression_fit`, `forecast`, `spatial_pattern`, `seasonality`, `change_point`, `smoothing`, `extreme_events`, `relationship`, `precipitation_indices`. **Los 13 verificados a mano con datos reales** (etapa A): `drought_spi` con POWER PRECTOTCORR 1991–2024 (escalas 1, 3, 6, 12); `precipitation_indices` con ERA5 `precipitation_sum` diario 2015–2024 (Rx1day 32–47 mm); `spatial_pattern` con un polígono alrededor de Villa Mercedes.

`spatial_pattern` agrupa los puntos con series idénticas (caen en la misma celda de la fuente; con POWER, 9 puntos en ~1° × 0,7° dan 4 series): tendencia y FDR una vez por serie distinta, `how_much.n_distinct_series` y `shared_by_points` en cada tendencia, más una limitación explícita. Antes contaba 9 series «significativas» y exageraba la evidencia.

**Ya no hay parámetros obligatorios** (etapa B, 2026-11-15). Valores **propuestos por Claude** a pedido del equipo (la ingeniera no los fijó; su documento `Trend_Detective_FRONTEND_MAPAS_v1` es de diseño de mapas): todos `provisional=True`, cada uno reportado como aviso «propuesto, sin validar (D-03)» y en `parameters_effective`:

| Parámetro | Valor | Fuente |
|---|---|---|
| `penalty` (change_point) | vacío → SIC: 2·σ²·ln n, σ = 1,4826·MAD(diff y)/√2 (en `models/optional_methods.py::pelt`, `penalty='sic'`) | Killick et al. 2012; default de R `changepoint` |
| `min_size` (change_point) | 12 meses / 5 años | un régimen más corto suele ser variabilidad |
| `window` (smoothing) | 31 días / 12 meses / 5 años | práctica estándar |
| `q` (extreme_events) | 0,9 si `direction=above`, 0,1 si `below` | percentiles ETCCDI |
| `min_duration` (extreme_events) | 1 paso | un mes o año extremo ya es evento |
| `lags` (relationship) | [0, 1, 2, 3, 6] meses / [0, 1] años | escalas de respuesta hidroclimática y teleconexiones |

Mecanismo: `ParamSpec.depends_on` (`"@cadence"` o el nombre de otro parámetro) + `by_value`; `analysis_handler.apply_dependent_defaults` los completa en `data_handler._analyze_one` después de preparar la serie (cuando se conoce la cadencia). `list_analyses` expone `depends_on` y `by_value`; el formulario los muestra como «automático: …». Otros provisionales: `harmonics` 2, `components` [0].

`change_point`: las medias por tramo se calculan sobre las anomalías (sin ciclo estacional) cuando el paso `deseason` corre (`how_much.basis`, `penalty_rule`). Con SIC, San Luis T2M 1991–2024 da un cambio (+0,68 °C, 2018). **Limitación conocida:** con series de ~25 años (2000–2024) SIC marca ~5 cambios que son años fríos/cálidos reales (2000, 2007): la autocorrelación hace la penalización demasiado chica (aviso incluido). Recomendar ≥ 30 años.

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

- No tocar `web app/`. No tocar `services/` ni el frontend sin pedido. No modificar archivos de `models/PRESERVATION.json`. **No editar el lado de JP** (ver «Fronteras con JP»); D-15: JP es dueño del asistente, Ema revisora.
- Los handlers **no contienen fórmulas**: todo cálculo sale de un método del motor.
- Nada de interpolación, orden ni conversión de unidades implícitos; toda transformación va en `transformations`.
- Nunca un «porcentaje de certeza»; p ≥ α o intervalo con 0 → «no hay evidencia suficiente», jamás «sin cambios».
- Valores provisionales (sin respaldo de la investigación): `min_points` 10, topes de horizonte (mensual 12, diario 14, anual 5), `max_origins` 24, `min_residuals` 10, `baseline_min_count` 3, `mk_lag` 1, `n_points` 9.
- Git: no hacer commit ni push sin pedido explícito. No incluir en commits `package.json` (agrega `pnpm` como dependencia), `package-lock.json` ni `src-tauri/Cargo.toml`: están modificados en la copia de Ema y no son parte del trabajo.

## Decisiones (`docs/plan-maestro/21_RIESGOS_Y_DECISIONES.md`)

- **D-06 decidida:** `statsmodels`, `pymannkendall`, `ruptures` en `pyproject.toml` (compilan en Windows y en el Linux de Eze).
- **D-03 resuelta provisionalmente:** valores propuestos desde la literatura (tabla arriba), marcados como no validados. Queda pendiente la validación de la ingeniera química; su documento de mapas no los cubre (menciona un «delta incremental v3 de backend» que no tenemos).
- **D-21 resuelta provisionalmente:** `min_skill` 0,05 por paso y tolerancia binomial de cobertura (ver etapa C), fijadas tras backtests reales; pendiente de validación por la investigación.

## Pendientes y riesgos conocidos

1. **Probar desde la interfaz** lo que la fusión tocó: panel con `prepareInvestigation`, chat → propuesta → «Ejecutar análisis» → explicación sin inventar, error de adquisición visible en el chat.
2. **Pulir el formulario de análisis:** los parámetros se ven por su id («baseline», «alpha», «confidence»); la barra de estado dice «1 variables».
3. **CHIRPS** (`data.chc.ucsb.edu`) no responde desde la red de Ema (DNS resuelve, la conexión da timeout); POWER y Open-Meteo sí. Es de red, no de código.
4. **Datos espaciales:** la convolución 2D y W11–W19 necesitan un conector de ráster; decidir si entra en esta versión.
5. **Auditoría independiente** pendiente de W01–W03 y de todo lo nuevo; todo está en estado `candidate`.
6. JSON Schema y fixtures generados en `docs/plan-maestro/schemas/` (ver su README); regenerarlos si cambia `contracts.py`.
7. `fire/fwi.py`: verificado contra xclim y corregido (ver etapa F). Las clases de peligro no están implementadas: requieren umbrales validados por región.
8. `models/tests/test_climatology.py` pasa (33 tests, `robust_z` coherente). Ningún test cuenta los métodos del registro. `services/test_assistant.py` no se corrió (es del asistente de JP).
12. `drought_spi` con POWER a escala 1 da mínimos de −4,75 (meses secos con ceros): revisar en la auditoría el ajuste gamma con ceros.
9. Desvíos de la fase 2: el paso `fdr` de `relationship` lo hace `decision.py` con `fdr_bh` (W06); `seasonality` informa coeficientes armónicos, amplitud espectral anual y rango STL; `change_point` calcula medias por tramo con NumPy sobre las anomalías (descriptivo); no hay `cusum`; `extreme_events` con hipótesis `threshold` compara un estadístico de la serie.
10. Desvíos respecto del plan 23: sin paso `lttb` en `describe`; `lag1_autocorrelation` acepta `groups`; código de error `CADENCE_INCOMPATIBLE`; el pronóstico es un único método registrado (`forecast_backtest`).
11. Avisos de Git sobre LF/CRLF: inofensivos.

## Flujo de trabajo para completar el motor de backend

Orden pensado para no quedar bloqueados: primero lo que no depende de nadie (A), en paralelo se prepara la decisión científica (B), y lo grande o lo que depende de datos reales va después (C–F). Cada función nueva o cambiada sigue el protocolo de una función por solicitud de `PY/models/AGENTS.md`. Verificación: a mano (llamada a `data_handler.run` con un pedido real + prueba en la interfaz), sin suites automáticas.

### Etapa A — Sin esperar decisiones (Ema + Claude) — **HECHA (2026-11-15)**: schemas y fixtures generados y validados, los 3 structs probados (y corregido `spatial_pattern`), `test_climatology.py` pasa
1. **Contratos:** correr `contracts.export_schemas()` y guardar los JSON Schema de request/response y un par de fixtures reales (el pedido de Villa Mercedes) en `docs/plan-maestro/schemas/`. Listo cuando el frontend y el chat puedan validar contra ellos.
2. **Probar los 3 structs sin verificar**, uno por vez, con datos que los cubran:
   - `drought_spi`: precipitación mensual de POWER o PMRA, ≥ 30 años (la base 1991–2020 lo pide).
   - `precipitation_indices`: CHIRPS diario o ERA5 diario, años calendario completos (CHIRPS diario admite hasta 366 días: usar ERA5 si CHIRPS no responde).
   - `spatial_pattern`: un polígono (provincia por nombre) con una fuente que acepte área.
   Listo cuando los tres den `completed` y el texto del panel se lea bien. Corregir errores sin rediseñar.
3. **Tests desactualizados:** ajustar los conteos del registro en los tests de `models/` y revisar `tests/test_climatology.py` (no correr la suite completa, decisión del equipo; solo dejarlos coherentes).

### Etapa B — Valores científicos (D-03) — **HECHA con valores propuestos (2026-11-15)**: ver la tabla de parámetros arriba. Si la ingeniera valida o cambia algún valor, editar `by_value`/`default` en `analysis_structs.py` y quitar `provisional` y `_PROPOSED` de ese parámetro. Pasos originales:
1. Armar una planilla para la ingeniera química con cada parámetro obligatorio y provisional: qué controla, valor actual, rango típico en la literatura y efecto observado (ej.: `penalty` 10 → 7 cortes en la serie mensual cruda).
2. La ingeniera define valores por fenómeno o por cadencia. Registrar la decisión en `21_RIESGOS_Y_DECISIONES.md`.
3. Cargar los valores en `PY/handlers/analysis_structs.py`: los obligatorios pasan a tener `default` (dejan de ser `required`), los confirmados pierden la marca `provisional`. Mismo cambio visible en el formulario (y en `analysisCatalog` del chat, que sale de `capabilities()`).
4. Decidir junto con esto si `change_point` corre sobre anomalías (sin ciclo estacional) en vez de la serie cruda. Si sí: agregar el paso de desestacionalización al struct (método ya existente, sin fórmulas en el handler).
Listo cuando ningún análisis exija un número que el usuario no sabe elegir.

### Etapa C — Tolerancias del pronóstico (D-21) — **HECHA con valores propuestos (2026-11-15)**
Backtest real (San Luis, Córdoba, Buenos Aires, Salta × T2M/PRECTOTCORR × horizonte 1/6, 1991–2024): con el criterio viejo (skill > 0, cobertura «medida») 9 de 16 salían validados con mejoras de 1–2 % e intervalos que cubrían 56–78 % para un nominal de 90 %. Criterios nuevos en `models/forecasting/pipeline.py`: `validated_forecast` exige mejora del MAE ≥ `min_skill` (0,05, parámetro provisional del struct) sobre la mejor referencia en **cada** paso, y el intervalo solo es `calibrated` si la cobertura fuera de muestra es ≥ nivel − 2·√(nivel·(1−nivel)/n_test) (tolerancia binomial unilateral; `interval.coverage_floor`). Resultado: 2 de 16 validados (lluvia Córdoba h1, temperatura Buenos Aires h1); 2 intervalos marcados como subcubiertos. El panel ya no presenta un intervalo no calibrado como incertidumbre. `horizon_validated` = pasos con mejora ≥ `min_skill`; `horizon_positive_skill` = pasos con mejora > 0. Pasos originales:
1. Correr `forecast` sobre 5–10 series reales (temperatura y precipitación, varias cadencias) y anotar habilidad, cobertura empírica y horizonte validado de cada una.
2. Con esos números, el equipo fija orígenes de backtest, tolerancia de cobertura y umbral de habilidad (piso: habilidad > 0, T11). Cargarlos en `analysis_handler.py`/`forecast_backtest`.
Listo cuando `validated_forecast` tenga criterios documentados y no provisionales.

### Etapa D — Datos espaciales (decisión de alcance primero)
1. **Decidir** si la versión de la hackatón incluye análisis sobre mapas. Si no: documentarlo como fuera de alcance y saltar a E.
2. Si sí: conector de ráster (rasterio ya es dependencia) que entregue una grilla recortada al polígono, empezando por una fuente que ya se descarga en ráster (CHIRPS mensual).
3. Registrar en `catalog_registry.py` y crear structs, una función por vez: convolución 2D / FIR 2D (`signal/convolution2d.py`) primero, después W11, W12, W14, W15, W16, W19 según qué datos entregue el conector. `fire/fwi.py` necesita varias variables diarias (temperatura, humedad, viento, lluvia): requiere un pedido multivariable de ERA5.
Listo cuando cada struct nuevo dé `completed` con datos reales.

### Etapa E — Pasos faltantes del plan 23 — **HECHA (2026-11-15)**
- `cusum`: método nuevo `cusum_reference` (`models/change_detection/cusum.py`), CUSUM tabular estandarizado con media y desvío de la base de referencia, k = 0,5 y h = 5 (Montgomery; provisionales). `change_point` con `method="cusum"` informa fecha y lado de cada alarma (sin medias entre alarmas: el acumulador se reinicia). San Luis T2M 1991–2024: 6 alarmas, 2020 y 2023 por encima de la base.
- `lttb` en `describe`: **descartado** (el frontend grafica la serie completa; no tendría consumidor).
- `event_composite` y `percentile_thresholds`: siguen sin registrar porque ningún struct los usa.
Pasos originales:
- `lttb` en `describe` para reducir series largas en vez de omitirlas.
- `cusum` en `change_point`: solo si B fija baseline, allowance y threshold.
- Registrar `event_composite` y `percentile_thresholds` (W04) si algún struct los necesita.

### Etapa F — Validación — **FWI HECHO (2026-11-15); auditoría independiente pendiente**
- `fire/fwi.py` v1.1.0 comparado día por día contra xclim 1.0.0 (entorno aparte, no es dependencia del proyecto) en latitudes −45, −24,8, 0, 22 y 46: FFMC, DC e ISI exactos; DMC/BUI/FWI < 0,006 (forma GFWED de la Ec. 15). Se corrigieron dos errores: el ISI multiplicaba por el viento en vez de `exp(0,05039·W)` (FWI ~3,6 veces más alto) y las tablas de duración del día (septiembre 9,4; bandas sur de GFWED/cffdrs; ya no rechaza |lat| < 30°). Sigue sin struct (necesita varias variables diarias).
Pasos originales:
1. **Auditoría independiente** (alguien distinto del autor) de W01–W03 y de todo lo nuevo, con referencia externa por método. Cambiar el estado de `candidate` solo con esa firma (D-08).
2. `fire/fwi.py`: comparar con las tablas de referencia del FWI canadiense y revisar el rechazo de |lat| < 30°.

### Regla general
Ante cualquier error al probar: corregir el módulo afectado sin rediseñar y sin tocar el asistente de JP salvo pedido. Antes de cada etapa, arrancar la app con el comando de arriba.
