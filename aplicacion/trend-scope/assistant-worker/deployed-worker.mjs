function reply(body, status = 200, retryAfter) {
  const headers = { 'Cache-Control': 'no-store' };
  if (retryAfter) headers['Retry-After'] = retryAfter;
  return Response.json(body, { status, headers });
}

const api = 'https://generativelanguage.googleapis.com/v1beta';
const model = 'gemini-3.5-flash-lite';

function runInteraction(prompt, previousInteractionId, key) {
  return fetch(api + '/interactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key, 'Api-Revision': '2026-05-20' },
    signal: AbortSignal.timeout(25_000),
    body: JSON.stringify({
      model, input: prompt, store: true,
      previous_interaction_id: previousInteractionId ?? undefined
    })
  });
}

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return reply({ error: 'Usar POST' }, 405);

    let body;
    try {
      body = await request.json();
    } catch {
      return reply({ error: 'JSON inválido' }, 400);
    }
    const prompt = body?.prompt;
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 40_000) {
      return reply({ error: 'El prompt debe tener entre 1 y 40.000 caracteres' }, 400);
    }
    const previousId = body.previousInteractionId;
    if (previousId != null && (typeof previousId !== 'string' || !/^[A-Za-z0-9_-]{1,256}$/.test(previousId))) {
      return reply({ error: 'Identificador de chat inválido' }, 400);
    }
    if (!env.GEMINI_API_KEY) {
      console.error('Falta el secreto GEMINI_API_KEY');
      return reply({ error: 'Asistente temporalmente no disponible' }, 503);
    }

    try {
      if (Object.hasOwn(body, 'previousInteractionId')) {
        let interaction = await runInteraction(prompt, previousId, env.GEMINI_API_KEY);
        if (previousId && [400, 404, 410].includes(interaction.status)) {
          await interaction.body?.cancel();
          interaction = await runInteraction(prompt, null, env.GEMINI_API_KEY);
        }
        if (!interaction.ok) {
          const status = [429, 503].includes(interaction.status) ? interaction.status : 502;
          return reply({ error: 'Error de Gemini' }, status, interaction.headers.get('Retry-After'));
        }
        const data = await interaction.json();
        const answer = data.steps?.filter(step => step.type === 'model_output')
          .flatMap(step => step.content ?? []).filter(part => part.type === 'text')
          .map(part => part.text ?? '').join('').trim();
        if (data.status !== 'completed' || !answer || typeof data.id !== 'string') {
          return reply({ error: 'Respuesta incompleta de Gemini' }, 502);
        }
        return reply({ answer, interactionId: data.id });
      }
      const response = await fetch(
        api + `/models/${model}:generateContent`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY },
          signal: AbortSignal.timeout(25_000),
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: { maxOutputTokens: 4096 }
          })
        }
      );
      const data = await response.json();
      if (!response.ok) {
        console.error('Gemini rechazó la solicitud', {
          httpStatus: response.status,
          status: data?.error?.status,
          reason: data?.error?.details?.find(detail => detail?.reason)?.reason
        });
        const status = [429, 503].includes(response.status) ? response.status : 502;
        return reply({ error: 'Error de Gemini' }, status, response.headers.get('Retry-After'));
      }

      const candidate = data.candidates?.[0];
      const answer = candidate?.content?.parts
        ?.filter(part => !part.thought)
        .map(part => part.text ?? '').join('').trim();
      if (candidate?.finishReason !== 'STOP' || !answer) {
        console.error('Gemini no completó la respuesta', { finishReason: candidate?.finishReason });
        return reply({ error: 'Respuesta incompleta de Gemini' }, 502);
      }
      return reply({ answer });
    } catch (error) {
      console.error('Falló la conexión con Gemini', { type: error?.name });
      return reply({ error: 'No se pudo consultar Gemini' }, 502);
    }
  }
};
