#!/usr/bin/env tsx
/**
 * check:ci-docs-browse-invariants -- the three /en/docs fixes that a browser would have
 * to catch, gated by the MECHANISM each one rests on instead.
 *
 * WHY NOT A BROWSER. Heading alignment, an element's absence and the absence of a flash
 * are visual facts, and the honest gate for them is an interactive one; that is wave D
 * gate 2 (agent/programs/www-round5/05-gates.md) and it is not this. But each of the
 * three fixes landed on 2026-08-24 rests on a STRUCTURAL property that is checkable from
 * source, and a structural gate that fires on the real cause beats no gate at all while
 * the visual one is unowned.
 *
 * WHAT A GREEN HERE DOES NOT MEAN, stated plainly because this gate's whole risk is
 * being over-read. It never renders the page, never measures a box and never compares a
 * pixel. Every one of these would pass it while looking wrong to a reader:
 *
 *   * the two headings sitting at different heights because something ABOVE them in the
 *     results column gained margin -- the gate checks that neither heading carries a
 *     competing rule, not that they end up level;
 *   * `.sr-only` itself being redefined so the tally is visible again, since the gate
 *     reads the class NAME and not its computed clip;
 *   * the category group being hidden before paint and then revealed by some other
 *     script, or hidden with `visibility` while still occupying its space;
 *   * any of it breaking at a viewport this gate cannot have an opinion about, since
 *     it has no viewport at all.
 *
 * Those are the interactive gate's to catch. This one is a tripwire on the three
 * mechanisms, and the failure text and the success line both say so, so a green in a CI
 * log cannot be read as "the layout is verified".
 *
 * THE THREE PROPERTIES:
 *
 * 1. THE TALLY IS ANNOUNCED, NOT SHOWN. A visible "79 / 79" answered a question nobody
 *    arrives with and pushed the results heading 41px below the rail's. It stays as an
 *    sr-only live region, because a screen reader gets no other signal that filtering
 *    changed the result set.
 * 2. THE TWO HEADINGS ARE STYLED BY ONE RULE. They align because both are `h2` inside
 *    `.article-content`. Four class-level declarations tried to size them and never won;
 *    re-adding one that DOES win is how they drift apart again.
 * 3. THE CATEGORY GROUP IS DECIDED BEFORE FIRST PAINT. Hiding it from the deferred
 *    module script is what made it flash on every ?category= navigation: a module script
 *    runs after paint by definition. The decision belongs to an inline script that sets
 *    a flag on <html>, plus CSS.
 *
 * CONTROL-FIRST. Every check is a function over source TEXT, so --selftest plants each
 * defect in memory and requires the production function to catch it. Nothing on disk is
 * touched, and a check that cannot fail fails the selftest instead of passing quietly.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const INDEX = path.join(REPO, 'packages/www/src/pages/[lang]/docs/index.astro');
const CSS = path.join(REPO, 'packages/www/src/styles/docs-browse.css');

/** The tally must exist, must be sr-only, and its old visible wrapper must be gone. */
export const tallyFaults = (astro: string): string[] => {
  const out: string[] = [];
  const m = /<output[^>]*class="([^"]*docs-browse-tally[^"]*)"/.exec(astro);
  if (!m) out.push('the docs-browse-tally live region is gone; filtering is then silent to a screen reader');
  else if (!/\bsr-only\b/.test(m[1])) out.push(`docs-browse-tally is visible again (class="${m[1]}")`);
  if (/docs-browse-status/.test(astro)) out.push('the visible docs-browse-status wrapper is back');
  return out;
};

/** Neither heading may carry a class-level size or margin; `.article-content h2` owns both. */
export const headingFaults = (css: string): string[] => {
  const out: string[] = [];
  for (const sel of ['.docs-rail-heading', '.docs-browse-group-title']) {
    const re = new RegExp(`\\${sel}\\s*\\{([^}]*)\\}`);
    const m = re.exec(css);
    if (!m) continue;
    const bad = m[1].split(';').map((d) => d.trim()).filter((d) => /^(font-size|margin)/.test(d));
    for (const d of bad) out.push(`${sel} declares \`${d}\`, which competes with .article-content h2 for the pair's size and spacing`);
  }
  return out;
};

