const savedMessageLimit = 200;

export function persistentTurns(messages) {
  return messages.filter(message => message && !message.temporary && typeof message.text === 'string'
    && ['user', 'assistant'].includes(message.role)).slice(-savedMessageLimit)
    .map(({ role, text, status, collections, preparation }) => ({ role, text, status, collections, preparation }));
}

export function boundedPreparationContext(context, limit = 23500) {
  if (JSON.stringify(context).length <= limit) return JSON.stringify(context);
  const history = [...context.history];
  const earlier = [];
  const bounded = { ...context, history, olderUserRequests: [] };
  const margin = Math.min(2400, Math.floor(limit / 8));
  while (history.length && JSON.stringify(bounded).length > limit - margin) {
    const turn = history.shift();
    if (turn.role === 'user') earlier.push(turn.text.slice(0, 240));
  }
  // Keep the start of the investigation as well as the latest archived requests.
  const distinct = [...new Set(earlier)];
  bounded.olderUserRequests = [...distinct.slice(0, 2), ...distinct.slice(2).slice(-12)];
  while (bounded.olderUserRequests.length && JSON.stringify(bounded).length > limit) {
    bounded.olderUserRequests.splice(Math.min(2, bounded.olderUserRequests.length - 1), 1);
  }
  return JSON.stringify(bounded);
}
