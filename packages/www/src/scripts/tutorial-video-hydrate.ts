/**
 * Client-side hydration for the new HTML5 tutorial video embeds.
 *
 * Finds .tutorial-video-container placeholder divs emitted by
 * remark-tutorial-embed.ts when a page sets `useVideoPlayer: true` in
 * frontmatter, and mounts TutorialVideoPlayer React components on them.
 *
 * The original .tutorial-player-container hydration in tutorial-hydrate.ts
 * remains active for any page that does not opt in.
 */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

async function hydrateTutorialVideos() {
  const containers = document.querySelectorAll<HTMLElement>(
    '.tutorial-video-container[data-video-src]'
  );
  if (containers.length === 0) return;

  const { default: TutorialVideoPlayer } = await import('../components/TutorialVideoPlayer');

  containers.forEach((el) => {
    if (el.dataset.hydrated) return;
    el.dataset.hydrated = 'true';

    const src = el.dataset.videoSrc ?? '';
    const posterSrc = el.dataset.posterSrc ?? '';
    const subtitlesSrc = el.dataset.subtitlesSrc ?? '';
    const chaptersSrc = el.dataset.chaptersSrc ?? '';
    const wordsSrc = el.dataset.wordsSrc ?? '';
    const title = el.dataset.title ?? '';
    const lang = (el.dataset.lang ?? document.documentElement.lang) || 'en';

    const root = createRoot(el);
    root.render(
      createElement(TutorialVideoPlayer, {
        src,
        posterSrc,
        subtitlesSrc,
        chaptersSrc,
        wordsSrc,
        title,
        lang,
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
