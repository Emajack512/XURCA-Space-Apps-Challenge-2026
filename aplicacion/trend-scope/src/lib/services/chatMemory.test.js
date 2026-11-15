import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boundedPreparationContext, persistentTurns } from './chatMemory.js';

test('persisted history restores 200 real messages and excludes transient errors', () => {
  const turns = Array.from({ length: 203 }, (_, index) => ({ role: 'user', text: String(index) }));
  turns.push({ role: 'assistant', text: 'retry', temporary: true });
  const saved = JSON.parse(JSON.stringify({ messages: persistentTurns(turns), interactionId: 'v1_active' }));
  const restored = persistentTurns(saved.messages);
  assert.equal(restored.length, 200);
  assert.equal(restored[0].text, '3');
  assert.equal(restored.at(-1).text, '202');
  assert.equal(saved.interactionId, 'v1_active');
});

test('compaction preserves the initial request, recent replies and the API size budget', () => {
  const history = [{ role: 'user', text: 'Precipitación de Jamaica durante 2025' }];
  for (let i = 0; i < 95; i++) history.push({ role: 'assistant', text: 'Respuesta ' + i + ': ' + 'x'.repeat(880) });
  history.push({ role: 'user', text: 'Mismo lugar, ahora irradiancia' });
  const encoded = boundedPreparationContext({ history, today: '2026-11-15' });
  const decoded = JSON.parse(encoded);
  assert.ok(encoded.length <= 23500);
  assert.equal(decoded.olderUserRequests[0], history[0].text);
  assert.deepEqual(decoded.history.at(-1), history.at(-1));
  assert.ok(decoded.history.some(message => message.role === 'assistant'));
});
