import { test } from 'node:test';
import assert from 'node:assert/strict';
import data from '../../../config/cfg_data.json' with { type: 'json' };
import visual from '../../../config/cfg_visual.json' with { type: 'json' };
import { addsToInvestigation, configureWorkspace } from './assistantConfiguration.js';
import { prepareInvestigation } from './acquisition.js';

const snapshot = () => structuredClone({ data, visual });
const coverage = async (command) => {
  assert.equal(command, 'evaluate_coverage');
  return { matches: [{ access: 'nasa.power.monthly', variables: ['T2M'], status: 'compatible', cadence: 'monthly' }] };
};

test('two-turn configuration preserves the point, variable and visual preferences', async () => {
  const initial = snapshot();
  const first = await configureWorkspace(initial, { point: { longitude: -66.33, latitude: -33.3 },
    sources: [{ id: 'power-temperature' }], time: { start: '2000-01-01', end: '2024-12-31' } }, coverage, 'es');
  const second = await configureWorkspace(first, { time: { start: '2010-01-01' } }, coverage, 'es');
  assert.equal(second.data.time.start, '2010-01-01');
  assert.equal(second.data.time.end, '2024-12-31');
  assert.deepEqual(second.data.sources, first.data.sources);
  assert.deepEqual(second.data.geography, first.data.geography);
  assert.deepEqual(second.visual, first.visual);
  assert.deepEqual(initial, snapshot());
});

test('invalid source and ambiguous place do not mutate existing configuration', async () => {
  const initial = snapshot();
  await assert.rejects(configureWorkspace(initial, { sources: [{ id: 'invented' }] }, coverage, 'es'), /catálogo/);
  await assert.rejects(configureWorkspace(initial, { place: { name: 'San Luis', kind: 'localidades' } },
    async () => JSON.stringify([{ name: 'San Luis', country: 'Argentina' }, { name: 'San Luis', country: 'México' }]), 'es'), /varios lugares/);
  assert.deepEqual(initial, snapshot());
});

test('incompatible coverage rejects the entire proposal, including title and theme', async () => {
  const initial = snapshot();
  await assert.rejects(configureWorkspace(initial, { title: 'New', theme: 'light',
    point: { longitude: -66, latitude: -33 }, sources: [{ id: 'power-temperature' }] },
    async () => ({ matches: [{ access: 'nasa.power.monthly', variables: ['T2M'], status: 'partial' }] }), 'es'), /compatibles/);
  assert.deepEqual(initial, snapshot());
});

const locations = [
  ['San Luis', 'San Luis', -66.335, -33.302],
  ['9 de Julio', 'Buenos Aires', -60.884, -35.445],
  ['El Volcán', 'San Luis', -66.183, -33.259]
];
const multiple = {
  places: locations.map(([name, province]) => ({ name: `${name}, ${province}, Argentina`, kind: 'localidades' })),
  sources: [{ id: 'power-precipitation' }, { id: 'noaa-precipitation' }],
  time: { start: '2005-01-01', end: '2024-12-31' }
};
const resolveLocations = async (command, args) => {
  if (command === 'search_places') {
    const [name, province, longitude, latitude] = locations.find(([name]) => args.query.startsWith(name));
    return JSON.stringify([{ name, province, country: 'Argentina', coordinates: [longitude, latitude] },
      { name, province: 'Otra provincia', country: 'Argentina', coordinates: [0, 0] }]);
  }
  return { matches: [
    { access: 'nasa.power.monthly', variables: ['PRECTOTCORR'], status: 'compatible', cadence: 'monthly' },
    { access: 'noaa.ncei.station', variables: ['PRCP'], status: 'unverified', cadence: 'monthly' }
  ] };
};

test('three named towns create six distinct source-point series and survive follow-ups', async () => {
  const initial = snapshot();
  initial.data.geography.selection.features = [];
  const configured = await configureWorkspace(initial, multiple, resolveLocations, 'es');
  assert.equal(configured.data.geography.selection.features.length, 3);
  assert.equal(configured.data.sources.length, 6);
  assert.equal(new Set(configured.data.sources.map(source => source.id)).size, 6);
  for (const point of configured.data.geography.selection.features) {
    assert.equal(configured.data.sources.filter(source => source.upstream.geometryId === point.id).length, 2);
  }
  const again = await configureWorkspace(configured, multiple, resolveLocations, 'es');
  assert.deepEqual(again.data, configured.data);
  const later = await configureWorkspace(configured, { time: { start: '2010-01-01' } }, resolveLocations, 'es');
  assert.deepEqual(later.data.sources, configured.data.sources);
});

test('an unresolved place rejects the entire multi-place proposal', async () => {
  const initial = snapshot();
  await assert.rejects(configureWorkspace(initial, multiple, async (command, args) =>
    args?.query?.startsWith('El Volcán') ? '[]' : resolveLocations(command, args), 'es'), /No encontré/);
  assert.deepEqual(initial, snapshot());
});

