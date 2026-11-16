import { writable } from 'svelte/store';

/** Last analysis run: { key: JSON of the investigation it was computed for, response: response.json }. */
export const analysisRun = writable(null);

/** An analysis proposed by the assistant, sent to the form to be reviewed or changed: { struct, targets, params?, hypothesis? }. */
export const analysisDraft = writable(null);
