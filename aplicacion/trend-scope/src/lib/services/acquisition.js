import { isTauri } from '@tauri-apps/api/core';
import { pyInvoke } from 'tauri-plugin-pytauri-api';
import { providers, providerGeometries, geometryMatchesScope, sourceMatchesScope } from './sources.js';
import { settingError } from './attention.js';

export function prepareInvestigation(data) {
  const investigation = JSON.parse(JSON.stringify(data));
  const { scope, selection } = investigation.geography;
  if (!investigation.sources.length) {
    throw settingError('Todavía no hay variables. Agregá una en Configuración (botón de engranaje) o pedísela al asistente.',
      scope ? 'sources' : 'scope');
  }
  const { start, end } = investigation.time;
  const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date());
  if (!validDate(start) || !validDate(end) || start > end || end > today) {
    throw settingError('Elegí un período histórico con las fechas en orden.', 'time');
  }
  if (investigation.methods?.length) throw new Error('Los métodos personalizados todavía no se ejecutan desde Procesar.');
  investigation.sources = investigation.sources.filter(source => sourceMatchesScope(source, scope, selection.features));
  if (!investigation.sources.length) throw settingError('En Fuentes de información, elegí una variable compatible y pulsá Agregar.', 'sources');
  selection.features = selection.features.filter(feature => geometryMatchesScope(feature.geometry.type, scope));
  for (const source of investigation.sources) {
    if (source.access === 'copernicus.cds' && source.upstream.selectors?.requestJson) continue;
    const route = providers.find(route => route.id === source.access);
    const geometries = providerGeometries(route);
    if (!geometries.length) continue;
    const compatible = selection.features.filter(feature => geometries.includes(feature.geometry.type));
    const requested = source.upstream.geometryId;
    if (compatible.some(feature => feature.id === requested)) continue;
    // No binding, or a binding to a selection that was removed: use the only compatible one if there is exactly one.
    if (compatible.length === 1) {
      source.upstream.geometryId = compatible[0].id;
      continue;
    }
    const name = source.product || source.variable;
    const kind = geometries.every(type => type === 'Point') ? 'un punto'
      : geometries.includes('Point') ? 'un punto o un área' : 'un área (polígono)';
    throw compatible.length
      ? settingError(`Hay ${compatible.length} selecciones que sirven para ${name}. Elegí cuál usar en Configuración (botón de engranaje) o pedíselo al asistente.`, 'sources')
      : settingError(`${name} necesita ${kind} en el mapa y no hay ninguna selección compatible.`, 'geometry');
  }
  return investigation;
}

function requireDesktop(action) {
  if (!isTauri()) throw new Error(`Abrí TrendScope como app de escritorio para ${action}.`);
}

export async function acquireData(investigation) {
  requireDesktop('consultar las fuentes');
  const response = await pyInvoke('acquire_data', { investigation });
  return JSON.parse(response);
}

/** request.json -> response.json (docs/plan-maestro/23_ARQUITECTURA_HANDLERS.md). Failures come back inside the response. */
export async function runAnalysis(request) {
  requireDesktop('ejecutar análisis');
  const response = await pyInvoke('run_analysis', { request });
  return JSON.parse(response);
}

/** Catalogue of analyses with parameters, hypotheses and availability in this installation. */
export async function listAnalyses() {
  requireDesktop('listar los análisis');
  return JSON.parse(await pyInvoke('list_analyses', {}));
}

/** request.json: the investigation (cfg_data) plus the analyses to run. */
export function analysisRequest(investigation, analyses, options = {}) {
  return {
    schema: 'earth-detective/request', schema_version: 1, origin: 'manual', language: 'es',
    investigation, analyses,
    options: { include_steps: true, max_points_per_array: 5000, allow_partial: true, ...options }
  };
}
