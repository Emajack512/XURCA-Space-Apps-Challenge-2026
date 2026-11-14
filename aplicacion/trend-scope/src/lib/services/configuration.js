import { isTauri } from '@tauri-apps/api/core';
import { pyInvoke } from 'tauri-plugin-pytauri-api';

const files = { data: 'cfg_data.json', visual: 'cfg_visual.json' };
const browserKey = 'earth-detective.workspace';

export async function loadWorkspace() {
  let snapshot;
  if (isTauri()) {
    const entries = await Promise.all(Object.entries(files).map(async ([key, name]) => {
      const raw = await pyInvoke('load_configuration', { name });
      return [key, raw ? JSON.parse(raw) : null];
    }));
    snapshot = Object.fromEntries(entries);
  } else {
    snapshot = JSON.parse(localStorage.getItem(browserKey) ?? 'null');
  }
  for (const key of Object.keys(files)) {
    if (snapshot?.[key] && snapshot[key].schemaVersion !== 1) {
      throw new Error('Versión de esquema incompatible en ' + files[key]);
    }
  }
  return snapshot;
}

export async function saveWorkspace(snapshot) {
  if (isTauri()) {
    await pyInvoke('save_configuration', {
      data: JSON.stringify(snapshot.data, null, 2), visual: JSON.stringify(snapshot.visual, null, 2)
    });
  } else {
    localStorage.setItem(browserKey, JSON.stringify(snapshot));
  }
}

export function downloadJson(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
