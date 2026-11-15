<script>
  import { tick } from 'svelte';
  import { Send } from '@lucide/svelte';
  import { isTauri } from '@tauri-apps/api/core';
  import { pyInvoke } from 'tauri-plugin-pytauri-api';
  import { workspace } from '$lib/stores/workspace.js';
  import { assistantCatalog as catalog } from '$lib/services/sources.js';
  import { configureWorkspace } from '$lib/services/assistantConfiguration.js';

  let draft = $state('');
  let messages = $state([]);
  let busy = $state(false);
  let thread;
  const tr = (es, en) => $workspace.visual.language === 'en' ? en : es;
  const sourceOptions = catalog.map(item => [item.id, item.label]);

  function contextFor(snapshot) {
    const { data, visual } = snapshot;
    const current = {
      title: data.title?.slice(0, 500), objective: data.objective?.slice(0, 500),
      description: data.description?.slice(0, 500), time: data.time,
      sources: data.sources.slice(0, 25).map(({ id, upstream }) => ({
        id, pointId: upstream?.geometryId, entityId: upstream?.selectors?.stationId ?? upstream?.selectors?.featureId
      })),
      selections: data.geography.selection.features.slice(-20).map(({ id, geometry, properties }) => ({
        id, type: geometry.type, name: properties?.name?.slice(0, 100),
        coordinates: geometry.type === 'Point' ? geometry.coordinates : undefined
      })),
      visual
    };
    const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date());
    const history = messages.slice(-8).map(({ role, text, status }) => ({ role, text: (text + (status ? '\n' + status : '')).slice(0, 900) }));
    const prefix = { today, current, sourceOptions };
    while (history.length && JSON.stringify({ ...prefix, history }).length > 18000) history.shift();
    return JSON.stringify({ ...prefix, history });
  }

  async function scrollToLatest() {
    await tick();
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  async function send(event) {
    event.preventDefault();
    const question = draft.trim();
    if (busy || !question) return;
    if (!isTauri()) {
      messages.push({ role: 'assistant', text: tr('Abrí la app de escritorio para usar el chat.', 'Open the desktop app to use the chat.') });
      await scrollToLatest();
      return;
    }
    const snapshot = $workspace;
    const original = JSON.stringify(snapshot);
    const context = contextFor(snapshot);
    const language = snapshot.visual.language;
    messages.push({ role: 'user', text: question });
    draft = '';
    busy = true;
    await scrollToLatest();
    try {
      const reply = await pyInvoke('interpret_question', {
        question, context, language, endpoint: import.meta.env.VITE_ASSISTANT_ENDPOINT || null
      });
      let status = '';
      if (Object.keys(reply.changes).length) {
        try {
          const next = await configureWorkspace(snapshot, reply.changes, pyInvoke, language);
          if (JSON.stringify($workspace) !== original) {
            throw new Error(tr('La configuración cambió durante la consulta. Pedime el cambio de nuevo.', 'Settings changed during this reply. Ask me again.'));
          }
          if (JSON.stringify(next) !== original) {
            workspace.set(next);
            status = tr('Configuración actualizada. Pulsá Procesar para ejecutar la consulta.', 'Settings updated. Select Process to run the query.');
          }
        } catch (error) {
          status = tr('No se aplicaron cambios. ', 'No settings were applied. ') + String(error.message ?? error);
        }
      }
      messages.push({ role: 'assistant', text: reply.message, status });
    } catch (error) {
      messages.push({ role: 'assistant', text: String(error.message ?? error) });
      if (!draft) draft = question;
    } finally {
      busy = false;
      await scrollToLatest();
    }
  }
</script>

<div class="chat">
  <div class="thread" role="log" aria-label={tr('Conversación con la IA', 'AI conversation')} bind:this={thread}>
    {#if !messages.length}
      <p class="quiet">{tr('Contame qué querés investigar o cómo querés configurar la app.', 'Tell me what you want to investigate or how to set up the app.')}</p>
    {/if}
    {#each messages as message}
      <article class:user={message.role === 'user'}>
        <strong>{message.role === 'user' ? tr('Vos', 'You') : tr('Asistente', 'Assistant')}</strong>
        <p>{message.text}</p>
        {#if message.status}<p class="quiet">{message.status}</p>{/if}
      </article>
    {/each}
    {#if busy}<p class="quiet">{tr('Preparando respuesta…', 'Preparing a reply…')}</p>{/if}
  </div>
  <form onsubmit={send}>
    <textarea aria-label={tr('Mensaje', 'Message')} placeholder={tr('Escribí un mensaje…', 'Write a message…')}
      maxlength="1200" rows="2" bind:value={draft}
      onkeydown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}></textarea>
    <button type="submit" class="primary" disabled={busy || !draft.trim()} aria-label={tr('Enviar mensaje', 'Send message')}>
      <Send size={16}/>
    </button>
  </form>
</div>

<style>
  .chat { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .thread { flex: 1; overflow: auto; min-height: 0; padding: 12px; scrollbar-width: thin; }
  article { padding: 8px 10px; margin: 0 10% 10px 0; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); overflow-wrap: anywhere; }
  article.user { margin: 0 0 10px 10%; background: var(--raised); }
  article p { margin: 4px 0 0; white-space: pre-wrap; }
  form { flex: none; display: flex; align-items: end; gap: 8px; padding: 10px; border-top: 1px solid var(--line); }
  textarea { resize: none; }
</style>
