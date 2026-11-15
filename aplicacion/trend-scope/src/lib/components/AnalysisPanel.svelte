<script>
  import { onMount } from 'svelte';
  import { FlaskConical, Play } from '@lucide/svelte';
  import ForecastChart from './ForecastChart.svelte';
  import { listAnalyses } from '$lib/services/acquisition.js';
  import { executeAnalysis } from '$lib/services/analysisRunner.js';
  import { analysisRun } from '$lib/stores/analysis.js';
  import { describeFinding, parameterValue, statusText, verdictText } from '$lib/services/analysisText.js';
  import { catalog } from '$lib/services/sources.js';
  import { translate } from '$lib/services/i18n.js';
  import { workspace } from '$lib/stores/workspace.js';

  // buildInvestigation() returns the cfg_data to analyse (or null after notifying why not).
  let { buildInvestigation, notify } = $props();

  const PREPARATION = ['aggregate', 'min_coverage', 'gap_policy'];
  const HYPOTHESES = {
    trend: 'Hay una tendencia', threshold: 'Se supera un umbral', change_point: 'Hay un cambio de régimen',
    relationship: 'Hay asociación', forecast_threshold: 'El pronóstico supera un umbral'
  };

  let catalogue = $state(null);
  let loadError = $state('');
  let structId = $state('trend_significance');
  let targets = $state([]);
  let values = $state({});
  let hypothesisKind = $state('');
  let hypothesis = $state({ direction: 'any', operator: '>', statistic: 'last', sign: 'any' });
  let running = $state(false);
  let response = $derived($analysisRun?.response ?? null);
  let stale = $derived($analysisRun !== null && $analysisRun.key !== JSON.stringify($workspace.data));

  let sources = $derived($workspace.data.sources);
  let struct = $derived(catalogue?.analyses.find(item => item.struct_id === structId));
  let primary = $derived(Object.entries(struct?.params ?? {}).filter(([name]) => !PREPARATION.includes(name)));
  let preparation = $derived(Object.entries(struct?.params ?? {}).filter(([name]) => PREPARATION.includes(name)));
  let multiple = $derived((struct?.targets.max ?? 1) > 1);

  onMount(async () => {
    try { catalogue = await listAnalyses(); } catch (error) { loadError = String(error.message ?? error); }
  });

  function changeStruct(event) {
    structId = event.currentTarget.value;
    values = {};
    hypothesisKind = '';
    const limit = catalogue?.analyses.find(item => item.struct_id === structId)?.targets.max ?? 1;
    targets = targets.slice(0, limit);
  }

  function label(source) {
    const known = catalog.find(item => item.id === source.id.split('::')[0]);
    return $translate(known?.label ?? source.label ?? source.id);
  }

  function pick(id) {
    if (!multiple) { targets = [id]; return; }
    targets = targets.includes(id) ? targets.filter(item => item !== id) : [...targets, id].slice(0, struct.targets.max);
  }

  function role(index) { return index === 0 ? 'antecede' : index === 1 ? 'respuesta' : 'control'; }

  function hypothesisBody() {
    if (!hypothesisKind) return undefined;
    const h = { kind: hypothesisKind };
    if (hypothesisKind === 'trend') {
      h.direction = hypothesis.direction;
      if (hypothesis.min_rate) h.min_rate = Number(hypothesis.min_rate);
    } else if (hypothesisKind === 'threshold') {
      Object.assign(h, { operator: hypothesis.operator, value: Number(hypothesis.value), statistic: hypothesis.statistic });
    } else if (hypothesisKind === 'forecast_threshold') {
      Object.assign(h, { operator: hypothesis.operator, value: Number(hypothesis.value) });
      if (hypothesis.at_step) h.at_step = Number.parseInt(hypothesis.at_step, 10);
    } else if (hypothesisKind === 'relationship') {
      h.sign = hypothesis.sign;
    } else if (hypothesisKind === 'change_point' && hypothesis.start && hypothesis.end) {
      h.window = { start: hypothesis.start, end: hypothesis.end };
    }
    return h;
  }

  async function run() {
    if (running || !struct) return;
    if (!struct.available) { notify(struct.reason ?? 'Este análisis no está disponible.'); return; }
    if (targets.length < struct.targets.min) {
      notify(struct.targets.min > 1 ? `Elegí al menos ${struct.targets.min} variables.` : 'Elegí una variable.');
      return;
    }
    const params = {};
    for (const [name, definition] of Object.entries(struct.params)) {
      const value = parameterValue(definition, values[name]);
      if (value !== undefined) params[name] = value;
      else if (definition.required) { notify(`Completá el parámetro obligatorio: ${name}.`); return; }
    }
    const body = hypothesisBody();
    if (body?.kind === 'threshold' && !Number.isFinite(body.value)) { notify('Indicá el valor del umbral.'); return; }
    if (body?.kind === 'forecast_threshold' && !Number.isFinite(body.value)) { notify('Indicá el valor del umbral.'); return; }
    const investigation = buildInvestigation();
    if (!investigation) return;
    running = true;
    analysisRun.set(null);
    try {
      await executeAnalysis(investigation, { struct: structId, targets: [...targets], params, hypothesis: body },
        JSON.stringify($workspace.data));
    } catch (error) {
      notify(String(error.message ?? error));
    } finally {
      running = false;
    }
  }
