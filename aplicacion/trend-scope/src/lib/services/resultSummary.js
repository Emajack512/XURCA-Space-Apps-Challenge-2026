// Plain-language report shown below the charts: what data is on screen and whether it was analysed.
import { catalog } from './sources.js';
import { describeFinding, fmt, statusText, verdictText } from './analysisText.js';

const cadenceNames = { daily: 'diaria', monthly: 'mensual', yearly: 'anual', weekly: 'semanal', overpass: 'por pasada' };

export function seriesLabel(item) {
  return catalog.find(source => source.id === item.id.split('::')[0])?.label ?? item.label ?? item.variable;
}

function describeSeries(item) {
  const summary = item.summary ?? {};
  const label = seriesLabel(item);
  const place = item.placeLabel ? ` en ${item.placeLabel}` : '';
  const source = [item.provider, item.product].filter(Boolean).join(' · ');
  if (!summary.validCount) {
    return `${label}${place}: la fuente${source ? ` (${source})` : ''} no devolvió valores válidos para el período elegido.`;
  }
  const cadence = cadenceNames[item.cadence] ?? item.cadence;
  const missing = summary.missingOrInvalidCount ? `, ${summary.missingOrInvalidCount} sin dato` : '';
  const parts = [
    `${label}${place}, de ${summary.start} a ${summary.end}`,
    `frecuencia ${cadence}`,
    `${summary.validCount} valores${missing}`,
    source ? `fuente ${source}` : ''
  ].filter(Boolean).join('; ');
  const stats = Number.isFinite(summary.mean)
    ? ` Promedio ${fmt(summary.mean)} ${item.unit ?? ''}, mínimo ${fmt(summary.minimum)}, máximo ${fmt(summary.maximum)}.`
    : '';
  const slope = summary.trend && Number.isFinite(summary.trend.perYear)
    ? ` La recta que mejor sigue los datos sube o baja ${fmt(summary.trend.perYear, 3)} ${item.unit ?? ''} por año (descriptivo: no dice si el cambio es significativo).`
    : '';
  return parts + '.' + stats + slope;
}

/**
 * series: every series of the current query (not only the chart on screen).
 * run: the analysisRun store value; fresh: whether it was computed for the current settings.
 * titles: struct id → readable analysis title.
 */
export function resultSummary(series, run, fresh, titles = {}) {
  const lines = [];
  lines.push(series.length === 1
    ? 'Estás viendo una serie descargada de la fuente original:'
    : `La consulta trajo ${series.length} series:`);
  const data = series.map(describeSeries);
  const processed = [];
  if (run && fresh) {
    const ids = new Set(series.map(item => item.id));
    for (const block of run.response?.analyses ?? []) {
      if (!block.targets?.some(id => ids.has(id))) continue;
      const title = titles[block.struct] ?? block.struct;
      const verdict = block.verdict ? verdictText(block.verdict) : null;
      const finding = block.findings?.[0] ? describeFinding(block.findings[0]) : null;
      const outcome = [verdict?.title, finding?.headline].filter(Boolean).join(' · ');
      processed.push(`Se aplicó «${title}» (${statusText(block.status)}). `
        + (outcome ? `Resultado: ${outcome}.` : 'No produjo hallazgos; revisá los avisos en Análisis estadístico.'));
    }
  }
  const status = processed.length
    ? { done: true, lines: processed, next: 'El detalle (intervalos, avisos y cómo se calculó) está en Análisis estadístico.' }
    : { done: false, lines: ['Los datos se descargaron y se graficaron, pero todavía no se les aplicó ningún análisis estadístico.'],
        next: run && !fresh
          ? 'Hay un análisis anterior, pero se hizo con otra configuración: volvé a ejecutarlo para que corresponda a estos datos.'
          : 'Para saber si hay una tendencia significativa, anomalías, eventos extremos o un pronóstico, abrí Análisis estadístico o pedíselo al asistente.' };
  return { lines, data, status };
}
