import coverageCatalog from '../../../src-tauri/src-python/trend_scope/services/source-coverage.json' with { type: 'json' };

export const providers = [
  { id: 'nasa.power.monthly', label: 'NASA POWER', provider: 'NASA', hint: 'Usa un punto del mapa' },
  { id: 'noaa.ncei.station', label: 'NOAA NCEI', provider: 'NOAA', hint: 'Busca estaciones con datos de la variable y las fechas elegidas.' },
  { id: 'nasa.swot.hydrocron', label: 'NASA SWOT / Hydrocron', provider: 'NASA', hint: 'Busca un tramo o lago según la selección del mapa' },
  { id: 'openmeteo.archive.daily', label: 'Open-Meteo · ERA5 / ERA5-Land', provider: 'ECMWF', hint: 'Series diarias por punto, sin cuenta para uso no comercial' },
  { id: 'noaa.ncei.daily', label: 'NOAA NCEI diario', provider: 'NOAA', station: true, hint: 'Busca estaciones con datos de la variable y las fechas elegidas.' },
  { id: 'noaa.oisst.daily', label: 'NOAA OISST', provider: 'NOAA', geometry: ['Point'], hint: 'Usa un punto en el mar' },
  { id: 'noaa.cpc.oni', label: 'NOAA ENSO · ONI / RONI', provider: 'NOAA', hint: 'Índice para la región Niño 3.4' },
  { id: 'usgs.earthquakes', label: 'USGS · Sismos', provider: 'USGS', geometry: ['Polygon', 'MultiPolygon'], hint: 'Usa un polígono' },
  { id: 'nasa.firms.area', label: 'NASA FIRMS', provider: 'NASA', geometry: ['Polygon', 'MultiPolygon'], product: 'Sensor FIRMS', hint: 'Usa un polígono y requiere FIRMS_MAP_KEY' },
  { id: 'nasa.appeears', label: 'NASA AppEEARS', provider: 'NASA', geometry: ['Point', 'Polygon', 'MultiPolygon'], product: 'Producto y versión', hint: 'Extracción por punto o área con Earthdata Login' },
  { id: 'nasa.earthdata', label: 'NASA Earthdata · CMR', provider: 'NASA', geometry: ['Point', 'Polygon', 'MultiPolygon'], product: 'ID de colección CMR', codeLabel: 'Archivo completo', defaultCode: 'all', hint: 'Descarga gránulos originales por fechas y zona. Usá all para todas las variables del archivo.' },
  { id: 'copernicus.dataspace', label: 'Copernicus Data Space · Sentinel', provider: 'ESA', geometry: ['Point', 'Polygon', 'MultiPolygon'], product: 'Colección (ej. SENTINEL-2)', codeLabel: 'Tipo de producto (ej. S2MSI2A)', hint: 'Descarga escenas Sentinel con CDSE_ACCESS_TOKEN' },
  { id: 'copernicus.cds', label: 'Copernicus Climate Data Store', provider: 'ECMWF', disabled: true },
  { id: 'microsoft.planetary.stac', label: 'Planetary Computer · STAC', provider: 'Microsoft', geometry: ['Point', 'Polygon', 'MultiPolygon'], product: 'Colección STAC (ej. landsat-c2-l2)', codeLabel: 'Clave del activo STAC', hint: 'Descarga bandas y archivos originales. Usá all para los activos de datos.' },
  { id: 'argentina.ina.series', label: 'INA · Datos hidrológicos', provider: 'INA', hint: 'Busca una serie hidrológica según el área o punto y las fechas' },
  { id: 'psmsl.rlr.monthly', label: 'PSMSL · Mareógrafos', provider: 'PSMSL', hint: 'Busca un mareógrafo para la selección y el período' },
  { id: 'ucsb.chirps.monthly', label: 'CHIRPS v3 · UCSB', provider: 'UCSB', geometry: ['Point', 'Polygon', 'MultiPolygon'], hint: 'Precipitación mensual sobre tierra entre 60° S y 60° N desde 1981.', catalogOnly: true },
  { id: 'argentina.pmra.monthly', label: 'PMRAv1 · Argentina', provider: 'Gaitán y Biancari', geometry: ['Point', 'Polygon', 'MultiPolygon'], hint: 'Precipitación mensual de Argentina en celdas de 5 km. Las fechas dependen del archivo publicado.', catalogOnly: true },
  { id: 'ucsb.chirps.daily', label: 'CHIRPS v3 diario · ERA5', provider: 'UCSB', geometry: ['Point', 'Polygon', 'MultiPolygon'], hint: 'Precipitación diaria estimada. Consultas de hasta 366 días.', catalogOnly: true },
  { id: 'noaa.ersst.monthly', label: 'NOAA ERSST v5', provider: 'NOAA', geometry: ['Point'], hint: 'Temperatura mensual del mar a 2° desde 1854.' },
  { id: 'nasa.power.solar.area', label: 'NASA POWER · Radiación regional', provider: 'NASA', geometry: ['Polygon', 'MultiPolygon'], catalogOnly: true },
  { id: 'noaa.etopo.area', label: 'NOAA ETOPO1 · Batimetría', provider: 'NOAA', geometry: ['Polygon', 'MultiPolygon'], catalogOnly: true },
  { id: 'nasa.power.temperature.area', label: 'NASA POWER · Temperatura regional', provider: 'NASA', geometry: ['Polygon', 'MultiPolygon'], catalogOnly: true }
];

