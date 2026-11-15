# Conectores de grillas — estado de implementación

Registro con IDs exactos de variables, despacho, límites de memoria, POWER mensual y Open-Meteo ERA5 diario implementados. Sin cambios al contrato. NaN para faltantes, máscara por centro mediante inside_area, unidades recibidas conservadas. Los meses representan el mes que contiene la fecha inicial; POWER excluye el agregado anual (mes 13).

## Fuentes y límites verificados

- [POWER mensual](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/): una variable por solicitud regional; meteorología MERRA-2 desde 1981. Una consulta real sobre San Luis para 2000 confirmó FeatureCollection, centros separados 0,5° lat / 0,625° lon, fill_value=-999, units=C y mes 13 anual. API v2.10.0. PRECTOTCORR conserva tasa media diaria, no suma mensual.
- Pendiente: confirmar límite espacial actual en documentación oficial POWER. No se declara max_bbox_deg porque el conocido 4,5° aparece en fuentes secundarias y no se pudo corroborar en la página mensual actual. No se recorta silenciosamente: se exige respuesta con todos los centros esperados.
- [Open-Meteo Archive](https://open-meteo.com/en/docs/historical-weather-api): múltiples coordenadas separadas por comas; lista de respuestas; ERA5 0,25°; elevation=nan desactiva ajuste altitudinal. Se pide models=era5, cell_selection=nearest y GMT. Se rechaza cualquier desplazamiento de centros: no se regrilla.
- [Respuesta del proyecto sobre múltiples coordenadas](https://github.com/open-meteo/open-meteo/issues/1295): hasta 1000 ubicaciones por llamada. Lote operativo de 10, no presentado como límite oficial.
- [Cuotas gratuitas](https://open-meteo.com/en/pricing): 600 llamadas/minuto, 5000/hora, 10000/día, 300000/mes; uso no comercial. El costo cuenta ubicaciones y duración, no solamente solicitudes HTTP. PENDIENTE implementar contabilidad y regulación de cuota; el lote pequeño por sí solo no garantiza respetarla. No ejecutar cargas grandes hasta completar este punto.
- Se reutiliza request_json del servicio existente: timeout 25 s por llamada; no se agregan dependencias.

## Verificación y pendientes

El venv solicitado falla antes de importar código: `No Python at ...Python311/python.exe`. No se ejecutaron validaciones Python ni se generaron fixtures. Una consulta POWER mediante PowerShell fuera del sandbox respondió correctamente; esto no reemplaza la ejecución del conector. manual_check.py está preparado para POWER 2000–2024 y Open-Meteo 2023 sobre San Luis. CHIRPS opcional no implementado.

## Pedidos a Claude

Reparar el intérprete base del venv indicado o indicar otro Python autorizado. Luego ejecutar manual_check y resolver cualquier incompatibilidad real antes de integrar. Faltan confirmar límite regional POWER y regular cuotas Open-Meteo. No requiere cambios al contrato por ahora.

## Pedidos a JP

Ninguno.
