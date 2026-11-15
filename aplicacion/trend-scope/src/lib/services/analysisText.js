// Plain-language rendering of response.json findings and verdicts (no interpretation beyond the backend's fields).
// Rule kept from the backend: never a "percentage of certainty", never "no change" when evidence is missing.

export function fmt(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (typeof value !== 'number') return String(value);
  return value.toLocaleString('es-AR', { maximumSignificantDigits: digits });
}

function pValue(value) {
  if (value === null || value === undefined) return '—';
  return value < 0.001 ? '< 0,001' : value.toLocaleString('es-AR', { maximumSignificantDigits: 2 });
}

// Display-only labels: the backend keeps its unit codes and method ids.
export function unit(value) {
  if (!value) return '';
  return String(value).split('/').map(part => ({ C: '°C', K: 'K', decade: 'década', year: 'año', day: 'día', month: 'mes' })[part] ?? part).join('/');
}

const testLabels = {
  modified_mann_kendall: 'Mann-Kendall modificado',
  mann_kendall: 'Mann-Kendall',
  theil_sen: 'Theil-Sen',
  ols: 'mínimos cuadrados'
};
const testName = test => testLabels[test] ?? test;

const statusLabels = {
  completed: 'Completado', partial: 'Parcial', failed: 'Con errores', skipped: 'Omitido'
};
export const statusText = status => statusLabels[status] ?? status;

const verdictLabels = {
  supported: 'La hipótesis es respaldada por los datos',
  not_supported: 'La hipótesis no es respaldada por los datos',
  inconclusive: 'No hay evidencia suficiente para concluir',
  not_testable: 'No se pudo evaluar la hipótesis con estos datos'
};

export function verdictText(verdict) {
  if (!verdict) return null;
  const evidence = verdict.evidence ?? {};
  const lines = [];
  if (evidence.p_value !== undefined && evidence.p_value !== null) {
    lines.push(`p = ${pValue(evidence.p_value)} (α = ${fmt(evidence.alpha)})`);
  }
  if (evidence.interval_excludes_zero !== undefined) {
    lines.push(evidence.interval_excludes_zero ? 'El intervalo de confianza no incluye 0.' : 'El intervalo de confianza incluye 0.');
  }
  if (evidence.direction_matches !== undefined) {
    lines.push(evidence.direction_matches ? 'La dirección coincide con la hipótesis.' : 'La dirección no coincide con la hipótesis.');
  }
  if (evidence.observed !== undefined) lines.push(`Valor observado (${evidence.statistic}): ${fmt(evidence.observed)} ${evidence.operator} ${fmt(evidence.value)}`);
  if (evidence.central !== undefined) lines.push(`Estimación central: ${fmt(evidence.central)} (${evidence.date})`);
  if (evidence.lags_significant_matching) {
    lines.push(evidence.lags_significant_matching.length
      ? `Desfases con asociación significativa tras el control de falsos descubrimientos: ${evidence.lags_significant_matching.join(', ')}.`
      : 'Ningún desfase evaluado quedó significativo tras el control de falsos descubrimientos.');
  }
  if (evidence.dates_in_window) lines.push(evidence.dates_in_window.length ? `Cambios detectados: ${evidence.dates_in_window.join(', ')}.` : 'No se detectaron cambios en la ventana pedida.');
  if (evidence.caveat) lines.push(evidence.caveat[0].toUpperCase() + evidence.caveat.slice(1) + '.');
  return { title: verdictLabels[verdict.status] ?? verdict.status, status: verdict.status, lines };
}

function where(finding) {
  const place = finding.where ?? {};
  if (place.mode === 'area_sample') return place.label;
  const name = place.label ?? (place.coordinates ? place.coordinates.join(', ') + ' (lon, lat)' : '');
  return name || 'lugar no especificado';
}

function variable(finding) {
  const what = finding.what ?? {};
  return what.variable ?? what.source_id ?? 'variable';
}

