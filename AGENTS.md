# XURCA Space Apps Challenge

Earth Detective (Trend Scope) es la aplicación de escritorio para investigar tendencias del sistema terrestre. La web de presentación vive en `web app/` y tiene sus propias instrucciones. `Memoria/` contiene los recursos del desafío.

## Aplicación

Trabajá desde `aplicacion/trend-scope/`. La interfaz usa SvelteKit con adaptador estático, Svelte 5, JavaScript y CSS. Tauri aloja la interfaz y PyTauri comunica JavaScript con Python. Usá los pasos de preparación del README de la aplicación.

- `src/routes/` compone el espacio de trabajo. `src/lib/components/` contiene paneles y controles reutilizables. Usá `src/lib/styles/` para variables y reglas visuales compartidas.
- `src/lib/stores/workspace.js` concentra el estado editable. Los controles modifican el estado por sus operaciones compartidas. `src/lib/services/` contiene presentación de datos, geografía, demostraciones y persistencia.
- `config/cfg_data.json` define la investigación. Guardá geometrías WGS 84 como GeoJSON con longitud antes de latitud. `config/cfg_visual.json` define paneles, cámara y gráficas, que referencian resultados por ID. Usá IDs estables y migraciones explícitas si cambia la versión de un esquema.
- `src-tauri/` contiene el host y la integración con Python. Accedé al almacenamiento a través del servicio de configuración y de comandos PyTauri específicos. Guardá credenciales por separado.
- El futuro modo asistido y los controles manuales operan sobre la misma configuración. Separá el cálculo científico de la presentación, y conservá las referencias y versiones que permitan reproducirlo. Marcá las simulaciones.
- Usá `pnpm dev` para la vista web y `pnpm tauri dev` desde el entorno virtual para escritorio. Antes de entregar cambios de interfaz, ejecutá `pnpm check` y `pnpm build` y probá el flujo afectado. Comprobá los cambios de IPC en la ventana nativa cuando el entorno lo permita.

`aplicacion/trend-scope/docs/SOUL.md` describe el comportamiento del futuro asistente científico.

## Fronteras de trabajo entre JP y Ema (leer antes de editar)

Trabajan en paralelo **tres agentes**: el **Codex de JP** (frontend y asistente), **Claude Code de Ema** (motor estadístico) y el **Codex de Ema** (solo `PY/raster/`, conectores de grillas; sus reglas están en `PY/raster/AGENTS.md` y trabaja en el worktree `XURCA-codex-raster`, rama `ema_codex_raster`). **Si sos el Codex de JP, `PY/raster/` no es tuyo ni del lado de JP: no lo edites.** Para no pisarse, cada archivo tiene un dueño. Rutas relativas a `aplicacion/trend-scope/`; `PY` = `src-tauri/src-python/trend_scope/`.

### Lado de JP — frontend general y asistente de IA (editable libremente por JP/Codex)
- `src/lib/components/Assistant.svelte`, `src/lib/services/assistantConfiguration.js` (+ su `.test.js`), `src/lib/assets/mascot/`.
- `PY/services/assistant-contract.json` y `PY/services/assistant*.py`, **excepto** `analysis_catalog()` y `check_analysis()` de `assistant.py` (leen del motor: ver frontera).
- `src/routes/+page.svelte`, `SettingsPanel`, mapa (`Globe`, `WorldMap`), geografía, búsqueda de lugares, `config/cfg_visual.json`.
- Fuentes de datos y cobertura: `src/lib/services/sources.js`, `PY/services/coverage.py`, `PY/services/source-coverage.json`, `PY/services/public_sources.py`, `PY/desktop.py` (comandos que no sean `run_analysis`/`list_analyses`).

