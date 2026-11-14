<script>
  let { label, value, min, max, direction = 1, resize } = $props();
  let drag;
  function move(event) {
    if (!drag) return;
    const next = drag.value + (event.clientX - drag.x) * direction;
    resize(Math.round(Math.max(min, Math.min(max, next))));
  }
  function keyboard(event) {
    if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const delta = (event.key === 'ArrowRight' ? 16 : -16) * direction;
    resize(Math.max(min, Math.min(max, value + delta)));
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (A resizable ARIA separator is keyboard interactive.) -->
<div class="resize-handle" role="separator" tabindex="0" aria-label={label} aria-orientation="vertical"
  aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
  onpointerdown={event => { if (event.button === 0) { drag = { x:event.clientX, value }; event.currentTarget.setPointerCapture(event.pointerId); } }}
  onpointermove={move} onpointerup={() => drag = null} onpointercancel={() => drag = null} onkeydown={keyboard}></div>
