<script>
  import { onMount } from 'svelte';
  import { ChartNoAxesCombined, FileText } from '@lucide/svelte';
  import ChartView from './ChartView.svelte';
  import EventMap from './EventMap.svelte';
  import { catalog } from '$lib/services/sources.js';
  import { translate } from '$lib/services/i18n.js';
  import { listAnalyses } from '$lib/services/acquisition.js';
  import { resultSummary } from '$lib/services/resultSummary.js';
  import { analysisRun } from '$lib/stores/analysis.js';
  import { workspace } from '$lib/stores/workspace.js';

  let resolution = $derived($workspace.visual.chartResolution ?? 'auto');
  let cadence = $derived($workspace.visual.chartCadence ?? 'native');
  // all: every series of the current query, for the report below the last chart.
  let { series, all = series, mapsOnly = false } = $props();
  let titles = $state({});
  let fresh = $derived($analysisRun !== null && $analysisRun.key === JSON.stringify($workspace.data));
  let report = $derived(mapsOnly ? null : resultSummary(all, $analysisRun, fresh, titles));

  onMount(async () => {
    try {
      const { analyses } = await listAnalyses();
      titles = Object.fromEntries(analyses.map(item => [item.struct_id, item.title]));
    } catch { /* Titles fall back to the analysis id. */ }
  });
</script>

<section class="results-panel">
  <header class="panel-heading"><span><ChartNoAxesCombined size={16}/> {$translate(mapsOnly ? (series[0]?.map?.pointView ? 'Mapa de datos' : 'Mapa coroplético') : 'Resultados')}</span>
  </header>
  <div class="results-scroll">
    {#each series as item (item.id)}
      {@const available = item.points.filter(point => point.value !== null).length}
      {@const variableLabel = catalog.find(source => source.id === item.id.split('::')[0])?.label ?? item.label ?? item.variable}
      {@const label = $translate(item.sourceSelection ? variableLabel.replace(/ \([^()]+\)$/, '') : variableLabel)}
      <article class="chart-card" data-series-id={item.id}>
        <header><strong>{label}</strong></header>
        {#if item.sourceSelection}<p class="quiet">{item.sourceSelection}</p>{/if}
        {#if item.downloadPath}<p class="quiet"><code>{item.downloadPath}</code></p>{/if}
        {#if mapsOnly && item.map}
          {#key item.map}
            <EventMap layer={item.map} {label} unit={$translate(item.map.unit ?? item.unit)}/>
          {/key}
        {/if}
        {#if item.mapMessage}<p>{item.mapMessage}</p>{/if}
        {#if item.cadence === 'distribution' && item.message}<p>{item.message}</p>{/if}
        {#if !mapsOnly && available}
          <ChartView series={item} {label} {resolution} {cadence}/>
        {:else if !mapsOnly && !item.message}
          <p>{$translate('No hay valores para el período seleccionado.')}</p>
        {/if}
      </article>
    {:else}
      <p class="quiet">{$translate('Elegí un punto en el mapa y consultá la serie para ver los resultados.')}</p>
    {/each}
    {#if report && all.length}
      <article class="chart-card result-report" aria-live="polite">
        <header><strong><FileText size={15}/> Resumen de lo que estás viendo</strong>
          <span class="tag">{report.status.done ? 'Procesado' : 'Sin procesar'}</span></header>
        <p>{report.lines[0]}</p>
        <ul>{#each report.data as line}<li>{line}</li>{/each}</ul>
        {#each report.status.lines as line}<p>{line}</p>{/each}
        <p class="quiet">{report.status.next}</p>
      </article>
    {/if}
  </div>
</section>

<style>
  .result-report header strong { display: inline-flex; align-items: center; gap: 6px; }
  .result-report ul { margin: 6px 0; padding-left: 18px; }
  .result-report li { margin-bottom: 4px; }
</style>