export const geographicEntityRoutes = new Set([
  'noaa.ncei.station', 'noaa.ncei.daily', 'nasa.swot.hydrocron', 'argentina.ina.series', 'psmsl.rlr.monthly'
]);
export const entityGeometries = ['Point', 'Polygon', 'MultiPolygon'];

export function providerGeometries(route) {
  if (!route) return [];
  if (geographicEntityRoutes.has(route.id)) return entityGeometries;
  return route.geometry ?? (['nasa.power.monthly', 'openmeteo.archive.daily'].includes(route.id) ? ['Point'] : []);
}

export function providerMatchesScope(route, scope) {
  if (route?.disabled) return false;
  if (!scope || scope === 'both') return true;
  const geometries = providerGeometries(route);
  return !geometries.length || geometries.some(type => geometryMatchesScope(type, scope));
}

export function geometryMatchesScope(type, scope) {
  return !scope || scope === 'both' || (scope === 'point' ? type === 'Point' : type !== 'Point');
}

export function sourceMatchesScope(source, scope, features) {
  const route = providers.find(item => item.id === source.access);
  const geometry = features.find(item => item.id === source.upstream?.geometryId)?.geometry;
  return (!route || providerMatchesScope(route, scope)) && (!geometry || geometryMatchesScope(geometry.type, scope));
}

