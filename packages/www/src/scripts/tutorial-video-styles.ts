/**
 * Load the video player's stylesheets at RUNTIME, so they stay off pages with no player.
 *
 * WHY THIS MODULE EXISTS. Importing them from TutorialVideoPlayer.tsx put them into that
 * chunk's `viteMetadata.importedCss`, and Astro's page-CSS hoisting attaches a client
 * chunk's CSS to every page carrying that script -- dynamic-import boundaries are
 * irrelevant to it. So 37,018 B of render-blocking CSS was linked on 1,366 pages while
 * only 572 had a player: 794 pages paid for a component they never build.
 *
 * `?url` is what fixes it, and it is a Vite implementation detail worth naming: a `?url`
 * CSS import compiles to a `transform-only` import plus a URL string, and Vite excludes
 * `transform-only` ids from the chunk's CSS. The sheet is emitted as a plain asset that
 * Astro's hoisting never reads.
 *
 * SO DO NOT TURN EITHER SPECIFIER BACK INTO A BARE `import`. That single edit re-links
 * 37 KB onto 794 pages, and `check:ci-player-css-scope` is the gate that would catch it.
 *
 * Order matters: plyr first, then the overrides, matching the concatenation order the
 * single emitted chunk used to have.
 *
 * AND THESE LINKS LAND AT THE END OF <head>, after every page stylesheet, whereas
 * Astro's hoisted <link> used to sit among the page CSS. Verified 2026-09-03 to change
 * nothing that exists today -- three browser screenshots are byte-identical to the
 * pre-change baselines -- but the cascade IS genuinely different: page CSS can no
 * longer beat a `.plyr`/`.tvp-*` rule by SOURCE ORDER at equal specificity.
 *
 * So a page-level override of a player selector must win on SPECIFICITY. That is
 * already how solution-video.css writes its overrides, and its comments say the reason
 * in as many words; what changed is that specificity is now the only lever rather than
 * the belt-and-braces one.
 */
import plyrCssUrl from 'plyr/dist/plyr.css?url';
import playerCssUrl from '../styles/tutorial-video.css?url';

let pending: Promise<void> | null = null;

function loadOne(href: string): Promise<void> {
  return new Promise((resolve) => {
    if (document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) {
      resolve();
      return;
    }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    // Resolve on error too: a missing stylesheet must leave an UGLY player, never no
    // player at all. Failing open here is the difference between a cosmetic regression
    // and a blank box where the video was.
    link.addEventListener('load', () => resolve(), { once: true });
    link.addEventListener('error', () => resolve(), { once: true });
    document.head.appendChild(link);
  });
}

/** Resolves once both sheets are in the document. Memoised; safe to call per mount. */
export function ensurePlayerStyles(): Promise<void> {
  pending ??= (async () => {
    await loadOne(plyrCssUrl);
    await loadOne(playerCssUrl);
  })();
  return pending;
}
