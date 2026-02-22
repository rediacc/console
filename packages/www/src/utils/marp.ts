/**
 * Marp rendering utility for the RDC CLI cheat sheet.
 *
 * Renders Marp-flavoured markdown into HTML + CSS using a custom theme
 * (`marp-cheatsheet.css`).  The output is intended for multi-column
 * document display, NOT a slide presentation.
 */
import { Marp } from '@marp-team/marp-core';
// Vite ?raw import embeds the CSS as a string literal at build time,
// avoiding readFileSync path resolution issues in Astro's SSG pipeline.
import THEME_CSS from '../styles/marp-cheatsheet.css?raw';

export interface CheatSheetResult {
  /** The rendered HTML — contains <section> elements, one per "slide" */
  html: string;
  /** The generated CSS — includes Marp base styles + custom theme */
  css: string;
}

/**
 * Render a Marp markdown document into HTML + CSS.
 *
 * The markdown should:
 *   - Include `marp: true` and `theme: rediacc-cheatsheet` in front matter
 *   - Use `---` to separate sections (cheatsheet "cards")
 *   - Optionally use `<!-- _class: cat-blue -->` etc. for card colour tints
 *
 * @example
 * ```md
 * ---
 * marp: true
 * theme: rediacc-cheatsheet
 * ---
 * ## Contexts
 * `rdc context list`
 * ```
 */
export function renderCheatSheet(markdown: string): CheatSheetResult {
  const marp = new Marp({
    // Allow HTML tags in markdown (needed for the branding header in the
    // first section and any other rich content)
    html: true,
    // Omit Marp's browser-side JavaScript — we only need static HTML/CSS
    script: false,
    // Disable SVG slide wrapping so sections render as plain HTML elements
    // suitable for multi-column document/cheatsheet layout
    inlineSVG: false,
  });

  // Register the custom cheat-sheet theme
  marp.themeSet.add(THEME_CSS);

  const { html, css } = marp.render(markdown);

  return { html, css };
}