export const catalog = [
  ['power-precipitation', 0, 'Precipitación media diaria por mes', 'precipitation', 'PRECTOTCORR'],
  ['power-humidity', 0, 'Humedad relativa del aire', 'relative-humidity', 'RH2M'],
  ['era5-snowfall', 3, 'Nieve caída diaria (ERA5)', 'snowfall', 'snowfall_sum'],
  ['era5-snow-depth', 3, 'Espesor medio diario de nieve (ERA5-Land)', 'snow-depth', 'snow_depth'],
  ['firms-fire-count', 8, 'Detecciones térmicas diarias (FIRMS VIIRS)', 'fire-detections', 'count'],
  ['power-wind', 0, 'Velocidad del viento a 2 m', 'wind-speed', 'WS2M'],
  ['power-soil', 0, 'Humedad de la zona radicular', 'soil-moisture', 'GWETROOT'],
  ['etopo-bathymetry', 21, 'Distribución de profundidad submarina (NOAA ETOPO1)', 'bathymetry', 'depth'],
  ['power-solar-area', 20, 'Irradiancia solar de superficie mensual (NASA POWER)', 'solar-radiation', 'ALLSKY_SFC_SW_DWN'],
  ['power-solar', 0, 'Radiación solar en superficie', 'solar-radiation', 'ALLSKY_SFC_SW_DWN'],
  ['power-temperature-area', 22, 'Temperatura media mensual del aire a 2 m (NASA POWER)', 'temperature', 'T2M'],
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
  ['era5-et0', 3, 'Evapotranspiración de referencia ET₀ (ERA5)', 'reference-et', 'et0_fao_evapotranspiration'],
  ['noaa-daily-precipitation', 4, 'Precipitación diaria de estación', 'precipitation', 'PRCP'],
  ['noaa-daily-max', 4, 'Temperatura máxima diaria de estación', 'temperature-max', 'TMAX'],
  ['noaa-daily-min', 4, 'Temperatura mínima diaria de estación', 'temperature-min', 'TMIN'],
  ['oisst-sst', 5, 'Temperatura superficial del mar', 'sea-surface-temperature', 'sst'],
  ['oisst-anomaly', 5, 'Anomalía de temperatura del mar', 'sea-surface-temperature-anomaly', 'anom'],
  ['oisst-error', 5, 'Error estimado de temperatura del mar', 'sea-surface-temperature-error', 'err'],
  ['oni', 6, 'Índice oceánico de El Niño', 'oni', 'anomaly'],
  ['roni', 6, 'Índice oceánico relativo de El Niño (RONI)', 'roni', 'roni'],
  ['oni-sst', 6, 'Temperatura media móvil Niño 3.4', 'nino34-temperature', 'total'],
  ['usgs-count', 7, 'Detecciones sísmicas diarias', 'earthquake-count', 'count'],
  ['usgs-magnitude', 7, 'Magnitud de sismos', 'earthquake-magnitude', 'magnitude'],
  ['oisst-ice', 5, 'Concentración de hielo marino', 'sea-ice-concentration', 'icec'],
  ['usgs-depth', 7, 'Profundidad de sismos', 'earthquake-depth', 'depth'],
  ['ina-height', 14, 'Altura hidrométrica', 'water-level', 'var-2'],
  ['ina-discharge', 14, 'Caudal', 'river-discharge', 'var-4'],
  ['ina-precipitation', 14, 'Precipitación diaria (12Z)', 'precipitation', 'var-1'],
  ['psmsl-level', 15, 'Nivel relativo del mar (RLR mensual)', 'relative-sea-level', 'rlr'],
  ['chirps-mean-daily-rain', 16, 'Lluvia media diaria por mes (CHIRPS v3)', 'mean-daily-rain', 'precipitation_daily_mean'],
  ['chirps-monthly-precipitation', 16, 'Precipitación acumulada mensual (CHIRPS v3)', 'precipitation', 'precipitation'],
  ['pmra-monthly-precipitation', 17, 'Precipitación acumulada mensual (PMRAv1)', 'precipitation', 'precipitation'],
  ['chirps-daily-precipitation', 18, 'Precipitación acumulada diaria (CHIRPS v3)', 'precipitation', 'precipitation'],
  ['era5-temperature', 3, 'Temperatura media del aire a 2 m', 'temperature', 'temperature_2m_mean'],
  ['era5-humidity', 3, 'Humedad relativa del aire a 2 m', 'relative-humidity', 'relative_humidity_2m_mean'],
  ['era5-wind', 3, 'Velocidad media del viento a 10 m', 'wind-speed', 'wind_speed_10m_mean'],
  ['era5-solar', 3, 'Radiación solar de onda corta', 'solar-radiation', 'shortwave_radiation_sum'],
  ['era5-pressure', 3, 'Presión media a nivel del mar', 'sea-level-pressure', 'pressure_msl_mean'],
  ['era5-snow', 3, 'Nieve caída', 'snowfall', 'snowfall_sum'],
  ['era5-cloud', 3, 'Nubosidad media', 'cloud-cover', 'cloud_cover_mean'],
  ['ersst-sst', 19, 'Temperatura superficial mensual del mar', 'sea-surface-temperature', 'sst']
].map(([id, index, label, variable, code, featureType]) => ({
  id, label, variable, code, featureType, route: providers[index]
}));

