import { isTauri } from '@tauri-apps/api/core';
import { pyInvoke } from 'tauri-plugin-pytauri-api';

function requireDesktop(action) {
  if (!isTauri()) throw new Error(`Abrí Earth Detective con pnpm tauri dev para ${action}.`);
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
