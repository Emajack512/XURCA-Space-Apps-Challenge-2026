# Uso de Súper Inteligencia (SI) en el proyecto

Declaración del equipo XURCA (Acrux) para el NASA Space Apps Challenge 2026, según las reglas sobre el uso de herramientas de SI. Parte del **código y de los datos de configuración de este repositorio fue generada o modificada con asistencia de SI** y revisada por integrantes del equipo.

## Herramientas utilizadas

| Herramienta | Proveedor | Para qué se usó |
|---|---|---|
| Claude Code (modelo Claude Opus) | Anthropic | Generación y corrección de código de la app de escritorio: motor estadístico y manejadores de análisis en Python (`aplicacion/trend-scope/src-tauri/src-python/trend_scope/handlers/`, `models/`), interfaz Svelte (panel de análisis, tutorial, avisos, resumen de resultados), arreglos de errores reportados por testers y scripts de empaquetado. |
| Codex | OpenAI | Generación de código del asistente conversacional, la integración geográfica y los conectores de grillas ráster (`services/`, `raster/`, componentes del chat). |
| Gemini (gemini-3.5-flash-lite) | Google | **Dentro de la app**: el «Asistente de IA» interpreta lo que el usuario escribe y propone la configuración o el análisis. Sus respuestas son texto generado por SI y la app lo indica en el panel del asistente. No calcula resultados científicos: los cálculos los hace el motor estadístico en Python. |

## Qué no hizo la SI

- **Los resultados científicos no los genera la SI.** Los calcula el código Python con métodos estadísticos documentados (Mann-Kendall, Sen, SPI, PELT, regresión, pronóstico validado con backtest) sobre datos públicos descargados de sus fuentes originales (NASA POWER, CHIRPS, ERA5/Open-Meteo, NOAA, USGS y otras).
- Los valores por defecto de los análisis y los criterios del pronóstico fueron **revisados y aprobados por una ingeniera química del equipo**.
- Las pruebas de la app se hicieron a mano por integrantes del equipo y testers.
- No se usaron logotipos, banderas ni identificadores de misión de la NASA. Los nombres de productos de datos (por ejemplo «NASA POWER») aparecen solo para citar la fuente de los datos.

## Dónde queda registrado (metadatos)

- Este archivo (`USO_DE_IA.md`) y la sección «Uso de SI» del `README.md`.
- Los metadatos de los manifiestos del proyecto: `aplicacion/trend-scope/package.json` (`aiAssistance`), `aplicacion/trend-scope/src-tauri/Cargo.toml` (`[package.metadata.ai-assistance]`), `aplicacion/trend-scope/src-tauri/pyproject.toml` (`[tool.trendscope.ai-assistance]`) y la descripción del instalador en `tauri.conf.json`.
- En el historial de Git, los commits hechos con asistencia de Claude llevan la línea `Co-Authored-By: Claude …`.
