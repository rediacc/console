/**
 * Client-side hydration for every TutorialVideoPlayer on the site.
 *
 * Finds placeholder divs and decides WHEN and WHERE each one's player gets built. The
 * building itself is tutorial-video-mount.ts; both kinds get the same player, including
 * its in-frame language picker.
 *
 * TWO PLACEHOLDERS, TWO ANSWERS:
 *
 *   `.tutorial-video-container` -- emitted by remark-tutorial-embed.ts when a docs page
 *     sets `useVideoPlayer: true`. Carries a poster and play button
 *     and `data-click-to-load="inline"`: the player builds in place on the first press.
 *
 *   `.video-player-mount` -- emitted by SPSolutionVideo.astro for the solution, persona
 *     and homepage videos. Carries a server-rendered poster and `data-click-to-load`, and
 *     the click opens the theater overlay (video-theater.ts) rather than building here.
 *     The inline box is 576px wide in a hero, which is about 30% scale for 1920x1080
 *     footage whose captions are burned in.
 *
 * The original .tutorial-player-container hydration in tutorial-hydrate.ts
 * remains active for any page that does not opt in.
 */

import { mountPlayers, whenVideoAppears } from './tutorial-video-mount';
import { openTheater } from './video-theater';

/** Build the player in place and start it. A blocked play() (the chunk fetch can outlast the gesture) leaves the built, paused player, which is the fallback worth having. */
async function playInline(el: HTMLElement) {
  await mountPlayers([el]);
  const video = await whenVideoAppears(el);
  await video?.play().catch(() => {});
}

/** The press handler for a docs mount. A failed chunk fetch (offline, a blip) would otherwise leave a dead button, because the listener fires once: it is re-armed so the next press retries. */
export function armInline(el: HTMLElement) {
  el.addEventListener(
    'click',
    () => {
      playInline(el).catch(() => armInline(el));
    },
    { once: true }
  );
}

/**
 * EVERY MOUNT IS CLICK-TO-LOAD. The Video.js skin plus the player is about 272 KB, and
 * it used to reach every visitor the moment the document parsed. A visibility observer
 * did not help: measured 2026-10-08, every solution, homepage and docs mount sits within
 * 600px of the fold, so the observer fired on load and deferred nothing. Both producers
 * now render a poster with `data-click-to-load`, and nothing builds before a press.
 */
function scheduleHydration() {
  const containers = Array.from(
    document.querySelectorAll<HTMLElement>(
      '.tutorial-video-container[data-video-src], .video-player-mount[data-video-src]'
    )
  ).filter((el) => !el.dataset.hydrated && !el.dataset.observed);
  if (containers.length === 0) return;

  // CLICK-TO-LOAD for any mount that carries a server-rendered poster.
  //
  // An IntersectionObserver cannot help these: measured across all 44 English mount-carrying pages at 1440x900 and 390x844, every mount is ABOVE THE FOLD, so the observer fires on load and defers nothing. The visitor is looking at the poster already; the 122 KB player only has to exist once they ask for it.
  //
  // The poster markup is server-rendered by SPSolutionVideo.astro, so the frame paints immediately -- sooner than before, when it waited for the player chunk to arrive and paint it. Both producers set `data-click-to-load`; a mount without it is markup no producer emits, and it stays a poster-less placeholder.
  const clickToLoad = containers.filter((el) => el.dataset.clickToLoad === '');
  // DOCS TUTORIALS: the same click-to-load, but the player is built IN PLACE. The docs column is up to 960px wide and the player carries its own fullscreen button, so the theater adds nothing there. Measured 2026-10-08: with the old bare-div observer path, every docs tutorial visit fetched the 272 KB Video.js chunk and the 82 KB skin on load, because the mount sits within 600px of the fold.
  const inline = containers.filter((el) => el.dataset.clickToLoad === 'inline');

  // CLICK OPENS THE THEATER; it no longer builds the player in place.
  //
  // The inline mount is 576px wide in a solution hero and 768px on the homepage, for 1920x1080 footage whose captions are burned into the pixels -- roughly 30% scale, and below reading size. The player is built inside a full-viewport overlay instead, and the poster STAYS so that closing the overlay returns the visitor to the page they clicked from. `data-hydrated` is therefore never set on the mount, which is what keeps `.video-player-mount:not([data-hydrated])` (solution-video.css) as its permanent styling rather than a pre-hydration placeholder.
  //
  // NOT `{ once: true }`: re-opening is the normal case, and the theater keeps the same
  // player and its playback position across a close.
  clickToLoad.forEach((el) => {
    el.dataset.observed = 'true';
    el.addEventListener('click', () => openTheater(el));
  });

  inline.forEach((el) => {
    el.dataset.observed = 'true';
    armInline(el);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', scheduleHydration);
} else {
  scheduleHydration();
}

document.addEventListener('astro:page-load', scheduleHydration);
