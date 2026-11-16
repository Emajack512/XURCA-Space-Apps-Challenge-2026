import { writable } from 'svelte/store';

/** Settings section the guided tour wants open ("objective", "sources", "time", "geography"). */
export const revealSection = writable(null);
/** Text the guided tour writes into the chat box (the user only presses Send). */
export const chatDraft = writable(null);
/** Current choice in the statistical-analysis form, so the tour can tell when a step is done. */
export const analysisForm = writable({ structId: null, targets: [] });

const storageKey = 'trendscope.tutorial.v1';

/** { level: 'novice' | 'intermediate' | 'expert', finished: boolean } or null on first run. */
export function loadTutorial() {
  try { return JSON.parse(localStorage.getItem(storageKey) ?? 'null'); } catch { return null; }
}

export function saveTutorial(value) {
  try { localStorage.setItem(storageKey, JSON.stringify(value)); } catch { /* The tutorial still works this session. */ }
}
