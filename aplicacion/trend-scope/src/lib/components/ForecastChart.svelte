<script>
  import { Chart, registerables } from 'chart.js';
  import { workspace } from '$lib/stores/workspace.js';
  Chart.register(...registerables);
  let { history, forecast, label } = $props();
  let light = $derived($workspace.visual.theme === 'light');
  let canvas = $state();

  function config(isLight) {
    const past = (history ?? []).filter(point => point.value !== null).slice(-72);
    const month = text => String(text).slice(0, 7);
    const labels = [...past.map(point => month(point.month)), ...forecast.times.map(month)];
    const blank = forecast.times.map(() => null);
    const lead = past.map((_, index) => index === past.length - 1 ? past[index].value : null);
    const text = isLight ? '#1d2733' : '#dbe6f2';
    const grid = isLight ? '#d7dee7' : '#2a3b4f';
    const fan = forecast.interval;
    const band = fan ? [
      { label: `Intervalo predictivo ${Math.round(fan.level * 100)}%`, data: [...past.map(() => null), ...fan.lower],
        borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(120,170,240,.25)', fill: '+1' },
      { label: 'Límite superior', data: [...past.map(() => null), ...fan.upper], borderWidth: 0, pointRadius: 0, fill: false }
    ] : [];
    return {
      type: 'line',
      data: { labels, datasets: [
        { label, data: [...past.map(point => point.value), ...blank], borderColor: '#7fb2ff', borderWidth: 1.5, pointRadius: 0, tension: 0 },
        { label: 'Pronóstico central', data: [...lead, ...forecast.central], borderColor: '#ffb454', borderDash: [5, 4], borderWidth: 2, pointRadius: 2 },
        { label: 'Referencia (' + forecast.baseline.name + ')', data: [...lead, ...forecast.baseline.values], borderColor: '#8a97a8', borderDash: [2, 3], borderWidth: 1, pointRadius: 0 },
        ...band
      ] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { labels: { color: text, filter: item => item.text !== 'Límite superior' } } },
        scales: { x: { ticks: { color: text, maxTicksLimit: 8 }, grid: { color: grid } },
                  y: { title: { display: true, text: forecast.unit, color: text }, ticks: { color: text }, grid: { color: grid } } }
      }
    };
  }

  $effect(() => {
    if (!canvas) return;
    const graph = new Chart(canvas, config(light));
    return () => graph.destroy();
  });
</script>
<div class="chart-canvas forecast-canvas" role="img" aria-label={label}><canvas bind:this={canvas}></canvas></div>