</script>

<section class="results-panel analysis-panel">
  <header class="panel-heading"><span><FlaskConical size={16}/> {$translate('Análisis estadístico')}</span></header>
  <div class="results-scroll">
    {#if loadError}
      <p class="quiet">{loadError}</p>
    {:else if !catalogue}
      <p class="quiet">{$translate('Cargando análisis…')}</p>
    {:else}
      <form class="analysis-form" onsubmit={event => { event.preventDefault(); run(); }}>
        <label>{$translate('Análisis')}
          <select value={structId} onchange={changeStruct}>
            {#each catalogue.analyses as item (item.struct_id)}
              <option value={item.struct_id} disabled={!item.available}>{item.title}{item.available ? '' : ' — no disponible'}</option>
            {/each}
          </select>
        </label>
        {#if struct}
          <p class="quiet">{struct.description}</p>
          {#if !struct.available}<p class="analysis-error">{struct.reason}</p>{/if}
          <fieldset>
            <legend>{multiple ? `Variables (${struct.targets.min} a ${struct.targets.max}, en orden: antecede, respuesta, controles)` : 'Variable'}</legend>
            {#each sources as source (source.id)}
              {@const position = targets.indexOf(source.id)}
              <label class="check">
                <input type={multiple ? 'checkbox' : 'radio'} name="target" checked={position >= 0} onchange={() => pick(source.id)}/>
                <span>{label(source)}{multiple && position >= 0 ? ` · ${role(position)}` : ''}</span>
              </label>
            {:else}
              <p class="quiet">{$translate('Agregá variables en la configuración.')}</p>
            {/each}
          </fieldset>
          <div class="analysis-params">
            {#each primary as [name, definition] (name)}
              <label>{name}{definition.required ? ' *' : ''}{definition.provisional ? ' (provisional)' : ''}
                {#if definition.type === 'bool'}
                  <input type="checkbox" checked={values[name] ?? definition.default} onchange={event => values[name] = event.currentTarget.checked}/>
                {:else if definition.choices?.length}
                  <select value={values[name] ?? definition.default} onchange={event => values[name] = event.currentTarget.value}>
                    {#each definition.choices as choice}<option value={choice}>{choice}</option>{/each}
                  </select>
                {:else if definition.type === 'period'}
                  <span class="input-row">
                    <input type="date" aria-label="inicio" value={values[name]?.start ?? ''} onchange={event => values[name] = { ...values[name], start: event.currentTarget.value }}/>
                    <input type="date" aria-label="fin" value={values[name]?.end ?? ''} onchange={event => values[name] = { ...values[name], end: event.currentTarget.value }}/>
                  </span>
                {:else}
                  <input type={definition.type === 'int_list' ? 'text' : 'number'} step={definition.type === 'int' ? 1 : 'any'}
                    placeholder={definition.default !== null && definition.default !== undefined ? String(definition.default)
                      : Object.keys(definition.by_value ?? {}).length
                        ? 'automático: ' + Object.entries(definition.by_value).map(([key, value]) => `${value} (${key})`).join(' · ')
                        : definition.required ? '' : 'automático'}
                    value={values[name] ?? ''} oninput={event => values[name] = event.currentTarget.value}/>
                {/if}
                <small>{definition.description}</small>
              </label>
            {/each}
          </div>
          {#if preparation.length}
            <details>
              <summary>{$translate('Preparación de los datos')}</summary>
              <div class="analysis-params">
                {#each preparation as [name, definition] (name)}
                  <label>{name}
                    {#if definition.choices?.length}
                      <select value={values[name] ?? definition.default} onchange={event => values[name] = event.currentTarget.value}>
                        {#each definition.choices as choice}<option value={choice}>{choice}</option>{/each}
                      </select>
                    {:else}
                      <input type="number" step="any" min={definition.minimum} max={definition.maximum}
                        placeholder={String(definition.default)} value={values[name] ?? ''} oninput={event => values[name] = event.currentTarget.value}/>
                    {/if}
                    <small>{definition.description}</small>
                  </label>
                {/each}
              </div>
            </details>
          {/if}
          {#if struct.hypotheses.length}
            <label>{$translate('Hipótesis (opcional)')}
              <select bind:value={hypothesisKind}>
                <option value="">{$translate('Sin hipótesis')}</option>
                {#each struct.hypotheses as kind}<option value={kind}>{HYPOTHESES[kind] ?? kind}</option>{/each}
              </select>
            </label>
            {#if hypothesisKind === 'trend'}
              <div class="analysis-params">
                <label>Dirección<select bind:value={hypothesis.direction}><option value="any">cualquiera</option><option value="increasing">creciente</option><option value="decreasing">decreciente</option></select></label>
                <label>Tasa mínima por año (opcional)<input type="number" step="any" min="0" bind:value={hypothesis.min_rate}/></label>
              </div>
            {:else if hypothesisKind === 'threshold' || hypothesisKind === 'forecast_threshold'}
              <div class="analysis-params">
                {#if hypothesisKind === 'threshold'}
                  <label>Estadístico<select bind:value={hypothesis.statistic}><option value="last">último valor</option><option value="max">máximo</option><option value="min">mínimo</option><option value="mean">media</option></select></label>
                {:else}
                  <label>Paso del pronóstico<input type="number" min="1" step="1" bind:value={hypothesis.at_step}/></label>
                {/if}
                <label>Operador<select bind:value={hypothesis.operator}><option>&gt;</option><option>&lt;</option><option>&gt;=</option><option>&lt;=</option></select></label>
                <label>Valor<input type="number" step="any" bind:value={hypothesis.value}/></label>
              </div>
            {:else if hypothesisKind === 'relationship'}
              <label>Signo esperado<select bind:value={hypothesis.sign}><option value="any">cualquiera</option><option value="positive">positivo</option><option value="negative">negativo</option></select></label>
            {:else if hypothesisKind === 'change_point'}
              <div class="analysis-params">
                <label>Ventana desde (opcional)<input type="date" bind:value={hypothesis.start}/></label>
                <label>Ventana hasta<input type="date" bind:value={hypothesis.end}/></label>
              </div>
            {/if}
          {/if}
          <button class="primary" disabled={running || !struct.available}><Play size={15} fill="currentColor"/> {$translate(running ? 'Analizando…' : 'Analizar')}</button>
        {/if}
      </form>
    {/if}

    {#if response}
      <section class="analysis-output" aria-live="polite">
        {#if stale}<p class="analysis-error">{$translate('La configuración cambió después de este análisis. Volvé a ejecutarlo para actualizarlo.')}</p>{/if}
        <p><strong>{$translate('Estado')}:</strong> {statusText(response.status)}</p>
        {#each response.errors as item}<p class="analysis-error">{item.message}</p>{/each}
        {#each response.analyses as block (block.id)}
          <article class="chart-card">
            <header><strong>{catalogue?.analyses.find(item => item.struct_id === block.struct)?.title ?? block.struct}</strong>
              <span class="tag">{statusText(block.status)}</span></header>
            {#each block.errors as item}<p class="analysis-error">{item.message}</p>{/each}
            {#if block.verdict}
              {@const verdict = verdictText(block.verdict)}
              <div class="verdict {verdict.status}">
                <strong>{verdict.title}</strong>
                {#each verdict.lines as line}<p class="quiet">{line}</p>{/each}
              </div>
            {/if}
            {#each block.findings as finding}
              {@const text = describeFinding(finding)}
              <div class="finding">
                <strong>{text.headline}</strong>
                {#each text.context as line}<p class="quiet">{line}</p>{/each}
                {#each text.lines as line}<p>{line}</p>{/each}
                {#each text.notes as note}<p class="quiet">{note}</p>{/each}
                {#if text.limitations.length}
                  <details><summary>{$translate('Limitaciones')}</summary>{#each text.limitations as item}<p class="quiet">{item}</p>{/each}</details>
                {/if}
              </div>
            {/each}
            {#if block.forecast}
              {@const history = response.series.find(item => item.id === block.targets[0])?.points}
              <ForecastChart {history} forecast={block.forecast} label={block.targets[0]}/>
              <table class="forecast-table">
                <thead><tr><th>Fecha</th><th>Central</th>{#if block.forecast.interval}<th>Inferior</th><th>Superior</th>{/if}<th>Referencia</th></tr></thead>
                <tbody>
                  {#each block.forecast.times as time, index}
                    <tr><td>{time.slice(0, 7)}</td><td>{block.forecast.central[index]?.toPrecision(4)}</td>
                      {#if block.forecast.interval}<td>{block.forecast.interval.lower[index]?.toPrecision(4) ?? '—'}</td><td>{block.forecast.interval.upper[index]?.toPrecision(4) ?? '—'}</td>{/if}
                      <td>{block.forecast.baseline.values[index]?.toPrecision(4)}</td></tr>
                  {/each}
                </tbody>
              </table>
              <p class="quiet">Unidad: {block.forecast.unit}. {block.forecast.interval ? `Intervalo predictivo de nivel ${block.forecast.interval.level}` : 'Sin intervalo: el pronóstico no está calibrado.'}
                {block.forecast.mode === 'validated_forecast' ? ' Validado con backtest de origen móvil.' : ' Exploratorio: no superó la validación.'}</p>
            {/if}
            {#if block.warnings.length}
              <details><summary>{$translate('Avisos')} ({block.warnings.length})</summary>{#each block.warnings.slice(0, 12) as warning}<p class="quiet">{warning.message}</p>{/each}</details>
            {/if}
            {#if block.steps.length}
              <details>
                <summary>{$translate('Cómo se calculó')}</summary>
                {#each block.transformations as item}<p class="quiet">Transformación: {item.operation}</p>{/each}
                {#each block.steps as step}
                  <p class="quiet">{step.label}: {step.status === 'completed' ? step.method_id : step.status}{step.selected_because ? ' — ' + step.selected_because : ''}{step.reason ? ' — ' + step.reason : ''}</p>
                {/each}
              </details>
            {/if}
          </article>
        {/each}
      </section>
    {/if}
  </div>
</section>
