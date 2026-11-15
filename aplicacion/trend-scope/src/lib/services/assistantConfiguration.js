import contract from '../../../src-tauri/src-python/trend_scope/services/assistant-contract.json' with { type: 'json' };
import { assistantCatalog as catalog, sourceConfig, geographicEntityRoutes } from './sources.js';
import { closedRegion, validCoordinates } from './geography.js';

function checkShape(value, schema) {
  switch (schema.type) {
    case 'object':
      return value !== null && typeof value === 'object' && !Array.isArray(value)
        && (schema.required ?? []).every(key => Object.hasOwn(value, key))
        && Object.entries(value).every(([key, item]) =>
          Object.hasOwn(schema.properties, key) && checkShape(item, schema.properties[key]));
    case 'array':
      return Array.isArray(value) && value.every(item => checkShape(item, schema.items));
    case 'string':
      return typeof value === 'string' && value.length <= 1200 && (!schema.enum || schema.enum.includes(value));
    case 'number':
      return Number.isFinite(value);
    case 'integer':
      return Number.isInteger(value);
    case 'boolean':
      return typeof value === 'boolean';
    default:
      return false;
  }
}

function isoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function bounded(value, min, max) {
  return value === undefined || (value >= min && value <= max);
}

function validate(changes) {
  if (!checkShape(changes, contract.schema.properties.changes)) throw new Error('La IA propuso campos de configuración inválidos.');
  const { point, place, places, polygon, sources, appearance, workspace, camera } = changes;
  if ([point, place, places, polygon].filter(Boolean).length > 1) throw new Error('Indicá una sola selección geográfica por mensaje.');
  if (point && !validCoordinates(point.longitude, point.latitude)) throw new Error('Las coordenadas están fuera del rango WGS 84.');
  if (polygon && (polygon.length > 100 || !polygon.every(p => p.length === 2 && validCoordinates(...p)) || !closedRegion(polygon))) {
    throw new Error('El polígono requiere vértices válidos en orden longitud, latitud.');
  }
  if (sources && (sources.length > 25 || new Set(sources.map(item => JSON.stringify([item.id, item.pointId ?? '']))).size !== sources.length)) {
    throw new Error('La lista de fuentes contiene variables duplicadas o excede el catálogo.');
  }
  if (appearance?.accent !== undefined && !/^#[0-9a-f]{6}$/i.test(appearance.accent)) throw new Error('El color requiere un valor hexadecimal de seis dígitos.');
  if (appearance?.fontSize !== undefined && ![12, 13, 15].includes(appearance.fontSize)) throw new Error('El tamaño de texto debe ser 12, 13 o 15.');
  if (!bounded(workspace?.settingsWidth, 220, 450) || !bounded(workspace?.assistantWidth, 265, 600)) {
    throw new Error('El ancho propuesto está fuera del rango de los paneles.');
  }
  if (!bounded(camera?.longitude, -180, 180) || !bounded(camera?.latitude, -90, 90) || !bounded(camera?.zoom, 0.65, 1024)) {
    throw new Error('La posición o el zoom del mapa están fuera de rango.');
  }
}

const catalogEntry = source => catalog.find(entry => entry.id === source.id.split('::')[0]);

function configureSource(item, points, newPoint, existing) {
  const entry = catalog.find(source => source.id === item.id);
  if (!entry) throw new Error('Una variable propuesta no está en el catálogo: ' + item.id);
  const config = sourceConfig(item.id);
  if (config.access === 'noaa.cpc.oni') return config;
  const { upstream } = config;
  const compatible = geographicEntityRoutes.has(config.access)
    ? points : points.filter(item => (entry.route.geometry ?? ['Point']).includes(item.geometry.type));
  if (item.pointId && !compatible.some(point => point.id === item.pointId)) throw new Error('La selección indicada no existe.');
  const preferred = item.pointId || newPoint?.id || existing?.upstream.geometryId;
  const selection = compatible.find(item => item.id === preferred) ?? (compatible.length === 1 ? compatible[0] : null);
  if (!selection) throw new Error('Elegí una selección geográfica para ' + entry.label + '.');
  upstream.geometryId = selection.id;
  return config;
}

export async function configureWorkspace(snapshot, changes, invoke, language) {
  validate(changes);
  const next = JSON.parse(JSON.stringify(snapshot));
  const { data, visual } = next;
  for (const key of ['title', 'objective', 'description']) if (key in changes) data[key] = changes[key];
  if (changes.time) {
    const { start, end } = { ...data.time, ...changes.time };
    if (!isoDate(start) || !isoDate(end) || start > end) throw new Error('Ingresá fechas válidas en orden.');
    Object.assign(data.time, { start, end });
  }

  const selection = data.geography.selection;
  if (changes.clearSelection) {
    selection.features = [];
    for (const source of data.sources) source.upstream.geometryId = null;
  }
  if (changes.places && (!changes.places.length || changes.places.length > 10)) throw new Error('Indicá entre uno y diez lugares.');
  const pointsToAdd = changes.point ? [changes.point] : [];
  for (const { name, kind } of changes.places ?? (changes.place ? [changes.place] : [])) {
    if (name.trim().length < 2 || name.length > 100) throw new Error('Indicá un nombre de lugar válido.');
    const found = JSON.parse(await invoke('search_places', { query: name, kind, language }));
    const normalize = text => (text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    const parts = name.split(',').map(normalize).filter(Boolean);
    const exact = found.filter(match => normalize(match.name) === parts[0]
      && parts.slice(1).every(part => [match.province, match.country].some(value => normalize(value) === part)));
    if (!exact.length && found.length === 1) {
      const candidate = found[0];
      throw new Error('No pude confirmar ' + name + '. El buscador devolvió: '
        + [candidate.name, candidate.province, candidate.country].filter(Boolean).join(', ') + '. Precisá la localidad.');
    }
    const matches = exact.length ? exact : found;

    if (matches.length !== 1) {
      const names = matches.slice(0, 4).map(match => [match.name, match.province, match.country].filter(Boolean).join(', '));
      throw new Error(names.length ? 'Hay varios lugares posibles para ' + name + '. Indicá cuál: ' + names.join(' / ') : 'No encontré ese lugar. Indicá la ciudad, provincia o coordenadas.');
    }
    const [{ coordinates: [longitude, latitude], name: label }] = matches;
    if (!validCoordinates(longitude, latitude)) throw new Error('El lugar no tiene coordenadas válidas.');
    pointsToAdd.push({ longitude, latitude, name: label });
  }
  const newFeatures = [];
  for (const point of pointsToAdd) {
    let feature = selection.features.find(item => item.geometry.type === 'Point'
      && item.geometry.coordinates[0] === point.longitude && item.geometry.coordinates[1] === point.latitude);
    if (!feature) {
      feature = { type: 'Feature', id: crypto.randomUUID(), properties: { name: point.name ?? '' },
        geometry: { type: 'Point', coordinates: [point.longitude, point.latitude] } };
      selection.features.push(feature);
    }
    if (!newFeatures.includes(feature)) newFeatures.push(feature);
  }
  if (changes.polygon) selection.features.push({ type: 'Feature', id: crypto.randomUUID(), properties: { name: changes.polygonName?.slice(0, 100).trim() ?? '' },
    geometry: { type: 'Polygon', coordinates: closedRegion(changes.polygon) } });
  if (newFeatures.length) {
    const [longitude, latitude] = newFeatures[0].geometry.coordinates;
    Object.assign(visual.map.camera, { longitude, latitude });
  }
  if (newFeatures.length || changes.polygon) {
    const scope = changes.polygon ? 'area' : 'point';
    data.geography.scope = !data.geography.scope || data.geography.scope === scope ? scope : 'both';
  }
  if (changes.sources || newFeatures.length) {
    const requests = changes.sources ?? [...new Set(data.sources.filter(catalogEntry).map(source => catalogEntry(source).id))].map(id => ({ id }));
    const configured = requests.flatMap(item => {
      const targets = !item.pointId && newFeatures.length ? newFeatures : [null];
      return targets.map(feature => configureSource(item, selection.features, feature,
        data.sources.filter(source => catalogEntry(source)?.id === item.id).length === 1
          ? data.sources.find(source => catalogEntry(source)?.id === item.id) : null));
    });
    const unique = [...new Map(configured.map(source => [source.id + '::' + source.upstream.geometryId, source])).values()];
    const counts = new Map();
    for (const source of unique) counts.set(source.id, (counts.get(source.id) ?? 0) + 1);
    for (const source of unique) {
      const existing = data.sources.find(item => catalogEntry(item)?.id === source.id && item.upstream.geometryId === source.upstream.geometryId);
      source.id = existing?.id ?? (counts.get(source.id) > 1 ? source.id + '::' + source.upstream.geometryId : source.id);
    }
    data.sources = changes.sources ? unique : [...data.sources.filter(source => !catalogEntry(source)), ...unique];
    if (data.sources.length > 25) throw new Error('La investigación admite hasta 25 series. Reducí los lugares o variables.');
  }
  if (changes.sources || changes.time || newFeatures.length) {
    const cadences = await Promise.all(data.sources.map(async source => {
      const entry = catalogEntry(source);
      if (!entry) return null;
      const geometry = selection.features.find(item => item.id === source.upstream.geometryId)?.geometry.type;
      const scope = source.access === 'noaa.ncei.station' ? 'station'
        : entry.featureType === 'Reach' ? 'river' : entry.featureType === 'PriorLake' ? 'lake'
          : geometry && geometry !== 'Point' ? 'area' : 'land';
      const { matches } = await invoke('evaluate_coverage', { variable: entry.variable, scope, start: data.time.start, end: data.time.end });
      const match = matches.find(row => row.access === source.access && row.variables.includes(entry.code)
        && (!entry.featureType || row.selection === entry.featureType));
      if (!match || !['compatible', 'unverified'].includes(match.status)) {
        throw new Error('El período o la selección no son compatibles con ' + entry.label + '.');
      }
      return match.cadence;
    }));
    if (cadences.includes('monthly')) data.time.resolution = 'Mensual';
    else if (cadences.includes('daily')) data.time.resolution = 'Diaria';
    else if (cadences.includes('overpass')) data.time.resolution = 'Por pasada';
  }
  for (const key of ['theme', 'language', 'chartResolution']) if (key in changes) visual[key] = changes[key];
  Object.assign(visual.appearance, changes.appearance);
  Object.assign(visual.workspace, changes.workspace);
  Object.assign(visual.map.camera, changes.camera);
  Object.assign(visual.map.layers, changes.mapLayers);
  return next;
}
