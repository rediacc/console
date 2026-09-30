/**
 * Building a TutorialVideoPlayer on a placeholder div, and knowing when it is really there.
 *
 * Split out of `tutorial-video-hydrate.ts` when the video theater arrived: the hydrator
 * schedules mounts and the theater hosts one, and both need these two functions. Keeping
 * them in the hydrator would have made the theater import the scheduler it is called
 * from, which is a cycle.
 *
 * WHY A PLACEHOLDER AND NOT `client:visible`. `plyr` reads `document` at module scope --
 * importing it under Node throws `ReferenceError: document is not defined` -- so the
 * player cannot be server-rendered at all, which is what an Astro island requires. The
 * dynamic `import()` below is what keeps it off the server.
 */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { ensurePlayerStyles } from './tutorial-video-styles';
import type { TutorialSourceSet } from '../components/TutorialVideoPlayer';

/** Resolve once React has actually rendered the <video>, or null if it never does.
 *
 * Bounded on purpose: a hydration that fails should leave the visitor a still page, not
 * an observer spinning for the life of the tab.
 */
export function whenVideoAppears(
  el: HTMLElement,
  timeoutMs = 4000
): Promise<HTMLVideoElement | null> {
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

export async function mountPlayers(els: HTMLElement[]) {
  const containers = els;
  if (containers.length === 0) return;

  // Both in one tick: the stylesheet is a quarter of the component chunk's size, so it never lengthens the critical path, and awaiting it means the first frame of player DOM is already styled rather than merely usually styled.
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
    // The portrait cut, which only the solution videos ship. Empty means "no portrait cut", and the player then uses the landscape one at every width.
    const verticalSrc = el.dataset.verticalSrc ?? '';
    const title = el.dataset.title ?? '';
    const lang = (el.dataset.lang ?? document.documentElement.lang) || 'en';
    // One JSON attribute holding <locale> -> {mp4, poster, vtt, chapters, words}, written
    // by remark-tutorial-embed.ts at build time. A malformed or absent attribute leaves `sources` undefined, and the player then renders without a language picker on the five URLs above -- exactly the behaviour it had before the picker existed.
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
