import contract from '../../../src-tauri/src-python/trend_scope/services/assistant-contract.json' with { type: 'json' };
import { assistantCatalog as catalog, sourceConfig, providerGeometries, geometryMatchesScope } from './sources.js';
import { closedRegion, regionProblem, validCoordinates } from './geography.js';

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
  const { point, place, places, polygon, coast, sources, appearance, workspace, camera } = changes;
  if (sources?.some(item => item.geometryId && item.pointId && item.geometryId !== item.pointId)) {
    throw new Error('Cada variable admite una sola selección geográfica.');
  }
  if ([point, place, places, polygon, coast].filter(Boolean).length > 1) throw new Error('Indicá una sola selección geográfica por mensaje.');
  if (coast && (!bounded(coast.distanceKm, 1, 500) || !coast.countries.length || coast.countries.length > 5
      || coast.countries.some(name => name.trim().length < 2 || name.length > 100)
      || coast.waters.trim().length < 2 || coast.waters.length > 100)) {
    throw new Error('Indicá los países, el tramo y una distancia costera entre 1 y 500 km.');
  }
  if (point && !validCoordinates(point.longitude, point.latitude)) throw new Error('Las coordenadas están fuera del rango WGS 84.');
  if (polygon && (polygon.length > 100 || !polygon.every(p => p.length === 2 && validCoordinates(...p)))) {
    throw new Error('El polígono requiere vértices válidos en orden longitud, latitud.');
  }
  if (polygon && !closedRegion(polygon)) throw new Error(regionProblem(polygon) || 'El polígono no delimita un área válida.');
  if (sources && (sources.length > 25 || new Set(sources.map(item => JSON.stringify([item.id, item.geometryId ?? item.pointId ?? '']))).size !== sources.length)) {
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

function configureSource(item, features, target, existing, scope) {
  const reference = item.geometryId ?? item.pointId;
  const requested = reference ? features.find(feature => feature.id === reference) : target;
  const area = requested ? requested.geometry.type !== 'Point' : scope === 'area';
  const areaSources = { 'power-temperature': 'power-temperature-area', 'power-solar': 'power-solar-area' };
  const pointSources = Object.fromEntries(Object.entries(areaSources).map(([point, region]) => [region, point]));
  const sourceId = area ? areaSources[item.id] ?? item.id : pointSources[item.id] ?? item.id;
  const entry = catalog.find(source => source.id === sourceId);
  if (!entry) throw new Error('Una variable propuesta no está en el catálogo: ' + item.id);
  const config = sourceConfig(sourceId);
  if (config.access === 'noaa.cpc.oni') return config;
  const { upstream } = config;
  const compatible = features.filter(feature => providerGeometries(entry.route).includes(feature.geometry.type));
  const preferred = reference ?? target?.id ?? existing?.upstream.geometryId;
  const scoped = compatible.filter(feature => geometryMatchesScope(feature.geometry.type, scope));
  const selection = preferred ? compatible.find(feature => feature.id === preferred)
    : scoped.length === 1 ? scoped[0] : compatible.length === 1 ? compatible[0] : null;
  if (reference && !selection) throw new Error('La selección indicada no existe o no es compatible con ' + entry.label + '.');
  if (!selection) throw new Error('Elegí una selección geográfica para ' + entry.label + '. Indicá cuál usar si hay más de una.');
  upstream.geometryId = selection.id;
  return config;
}

export function addsToInvestigation(question) {
  const words = question.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const replaces = /\b(solo|solamente|reemplaz\w*|cambia\w*|en vez de|quita\w*|borra\w*|only|instead|replace|remove|clear)\b/;
  return !replaces.test(words) && /\b(tambien|ademas|agrega\w*|anad\w*|suma\w*|inclu\w*|also|too|add|include|as well)\b/.test(words);
}

export async function configureWorkspace(snapshot, changes, invoke, language, additive = false) {
  validate(changes);
  const next = JSON.parse(JSON.stringify(snapshot));
  const { data, visual } = next;
  for (const key of ['title', 'objective', 'description']) if (key in changes) data[key] = changes[key];
  if (changes.time) {
    const years = changes.time.years?.slice().sort((a, b) => a - b);
    if (years && (!years.length || years.length > 25 || new Set(years).size !== years.length
      || years.some(year => year < 1900 || year >= new Date().getFullYear()))) {
      throw new Error('Elegí años calendario completos que ya hayan terminado.');
    }
    const start = years ? years[0] + '-01-01' : changes.time.start ?? data.time.start;
    const end = years ? years.at(-1) + '-12-31' : changes.time.end ?? data.time.end;
    if (!isoDate(start) || !isoDate(end) || start > end) throw new Error('Ingresá fechas válidas en orden.');
    Object.assign(data.time, { start, end });
    if (years) data.time.years = years;
    else delete data.time.years;
  }

  const selection = data.geography.selection;
  if (changes.clearSelection && !additive) {
    selection.features = [];
    for (const source of data.sources) source.upstream.geometryId = null;
  }
  if (changes.places && (!changes.places.length || changes.places.length > 10)) throw new Error('Indicá entre uno y diez lugares.');
  const additions = changes.point ? [{
    name: changes.point.name,
    center: [changes.point.longitude, changes.point.latitude],
    geometry: { type: 'Point', coordinates: [changes.point.longitude, changes.point.latitude] }
  }] : [];
  if (changes.polygon) additions.push({
    name: changes.polygonName?.slice(0, 100).trim() || 'Polígono',
    geometry: { type: 'Polygon', coordinates: closedRegion(changes.polygon) }
  });
  for (const { name, kind } of changes.places ?? (changes.place ? [changes.place] : [])) {
    if (name.trim().length < 2 || name.length > 100) throw new Error('Indicá un nombre de lugar válido.');
    const regional = kind !== 'localidades';
    const query = regional && kind !== 'regiones' ? name.split(',')[0].trim() : name;
    const found = JSON.parse(await invoke('search_places', { query, kind, language }));
    const normalize = text => (text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    const parts = name.split(',').map(normalize).filter(Boolean);
    const exact = found.filter(match => normalize(match.name) === parts[0]
      && parts.slice(1).every(part => [match.province, match.country].some(value => normalize(value) === part)));
    if (!exact.length && found.length && (found.length === 1 || (!regional && parts.length > 1))) {
      const candidates = found.slice(0, 4).map(candidate =>
        [candidate.name, candidate.province, candidate.country].filter(Boolean).join(', '));
      throw new Error('No pude confirmar ' + name + '. El buscador devolvió: '
        + candidates.join(' / ') + '. Precisá la localidad o indicá sus coordenadas.');
    }
    const matches = exact.length ? exact : found;

    if (matches.length !== 1) {
      const names = matches.slice(0, 4).map(match => [match.name, match.province, match.country].filter(Boolean).join(', '));
      throw new Error(names.length ? 'Hay varios lugares posibles para ' + name + '. Indicá cuál: ' + names.join(' / ') : 'No encontré ese lugar. Indicá la ciudad, provincia o coordenadas.');
    }
    const [place] = matches;
    const [longitude, latitude] = place.coordinates ?? [];
    if (!validCoordinates(longitude, latitude)) throw new Error('El lugar no tiene coordenadas válidas.');
    const geometry = regional ? await invoke('load_place_boundary', { kind, id: String(place.id) })
      : { type: 'Point', coordinates: [longitude, latitude] };
    if (regional && !['Polygon', 'MultiPolygon'].includes(geometry?.type)) {
      throw new Error('No encontré un límite publicado para ' + place.name + '. Podés dibujar el área en el mapa.');
    }
    additions.push({ geometry, name: place.name, center: [longitude, latitude] });
  }
  if (changes.coast) {
    const regions = await invoke('load_coastal_regions', changes.coast);
    if (regions.length !== changes.coast.countries.length || regions.some(region =>
      !['Polygon', 'MultiPolygon'].includes(region.geometry?.type))) {
      throw new Error('No pude confirmar todos los tramos de costa.');
    }
    additions.push(...regions.map(region => ({ ...region, coastDistanceKm: changes.coast.distanceKm })));
  }
  const newFeatures = [];
  for (const { name, geometry, coastDistanceKm } of additions) {
    let feature = selection.features.find(item => JSON.stringify(item.geometry) === JSON.stringify(geometry));
    if (!feature) {
      feature = { type: 'Feature', id: crypto.randomUUID(), properties: { name: name ?? '' }, geometry };
      selection.features.push(feature);
    }
    if (coastDistanceKm !== undefined) feature.properties.coastDistanceKm = coastDistanceKm;
    if (!newFeatures.includes(feature)) newFeatures.push(feature);
  }
  if (additions[0]?.center) {
    const [longitude, latitude] = additions[0].center;
    Object.assign(visual.map.camera, { longitude, latitude });
  }
  // A new place replaces the previous selection unless the user asked to add it ("también", "además", "sumá"…).
  // Otherwise the old place stayed on the map and the variables kept reading it.
  if (!additive && newFeatures.length) {
    const keep = new Set([...newFeatures.map(feature => feature.id),
      ...(changes.sources ?? []).map(item => item.geometryId ?? item.pointId).filter(Boolean)]);
    selection.features = selection.features.filter(feature => keep.has(feature.id));
    for (const source of data.sources) {
      if (!keep.has(source.upstream?.geometryId)) source.upstream.geometryId = null;
    }
  }
  const requestedSources = changes.sources ?? (newFeatures.length
    ? [...new Set(data.sources.map(source => catalogEntry(source)?.id).filter(Boolean))].map(id => ({ id }))
    : null);
  if (requestedSources) {
    const configured = requestedSources.flatMap(item => {
      const targets = !(item.geometryId || item.pointId) && newFeatures.length ? newFeatures : [null];
      const existing = data.sources.filter(source => catalogEntry(source)?.id === item.id);
      return targets.map(feature => configureSource(item, selection.features, feature,
        existing.length === 1 ? existing[0] : null, data.geography.scope));
    });
    const sourceKey = source => (catalogEntry(source)?.id ?? source.id) + '::' + source.upstream.geometryId;
    const additionsByKey = new Map((additive ? data.sources : []).map(source => [sourceKey(source), source]));
    for (const source of configured) {
      const key = sourceKey(source);
      if (!additionsByKey.has(key)) additionsByKey.set(key, source);
    }
    const unique = [...additionsByKey.values()];
    const counts = new Map();
    for (const source of unique) {
      const base = catalogEntry(source)?.id ?? source.id;
      counts.set(base, (counts.get(base) ?? 0) + 1);
    }
    for (const source of unique) {
      const base = catalogEntry(source)?.id ?? source.id;
      const existing = data.sources.find(item => sourceKey(item) === sourceKey(source));
      source.id = existing?.id ?? (counts.get(base) > 1 ? base + '::' + source.upstream.geometryId : base);
    }
    data.sources = unique;
    if (!changes.time && unique.length && unique.every(source => source.access === 'noaa.etopo.area')) {
      delete data.time.years;
    }
    if (data.sources.length > 25) throw new Error('La investigación admite hasta 25 series. Reducí los lugares o variables.');
  }
  if (requestedSources || newFeatures.length) {
    const ids = new Set(data.sources.map(source => source.upstream.geometryId).filter(Boolean));
    const relevant = requestedSources && ids.size ? selection.features.filter(feature => ids.has(feature.id)) : selection.features;
    const scopes = new Set(relevant.map(feature => feature.geometry.type === 'Point' ? 'point' : 'area'));
    if (scopes.size) data.geography.scope = scopes.size === 2 ? 'both' : scopes.values().next().value;
  }
  if (data.time.years?.length && data.sources.some(source => !['ucsb.chirps.monthly', 'argentina.pmra.monthly', 'nasa.power.solar.area', 'nasa.power.temperature.area'].includes(source.access))) {
    throw new Error('Para años separados usá CHIRPS o PMRA mensual, o un producto regional de NASA POWER.');
  }
  if (requestedSources || changes.time) {
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
      // Part of the period is outside the source (e.g. "hasta hoy" with a product that ends last year): keep the covered part.
      const covered = match?.status === 'partial' && match.reason === 'partial_period' && match.from && match.through
        ? { start: data.time.start > match.from ? data.time.start : match.from,
            end: data.time.end < match.through ? data.time.end : match.through }
        : null;
      if (!match || (!['compatible', 'unverified'].includes(match.status) && !(covered && covered.start <= covered.end))) {
        throw new Error('El período o la selección no son compatibles con ' + entry.label
          + (match?.from && match?.through ? ` (datos de ${match.from} a ${match.through}).` : '.'));
      }
      return { cadence: match.cadence, covered };
    })).then(rows => {
      const ranges = rows.map(row => row?.covered).filter(Boolean);
      if (ranges.length) {
        const start = ranges.map(range => range.start).sort().at(-1);
        const end = ranges.map(range => range.end).sort()[0];
        if (start > end) throw new Error('Las variables elegidas no tienen datos en un período común.');
        Object.assign(data.time, { start, end });
      }
      return rows.map(row => row?.cadence);
    });
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