export const assistantCatalog = catalog.filter(item => [
  'nasa.power.monthly', 'noaa.ncei.station', 'nasa.swot.hydrocron', 'openmeteo.archive.daily',
  'ucsb.chirps.monthly', 'ucsb.chirps.daily', 'argentina.pmra.monthly', 'noaa.cpc.oni', 'usgs.earthquakes', 'nasa.firms.area', 'nasa.power.solar.area', 'noaa.etopo.area', 'nasa.power.temperature.area', 'noaa.ersst.monthly'
].includes(item.route.id));

const comparableVariables = {
  'noaa-temperature': 'temperature-mean',
  'power-temperature': 'temperature-mean',
  'era5-temperature': 'temperature-mean',
  'power-humidity': 'humidity-mean',
  'era5-humidity': 'humidity-mean',
  'era5-precipitation': 'precipitation-total',
  'chirps-monthly-precipitation': 'precipitation-total',
  'pmra-monthly-precipitation': 'precipitation-total',
  'noaa-precipitation': 'precipitation-total',
  'noaa-daily-precipitation': 'precipitation-total',
  'noaa-daily-max': 'temperature-max',
  'era5-max-temperature': 'temperature-max',
  'noaa-daily-min': 'temperature-min',
  'era5-min-temperature': 'temperature-min',
  'era5-solar': 'solar-energy',
  'era5-pressure': 'sea-level-pressure',
  'era5-cloud': 'cloud-cover',
  'oisst-sst': 'sea-surface-temperature',
  'ersst-sst': 'sea-surface-temperature',
  'era5-soil-surface': 'soil-moisture-0-7',
  'era5-soil-shallow': 'soil-moisture-7-28',
  'era5-soil-root': 'soil-moisture-28-100',
  'era5-soil-deep': 'soil-moisture-100-255',
};
const variableLabels = {
  'temperature-mean': 'Temperatura media del aire',
  'humidity-mean': 'Humedad relativa del aire',
  'temperature-max': 'Temperatura máxima diaria',
  'temperature-min': 'Temperatura mínima diaria',
  'precipitation-total': 'Precipitación acumulada',
  'solar-energy': 'Radiación solar de onda corta',
  'sea-surface-temperature': 'Temperatura superficial del mar'
};
const mainWeatherVariables = ['temperature-mean', 'precipitation-total', 'temperature-max', 'temperature-min', 'humidity-mean'];
export const variableCategories = [
  ['weather', 'Clima'],
  ['soil', 'Suelo'],
  ['water', 'Ríos, lagos y mareógrafos'],
  ['ocean', 'Océano y El Niño'],
  ['earthquakes', 'Sismos']
];

function variableCategory(item) {
  if (item.route.id === 'argentina.ina.series' || item.route.id === 'nasa.swot.hydrocron'
    || item.route.id === 'psmsl.rlr.monthly') return 'water';
  if (item.route.id === 'usgs.earthquakes') return 'earthquakes';
  if (item.variable === 'soil-moisture') return 'soil';
  if (item.variable.startsWith('sea-surface-') || item.variable === 'sea-ice-concentration'
    || item.route.id === 'noaa.cpc.oni') return 'ocean';
  return 'weather';
}
const coverageProducts = coverageCatalog.products;
const coverageFor = item => coverageProducts.find(product => product.access === item.route.id
  && product.variables.includes(item.code) && (!item.featureType || item.featureType === product.selection));

function withinLatitude(geometry, limit) {
  if (geometry.type === 'Point') return Math.abs(geometry.coordinates[1]) <= limit;
  const rings = geometry.type === 'Polygon' ? geometry.coordinates : geometry.coordinates.flat();
  return rings.every(ring => ring.every(([, latitude]) => Math.abs(latitude) <= limit));
}

