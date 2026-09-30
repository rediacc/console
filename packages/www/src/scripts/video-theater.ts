/**
 * The video theater: a site-owned overlay that hosts the solution/homepage player.
 *
 * WHY THIS EXISTS. The inline mount is capped at 36rem (solution and persona heroes,
 * solution-pages.css) and 48rem (the homepage, SPHomeVideo.astro), and the footage is
 * 1920x1080 with its captions burned into the pixels -- there is no VTT, which is why
 * Plyr drops its CC button for these. At 576px the frame is displayed at about 30%
 * scale and the baked captions stop being readable.
 *
 * WHY NOT JUST CALL requestFullscreen(). Three measured reasons:
 *   1. It would race the transient user-activation window. The first click has to fetch
 *      122 KB of player before there is anything to fullscreen, and the hydrator already
 *      documents that even `play()` gets refused when that fetch outlasts the gesture.
 *      A refused fullscreen is louder (Firefox and Safari throw) and leaves the visitor
 *      a small player that also is not playing.
 *   2. iPhone Safari has no `Element.requestFullscreen`. Only
 *      `video.webkitEnterFullscreen()`, which hands off to the native iOS player and
 *      discards the in-frame language picker -- the control that exists precisely
 *      because Plyr's settings menu could not host it correctly.
 *   3. Taking the whole screen unasked is a context hijack whose only exit is Escape.
 *
 * An overlay we own has none of those problems: it opens synchronously on the click,
 * it behaves identically on every device, and Plyr's own fullscreen button is still
 * right there for anyone who wants the real thing -- reliably, because by then the
 * player exists.
 *
 * A FRESH STAGE, NOT A MOVED PLAYER. `mountPlayers` reads everything from the element's
 * dataset and calls `createRoot` on it, so copying the mount's dataset onto a stage div
 * inside the overlay builds the player in its final home with no reparenting. Moving a
 * live `.tvp-shell` node instead would be the risky path: TutorialVideoPlayer's own
 * notes record that Plyr's `destroy()` swaps in a clone and desyncs React, and that the
 * chapter and caption overlays are relocated into Plyr's DOM on `ready` and moved back
 * on teardown.
 */

import { FOCUSABLE, lockScroll } from '../utils/overlay-lock';
import { mountPlayers, whenVideoAppears } from './tutorial-video-mount';

let root: HTMLElement | null = null;
let stage: HTMLElement | null = null;
/** The mount whose video the stage currently holds; see the rebuild note in openTheater. */
let stageOwner: HTMLElement | null = null;
let releaseScroll: (() => void) | null = null;
/** Restored on close, so a keyboard visitor lands back on the control they pressed. */
let opener: HTMLElement | null = null;

function currentVideo(): HTMLVideoElement | null {
  return stage?.querySelector('video') ?? null;
}

export function closeTheater(): void {
  if (!root || root.hidden) return;
  // Pause rather than stop: the player and its position survive a close, so re-opening resumes instead of starting the demo over.
  currentVideo()?.pause();
  root.hidden = true;
  releaseScroll?.();
  releaseScroll = null;
  opener?.focus();
  opener = null;
}

function onKeyDown(e: KeyboardEvent): void {
  if (!root || root.hidden) return;
  if (e.key === 'Escape') {
    // ESCAPE BELONGS TO FULLSCREEN FIRST. Someone who pressed Plyr's fullscreen button
    // from inside the theater expects the first Escape to leave fullscreen and keep
    // watching, not to be thrown back to the page. Most browsers do not even deliver this keydown while fullscreen, so the guard is belt and braces rather than the only thing standing between the two behaviours.
    if (document.fullscreenElement) return;
    closeTheater();
    return;
  }
  if (e.key !== 'Tab') return;
  const focusable = root.querySelectorAll<HTMLElement>(FOCUSABLE);
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function build(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'video-theater';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  // `hidden` rather than an opacity or visibility trick. display:none is what takes the close button and Plyr's whole control bar out of the tab order while the theater is shut; ImageModal.astro carries a long comment about the site-wide axe `aria-hidden-focus` violation that the weaker spellings caused there.
  el.hidden = true;

  const frame = document.createElement('div');
  frame.className = 'video-theater-frame';

  stage = document.createElement('div');
  stage.className = 'video-theater-stage';
  frame.appendChild(stage);
  el.appendChild(frame);

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'video-theater-close';
  close.innerHTML =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    '<path d="M6 6l12 12M18 6L6 18" /></svg>';
  close.addEventListener('click', closeTheater);
  el.appendChild(close);

  el.addEventListener('click', (e) => {
    if (e.target === el || e.target === frame) closeTheater();
  });
  document.addEventListener('keydown', onKeyDown);

  document.body.appendChild(el);
  return el;
}

export function openTheater(mount: HTMLElement): void {
  root ??= build();
  if (!stage) return;

  const closeButton = root.querySelector<HTMLElement>('.video-theater-close');
  root.setAttribute('aria-label', mount.dataset.title ?? '');
  closeButton?.setAttribute('aria-label', mount.dataset.closeLabel ?? '');

  // REBUILD WHEN A DIFFERENT MOUNT CLAIMS THE STAGE. Every marketing page carries exactly one mount today, so this is defence rather than a live path -- but a stage still holding the previous mount's player would silently play the wrong video.
  const first = stageOwner !== mount;
  if (first) {
    stageOwner = mount;
    stage.replaceChildren();
    // The player reads its whole configuration off the dataset, so the stage becomes the mount for `mountPlayers`. The scheduling flags are deliberately not copied: they belong to the inline element's own lifecycle, not to this one.
    Object.entries(mount.dataset).forEach(([key, value]) => {
      if (value !== undefined) stage!.dataset[key] = value;
    });
    delete stage.dataset.hydrated;
    delete stage.dataset.observed;
    delete stage.dataset.clickToLoad;

    // A STAND-IN WHILE THE 122 KB CHUNK IS IN FLIGHT. The overlay opens in the same tick as the click, which is the whole point -- but the player is several hundred milliseconds behind it, and an empty black rectangle for that long reads as a broken click. The poster is already decoded in the page, so cloning it costs one element and paints immediately.
    const poster = mount.querySelector('.video-poster-preview');
    if (poster) {
      const clone = poster.cloneNode(true) as HTMLElement;
      clone.className = 'video-theater-poster';
      clone.setAttribute('aria-hidden', 'true');
      frameOf(stage).appendChild(clone);
    }
  }

  opener = mount.querySelector<HTMLElement>('.video-poster-play') ?? mount;
  root.hidden = false;
  releaseScroll ??= lockScroll();
  closeButton?.focus();

  if (!first) {
    currentVideo()
      ?.play()
      .catch(() => {});
    return;
  }

  void mountPlayers([stage])
    .then(() => whenVideoAppears(stage!))
    .then((video) => {
      root?.querySelector('.video-theater-poster')?.remove();
      // The rejection path is not an error and is deliberately silent: the chunk fetch can outlast the browser's user-gesture window, and a blocked play() leaves exactly the paused, fully-built player the visitor would have had anyway.
      video?.play().catch(() => {});
    });
}

/** The stage's parent, which is where the poster stand-in has to sit to overlap it. */
function frameOf(el: HTMLElement): HTMLElement {
  return el.parentElement ?? el;
}