test('explicit missing point references are rejected instead of silently reassigned', async () => {
  await assert.rejects(configureWorkspace(snapshot(), { point: { longitude: -66, latitude: -33 },
    sources: [{ id: 'power-temperature', pointId: 'missing' }] }, coverage, 'es'), /no existe/);
});

const ring = [[-61, -36], [-60, -36], [-60, -35], [-61, -35], [-61, -36]];
const polygon = { type: 'Polygon', coordinates: [ring] };
const rainfall = { access: 'ucsb.chirps.monthly', variables: ['precipitation'], status: 'unverified', cadence: 'monthly' };

test('a drawn polygon is reused from the chat, applied to scope, and passed to acquisition', async () => {
  const initial = snapshot();
  initial.data.geography.scope = 'point';
  initial.data.geography.selection.features = [
    { id: 'p', geometry: { type: 'Point', coordinates: [-60.5, -35.5] } },
    { id: 'drawn', properties: { name: 'Polígono manual' }, geometry: polygon }
  ];
  const result = await configureWorkspace(initial, { sources: [{ id: 'chirps-monthly-precipitation', geometryId: 'drawn' }] },
    async (command, args) => {
      assert.equal(command, 'evaluate_coverage');
      assert.equal(args.scope, 'area');
      return { matches: [rainfall] };
    }, 'es');
  assert.equal(result.data.geography.scope, 'area');
  assert.equal(result.data.sources[0].upstream.geometryId, 'drawn');
  assert.equal(result.data.geography.selection.features.length, 2);
  const payload = prepareInvestigation(result.data);
  assert.deepEqual(payload.geography.selection.features.map(item => item.geometry), [polygon]);
  assert.equal(payload.sources[0].upstream.geometryId, 'drawn');
});

test('a named Argentine locality uses its published boundary', async () => {
  const result = await configureWorkspace(snapshot(), {
    place: { name: '9 de Julio, Buenos Aires, Argentina', kind: 'localidades-censales' },
    sources: [{ id: 'chirps-monthly-precipitation' }]
  }, async (command, args) => {
    if (command === 'search_places') {
      assert.equal(args.query, '9 de Julio');
      return JSON.stringify([{ id: '006', name: '9 de Julio', province: 'Buenos Aires', country: 'Argentina', coordinates: [-60.88, -35.44] }]);
    }
    if (command === 'load_place_boundary') {
      assert.deepEqual(args, { kind: 'localidades-censales', id: '006' });
      return { type: 'MultiPolygon', coordinates: [[ring]] };
    }
    assert.equal(command, 'evaluate_coverage');
    assert.equal(args.scope, 'area');
    return { matches: [rainfall] };
  }, 'es');
  const [feature] = result.data.geography.selection.features;
  assert.equal(feature.geometry.type, 'MultiPolygon');
  assert.equal(prepareInvestigation(result.data).sources[0].upstream.geometryId, feature.id);
});

test('a polygon does not become a point for a point-only source', async () => {
  await assert.rejects(configureWorkspace(snapshot(), {
    polygon: ring, sources: [{ id: 'power-wind' }]
  }, async () => { throw new Error('Must reject before checking provider coverage'); }, 'es'), /selección geográfica/);
});

test('a named region keeps its country and uses its published boundary for daily mean rain', async () => {
  const next = await configureWorkspace(snapshot(), {
    place: { name: 'Asunción, Paraguay', kind: 'regiones' },
    time: { start: '2024-11-01', end: '2026-10-31' },
    sources: [{ id: 'chirps-mean-daily-rain' }]
  }, async (command, args) => {
    if (command === 'search_places') {
      assert.equal(args.query, 'Asunción, Paraguay');
      return JSON.stringify([{ id: 'asuncion', name: 'Asunción', country: 'Paraguay', coordinates: [-57.6, -25.3] }]);
    }
    if (command === 'load_place_boundary') return polygon;
    assert.equal(command, 'evaluate_coverage');
    assert.equal(args.scope, 'area');
    return { matches: [{ access: 'ucsb.chirps.monthly', variables: ['precipitation_daily_mean'], status: 'unverified', cadence: 'monthly' }] };
  }, 'es');
  const source = next.data.sources[0];
  const feature = next.data.geography.selection.features.find(item => item.id === source.upstream.geometryId);
  assert.equal(next.data.geography.scope, 'area');
  assert.deepEqual(feature.geometry, polygon);
});

test('the assistant separates named years for a country boundary', async () => {
  const next = await configureWorkspace(snapshot(), {
    place: { name: 'Madagascar', kind: 'paises' },
    sources: [{ id: 'chirps-monthly-precipitation' }],
    time: { years: [2006, 2000] }
  }, async command => {
    if (command === 'search_places') return JSON.stringify([{ id: 'MDG', name: 'Madagascar', coordinates: [47, -19] }]);
    if (command === 'load_place_boundary') return polygon;
    return { matches: [{ access: 'ucsb.chirps.monthly', variables: ['precipitation'], status: 'compatible', cadence: 'monthly' }] };
  }, 'es');
  assert.deepEqual(next.data.time.years, [2000, 2006]);
  assert.equal(next.data.time.start, '2000-01-01');
  assert.equal(next.data.time.end, '2006-12-31');
  assert.equal(next.data.geography.scope, 'area');
});


