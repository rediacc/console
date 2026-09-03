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

  if (typeof IntersectionObserver === 'undefined') {
    void mountPlayers(containers);
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
  containers.forEach((el) => {
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