function when(finding) {
  const span = finding.when ?? {};
  return span.start ? `${span.start} a ${span.end}` : '';
}

const FINDINGS = {
  descriptive(finding) {
    const h = finding.how_much;
    return {
      headline: `Resumen de ${variable(finding)}`,
      lines: [`${h.n} observaciones · media ${fmt(h.mean)} ${unit(h.unit)} · desvío ${fmt(h.std)}`,
        `Mínimo ${fmt(h.minimum)} · máximo ${fmt(h.maximum)}`,
        'Cuantiles: ' + Object.entries(h.quantiles ?? {}).map(([q, v]) => `${Number(q) * 100}% = ${fmt(v)}`).join(' · ')]
    };
  },
  trend(finding) {
    const h = finding.how_much;
    if (!h) return { headline: 'No se pudo estimar la tendencia', lines: [] };
    const direction = h.direction === 'increasing' ? 'creciente' : h.direction === 'decreasing' ? 'decreciente' : 'nula';
    return {
      headline: finding.conclusiveness === 'conclusive'
        ? `Tendencia ${direction} estadísticamente significativa`
        : 'No hay evidencia suficiente de una tendencia',
      lines: [
        `Pendiente estimada: ${fmt(h.per_decade)} ${unit(h.unit)} (intervalo de confianza ${fmt(h.interval.level * 100, 3)}%: ${fmt(h.interval.lower)} a ${fmt(h.interval.upper)})`,
        `Cambio total estimado en ${fmt(h.span_years, 3)} años: ${fmt(h.total_change)} ${unit(h.total_change_unit)}`,
        `p = ${pValue(finding.p_value)} (α = ${fmt(finding.alpha)}) · prueba: ${testName(finding.test)}`]
    };
  },
  anomaly(finding) {
    const h = finding.how_much;
    return {
      headline: 'Anomalías respecto de la referencia',
      lines: [`Última (${h.last_date}): ${fmt(h.last)} ${unit(h.unit)}`, `Mayor en valor absoluto (${h.largest_date}): ${fmt(h.largest)} ${unit(h.unit)}`,
        `Promedio de las anomalías: ${fmt(h.mean)} ${unit(h.unit)} · ${h.n} observaciones`]
    };
  },
  index(finding) {
    const h = finding.how_much;
    return {
      headline: `SPI a ${h.scale_months} ${h.scale_months === 1 ? 'mes' : 'meses'}`,
      lines: [`Meses secos (≤ ${h.thresholds.deficit}): ${fmt(h.deficit_fraction * 100, 3)}% · meses lluviosos (≥ +${h.thresholds.excess}): ${fmt(h.excess_fraction * 100, 3)}%`,
        `Último valor (${h.last_date}): ${fmt(h.last)} · mínimo: ${fmt(h.minimum)}`]
    };
  },
  fit(finding) {
    const h = finding.how_much;
    const lines = [`Modelo: ${h.model}`];
    if (h.slope_per_year !== undefined) lines.push(`Pendiente: ${fmt(h.slope_per_year)} ${unit(h.slope_unit)}`);
    if (h.metrics?.r2 !== null && h.metrics?.r2 !== undefined) lines.push(`R² = ${fmt(h.metrics.r2)} · RMSE = ${fmt(h.metrics.rmse)} ${unit(h.unit)}`);
    return { headline: 'Ajuste del modelo (descriptivo)', lines };
  },
  forecast(finding) {
    const h = finding.how_much;
    const validated = h.mode === 'validated_forecast';
    return {
      headline: validated ? 'Pronóstico validado fuera de muestra' : 'Pronóstico exploratorio (no validado)',
      lines: [`Modelo entregado: ${h.model}${finding.not_superior_to_baseline ? ' (ningún candidato superó a la referencia)' : ''}`,
        `${h.horizon_steps} pasos: de ${fmt(h.first)} a ${fmt(h.last)} ${unit(h.unit)}`,
        `Horizonte validado: ${h.horizon_validated ?? '—'} pasos`]
    };
  },
  seasonality(finding) {
    const h = finding.how_much;
    const lines = [`Ajuste armónico de ${h.harmonics} armónico(s), período de ${h.period}${h.r2 !== null ? ` · R² = ${fmt(h.r2)}` : ''}`];
    if (h.seasonal_strength !== null && h.seasonal_strength !== undefined) lines.push(`Fracción de la varianza explicada por el ciclo mensual: ${fmt(h.seasonal_strength * 100, 3)}%`);
    if (h.annual_bin) lines.push(`Amplitud del espectro en el ciclo anual: ${fmt(h.annual_bin.amplitude)} ${unit(h.unit)}`);
    if (h.stl_seasonal_range !== null) lines.push(`Rango del componente estacional (STL): ${fmt(h.stl_seasonal_range)} ${unit(h.unit)}`);
    return { headline: 'Estacionalidad de la serie', lines };
  },
  change_point(finding) {
    const h = finding.how_much;
    const what = h.basis === 'anomalies' ? 'la anomalía media' : 'la media';
    const side = { above_reference: ' · por encima de la base', below_reference: ' · por debajo de la base' };
    const lines = h.changes.map(c => c.direction
      ? `${c.date}: alarma${side[c.direction] ?? ''}`
      : `${c.date}: ${what} pasa de ${fmt(c.mean_before, 3)} a ${fmt(c.mean_after, 3)} ${unit(h.unit)} (cambio de ${fmt(c.shift, 3)} ${unit(h.unit)})`);
    if (h.method === 'cusum') {
      lines.push(`CUSUM: holgura k = ${fmt(h.k, 3)} y umbral h = ${fmt(h.h, 3)} desvíos de la base (media ${fmt(h.reference_mean, 3)}, desvío ${fmt(h.reference_std, 3)} ${unit(h.unit)})`);
    } else {
      const rule = h.penalty_rule === 'sic' ? 'criterio SIC' : 'indicada';
      lines.push(`Penalización ${fmt(h.penalty, 3)} (${rule}) · tamaño mínimo de tramo ${h.min_size} pasos`);
    }
    const noun = h.method === 'cusum' ? 'alarma(s) de apartamiento de la base' : 'cambio(s) de régimen detectado(s)';
    return {
      headline: h.n_changes ? `${h.n_changes} ${noun}` : 'No se detectaron cambios con este criterio (no hay evidencia suficiente; no significa que no los haya)',
      lines
    };
  },
  smoothing(finding) {
    const h = finding.how_much;
    return {
      headline: `Serie suavizada (${h.method === 'ssa' ? 'SSA' : 'media móvil causal'}, ventana ${h.window})`,
      lines: [`${h.n_smoothed} de ${h.n_input} valores · mínimo ${fmt(h.minimum)} · máximo ${fmt(h.maximum)} ${unit(h.unit)}`]
    };
  },
  event(finding) {
    const h = finding.how_much;
    const sense = h.direction === 'above' ? 'por encima' : 'por debajo';
    const lines = h.events.slice(0, 8).map(e => `${e.start}${e.end !== e.start ? ' a ' + e.end : ''}: ${e.duration_steps} paso(s), pico ${fmt(e.peak_value)} ${unit(h.unit)} (${e.peak_date})`);
    if (h.events.length > 8) lines.push(`… y ${h.n_events - 8} más.`);
    return {
      headline: h.n_events ? `${h.n_events} evento(s) ${sense} del percentil ${fmt(h.q * 100, 3)} de la base` : `Ningún evento ${sense} del percentil ${fmt(h.q * 100, 3)} de la base`,
      lines: [`Umbral entre ${fmt(h.threshold_min)} y ${fmt(h.threshold_max)} ${unit(h.unit)} · duración mínima ${h.min_duration_steps} paso(s)`, ...lines]
    };
  },
  association(finding) {
    const h = finding.how_much;
    const what = finding.what ?? {};
    const rows = h.lags.map(row => `Desfase ${row.lag}: r = ${fmt(row.r, 3)} · n efectivo ${fmt(row.n_effective, 3)} · p = ${pValue(row.p_value)}`
      + (row.q_value !== null ? ` · q = ${pValue(row.q_value)}${row.significant_fdr ? ' ✓' : ''}` : ' · no evaluable'));
    const lines = [`${what.first?.variable ?? 'primera'} → ${what.second?.variable ?? 'segunda'} · ${h.lag_convention}`, ...rows];
    if (h.partial && !h.partial.unavailable) {
      lines.push(`Correlación parcial (controlando ${h.partial.controls.join(', ')}): r = ${fmt(h.partial.r, 3)} · p = ${pValue(h.partial.p_value)}`);
    }
    return {
      headline: h.n_significant_fdr ? `Asociación estadísticamente significativa en ${h.n_significant_fdr} de ${h.n_tests} desfase(s)` : 'No hay evidencia suficiente de asociación en los desfases evaluados',
      lines
    };
  },
  climate_index(finding) {
    const h = finding.how_much;
    const lines = [`${h.n_years} años completos · media ${fmt(h.mean)} ${unit(h.unit)} · mínimo ${fmt(h.minimum)} · máximo ${fmt(h.maximum)} (${h.maximum_year})`,
      `Último año (${h.last_year}): ${fmt(h.last)} ${unit(h.unit)}`];
    if (h.threshold !== undefined) lines.push(`Umbral: percentil ${fmt(h.percentile)} de los días húmedos de la base = ${fmt(h.threshold)} mm (${h.n_reference_wet_days} días de referencia)`);
    lines.push('Por año: ' + h.years.map((year, i) => `${year}: ${fmt(h.values[i], 3)}`).slice(-12).join(' · '));
    return { headline: `${h.index}: ${h.title.charAt(0).toLowerCase()}${h.title.slice(1)}`, lines };
  },
  spatial_pattern(finding) {
    const h = finding.how_much;
    return {
      headline: `Patrón en una muestra de ${h.n_points} puntos`,
      lines: [...(h.n_distinct_series !== undefined && h.n_distinct_series < h.n_points
          ? [`Solo ${h.n_distinct_series} series distintas: varios puntos caen en la misma celda de la fuente`] : []),
        `${h.n_significant_fdr} de ${h.n_analyzed} series con tendencia significativa tras controlar falsos descubrimientos (${h.n_significant_raw} sin control)`,
        `Pendiente media: ${fmt(h.mean_per_decade)} ${unit(h.unit)} · ${h.n_positive} positivas, ${h.n_negative} negativas`]
    };
  }
};

