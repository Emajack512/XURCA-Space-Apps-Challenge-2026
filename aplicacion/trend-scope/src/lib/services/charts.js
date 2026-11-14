import { observations } from './demo.js';

const points = (field, x = 'year') => observations.map(row => ({ x: row[x], y: row[field] }));
function histogram(field) {
  return Array.from({ length: 8 }, (_, index) => {
    const low = 40 + index * 10;
    return { x: low + 5, y: observations.filter(row => row[field] >= low && row[field] < low + 10).length };
  });
}

export function chartSpec(chart) {
  const { type, series } = chart;
  const histogramMode = type === 'histogram';
  const scatterMode = type === 'scatter';
  const datasets = [];
  for (const [id, style] of Object.entries(series)) {
    if (!style.visible) continue;
    const data = histogramMode ? histogram(id)
      : scatterMode ? points(id, id === 'primary' ? 'secondary' : 'primary')
      : points(id);
    datasets.push({
      label: id === 'primary' ? (scatterMode ? 'A en función de B' : 'Producto A') : (scatterMode ? 'B en función de A' : 'Producto B'),
      data, borderColor: style.color, backgroundColor: style.color + (histogramMode ? 'a8' : 'ff'),
      borderWidth: histogramMode ? 0 : 2, pointRadius: scatterMode ? 3 : 0, pointHoverRadius: 5
    });
  }
  if (type === 'line' && series.primary.visible) {
    if (chart.interval) {
      for (const offset of [-10, 10]) {
        datasets.push({ label: 'IC simulado', interval: true, data: observations.map(row => ({ x: row.year, y: row.trend + offset })),
          fill: offset > 0 ? '-1' : false, borderColor: 'transparent', pointRadius: 0, pointHoverRadius: 0, backgroundColor: series.primary.color + '22' });
      }
    }
    if (chart.trend) datasets.push({ label: 'Tendencia', data: points('trend'), borderColor: '#f5ba7c', borderDash: [6,5], borderWidth: 1.5, pointRadius: 0 });
  }
  const axis = (label) => ({
    title: { display: !!label, text: label, color: '#93a2b6' },
    ticks: { color: '#93a2b6', maxTicksLimit: 6, font: { size: 10 } }, grid: { display: chart.grid, color: '#1f3044' },
    border: { color: '#304057' }
  });
  const options = {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: histogramMode || scatterMode ? 'nearest' : 'index', intersect: false },
    scales: {
      x: {
        ...axis(chart.xLabel || (histogramMode || scatterMode ? 'mm/mes' : 'Año')),
        type: 'linear',
        ticks: { ...axis('').ticks, callback: value => String(value) }
      },
      y: { ...axis(chart.yLabel), type: chart.scale }
    },
    plugins: {
      legend: { display: chart.legend, position: 'bottom', labels: { color: '#abb8c9', boxWidth: 10, usePointStyle: true, padding: 13, filter: item => item.text !== 'IC simulado' } },
      tooltip: { filter: item => !item.dataset.interval, callbacks: {
        title: items => items.length ? (histogramMode || scatterMode ? Number(items[0].parsed.x.toFixed(1)) + ' mm/mes' : Math.floor(items[0].parsed.x).toString()) : ''
      } }
    }
  };
  return { type: histogramMode ? 'bar' : scatterMode ? 'scatter' : 'line', data: { datasets }, options };
}
