// Points at a missing setting: the element tagged with use:attend={name} glows red for a moment and a short beep sounds.
import { writable } from 'svelte/store';

export const attention = writable(null);
let timer;
let audio;

function beep() {
  try {
    audio ??= new AudioContext();
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.08, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.14);
    oscillator.connect(gain).connect(audio.destination);
    oscillator.start();
    oscillator.stop(audio.currentTime + 0.15);
  } catch { /* Sound is optional. */ }
}

/** Flags one or more targets ("sources", "time", "geometry", "scope", "analysis-targets", …). */
export function flag(...targets) {
  clearTimeout(timer);
  attention.set({ targets, at: Date.now() });
  beep();
  timer = setTimeout(() => attention.set(null), 2600);
}

/** Svelte action: <div use:attend={'time'}> glows while that target is flagged. */
export function attend(node, name) {
  let current = name;
  const unsubscribe = attention.subscribe(value => {
    const on = !!value?.targets.includes(current);
    node.classList.remove('needs-attention');
    if (on) {
      void node.offsetWidth; // restart the animation when flagged again
      node.classList.add('needs-attention');
      node.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    }
  });
  return { update(next) { current = next; }, destroy: unsubscribe };
}

/** An Error that names the setting to flag. */
export function settingError(message, field) {
  return Object.assign(new Error(message), { field });
}