/** headline + detail lines + notes + limitations for one finding. */
export function describeFinding(finding) {
  const render = FINDINGS[finding.type];
  const body = render && finding.how_much ? render(finding) : { headline: finding.conclusiveness === 'insufficient_data' ? 'Datos insuficientes' : `Resultado: ${finding.type}`, lines: [] };
  const header = finding.type === 'spatial_pattern' || finding.type === 'association'
    ? [] : [`${variable(finding)} · ${where(finding)}${when(finding) ? ' · ' + when(finding) : ''}`];
  return { ...body, context: header, notes: finding.notes ?? [], limitations: finding.limitations ?? [] };
}

/** Request value for one parameter input (raw string/boolean from the form), or undefined to keep the backend default. */
export function parameterValue(definition, raw) {
  if (raw === undefined || raw === null || raw === '') return undefined;
  if (definition.type === 'bool') return Boolean(raw);
  if (definition.type === 'int') return Number.parseInt(raw, 10);
  if (definition.type === 'float') return Number(raw);
  if (definition.type === 'int_list') return String(raw).split(/[ ,;]+/).filter(Boolean).map(item => Number.parseInt(item, 10));
  if (definition.type === 'period') return raw.start && raw.end ? { start: raw.start, end: raw.end } : undefined;
  return raw;
}
