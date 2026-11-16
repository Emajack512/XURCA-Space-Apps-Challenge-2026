<script>
  import { onMount, tick, untrack } from 'svelte';
  import { GraduationCap, X } from '@lucide/svelte';
  import { LEVELS, stepsFor } from '$lib/services/tutorialSteps.js';
  import { revealSection } from '$lib/stores/tour.js';

  // phase: 'welcome' | 'tour'. appState: live app state for the steps' conditions. api: actions the steps can run.
  let { phase = 'welcome', level = 'novice', appState, api, onlevel = () => {}, onstart = () => {}, onclose = () => {} } = $props();

  let index = $state(0);
  let rect = $state(null);
  let advancing = false;
  let steps = $derived(stepsFor(level));
  let step = $derived(steps[index]);
  let chosen = $state(untrack(() => level));
  const pad = 6;

  function targetElement() {
    if (!step?.target) return null;
    const element = document.querySelector(`[data-tour="${step.target}"]`);
    return element && element.getClientRects().length ? element : null;
  }

  // Follows the target while it moves or resizes (panels opening, scrolling).
  onMount(() => {
    let frame;
    const follow = () => {
      const element = phase === 'tour' ? targetElement() : null;
      const box = element?.getBoundingClientRect();
      const next = box && box.width && box.height
        ? { left: box.left - pad, top: box.top - pad, width: box.width + 2 * pad, height: box.height + 2 * pad } : null;
      if (JSON.stringify(next) !== JSON.stringify(rect)) rect = next;
      frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    const onclick = event => {
      if (phase !== 'tour' || !step?.click) return;
      const element = targetElement();
      if (element?.contains(event.target)) setTimeout(next, 200);
    };
    document.addEventListener('click', onclick, true);
    return () => { cancelAnimationFrame(frame); document.removeEventListener('click', onclick, true); };
  });

  // Entering a step: open the section it needs, prepare it, and bring the target into view.
  let entered = -1;
  $effect(() => {
    if (phase !== 'tour' || !step || entered === index) return;
    entered = index;
    advancing = false;
    if (step.reveal) revealSection.set(step.reveal);
    step.prepare?.(api);
    tick().then(() => targetElement()?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }));
  });

  // A step whose condition is met advances by itself.
  $effect(() => {
    if (phase !== 'tour' || !step?.when || advancing) return;
    if (step.when(appState)) { advancing = true; setTimeout(next, 450); }
  });

  function next() {
    if (index < steps.length - 1) index += 1;
    else onclose(true);
  }

  async function doIt() {
    await step.doIt?.(api);
    if (!step.when) next();
  }

  function start() {
    onlevel(chosen);
    index = 0;
    entered = -1;
    phase = 'tour';
    onstart();
  }

  // Speech bubble next to the spotlight, kept inside the window.
  let bubble = $derived.by(() => {
    if (!rect) return 'left:50%;top:50%;transform:translate(-50%,-50%)';
    const width = 360, gap = 14;
    const left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left));
    const below = rect.top + rect.height + gap;
    return below + 220 < window.innerHeight
      ? `left:${left}px;top:${below}px`
      : `left:${left}px;bottom:${window.innerHeight - rect.top + gap}px`;
  });
</script>

