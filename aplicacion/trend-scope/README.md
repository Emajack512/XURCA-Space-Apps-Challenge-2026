# Earth Detective

Primera versión de la aplicación de escritorio de XURCA para el desafío Earth System Trend Detective. El mapa base es cartografía de Natural Earth a escala 1:110m. Las series, estadísticas, catálogos y conversación son ejemplos de demostración.

## Ejecutar en Windows

Desde esta carpeta, con Node.js, pnpm, Rust con toolchain MSVC, Microsoft C++ Build Tools, WebView2 y una instalación de Python compatible con PyTauri:

```powershell
pnpm install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .\src-tauri
$env:PYO3_PYTHON = (Get-Command python).Source
pnpm tauri dev
```

Tauri 2.8.3 se fija por compatibilidad con PyTauri 0.8. El archivo Cargo.lock conserva las versiones de las dependencias indirectas.

Para probar la interfaz en el navegador, usá `pnpm dev` y abrí `http://localhost:1420`. Este modo guarda la sesión en el almacenamiento del navegador. La aplicación nativa escribe `cfg_data.json` y `cfg_visual.json` en `%LOCALAPPDATA%\com.xurca.trend-scope`. El menú Proyecto permite guardar y recuperar ambos archivos. El menú Exportar permite descargar copias separadas.

## Recorrer la demostración

1. Configurá fuentes, período y métodos en el panel izquierdo.
2. Rotá el globo. Marcá puntos o vértices con las herramientas de la barra, o ingresá coordenadas con longitud y latitud. Para cerrar una región poligonal necesitás al menos tres vértices.
3. Ejecutá el análisis de demostración. Explorá series, histogramas, comparaciones y dispersión. Seleccioná una gráfica para editar su apariencia en el panel izquierdo.
4. Abrí Asistente IA y aplicá la propuesta de San Luis. La región dibujada es aproximada y los controles reflejan la propuesta.
5. Guardá y recuperá la configuración desde Proyecto.

`pnpm check` comprueba el frontend y `pnpm build` genera `dist/`. Ambos son independientes del empaquetado de Python. Para distribución nativa consultá `scripts/README.md`.

La interfaz usa D3 Geo y Natural Earth para el globo ortográfico, Chart.js para las gráficas y Lucide para los iconos. Las configuraciones base están en `config/`. Los recursos científicos del desafío están en `Memoria/General/Recursos_Earth_System_Trend_Detective.txt` desde la raíz del repositorio.
