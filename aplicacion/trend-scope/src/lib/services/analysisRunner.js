import { analysisRequest, runAnalysis } from '$lib/services/acquisition.js';
import { analysisRun } from '$lib/stores/analysis.js';

/** Source instance ids may carry a "::suffix"; a proposal can name the base catalog id instead. */
export function resolveTargets(targets, sources) {
  const ids = sources.map(source => source.id);
  return targets.map(target => ids.includes(target) ? target : ids.find(id => id.split('::')[0] === target));
}

/**
 * Runs one analysis through run_analysis and publishes the response in the analysisRun store.
 * `analysis` = { struct, targets, params?, hypothesis? } (from the form or from an assistant proposal).
 */
export async function executeAnalysis(investigation, analysis, key, isCurrent = () => true) {
  const targets = resolveTargets(analysis.targets, investigation.sources);
  if (!targets.length || targets.some(target => !target)) {
    throw new Error('Las variables del análisis no están en la configuración actual. Agregalas y volvé a intentar.');
  }
  const item = { id: 'a1', struct: analysis.struct, targets, params: analysis.params ?? {},
    ...(analysis.hypothesis ? { hypothesis: analysis.hypothesis } : {}) };
  const response = await runAnalysis(analysisRequest(investigation, [item]));
  // A cancelled run finishes in the background; its response is dropped.
  if (isCurrent()) analysisRun.set({ key, response });
  return response;
}
