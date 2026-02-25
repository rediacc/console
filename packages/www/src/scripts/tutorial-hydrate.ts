/**
 * Client-side hydration for tutorial player embeds.
 *
 * Finds .tutorial-player-container placeholder divs (emitted by
 * remark-tutorial-embed.ts) and mounts TerminalPlayer React components.
 */

import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

async function hydrateTutorials() {
  const containers = document.querySelectorAll<HTMLElement>(
    '.tutorial-player-container[data-tutorial-src]'
  );
  if (containers.length === 0) return;

  const { default: TerminalPlayer } = await import('../components/TerminalPlayer');

  containers.forEach((el) => {
    // Skip already-hydrated containers
    if (el.dataset.hydrated) return;
    el.dataset.hydrated = 'true';

    const src = el.dataset.tutorialSrc ?? '';
    const title = el.dataset.tutorialTitle ?? '';

    const root = createRoot(el);
    root.render(createElement(TerminalPlayer, { src, title }));
  });
}

// Initial load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', hydrateTutorials);
} else {
  void hydrateTutorials();
}

// Astro View Transitions support
document.addEventListener('astro:page-load', () => void hydrateTutorials());
