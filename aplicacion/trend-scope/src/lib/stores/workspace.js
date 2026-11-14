import { writable } from 'svelte/store';
import dataDefaults from '../../../config/cfg_data.json';
import visualDefaults from '../../../config/cfg_visual.json';

export const defaults = () => ({ data: structuredClone(dataDefaults), visual: structuredClone(visualDefaults) });
export const workspace = writable(defaults());

export function updateConfig(section, edit) {
  workspace.update(current => {
    const next = JSON.parse(JSON.stringify(current[section]));
    edit(next);
    return { ...current, [section]: next };
  });
}

export const editData = edit => updateConfig('data', edit);
export const editVisual = edit => updateConfig('visual', edit);
export const editChart = (id, edit) => editVisual(visual => {
  const chart = visual.charts.find(item => item.id === id);
  if (chart) edit(chart);
});

export function selectGeometry(type, coordinates, name = '') {
  const feature = {
    type: 'Feature', id: crypto.randomUUID(), properties: { name },
    geometry: { type, coordinates: JSON.parse(JSON.stringify(coordinates)) }
  };
  editData(data => data.geography.selection.features.push(feature));
}

export function addChart(type = 'line') {
  const titles = { line: 'Serie temporal', histogram: 'Distribución', comparison: 'Comparación de productos', scatter: 'Relación entre variables' };
  editVisual(visual => visual.charts.push({
    ...structuredClone(visualDefaults.charts[0]),
    id: crypto.randomUUID(), type, title: titles[type], yLabel: type === 'histogram' ? 'Frecuencia' : 'mm/mes',
    series: { primary: { visible: true, color: '#57dfc1' }, secondary: { visible: type === 'comparison', color: '#77a6fb' } }
  }));
}