### Lado de Ema — motor estadístico y análisis (NO editar sin avisar a Ema)
- `PY/handlers/` completo (`contracts`, `analysis_structs`, `analysis_handler`, `preparation`, `algorithm_handler`, `decision`, `data_handler`, `spatial`).
- `PY/models/` completo (motor científico; respetar `PY/models/AGENTS.md` y `PRESERVATION.json`).
- `src/lib/components/AnalysisPanel.svelte`, `ForecastChart.svelte`, `src/lib/services/analysisText.js`.
- `docs/plan-maestro/schemas/` (JSON Schema y fixtures de request/response).

### Lado de Ema — Codex de Ema (solo `PY/raster/`)
- `PY/raster/`: conectores de grillas (NASA POWER regional, ERA5 vía Open-Meteo, CHIRPS COG), fixtures y `NOTES.md`. Excepción: `PY/raster/contract.py` (`GridRequest`/`GridField`) es frontera congelada entre el Codex de Ema y Claude; se cambia solo de común acuerdo.
- Los mapas que el frontend dibuje a partir de estas grillas (componentes de mapa) siguen siendo de JP; el formato de las grillas en `response.json` lo define Claude en `contracts.py` y se avisa a JP antes de cambiarlo.

### Frontera — contrato compartido (cambiar solo de común acuerdo)
| Punto de contacto | Quién lo produce | Quién lo consume |
|---|---|---|
| `changes.analysis = {struct, targets, params, hypothesis}` | El modelo (instrucción de JP) | `check_analysis()` lo valida con `analysis_handler.resolve` (Ema) |
| `analysisCatalog` | `assistant.py::analysis_catalog()` desde `capabilities()` (Ema) | El prompt del chat (JP) |
| `analysisDigest` (= `response.assistant_digest`) | `data_handler`/`decision.py` (Ema) | El chat lo explica (JP) |
| `prepareInvestigation()` en `src/lib/services/acquisition.js` | JP | Panel de análisis y `data_handler.run()` (Ema) |
| `executeAnalysis()` en `src/lib/services/analysisRunner.js` + `src/lib/stores/analysis.js` | Compartido | Panel de análisis y botón «Ejecutar análisis» del chat |
| `request.json` / `response.json` | `PY/handlers/contracts.py` (Ema) | Todo el frontend; contrato formal en `docs/plan-maestro/schemas/` |

### Reglas
1. Editá solo tu lado. Si una tarea necesita tocar el otro lado o la frontera, detenete y avisá: describí el cambio necesario en vez de hacerlo.
2. **Presupuesto del prompt del asistente:** el worker acepta 30 000 caracteres (`PROMPT_LIMIT` 29 500). Hoy la instrucción + schema ocupan ~12 200, el catálogo de análisis ~2 500 y quedan ~14 800 para contexto y pregunta (el cliente recorta el contexto a 14 000). Alargar `assistant-contract.json` le quita lugar al contexto y a `analysisDigest`: medir antes de agregar texto.
3. Reglas científicas que el chat debe conservar: un análisis **nunca** se ejecuta solo (solo con el botón «Ejecutar análisis»); nunca un «porcentaje de certeza»; «no hay evidencia suficiente» nunca es «sin cambios»; asociación no es causalidad; un pronóstico solo es validado si su modo es `validated_forecast`; los valores marcados como propuestos/provisionales se mencionan como tales.
4. Desde 2026-11-15 **ningún parámetro de análisis es obligatorio**: el motor completa los valores según la cadencia y los informa como aviso. El chat no debe pedirle números técnicos al usuario; solo pasa en `params` lo que el usuario dijo explícitamente.
5. Si cambiás la forma de `investigation` (fuentes, geometrías, campos nuevos), avisá a Ema: afecta a `data_handler` y `spatial.py`.
6. Antes de subir a `main`: `git fetch` y revisar si el otro subió algo; nunca forzar push. No commitear `package.json`, `package-lock.json` ni `src-tauri/Cargo.toml` por cambios locales de entorno.
7. Arranque en Windows: exportar `VIRTUAL_ENV` al venv antes de `tauri dev` (ver `CLAUDE.md`).
