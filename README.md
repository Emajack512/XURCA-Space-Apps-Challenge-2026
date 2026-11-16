# TrendScope — XURCA (Acrux) · NASA Space Apps Challenge 2026

Desafío: **Earth System Trend Detective**. TrendScope es una aplicación de escritorio que permite a cualquier persona descargar datos ambientales públicos de fuentes oficiales, verlos en un mapa y en gráficas, y analizar con estadística si hay tendencias, anomalías, sequías, cambios de régimen o eventos extremos. Incluye un asistente conversacional y un tutorial guiado por nivel de experiencia.

## Contenido del repositorio

| Carpeta | Qué es |
|---|---|
| [`aplicacion/trend-scope/`](aplicacion/trend-scope/) | La app de escritorio (Tauri + SvelteKit + Python). Instalación, desarrollo y empaquetado en su [README](aplicacion/trend-scope/README.md). |
| [`web app/`](web%20app/) | Web de presentación del equipo (estática; se publica en Vercel usando esa carpeta como raíz). |

## Instalación rápida

- **Usuarios:** ejecutar el instalador de TrendScope (`.exe` o `.msi`). No requiere instalar Python, Node ni Rust.
- **Desarrollo:** ver [`aplicacion/trend-scope/README.md`](aplicacion/trend-scope/README.md): dependencias de JavaScript (`npm install`), de Python (`pip install -e src-tauri`) y de Rust (`cargo`, automático al compilar).

## Uso de SI

Parte del código fue generada con asistencia de herramientas de Súper Inteligencia (Claude Code, Codex) y revisada por el equipo, y el asistente de la app usa Gemini. Detalle en [`USO_DE_IA.md`](USO_DE_IA.md).

## Licencia

Ver [`LICENSE`](LICENSE).
