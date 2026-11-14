<script>
  import { Chart, registerables } from 'chart.js';
  import { chartSpec } from '$lib/services/charts.js';
  Chart.register(...registerables);
  let { chart } = $props();
  let canvas = $state();
  $effect(() => {
    if (!canvas) return;
    const graph = new Chart(canvas, chartSpec(chart));
    return () => graph.destroy();
  });
</script>
<div class="chart-canvas" role="img" aria-label={chart.title + ' con datos simulados'}><canvas bind:this={canvas}></canvas></div>
