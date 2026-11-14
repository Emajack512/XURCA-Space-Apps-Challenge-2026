<script>
  import { Activity, ChartNoAxesCombined, Maximize2, Minimize2, Plus, X } from '@lucide/svelte';
  import ChartView from './ChartView.svelte';
  import { workspace, addChart, editChart, editVisual } from '$lib/stores/workspace.js';
  import { chartTypes, statistics } from '$lib/services/demo.js';

  let { chartId = $bindable(), resultStatus } = $props();
  let visual = $derived($workspace.visual);
  let charts = $derived(visual.expandedChart ? visual.charts.filter(chart => chart.id === visual.expandedChart) : visual.charts);
  let tab = $state('charts');
  let addType = $state('line');
  function remove(id) {
    editVisual(next => {
      next.charts = next.charts.filter(chart => chart.id !== id);
      if (next.expandedChart === id) next.expandedChart = null;
      if (chartId === id) chartId = next.charts[0]?.id;
    });
  }
  function add() {
    addChart(addType);
    editVisual(next => { next.expandedChart = null; chartId = next.charts.at(-1).id; });
  }
</script>

<section class="results-panel">
  <header class="panel-heading"><span><ChartNoAxesCombined size={16}/> Resultados</span><span class="tag simulation-tag">Simulados</span></header>
  <div class="result-tabs">
    <button class:active={tab === 'charts'} onclick={() => tab = 'charts'}>Gráficas</button>
    <button class:active={tab === 'stats'} onclick={() => tab = 'stats'}>Estadísticas</button>
  </div>
  <div class="results-scroll">
    {#if tab === 'charts'}
      <div class="result-actions">
        <select aria-label="Tipo para nueva gráfica" bind:value={addType}>{#each chartTypes as item}<option value={item.id}>{item.label}</option>{/each}</select>
        <button class="outlined" onclick={add}><Plus size={15}/> Agregar</button>
      </div>
      {#each charts as chart (chart.id)}
        <article class:current={chartId === chart.id} class:expanded={visual.expandedChart === chart.id} class="chart-card">
          <header>
            <button class="chart-title" onclick={() => chartId = chart.id}>{chart.title || 'Gráfica sin título'}</button>
            <button class="icon-button" title={visual.expandedChart ? 'Restaurar' : 'Maximizar'} aria-label={visual.expandedChart ? 'Restaurar' : 'Maximizar'} onclick={() => editVisual(next => next.expandedChart = next.expandedChart ? null : chart.id)}>
              {#if visual.expandedChart}<Minimize2 size={14}/>{:else}<Maximize2 size={14}/>{/if}
            </button>
            <button class="icon-button" title="Eliminar gráfica" aria-label="Eliminar gráfica" onclick={() => remove(chart.id)}><X size={15}/></button>
          </header>
          <div class="chart-meta">
            <Activity size={13}/><span>2000–2025</span>
            <select aria-label={'Tipo de ' + chart.title} value={chart.type} onchange={event => editChart(chart.id, next => {
              next.type = event.currentTarget.value;
              next.yLabel = next.type === 'histogram' ? 'Frecuencia' : 'mm/mes';
              if (next.type === 'comparison') next.series.secondary.visible = true;
            })}>{#each chartTypes as item}<option value={item.id}>{item.label}</option>{/each}</select>
          </div>
          <ChartView {chart}/>
        </article>
      {:else}<p class="quiet">Agregá una gráfica para explorar las series de demostración.</p>{/each}
    {/if}
    {#if tab === 'stats' || !visual.expandedChart}
      <div class="stats-heading"><span>Resumen estadístico</span><span>{resultStatus}</span></div>
      <div class="stat-grid">
        {#each statistics as [label,value,unit]}
          <div class="stat"><small>{label}</small><strong>{value}</strong><span>{unit}</span></div>
        {/each}
      </div>
      <p class="quiet">Valores de ejemplo. Ejecutar la demostración confirma el flujo con la configuración actual y conserva estas series de muestra.</p>
    {/if}
  </div>
</section>
