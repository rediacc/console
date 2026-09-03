#!/usr/bin/env tsx
/**
 * A CSS rule whose class nothing renders is dead weight.
 *
 * WHY THIS EXISTS. This repo gates dead bash, dead case arms, dead service methods and
 * dead translation keys, and CSS, the biggest surface in the simplification programme,
 * had no such gate. `.cta-bolt` is the specimen: styled in `main.css`, never applied to
 * any element, and guarded by a whole dedicated CI gate policing the uniqueness of a
 * class nobody uses. Three instruments touched it and none asked whether it was alive.
 *
 * THE OPPOSITE QUESTION FROM check-css-dom-refs, which asks "is this USE still styled".
 * This asks "is this RULE still used". The two together close the loop; neither implies
 * the other, and running only one is how a range deletion unstyles a live element or a
 * dead block survives a sweep.
 *
 * CONSERVATIVE BY CONSTRUCTION, because here a false positive would delete live styling.
 * A class counts as ALIVE if its name appears anywhere in any source file, not merely
 * inside a class attribute. That deliberately over-counts life: a name mentioned in a
 * comment, a doc, or a runtime template keeps its rule. The gate's job is to catch the
 * clearly dead, never to win an argument about the marginal.
 *
 * SHRINK-ONLY BASELINE. The existing dead set is frozen, so this fails on GROWTH from
 * today. Drain with --write-baseline as sweeps land; it only ever shrinks.
 *
 * Usage:
 *   npx tsx scripts/check-dead-css.ts [--write-baseline] [--selftest] [--list]
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';
import { GREEN, NC, RED } from './utils/console.js';

import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WWW = path.join(ROOT, 'packages/www');
const BASELINE = path.join(ROOT, 'scripts/data/dead-css-baseline.json');

/** Class selectors defined by a stylesheet. */
export function definedClasses(css: string): Set<string> {
  const out = new Set<string>();
  const body = css.replace(/\/\*[\s\S]*?\*\//g, ' ');
  for (const m of body.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) out.add(m[1]);
  return out;
}

/**
 * Vendor classes built by a third-party library at RUNTIME, which no source file can
 * mention because our code never writes them.
 *
 * BLOCKER: `plyr` is a declared dependency (`packages/www/package.json`) imported by
 * `src/components/TutorialVideoPlayer.tsx`. Its stylesheet and
 * `src/styles/tutorial-video.css` are loaded at RUNTIME by
 * `src/scripts/tutorial-video-styles.ts` (2026-09-03) rather than imported by the
 * component -- a module-scope import put them on 794 pages with no player. The
 * suppression is unchanged in substance; only the citation moved, because a reason
 * that points at a line which no longer exists is a reason nobody can check. The library builds `.plyr__poster` and `.plyr__captions`
 * itself; styling a vendor library's generated DOM is the entire point of those rules, and
 * the gate reported both as dead. Deleting them would unstyle the tutorial player's poster
 * and captions. Scanning `node_modules/plyr/dist` instead was considered and rejected: it
 * would make the gate depend on an installed tree and on a minified bundle's token soup,
 * and slow every run for one library.
 */
const VENDOR_CLASS_PREFIXES = ['plyr__'];

/**
 * Class-name fragments a source builds by interpolation, harvested ONLY from a class
 * position (`class=`, `className=`, `class:list`).
 *
 * A class assembled as `` `toc-item toc-level-${heading.level}` `` is never spelled out, so
 * the token scan cannot see `toc-level-3` and reports it dead. Eight baselined entries were
 * live this way: `toc-level-3..6` from `DocsLayout.astro` and `ContentLayout.astro`, and
 * `newsletter-footer` / `-inline` / `-modal` / `-sticky-bar` from
 * `NewsletterSignup.tsx`, every variant reachable from a real call site.
 *
 * RESTRICTED TO A CLASS POSITION ON PURPOSE. Harvesting every `prefix-${` in the file was
 * tried and is too loose: `SPDownloadGated.astro` holds
 * `` const source = `solution-${slug}-30scroll` ``, an analytics string, and the loose rule
 * rescued four genuinely dead `solution-*` classes.
 */
export function interpolatedClassPrefixes(source: string): Set<string> {
  const out = new Set<string>();
  const attr = /(?:class|className)\s*=\s*\{?\s*`([^`]*)`|class:list\s*=\s*\{([^}]*)\}/g;
  for (const m of source.matchAll(attr)) {
    const body = m[1] ?? m[2] ?? '';
    for (const f of body.matchAll(/([-_a-zA-Z][\w-]*?)-\$\{/g)) out.add(f[1]);
  }
  return out;
}

/**
 * Class names supplied by the translation CATALOGUE rather than by code.
 *
 * `cardClass` values live only in `src/i18n/translations/en.json`, which `sources()` never
 * read. Today's six values are ordinary English words that happen to occur in docs prose,
 * so the over-broad token scan rescued them BY COINCIDENCE; the first hyphenated value
 * would have been reported dead. Only the values of keys literally named `cardClass` are
 * harvested: feeding the whole catalogue in as token soup was measured to rescue
 * `pricing-page.css:emergency`, which is genuinely dead and only matched prose about a
 * "24/7 emergency hotline".
 */
export function catalogClassValues(json: string): Set<string> {
  const out = new Set<string>();
  for (const m of json.matchAll(/"cardClass"\s*:\s*"([^"]*)"/g)) {
    for (const c of m[1].split(/\s+/)) if (c) out.add(c);
  }
  return out;
}

/** Every identifier-ish token in a source file. Over-broad ON PURPOSE: see the header. */
export function mentionedTokens(source: string): Set<string> {
  const out = new Set<string>();
  for (const m of source.matchAll(/[-_a-zA-Z][\w-]*/g)) out.add(m[0]);
  return out;
}

function sheets(): string[] {
  return [...globSync(`${WWW}/public/styles/**/*.css`), ...globSync(`${WWW}/src/styles/**/*.css`)];
}

function sources(): string[] {
  return [
    ...globSync(`${WWW}/src/**/*.{astro,tsx,ts,jsx,js,md,mdx}`),
    ...globSync(`${WWW}/public/**/*.js`),
  ];
}

/**
 * Stylesheets in which EVERY class is dead, i.e. the whole file is orphaned.
 *
 * This capability used to live in the unwired `check-unused-css-files.js`, which was
 * deleted as superseded (it found 2 real orphans and both were removed: `team-video.css`
 * at 235 lines and `language-switcher-inline.css` at 34). Nothing else covers it: knip's
 * `packages/www` project globs carry no `.css`, and adding it would immediately
 * false-positive on `main.css` and `responsive.css`, which are loaded by a `<link>` tag
 * rather than imported by any module.
 *
 * A newly orphaned sheet is already caught, because each of its classes becomes a NEW dead
 * class. The residual gap this closes is the sheet whose classes are ALREADY baselined, or
 * one with no class selectors at all, where the per-class view reports nothing new and the
 * file sits there forever.
 */
export function fullyDeadSheets(deadSet: Set<string>): string[] {
  const out: string[] = [];
  for (const f of sheets()) {
    const rel = path.relative(ROOT, f);
    const classes = definedClasses(readFileSync(f, 'utf8'));
    if (classes.size === 0) continue; // a sheet of element/keyframe rules only, not our call
    if ([...classes].every((c) => deadSet.has(`${rel}:${c}`))) out.push(rel);
  }
  return out;
}

function findDead(): string[] {
  const defined = new Map<string, string>();
  for (const f of sheets()) {
    for (const c of definedClasses(readFileSync(f, 'utf8'))) {
      if (!defined.has(c)) defined.set(c, path.relative(ROOT, f));
    }
  }
  const alive = new Set<string>();
  const prefixes = new Set<string>();
  for (const f of sources()) {
    const text = readFileSync(f, 'utf8');
    for (const t of mentionedTokens(text)) alive.add(t);
    for (const p of interpolatedClassPrefixes(text)) prefixes.add(p);
  }
  const catalog = path.join(WWW, 'src/i18n/translations/en.json');
  if (existsSync(catalog)) {
    for (const c of catalogClassValues(readFileSync(catalog, 'utf8'))) alive.add(c);
  }
  const livesByPrefix = (c: string): boolean =>
    VENDOR_CLASS_PREFIXES.some((p) => c.startsWith(p)) ||
    [...prefixes].some((p) => c.startsWith(`${p}-`) && c.length > p.length + 1);
  // A class referenced by another STYLESHEET (a compound selector) is not evidence of
  // life: both rules can be dead together. Only source files vouch for a class.
  const dead: string[] = [];
  for (const [c, file] of defined)
    if (!alive.has(c) && !livesByPrefix(c)) dead.push(`${file}:${c}`);
  return dead.sort();
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? `${GREEN}PASS${NC}` : `${RED}FAIL${NC}`}  ${label}`);
    if (!ok) bad++;
  };
  const d = definedClasses(
    '.alpha { color: red } /* .commented {} */ .beta:hover, .gamma::after {}'
  );
  check('class selectors are collected', d.has('alpha') && d.has('beta') && d.has('gamma'));
  check('a class inside a CSS COMMENT is not treated as defined', !d.has('commented'));
  check('a pseudo-element is not mistaken for a class', !d.has('after') && !d.has('hover'));
  const t = mentionedTokens('<div class="alpha"> `cf-${x}-tail` // beta');
  check('CONTROL: a class in a class attribute is alive', t.has('alpha'));
  check('CONTROL: a name mentioned only in a comment is alive (conservative)', t.has('beta'));
  check('a class defined but mentioned nowhere is dead', !t.has('gamma'));
  check('a hyphenated class survives tokenizing', mentionedTokens('x cta-bolt y').has('cta-bolt'));

  // DEFECT A: a class supplied only by the translation catalogue.
  const cat = catalogClassValues('{"a":{"cardClass":"compliant"},"b":{"other":"emergency"}}');
  check('a cardClass VALUE is harvested from the catalogue', cat.has('compliant'));
  check(
    'CONTROL: a non-cardClass value is NOT harvested (token soup would rescue dead classes)',
    !cat.has('emergency')
  );

  // DEFECT B: a class built by interpolation inside a class position.
  check(
    'an interpolated prefix in class= is harvested',
    interpolatedClassPrefixes('<li class={`sidebar-item toc-item toc-level-${h.level}`}>').has(
      'toc-level'
    )
  );
  check(
    'an interpolated prefix in className= is harvested',
    interpolatedClassPrefixes('<div className={`newsletter-signup newsletter-${variant}`}>').has(
      'newsletter'
    )
  );
  check(
    'CONTROL: an interpolated string OUTSIDE a class position is ignored',
    interpolatedClassPrefixes('const source = `solution-${slug}-30scroll`;').size === 0
  );

  // DEFECT C: a vendor runtime class no source can mention.
  check(
    'the vendor prefix list covers the plyr runtime classes',
    VENDOR_CLASS_PREFIXES.some((p) => 'plyr__poster'.startsWith(p))
  );
  check(
    'CONTROL: the vendor prefix does not rescue an unrelated class',
    !VENDOR_CLASS_PREFIXES.some((p) => 'player-shell'.startsWith(p))
  );

  // The whole-sheet view. NOTE what is NOT asserted here: whether the live tree currently
  // has an orphaned stylesheet. That is a property of the REPO, and asserting it in the
  // selftest made a real orphan print "controls failed; the gate cannot be trusted" and
  // exit before main() could name the file. A selftest answers "does the instrument
  // work", never "is the repo clean"; conflating the two turns an actionable finding into
  // a broken-tool message. main() owns the live check.
  check(
    'CONTROL: a sheet IS reported when every one of its classes is dead',
    (() => {
      const first = sheets()[0];
      if (!first) return false;
      const rel = path.relative(ROOT, first);
      const all = new Set(
        [...definedClasses(readFileSync(first, 'utf8'))].map((c) => `${rel}:${c}`)
      );
      return all.size > 0 && fullyDeadSheets(all).includes(rel);
    })()
  );
  // THE SHRINK-ONLY COMPOSITION RULE, shared with every other baselined gate here.
  for (const c of sharedSelftestCases()) check(c.name, c.ok);

  return bad;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    console.log('dead-css gate selftest');
    const bad = selftest();
    console.log(bad === 0 ? '\n${GREEN}✓${NC} all controls pass' : `\n${RED}✗${NC} ${bad} failed`);
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  const dead = findDead();
  if (sheets().length === 0 || sources().length === 0) {
    console.error('✗ zero stylesheets or zero sources scanned; the gate is not seeing the site');
    process.exit(1);
  }
  if (process.argv.includes('--list')) {
    for (const d of dead) console.log(d);
    process.exit(0);
  }

  if (process.argv.includes('--write-baseline')) {
    // COMPOSITION. Shrink-only used to be enforced on the read path only, so a reseed
    // could shed twenty dead classes, absorb one fresh one, and print a smaller number.
    // This gate is the reason `rekeyHint` exists: its ids carry the SELECTOR TEXT, so
    // editing a rule re-keys the entry and the old id dies while a new one is born.
    // A reseed would swallow the newcomer; the right move is to hand-edit the one line.
    const previous: string[] = existsSync(BASELINE)
      ? JSON.parse(readFileSync(BASELINE, 'utf8'))
      : [];
    const verdict = writeBaselineVerdict({
      baselineExists: existsSync(BASELINE),
      firstSeedFlag: process.argv.includes('--first-seed'),
      additions: existsSync(BASELINE) ? baselineAdditions(previous, dead) : [],
    });
    if (verdict !== null) {
      console.error(
        `\n${RED}✗${NC} ${renderRefusal(verdict, {
          baselineLabel: path.relative(ROOT, BASELINE),
          noun: 'dead class',
          previousCount: previous.length,
          newCount: dead.length,
          rekeyHint: true,
        })}`
      );
      process.exit(1);
    }
    writeFileSync(BASELINE, `${JSON.stringify(dead, null, 2)}\n`);
    console.log(
      `baseline written: ${dead.length} dead class(es) ` +
        `(${previous.length} before, ${previous.filter((d) => !dead.includes(d)).length} drained, 0 added)`
    );
    process.exit(0);
  }

  const base: string[] = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : [];
  const known = new Set(base);
  const fresh = dead.filter((d) => !known.has(d));
  const fixed = base.filter((d) => !dead.includes(d));

  console.log(
    `${sheets().length} stylesheet(s), ${sources().length} source file(s); ${dead.length} dead class(es), baseline ${base.length}.`
  );
  if (fresh.length > 0) {
    console.error(`\n${RED}✗${NC} ${fresh.length} NEW dead class(es):`);
    for (const f of fresh.slice(0, 25)) console.error(`    ${f}`);
    if (fresh.length > 25) console.error(`    ... and ${fresh.length - 25} more`);
    console.error('\nDelete the rule, or render the class. Do not add it to the baseline.');
    process.exit(1);
  }
  if (fixed.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${fixed.length} baselined class(es) are no longer dead. This baseline is`
    );
    console.error('SHRINK-ONLY, so drain it: npx tsx scripts/check-dead-css.ts --write-baseline');
    process.exit(1);
  }
  // WHOLE-SHEET view, reported even when every class is already baselined. Without this a
  // fully orphaned stylesheet is invisible: each of its classes is a known finding, so the
  // per-class check is silent and the file survives every sweep. This is the capability
  // inherited from the deleted `check-unused-css-files.js`.
  const orphaned = fullyDeadSheets(new Set(dead));
  if (orphaned.length > 0) {
    console.error(`\n${RED}✗${NC} ${orphaned.length} stylesheet(s) in which EVERY class is dead:`);
    for (const o of orphaned) console.error(`    ${o}`);
    console.error('\nDelete the file and drain its baseline entries, or render what it styles.');
    process.exit(1);
  }
  console.log(`${GREEN}✓${NC} no new dead CSS. ${base.length} known finding(s) still baselined.`);
}

main();