export function coverageProblem(item, time, geometry, today = new Date()) {
  const product = coverageFor(item);
  if (!product || !time.start || !time.end || time.start > time.end) return '';
  const start = product.from ?? product.collectionFrom;
  const end = new Date(today);
  end.setUTCDate(end.getUTCDate() - (product.publicationLagDays ?? 0));
  const through = product.through ?? (product.endRule === 'previous-calendar-year'
    ? (today.getUTCFullYear() - 1) + '-12-31' : end.toISOString().slice(0, 10));
  if (time.start < start || time.end > through) return `Cobertura publicada: ${start} a ${through}.`;
  if (product.maxDays && (Date.parse(time.end) - Date.parse(time.start)) / 86400000 + 1 > product.maxDays) {
    return `La fuente admite hasta ${product.maxDays} días por consulta.`;
  }
  if (product.latitudeLimit && geometry && !withinLatitude(geometry, product.latitudeLimit)) {
    return `La fuente cubre entre ${product.latitudeLimit}° S y ${product.latitudeLimit}° N.`;
  }
  return '';
}

export function variableOptions(scope, time, geometry, today = new Date()) {
  const grouped = new Map();
  for (const item of catalog) {
    const types = providerGeometries(item.route);
    if (!providerMatchesScope(item.route, scope) || (types.length && geometry && !types.includes(geometry.type))) continue;
    const key = comparableVariables[item.id] ?? item.id;
    const option = grouped.get(key) ?? { id: key, label: variableLabels[key] ?? item.label,
      category: variableCategory(item), choices: [] };
    option.choices.push(item);
    grouped.set(key, option);
  }
  return [...grouped.values()].map(option => {
    const valid = option.choices.filter(item => !coverageProblem(item, time, geometry, today));
    const rank = item => {
      if (item.route.id === 'openmeteo.archive.daily') return 0;
      if (item.route.id === 'ucsb.chirps.monthly') return 1;
      if (item.route.id === 'ucsb.chirps.daily') return 3;
      return 4;
    };
    const candidate = valid.sort((a, b) => rank(a) - rank(b))[0];
    return { id: option.id, label: option.label, category: option.category, item: candidate,
      problem: candidate ? '' : coverageProblem(option.choices[0], time, geometry, today) };
  }).sort((a, b) => {
    const order = id => (mainWeatherVariables.indexOf(id) + 1 || Infinity);
    return order(a.id) - order(b.id) || a.label.localeCompare(b.label, 'es');
  });
}

export function legacyInaClimateVariable(source) {
  if (source.access !== 'argentina.ina.series' || !source.id.startsWith('argentina.ina.series:')) return null;
  const label = source.variable.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  if (label === 'temperatura media') return 'temperature-mean';
  if (label === 'precipitacion a intervalo nativo') return 'precipitation-total';
  return null;
}

export function sourceConfig(id) {
  const item = catalog.find(entry => entry.id === id);
  const { route, featureType } = item;
  const selectors = route.id === 'nasa.power.monthly' ? { community: 'AG' }
    : featureType ? { featureType, featureId: '' } : (route.id === 'noaa.ncei.station' || route.station) ? { stationId: '' } : {};
  return {
    id, variable: item.variable, provider: route.provider, product: route.label, access: route.id,
    upstream: { variableId: item.code, geometryId: null, selectors,
      ...(id === 'firms-fire-count' ? { productId: 'VIIRS_SNPP_SP' } : {}) }
  };
}
export function customSource(routeId, code, featureType, productId) {
  const route = providers.find(item => item.id === routeId);
  return {
    id: [routeId, featureType, productId, code].filter(Boolean).join(':'),
    variable: code, provider: route.provider, product: productId ? route.label + ' · ' + productId : route.label, access: routeId,
    upstream: {
      variableId: code, ...(productId ? { productId } : {}), geometryId: null,
      selectors: routeId === 'nasa.power.monthly' ? { community: 'AG' }
        : featureType ? { featureType, featureId: '' } : (routeId === 'noaa.ncei.station' || route.station) ? { stationId: '' } : {}
    }
  };
}
