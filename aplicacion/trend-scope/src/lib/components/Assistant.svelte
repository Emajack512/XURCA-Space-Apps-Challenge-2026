<script>
  import { onMount, tick } from 'svelte';
  import { boundedPreparationContext, persistentTurns } from '$lib/services/chatMemory.js';
  import { shouldRetryAssistant, waitForAssistantRetry } from '$lib/services/assistantRetry.js';
  import { geoMercator } from 'd3-geo';
  import { featurePath } from '$lib/services/geography.js';
  import { Send, Trash2 } from '@lucide/svelte';
  import { isTauri } from '@tauri-apps/api/core';
  import { pyInvoke } from 'tauri-plugin-pytauri-api';
  import { workspace } from '$lib/stores/workspace.js';
  import { assistantCatalog as catalog } from '$lib/services/sources.js';
  import { providerGeometries } from '$lib/services/sources.js';
  import { addsToInvestigation, configureWorkspace } from '$lib/services/assistantConfiguration.js';
  import { executeAnalysis } from '$lib/services/analysisRunner.js';
  import { analysisDraft, analysisRun } from '$lib/stores/analysis.js';
  import { chatDraft } from '$lib/stores/tour.js';
  import { prepareInvestigation } from '$lib/services/acquisition.js';
  import idleMascot from '$lib/assets/mascot/reposo.png';
  import thinkingMascot from '$lib/assets/mascot/pensando.png';
  import analyzingMascot from '$lib/assets/mascot/analizando.png';
  import discoveryMascot from '$lib/assets/mascot/descubrimiento.png';
  import errorMascot from '$lib/assets/mascot/error.png';
  import restingMascot from '$lib/assets/mascot/descansando.png';

  let { series = [], running = false, storageBusy = false, acquisitionError = '',
    regionReset = 0, onprocess = () => {}, onresults = () => {}, onreset = () => {},
    buildInvestigation = () => null, onanalysis = () => {}, oncancel = () => {} } = $props();
  let executing = $state(false);
  let executionGeneration = 0;
  let digestFresh = $derived($analysisRun !== null && $analysisRun.key === JSON.stringify($workspace.data));
  let pendingArea = $state.raw(null);
  let failedQuestion = $state('');
  let recovering = $state(false);

  let draft = $state('');
  let messages = $state([]);
  let busy = $state(false);
  let configured = $state(false);
  let thread;
  const chatStorageKey = 'trend-scope.assistant-chat.v1';
  let interactionId = $state(null);
  let chatLoaded = $state(false);
  let generation = 0;
  $effect(() => {
    if (regionReset) pendingArea = null;
  });
  // The guided tour writes an example request; the user only presses Send.
  $effect(() => {
    if ($chatDraft) { draft = $chatDraft; chatDraft.set(null); }
  });

  function resetChat() {
    generation++;
    interactionId = null;
    messages = [];
    draft = '';
    failedQuestion = '';
    pendingArea = null;
    configured = false;
    busy = false;
    recovering = false;
    try { localStorage.removeItem(chatStorageKey); } catch { /* Storage may be unavailable. */ }
    onreset();
  }

  onMount(() => {
    if (!isTauri()) return;
    try {
      const saved = JSON.parse(localStorage.getItem(chatStorageKey) ?? '{}');
      if (Array.isArray(saved.messages)) messages = persistentTurns(saved.messages);
      if (typeof saved.interactionId === 'string') interactionId = saved.interactionId;
    } catch { /* Storage may be unavailable in the webview. */ }
    chatLoaded = true;
    void scrollToLatest();
  });

  $effect(() => {
    if (!chatLoaded) return;
    const history = persistentTurns(messages);
    try {
      localStorage.setItem(chatStorageKey, JSON.stringify({ messages: history, interactionId }));
    } catch { /* The current chat remains available in memory. */ }
  });
  const tr = (es, en) => $workspace.visual.language === 'en' ? en : es;
  let processing = $derived(running || storageBusy || executing);
  let mascot = $derived.by(() => {
    if (busy) return { image: thinkingMascot, status: tr('Preparando respuesta…', 'Preparing a reply…') };
    if (executing) return { image: analyzingMascot, status: tr('Ejecutando el análisis…', 'Running the analysis…') };
    if (running) return { image: analyzingMascot, status: tr('Consultando las fuentes…', 'Fetching data…') };
    if (failedQuestion || acquisitionError) return { image: errorMascot, status: tr('La consulta no pudo completarse.', 'The request could not be completed.') };
    if (series.length || digestFresh) return { image: discoveryMascot, status: tr('Resultados disponibles', 'Results available') };
    if (messages.length) return { image: restingMascot, status: tr('Esperando tu mensaje', 'Waiting for your message') };
    return { image: idleMascot, status: '' };
  });
  const sourceOptions = catalog.map(item => ({ id: item.id, label: item.label, variable: item.variable,
    geometries: providerGeometries(item.route) }));
  let prepared = $derived.by(() => {
    try { return { investigation: prepareInvestigation($workspace.data) }; }
    catch (error) { return { error: error.message }; }
  });
  let configuredSources = $derived(prepared.investigation?.sources.map(source => {
    const feature = prepared.investigation.geography.selection.features.find(item => item.id === source.upstream.geometryId);
    const label = catalog.find(item => item.id === source.id.split('::')[0])?.label ?? source.variable;
    const place = feature?.properties?.name || (feature?.geometry.type === 'Point' ? tr('Punto del mapa', 'Map point')
      : feature ? tr('Área del mapa', 'Map area') : '');
    return { id: source.id, label, place };
  }) ?? []);

  const coastWords = /\b(costas?|coster[ao]s?|litoral(?:es)?|coasts?|coastal|shorelines?)\b/i;
  function coastalDistances(text) {
    const amounts = [...text.matchAll(/\b(\d+(?:[.,]\d+)?)\s*(?:km|kil[oó]metros?|kilomet(?:er|re)s?)\b/gi)];
    const standalone = text.trim().match(/^(\d+(?:[.,]\d+)?)[.!?]?$/);
    return [...amounts, ...(standalone ? [standalone] : [])].map(match => Number(match[1].replace(',', '.')));
  }

  function contextFor(snapshot, retryQuestion) {
    const { data, visual } = snapshot;
    const proposal = pendingArea?.original === JSON.stringify(snapshot) ? pendingArea : null;
    const activeData = proposal?.next.data ?? data;
    const current = {
      title: data.title?.slice(0, 500), objective: data.objective?.slice(0, 500),
      description: data.description?.slice(0, 500), time: activeData.time,
      geographicScope: activeData.geography.scope,
      sources: activeData.sources.slice(0, 25).map(({ id, upstream }) => ({
        id, geometryId: upstream?.geometryId
      })),
      selections: activeData.geography.selection.features.slice(-20).map(({ id, geometry, properties }) => ({
        id, type: geometry.type, name: properties?.name?.slice(0, 100),
        coordinates: geometry.type === 'Point' ? geometry.coordinates : undefined
      })),
      visual
    };
    const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date());
    const conversation = messages.filter(message => !message.temporary);
    if (retryQuestion && conversation.at(-1)?.role === 'user' && conversation.at(-1)?.text === retryQuestion) conversation.pop();
    const olderUserRequests = conversation.slice(0, -24)
      .filter(message => message.role === 'user').slice(-20).map(message => message.text.slice(0, 260));
    const transcript = conversation.slice(-200).map(({ role, text, status }) => ({ role, text: (text + (status ? '\n' + status : '')).slice(0, 900) }));
    const history = transcript.slice(-24);
    const previousDraft = conversation.findLast(message => message.preparation)?.preparation;
    const preparation = { today, current, sourceOptions, previousDraft, history: transcript,
      pendingArea: proposal?.areas.map(area => area.name) };
    const results = series.filter(item => item.summary).slice(0, 4).map(item => item.summary);
    const run = $analysisRun;
    const fresh = run && run.key === JSON.stringify(data);
    const prefix = { today, current, sourceOptions, results, olderUserRequests, pendingArea: proposal?.areas.map(area => area.name),
      analysisDigest: fresh ? run.response.assistant_digest : undefined, analysisStale: run && !fresh ? true : undefined,
      omittedResults: Math.max(0, series.length - results.length) };
    const contextBudget = 9500;
    while (olderUserRequests.length && JSON.stringify({ ...prefix, history }).length > contextBudget) olderUserRequests.shift();
    while (history.length && JSON.stringify({ ...prefix, history }).length > contextBudget) history.shift();
    while (results.length && JSON.stringify({ ...prefix, history }).length > contextBudget) {
      results.pop(); prefix.omittedResults += 1;
    }
    if (prefix.analysisDigest && JSON.stringify({ ...prefix, history }).length > contextBudget) {
      prefix.analysisDigest = undefined;
      prefix.analysisStale = true;
    }
    if (JSON.stringify({ ...prefix, history }).length > contextBudget) throw new Error('La investigación es demasiado grande para el chat. Reducí las selecciones o variables.');
    return { context: JSON.stringify({ ...prefix, history }), preparationContext: boundedPreparationContext(preparation) };
  }

  async function runProposal(message) {
    if (executing || busy || processing) return;
    const investigation = buildInvestigation();
    if (!investigation) return;
    const current = ++executionGeneration;
    executing = true;
    try {
      await executeAnalysis(investigation, message.analysis, JSON.stringify($workspace.data), () => current === executionGeneration);
      if (current !== executionGeneration) return;
      message.executed = true;
      onanalysis();
    } catch (error) {
      if (current !== executionGeneration) return;
      messages.push({ role: 'assistant', text: String(error.message ?? error), temporary: true });
      await scrollToLatest();
    } finally {
      if (current === executionGeneration) executing = false;
    }
  }

  function cancelExecution() {
    executionGeneration++;
    executing = false;
  }

  /** Opens the proposed analysis in the statistical-analysis form so the user can change it before running it. */
  function editProposal(message) {
    analysisDraft.set(JSON.parse(JSON.stringify(message.analysis)));
    onanalysis();
  }

  function fetchData(message) {
    if (busy || processing) return;
    message.fetchRequested = true;
    onprocess();
  }

  async function scrollToLatest() {
    await tick();
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function previewPath(geometry) {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    const coordinates = polygons.flatMap(polygon => polygon[0]);
    const projection = geoMercator().fitExtent([[13, 10], [257, 116]], { type: 'MultiPoint', coordinates });
    return featurePath(projection, { geometry });
  }

  async function confirmArea(accepted, response = '') {
    const started = generation;
    const proposal = pendingArea;
    if (!proposal || busy || processing) return;
    pendingArea = null;
    const confirmation = response || (accepted ? tr('Sí, es el área correcta.', 'Yes, this is the correct area.')
      : tr('No, es otra área.', 'No, this is a different area.'));
    messages.push({ role: 'user', text: confirmation });
    if (response) draft = '';
    if (!accepted) {
      messages.push({ role: 'assistant', text: tr('Decime qué límite querés usar y te muestro otra propuesta.', 'Tell me which boundary you want and I will show another preview.') });
    } else if (JSON.stringify($workspace) !== proposal.original) {
      messages.push({ role: 'assistant', text: tr('La investigación cambió mientras esperábamos. Volvé a pedir el área para revisar el límite.', 'The investigation changed. Request the area again to review its boundary.') });
    } else {
      workspace.set(proposal.next);
      configured = true;
      // Nothing is fetched until the user reviews the query and presses the button.
      messages.push({ role: 'assistant', text: tr('Área confirmada: ', 'Area confirmed: ') + proposal.areas.map(area => area.name).join(', '),
        analysis: proposal.analysis ?? null, fetch: proposal.ready && generation === started });
    }
    await scrollToLatest();
  }

  async function send(event, suggested = '', retry = false) {
    event.preventDefault();
    const question = suggested || draft.trim();
    if (busy || processing || !question) return;
    if (pendingArea && !retry) {
      const decision = question.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[.!?,]/g, '').trim();
      if (/^(si|si es correcta|si es correcto|si es el area correcta|si esa es|si es esa|si continua|si dale|confirmo|correcto|dale|continuar|yes|ok)$/.test(decision)) {
        await confirmArea(true, question);
        return;
      }
      if (/^(no|no es correcta|no es correcto|no es esa|no es esa area)$/.test(decision)) {
        await confirmArea(false, question);
        return;
      }
    }
    if (!isTauri()) {
      messages.push({ role: 'assistant', text: tr('Abrí la app de escritorio para usar el chat.', 'Open the desktop app to use the chat.') });
      await scrollToLatest();
      return;
    }
    const snapshot = $workspace;
    const hasPoint = snapshot.data.geography.selection.features.some(feature => feature.geometry.type === 'Point');
    if (!hasPoint && /\b(punto seleccionado|selected point)\b/i.test(question)) {
      if (!retry) messages.push({ role: 'user', text: question });
      messages.push({ role: 'assistant', text: tr(
        'Todavía no hay un punto seleccionado. Escribí el nombre de la localidad o marcá un punto en el mapa.',
        'There is no selected point yet. Enter the town name or mark a point on the map.'
      ) });
      failedQuestion = '';
      if (!retry) draft = '';
      await scrollToLatest();
      return;
    }
    const additive = addsToInvestigation(question);
    const original = JSON.stringify(snapshot);
    const started = generation;
    const initialRegionReset = regionReset;
    let context, preparationContext;
    try { ({ context, preparationContext } = contextFor(snapshot, retry ? question : null)); }
    catch (error) { messages.push({ role: 'assistant', text: error.message }); return; }
    if (pendingArea?.original !== original) pendingArea = null;
    const baseline = pendingArea?.next ?? snapshot;
    const previousInteractionId = interactionId;
    const coastalTurns = messages.filter(message => message.role === 'user').map(message => message.text);
    if (!retry) coastalTurns.push(question);
    const coastStart = coastalTurns.findLastIndex(text => coastWords.test(text));
    const latestDistances = coastalDistances(question);
    const coastalFollowup = coastStart >= 0 && latestDistances.length > 0
      && coastalTurns.length - coastStart <= 5 && question.length <= 100;
    const coastalRequest = coastWords.test(question) || coastalFollowup;
    const userDistances = coastalTurns.slice(-8).map(coastalDistances).findLast(amounts => amounts.length) ?? [];
    const evidenceKey = JSON.stringify([series.map(item => item.summary), $analysisRun?.key]);
    const language = snapshot.visual.language;
    messages = messages.filter(message => !message.temporary);
    if (!retry) {
      messages.push({ role: 'user', text: question });
      draft = '';
    }
    failedQuestion = '';
    busy = true;
    await scrollToLatest();
    try {
      const ensureCurrent = () => {
        if (generation !== started || regionReset !== initialRegionReset || JSON.stringify($workspace) !== original || JSON.stringify([series.map(item => item.summary), $analysisRun?.key]) !== evidenceKey) {
          throw new Error(tr('La investigación cambió. Volvé a enviar la consulta.', 'The investigation changed. Please resend the question.'));
        }
      };
      ensureCurrent();
      let preparation = retry ? messages.at(-1)?.preparation : undefined;
      if (!preparation) {
        try {
          ({ preparation } = await pyInvoke('prepare_assistant_question', { question, language, context: preparationContext }));
        } catch (error) {
          // Both stages use the same Gemini quota.
          if (String(error.message ?? error).includes('HTTP 429')) throw error;
        }
      }
      ensureCurrent();
      if (preparation && messages.at(-1)?.role === "user") messages.at(-1).preparation = preparation;
      let feedback = '';
      for (let attempt = 0; attempt < 2; attempt++) {
        if (attempt) {
          recovering = true;
          await waitForAssistantRetry();
          ensureCurrent();
        }
        let reply;
        let next;
        let settings;
        try {
          reply = await pyInvoke('interpret_question', { question, context, language, feedback, previousInteractionId, preparation });
        } catch (error) {
          ensureCurrent();
          const reason = String(error.message ?? error);
          if (attempt || !shouldRetryAssistant(error)) throw error;
          feedback = reason.includes('propuesta inválida')
            ? 'The previous reply violated the response schema. Return a valid proposal for the original question. Detail: ' + reason.slice(0, 400)
            : '';
          continue;
        }
        ensureCurrent();
        if (reply.changes.coast && !userDistances.includes(reply.changes.coast.distanceKm)) {
          messages.push({ role: 'assistant', text: tr(
            '¿A cuántos kilómetros de la orilla querés extender la franja?',
            'How many kilometres from the shoreline should the band extend?'
          ) });
          return;
        }
        if (coastalRequest && !reply.changes.coast && (reply.readyToProcess
            || reply.changes.place || reply.changes.places || reply.changes.point || reply.changes.polygon)) {
          messages.push({ role: 'assistant', text: tr(
            '¿Qué tramo de costa querés incluir y a cuántos kilómetros de la orilla? Indicá si es hacia el mar, tierra adentro o ambos, y si incluimos las islas.',
            'Which stretch of coast and how many kilometres from shore? Specify seaward, inland or both, and whether to include islands.'
          ) });
          return;
        }
        const hasQueryChanges = ['point', 'place', 'places', 'polygon', 'coast', 'sources', 'time']
          .some(key => key in reply.changes);
        if (!reply.readyToProcess && hasQueryChanges && /[?¿]/.test(reply.message)) {
          messages.push({ role: "assistant", text: reply.message });
          return;
        }
        if (reply.changes.catalogQuery) {
          if (reply.interactionId) interactionId = reply.interactionId;
          const search = await pyInvoke('search_collections', { keyword: reply.changes.catalogQuery });
          ensureCurrent();
          if (search.collections.length) {
            messages.push({ role: 'assistant', text: tr(
              'Encontré estas referencias. Revisá la cobertura y el formato antes de usarlas.',
              'I found these references. Check coverage and format before using them.'
            ), collections: search.collections });
          } else {
            const detail = search.attempts.map(item => item.provider + ': ' + item.status).join('; ');
            let suggestion = '';
            try {
              const fallback = await pyInvoke('interpret_question', { question, context, language, previousInteractionId,
                feedback: 'catalogSearch found no matches. Attempts: ' + detail + '. Suggest other official sources as unverified leads. Return empty changes.' });
              if (!fallback.readyToProcess && !Object.keys(fallback.changes).length) suggestion = fallback.message;
            } catch { /* The catalog search result is still available. */ }
            ensureCurrent();
            messages.push({ role: 'assistant', text: tr(
              'La búsqueda no devolvió resultados utilizables en los catálogos consultados.',
              'The search returned no usable results from the catalogs checked.'
            ), status: suggestion });
          }
          return;
        }
        const { analysis, ...rest } = reply.changes;
        settings = rest;
        try {
          if (Object.keys(settings).length) next = await configureWorkspace(baseline, settings, pyInvoke, language, additive);
          if (reply.readyToProcess === true && !analysis) {
            next ??= baseline;
            prepareInvestigation(next.data);
          }
        } catch (error) {
          ensureCurrent();
          const reason = String(error.message ?? error);
          if (/^(Hay varios lugares|No pude confirmar)/.test(reason) || (attempt && /^No encontré/.test(reason))) {
            if (reply.interactionId) interactionId = reply.interactionId;
            messages.push({ role: 'assistant', text: reason });
            return;
          }
          if (attempt) throw error;
          feedback = 'The app could not apply the proposal. Correct the configuration, or ask a simple question if essential information is missing. Do not invent data. Validation detail: ' + reason.slice(0, 400);
          if (/^No encontré/.test(reason)) feedback += ' Try an alternative official local or English spelling for the same named area. Keep the requested geography; never substitute a point.';
          recovering = true;
          continue;
        }
        ensureCurrent();
        if (reply.interactionId) interactionId = reply.interactionId;
        const applied = next && JSON.stringify(next) !== original;
        if (applied) {
          const previousIds = new Set(snapshot.data.geography.selection.features.map(feature => feature.id));
          const areas = next.data.geography.selection.features.filter(feature =>
            !previousIds.has(feature.id) && ['Polygon', 'MultiPolygon'].includes(feature.geometry.type))
            .map(feature => ({ name: feature.properties?.name || tr('Área propuesta', 'Proposed area'), path: previewPath(feature.geometry) }));
          if (areas.length) {
            pendingArea = { original, next, areas, ready: reply.readyToProcess === true && !analysis, analysis };
            messages.push({ role: 'assistant', text: reply.message });
            return;
          }
          pendingArea = null;
          if (JSON.stringify(next.data) !== JSON.stringify(snapshot.data)) configured = true;
          workspace.set(next);
        }
        // The query is ready, but it only runs when the user reviews it and presses «Consultar estos datos».
        const readyToFetch = reply.readyToProcess === true && !analysis;
        const requestedEnd = next?.data && settings.time?.end;
        const trimmed = requestedEnd && next.data.time.end < requestedEnd;
        const status = [
          applied ? tr('Configuración aplicada.', 'Settings applied.') : '',
          trimmed ? tr(`La fuente tiene datos hasta ${next.data.time.end}: el período se ajustó a ${next.data.time.start} – ${next.data.time.end}.`,
            `The source has data until ${next.data.time.end}: the period was set to ${next.data.time.start} – ${next.data.time.end}.`) : '',
          readyToFetch ? tr('Revisá el período, el lugar y las variables abajo y pulsá Consultar estos datos.', 'Check the period, place and variables below and select Fetch this data.') : '',
          analysis ? tr('Revisá la propuesta: podés ejecutarla, o abrirla en el panel para cambiar el análisis o sumar variables.', 'Review the proposal: run it, or open it in the panel to change the analysis or add variables.') : ''
        ].filter(Boolean).join('\n');
        if (readyToFetch) configured = true;
        messages.push({ role: 'assistant', text: reply.message, analysis: analysis ?? null, status, fetch: readyToFetch,
          evidence: (series.length || digestFresh) && !readyToFetch && !Object.keys(settings).length && !analysis ? original : null });
        return;
      }
    } catch (error) {
      if (generation !== started || regionReset !== initialRegionReset) return;
      const reason = String(error.message ?? error);
      const quota = reason.includes('HTTP 429');
      const retryAfter = reason.match(/Retry-After: (\d+)/)?.[1];
      let message = quota
        ? (retryAfter
          ? tr(`El asistente alcanzó su límite. Reintentá en ${retryAfter} segundos.`, `The assistant reached its limit. Retry in ${retryAfter} seconds.`)
          : tr('El asistente alcanzó su límite de consultas. Probá más tarde.', 'The assistant reached its request limit. Try again later.'))
        : tr('No pude completar tu consulta. Podés reintentar sin perder la conversación.', 'I could not complete your request. You can retry without losing the conversation.');
      if (/No se pudo conectar con Servicio de IA/i.test(reason)) {
        message = tr('No pude conectarme al servicio de IA. Podés reintentar con el mismo mensaje.', 'I could not connect to the AI service. You can retry the same message.');
      } else if (/Servicio de IA devolvió HTTP 5\d\d/i.test(reason)) {
        message = tr('El servicio de IA no pudo responder. Probá de nuevo en unos minutos.', 'The AI service could not respond. Try again in a few minutes.');
      } else if (/Georef Argentina/i.test(reason)) {
        message = tr('No pude consultar el límite en Georef Argentina. Podés reintentar con el mismo mensaje.', 'I could not fetch the boundary from Georef Argentina. You can retry the same message.');
      }
      // App-side validation errors are plain Spanish sentences: show why the request failed instead of a generic message.
      const detail = !quota && !/HTTP|conectar|Servicio de IA|propuesta inválida|Georef/i.test(reason) && reason.length < 300 ? reason : '';
      messages.push({ role: 'assistant', text: message, status: detail ? tr('Motivo: ', 'Reason: ') + detail : '', temporary: true });
      failedQuestion = question;
    } finally {
      if (generation === started) {
        busy = false;
        recovering = false;
        await scrollToLatest();
      }
    }
  }
