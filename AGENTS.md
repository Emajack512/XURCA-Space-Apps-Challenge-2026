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
