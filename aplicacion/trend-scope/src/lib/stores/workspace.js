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
export function selectGeometry(type, coordinates, name = '') {
  const feature = {
    type: 'Feature', id: crypto.randomUUID(), properties: { name },
    geometry: { type, coordinates: JSON.parse(JSON.stringify(coordinates)) }
  };
  editData(data => data.geography.selection.features.push(feature));
  return feature.id;
}

/** Removes selections and unbinds every variable that pointed at them. */
export function removeSelections(shouldRemove) {
  let removed = [];
  editData(data => {
    const features = data.geography.selection.features;
    removed = features.filter(shouldRemove).map(feature => feature.id);
    data.geography.selection.features = features.filter(feature => !removed.includes(feature.id));
    for (const source of data.sources) {
      if (removed.includes(source.upstream?.geometryId)) source.upstream.geometryId = null;
    }
  });
  return removed;
}