</script>

<div class="chat">
  <div class="mascot" role="status">
    <img src={mascot.image} alt="" width="56" height="56" draggable="false"/>
    {#if busy && recovering}
      <span>{tr('Volviendo a intentar…', 'Trying again…')}</span>
    {:else if mascot.status}
      <span>{mascot.status}</span>
    {/if}
    <button type="button" class="reset-chat" onclick={resetChat}
      title={tr('Limpiar chat y resultados', 'Clear chat and results')}
      aria-label={tr('Limpiar chat y resultados', 'Clear chat and results')}><Trash2 size={16}/></button>
  </div>
  <div class="thread" role="log" aria-label={tr('Conversación con la IA', 'AI conversation')} bind:this={thread}>
    {#if !messages.length}
      <p>{tr('¿Qué querés investigar?', 'What would you like to investigate?')}</p>
      <p class="quiet">{tr('Contame qué querés estudiar. Te voy a preguntar por el lugar o el período si hace falta. También puedo usar un polígono que ya dibujaste.', 'Tell me what you want to study. I will ask for the place or period if needed. I can also use a polygon you already drew.')}</p>
      <button class="example" onclick={() => draft = 'Quiero ver cómo cambió la temperatura en el punto seleccionado entre 2000 y 2024.'}>¿Cómo cambió la temperatura?</button>
      <button class="example" onclick={() => draft = 'Quiero investigar si llueve menos en San Luis.'}>¿Está lloviendo menos en San Luis?</button>
      <button class="example" onclick={() => draft = tr('Quiero ver la lluvia mensual en el polígono que dibujé.', 'Show monthly precipitation in the polygon I drew.')}>{tr('Estudiar el área dibujada', 'Study the drawn area')}</button>
    {/if}
    {#each messages as message}
      <article class:user={message.role === 'user'}>
        <strong>{message.role === 'user' ? tr('Usuario', 'User') : tr('Asistente', 'Assistant')}</strong>
        <p>{message.text}</p>
        {#if message.preparation}
          <details class="prepared-question" open>
            <summary>{tr('Pedido interpretado', 'Interpreted request')}</summary>
            <p>{message.preparation.request}</p>
            {#if message.preparation.sourceIds.length}
              <small>{tr('Fuentes sugeridas', 'Suggested sources')}</small>
              <ul>
                {#each message.preparation.sourceIds as sourceId (sourceId)}
                  <li>{sourceOptions.find(option => option.id === sourceId)?.label ?? sourceId}</li>
                {/each}
              </ul>
            {/if}
          </details>
        {/if}
        {#if message.collections?.length}
          <ul>
            {#each message.collections as collection (collection.id)}
              <li>{collection.title} · {collection.provider} · <code>{collection.id}</code></li>
            {/each}
          </ul>
        {/if}
        {#if message.status}<p class="quiet">{message.status}</p>{/if}
        {#if message.evidence && message.evidence !== JSON.stringify($workspace)}<p class="quiet">Esta explicación corresponde a una configuración anterior. Procesá la actual para actualizarla.</p>{/if}
        {#if message.fetch && message === messages.findLast(item => item.fetch)}
          <div class="message-actions">
            <button class="primary" onclick={() => fetchData(message)} disabled={busy || processing || !prepared.investigation}>
              {message.fetchRequested ? tr('Consultar de nuevo', 'Fetch again') : tr('Consultar estos datos', 'Fetch this data')}
            </button>
          </div>
        {/if}
        {#if message.analysis}
          <details>
            <summary>{tr('Análisis propuesto', 'Proposed analysis')}: {message.analysis.struct} · {message.analysis.targets?.join(', ')}</summary>
            <pre>{JSON.stringify(message.analysis, null, 2)}</pre>
          </details>
          <div class="message-actions">
            {#if executing}
              <button class="primary" disabled>{tr('Analizando…', 'Analyzing…')}</button>
              <button onclick={cancelExecution}>{tr('Cancelar', 'Cancel')}</button>
            {:else}
              <button class="primary" onclick={() => runProposal(message)} disabled={busy || processing}>
                {message.executed ? tr('Ejecutar de nuevo', 'Run again') : tr('Ejecutar análisis', 'Run analysis')}
              </button>
              <button onclick={() => editProposal(message)} disabled={busy}>{tr('Cambiar análisis o variables', 'Change analysis or variables')}</button>
            {/if}
          </div>
        {/if}
      </article>
    {/each}
    {#if pendingArea}
      <article class="area-preview">
        <strong>{tr('¿Es esta el área que querés estudiar?', 'Is this the area you want to study?')}</strong>
        {#each pendingArea.areas as area}
          <figure>
            <svg viewBox="0 0 270 126" role="img" aria-label={area.name}>
              <path d={area.path} fill-rule="evenodd"/>
            </svg>
            <figcaption>{area.name}</figcaption>
          </figure>
        {/each}
        {#if pendingArea.next.data.time.years?.length}
          <p>{tr('Años de la consulta', 'Query years')} · {pendingArea.next.data.time.years.join(', ')}</p>
        {/if}
        <button onclick={() => confirmArea(true)} disabled={busy || processing}>{tr('Confirmar área', 'Confirm area')}</button>
        <button onclick={() => confirmArea(false)} disabled={busy || processing}>{tr('Elegir otra área', 'Choose another area')}</button>
      </article>
    {/if}
  </div>
  {#if configured}
    <div class="query-summary">
      {#if prepared.investigation}
        <strong>{tr('Investigación', 'Investigation')}</strong>
        <small>{prepared.investigation.time.start} – {prepared.investigation.time.end}</small>
        <ul>
          {#each configuredSources as source (source.id)}
            <li>{source.label}{source.place ? ' · ' + source.place : ''}</li>
          {/each}
        </ul>
      {:else}
        <small>{prepared.error}</small>
      {/if}
    </div>
  {/if}
  <div class="actions">
    {#if running}
      <button onclick={oncancel}>{tr('Cancelar consulta', 'Cancel request')}</button>
    {/if}
    {#if failedQuestion}
      <button onclick={event => send(event, failedQuestion, true)} disabled={busy || processing}>{tr('Reintentar consulta', 'Retry request')}</button>
    {/if}
    {#if acquisitionError}
      <button onclick={onprocess} disabled={busy || processing || !prepared.investigation}>{tr('Reintentar procesamiento', 'Retry processing')}</button>
    {/if}
    {#if series.length || digestFresh}
      <button onclick={series.length ? onresults : onanalysis} disabled={busy || processing}>{tr('Ver resultados', 'View results')}</button>
      <button onclick={event => send(event, 'Explicame los resultados actuales en lenguaje sencillo, con sus fuentes, unidades y limitaciones.')} disabled={busy || processing}>Explicar resultados</button>
    {/if}
  </div>
  <form onsubmit={send}>
    <textarea aria-label={tr('Mensaje', 'Message')} placeholder={tr('Escribí un mensaje…', 'Write a message…')}
      maxlength="1200" rows="4" bind:value={draft}
      onkeydown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}></textarea>
    <button type="submit" class="primary" data-tour="chat-send" disabled={busy || processing || !draft.trim()} aria-label={tr('Enviar mensaje', 'Send message')}>
      <Send size={16}/>
    </button>
  </form>
</div>

<style>
  .chat { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .mascot { display: flex; flex: none; align-items: center; gap: 8px; min-height: 58px; padding: 2px 12px; color: var(--muted); font-size: 12px; }
  .mascot img { flex: none; object-fit: contain; }
  .thread { flex: 1; overflow: auto; min-height: 0; padding: 12px; scrollbar-width: thin; }
  article { padding: 8px 10px; margin: 0 10% 10px 0; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); overflow-wrap: anywhere; }
  article.user { margin: 0 0 10px 10%; background: var(--raised); }
  article p { margin: 4px 0 0; white-space: pre-wrap; }
  form { flex: none; display: flex; align-items: end; gap: 8px; padding: 10px; border-top: 1px solid var(--line); }
  textarea { resize: none; height: 92px; }
  .reset-chat { margin-left:auto; display:grid; place-items:center; padding:6px; }
  .prepared-question { margin-top:8px; color:var(--muted); font-size:.9em; }
  .prepared-question ul { margin:4px 0; padding-left:18px; }
  .actions { display: flex; gap: 6px; padding: 8px; flex-wrap: wrap; border-top: 1px solid var(--line); }
  .actions button, .example { font-size: 12px; }
  .message-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .message-actions button { font-size: 12px; }
  .example { display: block; margin: 8px 0; text-align: left; width: 100%; white-space: normal; }
  .query-summary { display: grid; gap: 4px; margin: 0 8px 8px; padding: 8px; border: 1px solid var(--line); border-radius: 7px; max-height: 120px; overflow: auto; }
  .query-summary ul { margin: 0; padding-left: 18px; font-size: .88em; }
  .area-preview figure { margin: 8px 0; }
  .area-preview svg { display: block; width: 100%; max-height: 130px; background: var(--surface); border-radius: 6px; }
  .area-preview path { fill: var(--raised); stroke: var(--accent); stroke-width: 1.5; }
  .area-preview figcaption { margin-top: 4px; }
</style>
