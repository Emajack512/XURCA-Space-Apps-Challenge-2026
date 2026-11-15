# AGENTS.md — Codex de EMA · conectores de grillas (`raster/`)

## Quién sos (leer primero)

Sos el **Codex de Ema**, NO el de JP. En este repositorio trabajan tres agentes a la vez:

| Agente | Persona | Carril |
|---|---|---|
| Codex de JP | JP Marsi | frontend general, asistente de IA, fuentes y cobertura (`services/`) — ver `AGENTS.md` de la raíz |
| Claude Code | Ema | motor estadístico: `handlers/`, `models/`, panel de análisis |
| **Vos: Codex de Ema** | Ema | **solo este directorio: `trend_scope/raster/`** |

Las reglas de la raíz (`AGENTS.md`, sección «Fronteras de trabajo entre JP y Ema») también valen para vos: estás del **lado de Ema**, pero tu carril es más chico. Rutas abajo: `PY` = `aplicacion/trend-scope/src-tauri/src-python/trend_scope/`.

## Objetivo

Construir la capa que trae **campos espaciales en grilla** (mapas de valores) para que Claude haga análisis sobre mapas (tendencia por celda, anomalías, suavizado 2D, resúmenes de área). Vos entregás datos fieles; Claude hace la ciencia. Idioma: español rioplatense en mensajes y textos para el usuario; código y docstrings pueden ir en inglés.

## Qué podés editar

- Crear y editar archivos **dentro de `PY/raster/`**, excepto `contract.py` y este `AGENTS.md`.
- Nada más. **No toques** `PY/handlers/`, `PY/models/`, `PY/services/`, `PY/desktop.py`, `src/`, `config/`, `pyproject.toml`, `CLAUDE.md` ni el `AGENTS.md` de la raíz. Si necesitás algo de afuera, dejalo escrito en `PY/raster/NOTES.md` (sección «Pedidos a Claude» o «Pedidos a JP») y seguí con otra cosa.
- Podés **leer** todo el repositorio. Para reusar código de `services/` (por ejemplo `services/environmental_series.py::area_bounds`, `inside_area`, `read_text`; `services/public_sources.py::request_json`), importalo, no lo copies ni lo modifiques.

## Contrato congelado: `PY/raster/contract.py`

- `GridRequest` (lo que te piden) y `GridField` (lo que devolvés). Leé su docstring: convenciones de ejes, NaN, unidades y procedencia son obligatorias.
- **No lo cambies.** Si te falta un campo, anotalo en `NOTES.md` → «Pedidos a Claude» y usá `warnings` del `GridField` mientras tanto.
- Todo `GridField` que devuelvas debe pasar `field.validate()`.

## Qué tenés que entregar

1. `PY/raster/providers.py` con:
   - `PROVIDERS: dict[str, dict]` — por proveedor: `id`, `title`, `cadences`, `variables` (`{variable_id: {"name", "unit", "kind", "aggregation"}}`), `native_resolution_deg`, `max_bbox_deg` si el proveedor lo limita, `notes`.
   - `fetch_grid(request: GridRequest) -> GridField` — despacha al conector; valida el pedido; respeta `max_cells` y `max_values` (si se excede, `ValueError` en español explicando cuánto reducir; nunca recortar en silencio).
2. Un módulo por proveedor, en este orden de prioridad:
   1. **`power_regional.py`** — NASA POWER, endpoint regional mensual (`https://power.larc.nasa.gov/api/temporal/monthly/regional`), comunidad `AG`, variables al menos `T2M`, `PRECTOTCORR`, `RH2M`, `WS2M`. Verificá en la documentación oficial de POWER los límites del bbox y el formato de respuesta antes de codificar; **no los inventes**. `PRECTOTCORR` es tasa media diaria (mm/day), no acumulado mensual: decilo en `aggregation`. Es la fuente principal (responde bien desde la red de Ema).
   2. **`openmeteo_grid.py`** — ERA5 diario vía Open-Meteo Archive (`https://archive-api.open-meteo.com/v1/archive`) pidiendo **varias coordenadas en una sola llamada** (centros de una grilla regular de paso = resolución nativa de ERA5, 0,25°). Variables al menos `temperature_2m_mean`, `precipitation_sum`, `relative_humidity_2m_mean`, `wind_speed_10m_max`. Verificá en la documentación de Open-Meteo el máximo de coordenadas por llamada y los límites de uso; agrupá en lotes y respetalos. `kind="reanalysis"`.
   3. **`chirps_cog.py`** (opcional, último) — CHIRPS v3 mensual en GeoTIFF/COG con `rasterio` (ya es dependencia), leyendo solo la ventana del bbox. Ojo: `data.chc.ucsb.edu` **no responde desde la red de Ema** (timeout); el conector debe fallar con un mensaje claro y no colgar la app (timeout corto).
3. `PY/raster/manual_check.py` — script ejecutable (`python -m trend_scope.raster.manual_check`) que pide una grilla real chica por proveedor sobre San Luis, Argentina (bbox aprox. −67,0 −35,0 −65,0 −33,0; 2000–2024 mensual para POWER; 2023 diario para Open-Meteo), valida el `GridField` e imprime forma, rango de valores, cobertura y URLs. **No escribas tests de pytest** (decisión del equipo: verificación manual).
4. `PY/raster/fixtures/` — guardá **una** grilla real chica por proveedor (`.npz` + `.json` de metadatos) generada por `manual_check.py`, para que Claude pueda desarrollar sin red. Etiquetá el JSON con fecha de descarga y URL.
5. `PY/raster/NOTES.md` — qué hiciste, límites reales de cada API que verificaste (con link a la documentación), problemas encontrados y pedidos a Claude o a JP.

