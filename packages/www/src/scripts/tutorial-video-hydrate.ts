/**
 * Client-side hydration for every TutorialVideoPlayer on the site.
 *
 * Finds placeholder divs and mounts the player on them: `.tutorial-video-container`
 * emitted by remark-tutorial-embed.ts when a page sets `useVideoPlayer: true`, and
 * `.video-player-mount` emitted by SPSolutionVideo.astro for the solution-page hero.
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
import type { TutorialSourceSet } from '../components/TutorialVideoPlayer';

async function hydrateTutorialVideos() {
  const containers = document.querySelectorAll<HTMLElement>(
    '.tutorial-video-container[data-video-src], .video-player-mount[data-video-src]'
  );
  if (containers.length === 0) return;

  const { default: TutorialVideoPlayer } = await import('../components/TutorialVideoPlayer');
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

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', hydrateTutorialVideos);
} else {
  void hydrateTutorialVideos();
}

document.addEventListener('astro:page-load', () => void hydrateTutorialVideos());
