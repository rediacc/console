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
 *     sets `useVideoPlayer: true`. A bare div with no poster, so there is nothing for a
 *     visitor to click; it builds in place when an IntersectionObserver says it is near.
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

import { mountPlayers } from './tutorial-video-mount';
import { openTheater } from './video-theater';

/**
 * HYDRATE WHEN THE PLAYER IS ACTUALLY IN VIEW, not on DOMContentLoaded.
 *
 * plyr plus the player is 122,110 B, and it was reaching every visitor of every
 * locale homepage the moment the document parsed -- `check:ci-client-bundle-budget`
 * measures the homepage at 576,294 B against a 500,000 B target, and this chunk is
 * essentially the whole overage.
 *
 * `rootMargin` is deliberately generous: the point is to skip the download for a
 * visitor who never scrolls to the video, not to make someone who does scroll wait
 * for it. Loading starts while the mount is still a screen away.
 *
 * A browser without IntersectionObserver mounts immediately, which is the old
 * behaviour and the safe direction to fail.
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
  // The poster markup is server-rendered by SPSolutionVideo.astro, so the frame paints immediately -- sooner than before, when it waited for the player chunk to arrive and paint it. Mounts WITHOUT a poster (the docs `.tutorial-video-container`, emitted by remark-tutorial-embed.ts as a bare div) keep the observer path below, because there is nothing for a visitor to click.
  const clickToLoad = containers.filter((el) => el.dataset.clickToLoad !== undefined);
  const observed = containers.filter((el) => el.dataset.clickToLoad === undefined);

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

  if (observed.length === 0) return;

  if (typeof IntersectionObserver === 'undefined') {
    void mountPlayers(observed);
    return;
  }

  const io = new IntersectionObserver(
    (entries, observer) => {
      const visible = entries.filter((e) => e.isIntersecting).map((e) => e.target as HTMLElement);
      if (visible.length === 0) return;
      visible.forEach((el) => observer.unobserve(el));
      void mountPlayers(visible);
    },
    { rootMargin: '600px 0px' }
  );
  observed.forEach((el) => {
    el.dataset.observed = 'true';
    io.observe(el);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', scheduleHydration);
} else {
  scheduleHydration();
}

document.addEventListener('astro:page-load', scheduleHydration);