## Reglas científicas (de la ingeniera química y del equipo)

- NoData, nubes, fuera de cobertura → **NaN**, nunca 0. No interpolar huecos ni rellenar.
- No regrillar, no suavizar, no promediar celdas, no convertir unidades. Devolvé la grilla nativa del proveedor; si una celda del proveedor cae dentro del bbox, entra entera.
- `mask` según el centro de la celda dentro del polígono (`inside_area` de `services/environmental_series.py`).
- Distinguí bien la variable: temperatura del aire a 2 m ≠ temperatura de superficie (LST) ≠ temperatura del suelo. `variable_name` sin ambigüedad; `depth_range` para suelo.
- Toda grilla lleva `urls`, `retrieved_at` (UTC), `product`, `kind` y `native_resolution_deg`.
- Errores de red o del proveedor → `ValueError` con mensaje en español que nombre el host y qué hacer; timeouts cortos (≤ 45 s por llamada).

## Entorno y git

- Trabajás en el **worktree** `C:\Users\Victus\Desktop\nasa-hackathon\XURCA-codex-raster` (rama `ema_codex_raster`), NO en la carpeta principal del repo, donde trabaja Claude.
- Python: usá el venv del repo principal: `C:\Users\Victus\Desktop\nasa-hackathon\XURCA-Space-Apps-Challenge-2026\aplicacion\trend-scope\.venv\Scripts\python.exe`, ejecutando desde `aplicacion\trend-scope\src-tauri\src-python` **del worktree** para que importe tu código.
- No instales dependencias nuevas. Si una es imprescindible, pedila en `NOTES.md`.
- Hacé commits chicos en `ema_codex_raster` con mensajes en español. **Nunca** hagas push a `main` ni merge: Ema integra tu rama.
- No commitees `package.json`, `package-lock.json` ni `src-tauri/Cargo.toml`.

## TAREA 2 (2026-11-15) — nombre e ícono de la app compilada

La tarea 1 (conectores) ya fue integrada en `main`. Esta es una tarea nueva y acotada. **Solo para esta tarea** podés editar, además de `PY/raster/`:
- `aplicacion/trend-scope/src-tauri/tauri.conf.json` — **únicamente** el campo `productName`.
- `aplicacion/trend-scope/src-tauri/icons/` — los archivos de ícono.

Pasos:
1. En `tauri.conf.json` cambiá `"productName": "trend-scope"` por `"productName": "TrendScope"`. **No cambies** `identifier` (`com.xurca.trend-scope`): define dónde se guardan las configuraciones de cada usuario y cambiarlo les borra lo guardado. No cambies `version`, el título de la ventana («Earth Detective»), `Cargo.toml` ni `package.json`.
2. Copiá el ícono fuente `C:\Users\Victus\Downloads\app_icon_01.jpeg` (JPEG RGB, 1024 × 1024, ya es cuadrado) a `aplicacion/trend-scope/src-tauri/icons/source/app_icon_01.jpeg` para que quede versionado.
3. Convertilo a PNG 1024 × 1024 con Pillow (está en el venv del repo principal) en `icons/source/app_icon.png`. No lo recortes ni lo deformes.
4. Generá todos los tamaños con la CLI de Tauri usando los `node_modules` del repo principal (el worktree no los tiene):
   `C:\Users\Victus\Desktop\nasa-hackathon\XURCA-Space-Apps-Challenge-2026\aplicacion\trend-scope\node_modules\.bin\tauri.cmd icon <ruta del worktree>\aplicacion\trend-scope\src-tauri\icons\source\app_icon.png --output <ruta del worktree>\aplicacion\trend-scope\src-tauri\icons`
   Verificá con `tauri icon --help` el nombre exacto de la opción de salida antes de correrlo. Debe reemplazar `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`, `icon.png` y los `Square*Logo.png`/`StoreLogo.png`. Si genera carpetas extra (por ejemplo `android/` o `ios/`), borralas: la app es solo de escritorio.
5. Confirmá que la lista `bundle.icon` de `tauri.conf.json` sigue apuntando a archivos existentes (no la cambies si ya coinciden).
6. Si tu sandbox no puede ejecutar Python o la CLI, dejá los pasos que faltan escritos en `NOTES.md` → «Pedidos a Claude» en vez de improvisar otra herramienta.
7. Commit en `ema_codex_raster` con mensaje en español. Sin push ni merge.

Terminado cuando: `productName` es `TrendScope`, `identifier` no cambió, los íconos de `icons/` salen de `app_icon_01.jpeg` y el ícono fuente quedó en `icons/source/`.

## Cuándo está terminado (tarea 1)

`python -m trend_scope.raster.manual_check` corre sin errores para POWER y Open-Meteo (CHIRPS puede informar que no responde), los `GridField` pasan `validate()`, hay fixtures en `PY/raster/fixtures/` y `NOTES.md` documenta límites y pendientes.