/** The flag is set inline, the hiding is CSS, and the deferred script stays out of it. */
export const flashFaults = (astro: string, css: string): string[] => {
  const out: string[] = [];
  if (!/is:inline[\s\S]{0,400}docsCategory/.test(astro))
    out.push('no is:inline script sets data-docs-category, so the decision moves back after first paint');
  if (!/\[data-docs-category\][^{]*\.docs-rail-group--primary/.test(css))
    out.push('no CSS hides .docs-rail-group--primary under [data-docs-category]');
  const mod = astro.slice(astro.lastIndexOf('<script>'));
  if (/docs-rail-group--primary/.test(mod))
    out.push('the deferred module script references .docs-rail-group--primary again; it runs after paint, which is the flash');
  return out;
};

const selftest = (astro: string, css: string): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };

  check('the tree as it stands is clean', [...tallyFaults(astro), ...headingFaults(css), ...flashFaults(astro, css)].length === 0,
    JSON.stringify([...tallyFaults(astro), ...headingFaults(css), ...flashFaults(astro, css)]));

  // Each control plants exactly the regression the fix prevents.
  check('a tally made visible again is caught',
    tallyFaults(astro.replace('docs-browse-tally sr-only', 'docs-browse-tally')).length > 0);
  check('a deleted tally is caught too, not just an unhidden one',
    tallyFaults(astro.replace(/<output[^>]*docs-browse-tally[\s\S]*?<\/output>/, '')).length > 0);
  check('the old visible status wrapper coming back is caught',
    tallyFaults(`${astro}\n<p class="docs-browse-status"></p>`).length > 0);
  check('a font-size put back on the rail heading is caught',
    headingFaults(`${css}\n.docs-rail-heading { font-size: 1rem; }`).length > 0);
  check('a margin put back on the results heading is caught',
    headingFaults(`${css}\n.docs-browse-group-title { margin-block-end: 1rem; }`).length > 0);
  check('losing the inline flag script is caught',
    flashFaults(astro.replace('docsCategory', 'somethingElse'), css).length > 0);
  check('losing the CSS that hides the group is caught',
    flashFaults(astro, css.replace('[data-docs-category]', '.never-matches')).length > 0);
  check('the deferred script taking the decision back is caught',
    flashFaults(`${astro}\n<script>\n  const g = document.querySelector('.docs-rail-group--primary');\n</script>`, css).length > 0);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  const astro = fs.readFileSync(INDEX, 'utf8');
  const css = fs.readFileSync(CSS, 'utf8');
  // Anti-vacuity: a gate reading the wrong file, or an empty one, must not report success.
  if (!/docs-browse-body/.test(astro) || !/docs-rail-group--primary/.test(css)) {
    console.error('✗ the docs browse sources do not look like themselves; a green here would mean nothing.');
    return 1;
  }
  if (process.argv.slice(2).includes('--selftest')) return selftest(astro, css);

  const faults = [...tallyFaults(astro), ...headingFaults(css), ...flashFaults(astro, css)];
  if (faults.length) {
    console.error(`✗ ${faults.length} docs-browse invariant(s) broken:\n`);
    for (const f of faults) console.error(`  ${f}`);
    console.error('\n  These are the mechanisms three shipped fixes rest on. This gate cannot see the');
    console.error('  pixels; the interactive gate that can is wave D gate 2, still unowned.');
    return 1;
  }
  console.log('✓ docs browse invariants hold: the tally is sr-only, neither heading carries a competing size or margin, and the category group is decided before first paint.');
  // The caveat rides the SUCCESS line, not just the failure path: a green is the only
  // output most readers of a CI log will ever see, and this one is structural.
  console.log('  STRUCTURAL ONLY -- nothing was rendered, measured or compared. Pixel-level regressions with correct selectors and valid CSS pass this gate; that is wave D gate 2.');
  return 0;
};

process.exit(main());
