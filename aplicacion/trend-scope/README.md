# TrendScope — aplicación de escritorio

App de escritorio (Tauri + SvelteKit + Python con PyTauri) para descargar datos ambientales públicos, graficarlos y analizar sus tendencias. Fuentes: NASA POWER, CHIRPS, PMRA, ERA5 y ERA5-Land (Open-Meteo / Copernicus), NOAA, SWOT, USGS y otras.

## Usar la app (sin instalar nada más)

Ejecutá el instalador `TrendScope_0.1.0_x64-setup.exe` (o el `.msi`). Trae su propio Python con todas las dependencias y, si hace falta, instala WebView2. No requiere Python, Node ni Rust en la PC. Necesita conexión a internet para consultar las fuentes de datos.

## Preparar el entorno de desarrollo (Windows)

Requisitos: Node.js 20+, Rust con toolchain MSVC, Microsoft C++ Build Tools, WebView2 y Python 3.11–3.13.

Desde esta carpeta (`aplicacion/trend-scope`):

```powershell
npm install                                  # dependencias de JavaScript (o pnpm install)
python -m venv .venv                         # entorno de Python
.\.venv\Scripts\python.exe -m pip install -e .\src-tauri   # dependencias de Python (numpy, scipy, statsmodels, rasterio…)
```

Las dependencias de Rust las descarga `cargo` la primera vez que se compila (versiones fijadas en `Cargo.lock`; Tauri 2.8.3 por compatibilidad con PyTauri 0.8).

## Ejecutar en modo desarrollo

Doble clic en **Iniciar TrendScope.cmd**, o en PowerShell:

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path; $env:PATH = "$env:VIRTUAL_ENV\Scripts;$env:PATH"
.\node_modules\.bin\tauri.cmd dev
```

En Linux: `source .venv/bin/activate && pnpm tauri dev`.

## Generar el instalador

```powershell
.\scripts\windows\download-py.ps1   # solo la primera vez: baja el Python que va dentro del instalador
.\scripts\windows\build.ps1         # instala la app en ese Python y genera los instaladores
```

Los instaladores quedan en `target\bundle-release\bundle\nsis\` y `target\bundle-release\bundle\msi\`. Hay scripts equivalentes para Linux y macOS en `scripts/linux` y `scripts/macos`.

## Configuración

La app guarda `cfg_data.json` (consulta) y `cfg_visual.json` (apariencia) en `%LOCALAPPDATA%\com.xurca.trend-scope`. Los valores iniciales están en `config/`. El asistente de IA usa el servicio del equipo (`assistant-worker/`, Cloudflare Workers + Gemini).

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/` | Interfaz (SvelteKit): mapa, panel de configuración, chat, gráficas, análisis estadístico y tutorial. |
| `src-tauri/src/` | Contenedor de escritorio (Rust). |
| `src-tauri/src-python/trend_scope/services/` | Descarga y preparación de datos de cada fuente. |
| `src-tauri/src-python/trend_scope/handlers/` | Flujo de análisis: pedido → preparación → cálculo → respuesta. |
| `src-tauri/src-python/trend_scope/models/` | Motor científico (tendencias, anomalías, sequía, cambios, extremos, pronóstico, regresión, FWI…). |
| `src-tauri/src-python/trend_scope/raster/` | Conectores de grillas para los análisis sobre mapas. |
| `assistant-worker/` | Servicio del asistente de IA. |
| `scripts/` | Arranque en modo desarrollo y empaquetado. |
