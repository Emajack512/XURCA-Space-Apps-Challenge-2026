export const providers = [
  { id: 'nasa.power.monthly', label: 'NASA POWER', provider: 'NASA', hint: 'Usa un punto del mapa' },
  { id: 'noaa.ncei.station', label: 'NOAA NCEI', provider: 'NOAA', hint: 'Usa el identificador de una estación' },
  { id: 'nasa.swot.hydrocron', label: 'NASA SWOT / Hydrocron', provider: 'NASA', hint: 'Usa el identificador de un río o lago' },
  { id: 'openmeteo.archive.daily', label: 'Open-Meteo · ERA5 / ERA5-Land', provider: 'ECMWF', hint: 'Series diarias por punto, sin cuenta para uso no comercial' }
];

export const catalog = [
  ['power-precipitation', 0, 'Precipitación media diaria por mes', 'precipitation', 'PRECTOTCORR'],
  ['power-humidity', 0, 'Humedad relativa del aire', 'relative-humidity', 'RH2M'],
  ['power-wind', 0, 'Velocidad del viento a 2 m', 'wind-speed', 'WS2M'],
  ['power-soil', 0, 'Humedad de la zona radicular', 'soil-moisture', 'GWETROOT'],
  ['power-solar', 0, 'Radiación solar en superficie', 'solar-radiation', 'ALLSKY_SFC_SW_DWN'],
  ['power-temperature', 0, 'Temperatura del aire a 2 m', 'temperature', 'T2M'],
  ['noaa-precipitation', 1, 'Precipitación acumulada mensual', 'precipitation', 'PRCP'],
  ['noaa-temperature', 1, 'Temperatura media mensual', 'temperature', 'TAVG'],
  ['swot-river-elevation', 2, 'Altura del agua en río', 'water-elevation', 'wse', 'Reach'],
  ['swot-lake-elevation', 2, 'Altura del agua en lago', 'water-elevation', 'wse', 'PriorLake'],
  ['swot-lake-area', 2, 'Superficie de lago', 'water-area', 'area_total', 'PriorLake'],
  ['era5-soil-surface', 3, 'Humedad del suelo 0–7 cm (ERA5-Land)', 'soil-moisture', 'soil_moisture_0_to_7cm_mean'],
  ['era5-soil-shallow', 3, 'Humedad del suelo 7–28 cm (ERA5-Land)', 'soil-moisture', 'soil_moisture_7_to_28cm_mean'],
  ['era5-soil-root', 3, 'Humedad del suelo 28–100 cm (ERA5-Land)', 'soil-moisture', 'soil_moisture_28_to_100cm_mean'],
  ['era5-soil-deep', 3, 'Humedad del suelo 100–255 cm (ERA5-Land)', 'soil-moisture', 'soil_moisture_100_to_255cm_mean'],
  ['era5-max-temperature', 3, 'Temperatura máxima diaria (ERA5-Land)', 'temperature-max', 'temperature_2m_max'],
  ['era5-min-temperature', 3, 'Temperatura mínima diaria (ERA5-Land)', 'temperature-min', 'temperature_2m_min'],
  ['era5-precipitation', 3, 'Precipitación acumulada diaria (ERA5)', 'precipitation', 'precipitation_sum'],
  ['era5-et0', 3, 'Evapotranspiración de referencia ET₀ (ERA5)', 'reference-et', 'et0_fao_evapotranspiration']
].map(([id, index, label, variable, code, featureType]) => ({
  id, label, variable, code, featureType, route: providers[index]
}));

export function sourceConfig(id) {
  const item = catalog.find(entry => entry.id === id);
  const { route, featureType } = item;
  const selectors = route.id === 'nasa.power.monthly' ? { community: 'AG' }
    : featureType ? { featureType, featureId: '' } : route.id === 'noaa.ncei.station' ? { stationId: '' } : {};
  return {
    id, variable: item.variable, provider: route.provider, product: route.label, access: route.id,
    upstream: { variableId: item.code, geometryId: null, selectors }
  };
}
export function customSource(routeId, code, featureType) {
  const route = providers.find(item => item.id === routeId);
  return {
    id: [routeId, featureType, code].filter(Boolean).join(':'),
    variable: code, provider: route.provider, product: route.label, access: routeId,
    upstream: {
      variableId: code, geometryId: null,
      selectors: routeId === 'nasa.power.monthly' ? { community: 'AG' }
        : featureType ? { featureType, featureId: '' } : routeId === 'noaa.ncei.station' ? { stationId: '' } : {}
    }
  };
}
