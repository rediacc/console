/**
 * Client-side hydration for tutorial player embeds.
 *
 * Finds .tutorial-player-container placeholder divs (emitted by
 * remark-tutorial-embed.ts) and mounts TerminalPlayer React components.
 */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

function getCastKey(src: string): string {
  try {
    const pathname = new URL(src, window.location.origin).pathname;
    const filename = pathname.split('/').pop() ?? '';
    return filename.replace(/\.cast$/i, '');
  } catch {
    return (
      src
        .split('/')
        .pop()
        ?.replace(/\.cast$/i, '') ?? ''
    );
  }
}

async function hydrateTutorials() {
  const containers = document.querySelectorAll<HTMLElement>(
    '.tutorial-player-container[data-tutorial-src]'
  );
  if (containers.length === 0) return;

  const { default: TerminalPlayer } = await import('../components/TerminalPlayer');
  const lang = document.documentElement.lang || 'en';

  containers.forEach((el) => {
    if (el.dataset.hydrated) return;
    el.dataset.hydrated = 'true';

    const src = el.dataset.tutorialSrc ?? '';
    const title = el.dataset.tutorialTitle ?? '';
    const castKey = getCastKey(src);

    const root = createRoot(el);
    root.render(createElement(TerminalPlayer, { src, title, lang, castKey }));
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', hydrateTutorials);
} else {
  void hydrateTutorials();
}

document.addEventListener('astro:page-load', () => void hydrateTutorials());
