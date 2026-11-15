import { writable } from 'svelte/store';

/** Last analysis run: { key: JSON of the investigation it was computed for, response: response.json }. */
export const analysisRun = writable(null);