test('a temperature query bound to a polygon uses the regional adapter', async () => {
  const next = await configureWorkspace(snapshot(), {
    polygon: ring, sources: [{ id: 'power-temperature' }],
    time: { start: '2025-01-01', end: '2025-12-31' }
  }, async (command, args) => {
    assert.equal(command, 'evaluate_coverage');
    assert.equal(args.scope, 'area');
    return { matches: [{ access: 'nasa.power.temperature.area', variables: ['T2M'], status: 'compatible', cadence: 'monthly' }] };
  }, 'es');
  assert.equal(next.data.sources[0].id, 'power-temperature-area');
});

test('Tucumán stays a provincial temperature query when the year changes', async () => {
  const invoke = async (command, args) => {
    if (command === 'search_places') {
      assert.deepEqual(args, { query: 'Tucumán', kind: 'provincias', language: 'es' });
      return JSON.stringify([{ id: '90', name: 'Tucumán', province: 'Tucumán', country: 'Argentina', coordinates: [-65.3, -26.8] }]);
    }
    if (command === 'load_place_boundary') {
      assert.deepEqual(args, { kind: 'provincias', id: '90' });
      return { type: 'Polygon', coordinates: [ring] };
    }
    assert.equal(command, 'evaluate_coverage');
    assert.equal(args.scope, 'area');
    return { matches: [{ access: 'nasa.power.temperature.area', variables: ['T2M'], status: 'unverified', cadence: 'monthly' }] };
  };
  const first = await configureWorkspace(snapshot(), {
    place: { name: 'Tucumán', kind: 'provincias' }, sources: [{ id: 'power-temperature-area' }],
    time: { start: '2025-01-01', end: '2025-12-31' }
  }, invoke, 'es');
  const next = await configureWorkspace(first, {
    time: { start: '2024-01-01', end: '2024-12-31' }
  }, invoke, 'es');
  const request = prepareInvestigation(next.data);
  assert.equal(request.time.start, '2024-01-01');
  assert.equal(request.time.end, '2024-12-31');
  assert.deepEqual(next.data.geography, first.data.geography);
  assert.deepEqual(next.data.sources, first.data.sources);
});

test('an offshore comparison resolves both shores and keeps its requested distance', async () => {
  const coast = { countries: ['España', 'Portugal'], territory: 'mainland', side: 'sea', distanceKm: 50, waters: 'Atlántico' };
  const result = await configureWorkspace(snapshot(), { coast, sources: [{ id: 'etopo-bathymetry' }] }, async (command, args) => {
    if (command === 'load_coastal_regions') {
      assert.deepEqual(args, coast);
      return coast.countries.map((name, index) => ({ name, geometry: { type: 'Polygon',
        coordinates: [ring.map(([x, y]) => [x + index, y])] } }));
    }
    assert.equal(command, 'evaluate_coverage');
    assert.equal(args.scope, 'area');
    return { matches: [{ access: 'noaa.etopo.area', variables: ['depth'], status: 'compatible', cadence: 'static' }] };
  }, 'es');
  const features = result.data.geography.selection.features;
  assert.deepEqual(features.map(feature => feature.properties.coastDistanceKm), [50, 50]);
  assert.deepEqual(result.data.sources.map(source => source.upstream.geometryId), features.map(feature => feature.id));
});

test('an additive place keeps the previous series even if the proposal tries to replace it', async () => {
  const initial = snapshot();
  const invoke = async (command, args) => {
    if (command === 'search_places') {
      return JSON.stringify([{ id: args.query, name: args.query, coordinates: [-65, -30] }]);
    }
    if (command === 'load_place_boundary') return { type: 'Polygon', coordinates: [
      ring.map(([x, y]) => [x + (args.id === 'Jamaica' ? 0 : 2), y])
    ] };
    assert.equal(command, 'evaluate_coverage');
    return { matches: [rainfall] };
  };
  const source = { id: 'chirps-monthly-precipitation' };
  const first = await configureWorkspace(initial, { place: { kind: 'paises', name: 'Jamaica' }, sources: [source] }, invoke, 'es');
  const changes = { place: { kind: 'paises', name: 'Filipinas' }, clearSelection: true };
  const additive = addsToInvestigation('Y Filipinas también.');
  const next = await configureWorkspace(first, changes, invoke, 'es', additive);
  assert.equal(additive, true);
  assert.equal(addsToInvestigation('En vez de Jamaica, solo Filipinas'), false);
  assert.equal(next.data.sources.length, 2);
  assert.ok(next.data.sources.some(item => item.id === first.data.sources[0].id));
  assert.deepEqual(new Set(next.data.sources.map(item => item.upstream.geometryId)),
    new Set(next.data.geography.selection.features.map(item => item.id)));
});