{#if phase === 'welcome'}
  <div class="tour-backdrop" role="presentation"></div>
  <div class="tour-card welcome" role="dialog" aria-modal="true" aria-labelledby="tour-welcome-title">
    <button class="icon-button tour-close" aria-label="Cerrar" onclick={() => onclose(false)}><X size={16}/></button>
    <h2 id="tour-welcome-title"><GraduationCap size={22}/> ¡Bienvenido!</h2>
    <p>TrendScope te ayuda a descargar datos ambientales públicos (temperatura, lluvia, sismos y más), graficarlos y analizarlos con estadística.</p>
    <p><strong>¿Cuánta experiencia tenés?</strong> El tutorial se adapta a tu nivel. Podés cambiarlo cuando quieras desde Preferencias.</p>
    <div class="levels" role="radiogroup" aria-label="Nivel de experiencia">
      {#each LEVELS as [id, label, hint] (id)}
        <label class:selected={chosen === id}>
          <input type="radio" name="tour-level" value={id} checked={chosen === id} onchange={() => chosen = id}/>
          <span><strong>{label}</strong><small>{hint}</small></span>
        </label>
      {/each}
    </div>
    <div class="tour-actions">
      <button onclick={() => { onlevel(chosen); onclose(false); }}>Ahora no</button>
      <button class="primary" onclick={start}>Empezar el tutorial</button>
    </div>
  </div>
{:else if step}
  <!-- Four dark panels around the highlighted element: only the highlighted element can be clicked. -->
  {#if rect}
    <div class="tour-shade" style:left="0" style:top="0" style:width="100vw" style:height="{Math.max(0, rect.top)}px"></div>
    <div class="tour-shade" style:left="0" style:top="{rect.top + rect.height}px" style:width="100vw" style:bottom="0"></div>
    <div class="tour-shade" style:left="0" style:top="{rect.top}px" style:width="{Math.max(0, rect.left)}px" style:height="{rect.height}px"></div>
    <div class="tour-shade" style:left="{rect.left + rect.width}px" style:top="{rect.top}px" style:right="0" style:height="{rect.height}px"></div>
    <div class="tour-hole" style:left="{rect.left}px" style:top="{rect.top}px" style:width="{rect.width}px" style:height="{rect.height}px"></div>
  {:else}
    <div class="tour-backdrop" role="presentation"></div>
  {/if}
  <div class="tour-card" style={bubble} role="dialog" aria-live="polite" aria-label="Tutorial">
    <small class="tour-progress">Paso {index + 1} de {steps.length}</small>
    <p class="tour-text">{step.text[level]}</p>
    <div class="tour-actions">
      <button class="tour-exit" onclick={() => onclose(false)}>Salir del tutorial</button>
      {#if step.doIt && (step.when || step.click)}
        <button onclick={doIt}>Hacelo por mí</button>
      {/if}
      {#if !step.when && !step.click}
        <button class="primary" onclick={next}>{index === steps.length - 1 ? 'Terminar' : 'Siguiente'}</button>
      {:else}
        <button onclick={next} title="Pasar a la siguiente explicación sin hacer este paso">Saltar paso</button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .tour-backdrop, .tour-shade { position: fixed; z-index: 900; background: rgb(2 6 14 / .72); }
  .tour-backdrop { inset: 0; }
  .tour-hole { position: fixed; z-index: 901; pointer-events: none; border-radius: 9px;
    box-shadow: 0 0 0 2px var(--accent), 0 0 18px 2px color-mix(in srgb, var(--accent), transparent 40%); transition: all .18s ease; }
  .tour-card { position: fixed; z-index: 902; width: min(360px, calc(100vw - 24px)); padding: 14px 16px;
    background: var(--panel); color: var(--text); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); }
  .tour-card.welcome { left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(520px, calc(100vw - 24px)); padding: 22px 24px; }
  .tour-card h2 { display: flex; align-items: center; gap: 10px; margin: 0 0 10px; font-size: 1.5em; }
  .tour-close { position: absolute; right: 10px; top: 10px; }
  .tour-text { white-space: pre-line; margin: 6px 0 12px; line-height: 1.45; }
  .tour-progress { color: var(--muted); }
  .tour-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
  .tour-exit { margin-right: auto; }
  .levels { display: grid; gap: 8px; margin: 12px 0 16px; }
  .levels label { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 9px; cursor: pointer; }
  .levels label.selected { border-color: var(--accent); background: color-mix(in srgb, var(--accent), transparent 90%); }
  .levels input { width: auto; margin-top: 3px; }
  .levels span { display: grid; gap: 2px; }
  .levels small { color: var(--muted); }
</style>
