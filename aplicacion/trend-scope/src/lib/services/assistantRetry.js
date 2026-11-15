export const assistantRetryDelay = 5000;

export function shouldRetryAssistant(error) {
  const reason = String(error?.message ?? error);
  const status = Number(reason.match(/HTTP (\d{3})/i)?.[1]);
  if (status === 429) {
    const after = reason.match(/Retry-After: (\d+)/i)?.[1];
    return Boolean(after) && Number(after) * 1000 <= assistantRetryDelay;
  }
  return !(status >= 400 && status < 500 && status !== 408);
}

export function waitForAssistantRetry() {
  return new Promise(resolve => setTimeout(resolve, assistantRetryDelay));
}
