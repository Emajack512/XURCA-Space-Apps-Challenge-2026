<script>
  import { Bot, Check, CircleAlert, Plus, Send, X } from '@lucide/svelte';
  import { demoProposal, demoQuestion, methodConfig, sourceConfig } from '$lib/services/demo.js';
  import { editData, editVisual } from '$lib/stores/workspace.js';
  let { messages = $bindable([]), close, notify } = $props();
  let input = $state('');
  function send(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    messages = [...messages, { role:'user', text }, {
      role:'assistant', text:'Puedo mostrarte cómo se aplicaría una configuración de ejemplo para investigar el clima de San Luis.',
      proposal:true
    }];
    input = '';
  }
  function apply(index) {
    editData(data => {
      data.objective = demoQuestion;
      data.sources = ['gldas-precipitation','fldas-soil'].map(sourceConfig);
      data.time = { start:'2000-01-01', end:'2025-12-31', resolution:'Mensual', aggregation:'Media' };
      if (!data.geography.selection.features.some(feature => feature.id === demoProposal.id)) {
        data.geography.selection.features.push(structuredClone(demoProposal));
      }
      data.methods = ['mann-kendall','sen'].map(methodConfig);
    });
    editVisual(visual => {
      visual.map.camera = { longitude:-66.2, latitude:-33.45, zoom:3.8 };
      visual.map.layers.selection = true;
    });
    messages = messages.map((message, position) => position === index ? { ...message, applied:true } : message);
    notify('Propuesta aplicada a la configuración manual');
  }
</script>

<section class="assistant-panel">
  <header class="panel-heading"><span><Bot size={17}/> Asistente científico</span><button class="icon-button" aria-label="Cerrar asistente" onclick={close}><X size={16}/></button></header>
  <div class="assistant-actions"><span class="tag simulation-tag">Demostración</span><button class="outlined" onclick={() => messages = []}><Plus size={14}/> Nueva conversación</button></div>
  <div class="conversation">
    {#each messages as message,index}
      <div class:user-message={message.role === 'user'} class="chat-message">
        <strong>{message.role === 'user' ? 'Vos' : 'Asistente · simulado'}</strong><p>{message.text}</p>
        {#if message.proposal}
          <div class="proposal">
            <strong>Configuración propuesta</strong>
            <dl><dt>Región</dt><dd>San Luis, Argentina</dd><dt>Período</dt><dd>2000–2025</dd><dt>Variables</dt><dd>Precipitación · Humedad del suelo</dd><dt>Productos</dt><dd>GLDAS · FLDAS</dd><dt>Métodos</dt><dd>Mann-Kendall · Sen</dd></dl>
            <p class="quiet"><CircleAlert size={14}/> Área aproximada de demostración.</p>
            <button class="outlined" disabled={message.applied} onclick={() => apply(index)}><Check size={15}/> {message.applied ? 'Configuración aplicada' : 'Aplicar configuración'}</button>
          </div>
        {/if}
      </div>
    {:else}
      <p class="quiet">Escribí una pregunta para explorar el flujo de demostración.</p>
      <button class="outlined" onclick={() => input = demoQuestion}>{demoQuestion}</button>
    {/each}
  </div>
  <form class="compose" onsubmit={send}>
    <input aria-label="Mensaje" placeholder="Escribí una pregunta…" bind:value={input}/>
    <button class="primary" aria-label="Enviar" disabled={!input.trim()}><Send size={16}/></button>
  </form>
</section>
