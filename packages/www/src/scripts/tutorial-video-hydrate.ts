/**
 * Client-side hydration for every TutorialVideoPlayer on the site.
 *
 * Finds placeholder divs and mounts the player on them: `.tutorial-video-container`
 * emitted by remark-tutorial-embed.ts when a page sets `useVideoPlayer: true`, and
 * `.video-player-mount` emitted by SPSolutionVideo.astro for the solution-page hero.
 * Both get the same player, including its in-frame language picker.
 *
 * WHY A PLACEHOLDER AND NOT `client:visible`. `plyr` reads `document` at module scope --
 * importing it under Node throws `ReferenceError: document is not defined` -- so the
 * player cannot be server-rendered at all, which is what an Astro island requires. The
 * dynamic `import()` below is what keeps it off the server, and it is why the solution
 * hero mounts this way rather than as an island.
 *
 * The original .tutorial-player-container hydration in tutorial-hydrate.ts
 * remains active for any page that does not opt in.
 */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { ensurePlayerStyles } from './tutorial-video-styles';
import type { TutorialSourceSet } from '../components/TutorialVideoPlayer';

/**
 * Mount the players inside `els`. Split out from the scheduling below so the
 * `import()` -- and therefore plyr's 122,110 B -- happens per visible container
 * rather than once for the whole page on load.
 */
/** Resolve once React has actually rendered the <video>, or null if it never does.
 *
 * Bounded on purpose: a hydration that fails should leave the visitor a still page, not
 * an observer spinning for the life of the tab.
 */
function whenVideoAppears(el: HTMLElement, timeoutMs = 4000): Promise<HTMLVideoElement | null> {
  const found = el.querySelector('video');
  if (found) return Promise.resolve(found);
  return new Promise((resolve) => {
    let done = false;
    const finish = (v: HTMLVideoElement | null) => {
      if (done) return;
      done = true;
      observer.disconnect();
      clearTimeout(timer);
      resolve(v);
    };
    const observer = new MutationObserver(() => {
      const v = el.querySelector('video');
      if (v) finish(v);
    });
    observer.observe(el, { childList: true, subtree: true });
    const timer = setTimeout(() => finish(el.querySelector('video')), timeoutMs);
  });
}

async function mountPlayers(els: HTMLElement[]) {
  const containers = els;
  if (containers.length === 0) return;

  // Both in one tick: the stylesheet is a quarter of the component chunk's size, so it
  // never lengthens the critical path, and awaiting it means the first frame of player
  // DOM is already styled rather than merely usually styled.
  const [, { default: TutorialVideoPlayer }] = await Promise.all([
    ensurePlayerStyles(),
    import('../components/TutorialVideoPlayer'),
  ]);
  type SourceSet = TutorialSourceSet;

  containers.forEach((el) => {
    if (el.dataset.hydrated) return;
    el.dataset.hydrated = 'true';

    const src = el.dataset.videoSrc ?? '';
    const posterSrc = el.dataset.posterSrc ?? '';
    const subtitlesSrc = el.dataset.subtitlesSrc ?? '';
    const chaptersSrc = el.dataset.chaptersSrc ?? '';
    const wordsSrc = el.dataset.wordsSrc ?? '';
    // The portrait cut, which only the solution videos ship. Empty means "no portrait
    // cut", and the player then uses the landscape one at every width.
    const verticalSrc = el.dataset.verticalSrc ?? '';
    const title = el.dataset.title ?? '';
    const lang = (el.dataset.lang ?? document.documentElement.lang) || 'en';
    // One JSON attribute holding <locale> -> {mp4, poster, vtt, chapters, words}, written
    // by remark-tutorial-embed.ts at build time. A malformed or absent attribute leaves
    // `sources` undefined, and the player then renders without a language picker on the
    // five URLs above -- exactly the behaviour it had before the picker existed.
    let sources: Record<string, SourceSet> | undefined;
    if (el.dataset.sources) {
      try {
        sources = JSON.parse(el.dataset.sources) as Record<string, SourceSet>;
      } catch {
        sources = undefined;
      }
    }

    const root = createRoot(el);
    root.render(
      createElement(TutorialVideoPlayer, {
        src,
        posterSrc,
        subtitlesSrc,
        chaptersSrc,
        wordsSrc,
        verticalSrc,
        title,
        lang,
        sources,
      })
    );
  });
}

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
  // An IntersectionObserver cannot help these: measured across all 44 English
  // mount-carrying pages at 1440x900 and 390x844, every mount is ABOVE THE FOLD, so the
  // observer fires on load and defers nothing. The visitor is looking at the poster
  // already; the 122 KB player only has to exist once they ask for it.
  //
  // The poster markup is server-rendered by SPSolutionVideo.astro, so the frame paints
  // immediately -- sooner than before, when it waited for the player chunk to arrive and
  // paint it. Mounts WITHOUT a poster (the docs `.tutorial-video-container`, emitted by
  // remark-tutorial-embed.ts as a bare div) keep the observer path below, because there
  // is nothing for a visitor to click.
  const clickToLoad = containers.filter((el) => el.dataset.clickToLoad !== undefined);
  const observed = containers.filter((el) => el.dataset.clickToLoad === undefined);

  clickToLoad.forEach((el) => {
    el.dataset.observed = 'true';
    const start = () => {
      el.querySelectorAll('.video-poster-preview, .video-poster-play').forEach((n) => n.remove());
      void mountPlayers([el])
        .then(() => whenVideoAppears(el))
        .then((video) => {
          // START IT. Without this the poster is a TWO-CLICK play: the first click builds
          // the player and hands back a paused one, so the visitor presses play, watches
          // nothing happen, and presses play again. Caught in agent-browser on
          // /en/solutions/backup-verification/ -- the click hydrated correctly and the
          // video sat at 00:00, which every automated check here would have called a pass.
          //
          // The rejection path is not an error and is deliberately silent: the chunk fetch
          // can outlast the browser's user-gesture window, and a blocked play() leaves
          // exactly the paused, fully-built player the visitor would have had anyway.
          //
          // What it is NOT is the element being missing -- see whenVideoAppears. The first
          // draft wrote `el.querySelector('video')?.play()` directly here and did nothing at
          // all, because mountPlayers resolves when the component chunk has LOADED, several
          // frames before React has rendered a <video>. The `?.` then made a real bug look
          // like a no-op with no console output, no rejection, and a player that just sat at
          // 00:00. Measured, not guessed: readyState was 4 and the same play() call
          // succeeded from the console a second later.
          video?.play().catch(() => {});
        });
    };
    el.addEventListener('click', start, { once: true });
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
