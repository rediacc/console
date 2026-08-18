#!/usr/bin/env tsx
/**
 * Every in-page fragment link must land on something, on every page, in every locale.
 *
 * WHAT IS BROKEN TODAY, MEASURED ON A REAL BUILD. 1,090 of 1,829 built pages carry at
 * least one dead in-page link, and 7,467 of 21,542 fragment links resolve to no element
 * (34.7%). Every locale is affected, English included. `en/docs/cli-application/index.html`
 * emits `href="#set"` SEVEN times from one table of contents, which is dead AND ambiguous
 * at once.
 *
 * THE ROOT CAUSE IS TWO SLUG ALGORITHMS OVER ONE HEADING. Ids come from Astro's default
 * `rehypeHeadingIds` (github-slugger: Unicode-preserving, deduplicating), because
 * `astro.config.mjs` declares no `rehypePlugins`. Hrefs come from `stringToSlug` in
 * `packages/www/src/utils/slug.ts`, whose `[^\w\s-]` character class carries NO `u` flag,
 * so it strips every non-ASCII letter. Non-English headings therefore slug to nothing
 * usable, and English headings containing `&`, `/` or `+` slug to a doubled hyphen. On top
 * of that, one algorithm numbers repeated headings and the other does not.
 *
 * WHY A STATIC PARSE OF BUILT HTML, AND NOT A BROWSER. The property is decidable from the
 * document: a fragment link is dead if no element on the same page carries that id. A
 * browser would add a page load per route (1,829 of them) and could only ever check the
 * routes it was pointed at. The build output is the whole site, so this reads all of it.
 *
 * THE LOCALE SET COMES FROM `@rediacc/locales`, NEVER FROM A DIRECTORY LISTING. That rule
 * is not stylistic. This repo shipped a 379-key blind spot in exactly the shape a
 * hand-rolled locale list produces: the instrument walked what happened to be on disk, so
 * a locale nobody had built was a locale nobody checked, and the output looked identical
 * to a clean run. Here that means BOTH directions are hard errors -- a build missing a
 * modelled locale, and a locale-shaped directory in the build that is not a site locale.
 *
 * Usage:
 *   tsx scripts/check-anchor-integrity.ts [--dist <dir>] [--selftest] [--max-report N]
 */
import fs, { readdirSync, statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { isSiteLocale, SITE_LOCALES } from '@rediacc/locales';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_DIST = 'packages/www/dist';

/**
 * A built site has well over a thousand pages. Anything below this is a broken or partial
 * build, and "no dead anchors in 3 pages" must never print the same checkmark as "no dead
 * anchors in 1,829 pages".
 */
const MIN_PAGES = 200;

/**
 * Fragments the page itself does not own but the browser does, or that are placeholders.
 * `#` alone is a no-op link and is excluded by the non-empty rule, not by this list.
 */
const WELL_KNOWN_FRAGMENTS = new Set(['top']);

export interface DeadAnchor {
  page: string;
  fragment: string;
  kind: 'dead' | 'duplicate-toc';
  count?: number;
}

interface PageScan {
  dead: DeadAnchor[];
  links: number;
}

/** Attribute soup, parsed once per tag. Astro emits `href` before `class` on TOC links and
 *  the other way round elsewhere, so anything that assumes an order silently misses half
 *  the tags -- the first draft of this gate did exactly that and reported ZERO duplicate
 *  TOC fragments on a page that has seven `#set` links. */
function attrs(tag: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of tag.matchAll(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')/g)) {
    out[m[1].toLowerCase()] = m[3] ?? m[4] ?? '';
  }
  return out;
}

/** Percent-decoding must not throw on a malformed sequence; a bad escape is a dead link,
 *  not a crashed gate. */
function decode(fragment: string): string {
  try {
    return decodeURIComponent(fragment);
  } catch {
    return fragment;
  }
}

export function scanPage(html: string, page: string): PageScan {
  const ids = new Set<string>();
  for (const m of html.matchAll(/\bid\s*=\s*("([^"]*)"|'([^']*)')/g)) {
    const id = m[2] ?? m[3] ?? '';
    if (id) {
      ids.add(id);
      ids.add(decode(id));
    }
  }

  const dead: DeadAnchor[] = [];
  const tocFragments = new Map<string, number>();
  let links = 0;

  for (const m of html.matchAll(/<a\b[^>]*>/g)) {
    const a = attrs(m[0]);
    const href = a.href ?? '';
    if (!href.startsWith('#')) continue;
    const raw = href.slice(1);
    if (raw === '') continue; // `href="#"` is a deliberate no-op, not a broken target
    links++;

    const fragment = decode(raw);
    if (!ids.has(raw) && !ids.has(fragment) && !WELL_KNOWN_FRAGMENTS.has(fragment)) {
      dead.push({ page, fragment: raw, kind: 'dead' });
    }
    if ((a.class ?? '').split(/\s+/).includes('toc-link')) {
      tocFragments.set(raw, (tocFragments.get(raw) ?? 0) + 1);
    }
  }

  for (const [fragment, count] of tocFragments) {
    if (count > 1) dead.push({ page, fragment, kind: 'duplicate-toc', count });
  }
  return { dead, links };
}

function htmlFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    // The asset trees hold no documents and are enormous (dist is 7.1 GB, almost all of
    // it copied video). Skipping them by NAME rather than by extension keeps the walk off
    // 6.9 GB of media that could never contain an anchor.
    if (entry.isDirectory()) {
      if (['assets', 'fonts', 'img', 'scripts', 'styles', '_astro'].includes(entry.name)) continue;
      htmlFiles(abs, out);
    } else if (entry.name.endsWith('.html')) out.push(abs);
  }
  return out;
}

/**
 * Both directions of the locale-set check, against `@rediacc/locales`.
 *
 * A directory is judged to be locale-shaped by its NAME (`xx` or `xx-YY`), never by
 * whether it happens to be in the site-locale list -- otherwise an unknown locale would be
 * indistinguishable from `img/`, and the plant this exists to catch would pass.
 */
/**
 * A dist older than the sources it describes answers YESTERDAY'S question.
 *
 * This fired for real: a local run reported "6452 dead in-page link(s)" with full
 * confidence against a dist built 25 hours earlier, minutes after the fix that
 * removed every one of them had landed. In CI the manifest entry declares
 * `needs: ['build:www']` so the build is always fresh, which is exactly why the
 * hazard is invisible there and expensive locally.
 *
 * Deliberately a WARNING, not a failure: a stale dist is a misleading input, not
 * a broken gate, and failing here would block anyone inspecting an old build on
 * purpose. The point is that the number can never again look current when it is not.
 */
export function warnIfDistIsStale(dist: string, sourceRoots: readonly string[]): void {
  let distTime = 0;
  try {
    distTime = statSync(dist).mtimeMs;
  } catch {
    return; // absence is the caller's problem, not staleness
  }
  let newest = 0;
  let newestPath = '';
  for (const root of sourceRoots) {
    const stack: string[] = [root];
    while (stack.length > 0) {
      const current = stack.pop() as string;
      let entries;
      try {
        entries = readdirSync(current, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
        const full = `${current}/${entry.name}`;
        if (entry.isDirectory()) stack.push(full);
        else {
          const m = statSync(full).mtimeMs;
          if (m > newest) {
            newest = m;
            newestPath = full;
          }
        }
      }
    }
  }
  if (newest > distTime) {
    const hours = ((newest - distTime) / 3_600_000).toFixed(1);
    console.warn(
      `\x1b[33mWARNING: ${dist} is ${hours}h OLDER than its newest source ` +
        `(${newestPath}). Every number below describes that stale build, not your tree. ` +
        `Rebuild before trusting this result.\x1b[0m`
    );
  }
}

export function assertLocaleCoverage(dist: string): string[] {
  const dirs = fs
    .readdirSync(dist, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name);
  const localeShaped = dirs.filter((d) => /^[a-z]{2}(-[A-Za-z]{2,4})?$/.test(d));

  const unknown = localeShaped.filter((d) => !isSiteLocale(d));
  if (unknown.length > 0) {
    throw new Error(
      `The build output holds ${unknown.length} locale-shaped director(y/ies) that are not ` +
        `site locales: ${unknown.join(', ')}.\n` +
        `Site locales come from @rediacc/locales: ${SITE_LOCALES.join(', ')}.\n` +
        `Either declare the locale in packages/locales/index.js, or stop building it. A ` +
        `locale nobody declared is a locale no other gate is checking either.`
    );
  }
  const missing = SITE_LOCALES.filter((l) => !dirs.includes(l));
  if (missing.length > 0) {
    throw new Error(
      `The build output is missing ${missing.length} declared site locale(s): ${missing.join(', ')}.\n` +
        `Their pages would be scanned zero times, and zero dead anchors in a locale that ` +
        `was never built reads exactly like a clean locale.`
    );
  }
  return localeShaped;
}

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  // ---- PLANT 1: an `&` heading. github-slugger keeps one hyphen, stringToSlug leaves a
  // doubled one, so the href misses the id by a single character.
  const AMP = `<h2 id="backup-restore">Backup &amp; Restore</h2>
    <a href="#backup--restore" class="sidebar-link toc-link">Backup &amp; Restore</a>`;
  const amp = scanPage(AMP, 'amp.html');
  check(
    'an `&` heading whose href doubles the hyphen is reported',
    amp.dead.length === 1 && amp.dead[0].fragment === 'backup--restore',
    JSON.stringify(amp.dead)
  );

  // ---- PLANT 2: a duplicate heading. One slugger numbers the repeat, the other does not,
  // so the TOC points at the same fragment several times: dead for all but the first, and
  // ambiguous even where it resolves.
  const DUP = `<h3 id="set">set</h3><h3 id="set-1">set</h3>
    <a href="#set" class="sidebar-link toc-link">set</a>
    <a href="#set" class="sidebar-link toc-link">set</a>`;
  const dup = scanPage(DUP, 'dup.html');
  check(
    'two TOC links sharing one fragment are reported',
    dup.dead.some((d) => d.kind === 'duplicate-toc' && d.fragment === 'set' && d.count === 2),
    JSON.stringify(dup.dead)
  );

  // The attribute order must not matter. Astro emits `href` first on TOC links and `class`
  // first elsewhere; a regex that assumed one order reported ZERO duplicates on a page
  // carrying seven identical `#set` links, which is how this control came to exist.
  const DUP_REORDERED = `<h3 id="set">set</h3>
    <a class="sidebar-link toc-link" href="#set">set</a>
    <a class="sidebar-link toc-link" href="#set">set</a>`;
  check(
    'duplicate TOC detection is independent of attribute order',
    scanPage(DUP_REORDERED, 'dup2.html').dead.some((d) => d.kind === 'duplicate-toc'),
    JSON.stringify(scanPage(DUP_REORDERED, 'dup2.html').dead)
  );

  // Non-ASCII: the actual mechanism behind the non-English failures. The id is the real
  // Unicode slug, the href is what `[^\w\s-]` left of it.
  const UNICODE = `<h2 id="مقدمة">مقدمة</h2><a href="#" class="x">skip</a><a href="#-">مقدمة</a>`;
  check(
    'a non-ASCII heading whose href was ASCII-stripped is reported',
    scanPage(UNICODE, 'ar.html').dead.some((d) => d.fragment === '-'),
    JSON.stringify(scanPage(UNICODE, 'ar.html').dead)
  );

  // ---- CONTROLS THAT MUST NOT FIRE ------------------------------------------------
  const CLEAN = `<h2 id="overview">Overview</h2>
    <a href="#overview" class="sidebar-link toc-link">Overview</a>
    <a href="#">no-op</a>
    <a href="/en/docs/#elsewhere">another page</a>`;
  const clean = scanPage(CLEAN, 'clean.html');
  check(
    'a page whose fragments all resolve reports nothing (control)',
    clean.dead.length === 0,
    JSON.stringify(clean.dead)
  );
  check('`href="#"` is not counted as a link at all', clean.links === 1, `links=${clean.links}`);

  const ENCODED = `<h2 id="مقدمة">م</h2><a href="#%D9%85%D9%82%D8%AF%D9%85%D8%A9">م</a>`;
  check(
    'a percent-encoded href matching a Unicode id resolves (control)',
    scanPage(ENCODED, 'enc.html').dead.length === 0,
    JSON.stringify(scanPage(ENCODED, 'enc.html').dead)
  );

  const BAD_ESCAPE = `<h2 id="ok">ok</h2><a href="#%E0%A4%A">broken escape</a>`;
  check(
    'a malformed percent-escape is a finding, not a crash',
    scanPage(BAD_ESCAPE, 'bad.html').dead.length === 1
  );

  // ---- PLANTS 3 AND 4: the locale set --------------------------------------------
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'anchor-dist-'));
  for (const l of SITE_LOCALES) fs.mkdirSync(path.join(dist, l), { recursive: true });
  for (const d of ['assets', 'img', 'json']) fs.mkdirSync(path.join(dist, d), { recursive: true });
  const throwsWith = (fn: () => unknown): unknown => {
    try {
      fn();
      return null;
    } catch (e) {
      return e;
    }
  };
  check(
    'a complete build passes the locale-set check (control)',
    throwsWith(() => assertLocaleCoverage(dist)) === null
  );

  fs.mkdirSync(path.join(dist, 'nl'));
  check(
    'PLANT 3: an unknown locale directory in the build output is a hard error',
    throwsWith(() => assertLocaleCoverage(dist)) instanceof Error
  );
  fs.rmSync(path.join(dist, 'nl'), { recursive: true });

  fs.rmSync(path.join(dist, 'ko'), { recursive: true });
  const missing = throwsWith(() => assertLocaleCoverage(dist));
  check(
    'PLANT 4: a modelled locale missing from the build is a hard error',
    missing instanceof Error && missing.message.includes('ko'),
    missing instanceof Error ? missing.message.split('\n')[0] : String(missing)
  );
  fs.mkdirSync(path.join(dist, 'ko'));

  // A non-locale directory must never be mistaken for one, or every build fails.
  fs.mkdirSync(path.join(dist, 'legal-information'));
  check(
    'a non-locale directory is not judged as a locale (control)',
    throwsWith(() => assertLocaleCoverage(dist)) === null
  );

  fs.rmSync(dist, { recursive: true, force: true });
  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const dist = path.resolve(arg('--dist') ?? path.join(REPO_ROOT, DEFAULT_DIST));
  const maxReport = Number(arg('--max-report') ?? 25);

  // REFUSE, never self-skip. check:ci-seo's built-HTML link scan self-skipped on a missing
  // dist and was therefore vacuous on every developer machine for its whole life; this
  // gate declares `needs: ['build:www']` in the manifest instead, so the build is a
  // prerequisite rather than an excuse.
  if (!fs.existsSync(dist)) {
    console.error(
      `✗ Refusing to run: no build output at ${dist}.\n` +
        `  Run \`npm run build:www\` first. A scan over an absent build reports zero dead ` +
        `anchors, which is what a perfect site looks like too.`
    );
    process.exit(1);
  }

  try {
    warnIfDistIsStale(dist, ['packages/www/src', 'packages/www/public']);
    assertLocaleCoverage(dist);
  } catch (e) {
    console.error(`✗ ${(e as Error).message}`);
    process.exit(1);
  }

  const pages = htmlFiles(dist);
  if (pages.length < MIN_PAGES) {
    console.error(
      `✗ Refusing to run: only ${pages.length} HTML page(s) under ${dist}, below the floor ` +
        `of ${MIN_PAGES}.\n  A partial build cannot support a verdict about the whole site.`
    );
    process.exit(1);
  }

  const findings: DeadAnchor[] = [];
  let links = 0;
  for (const file of pages) {
    const res = scanPage(fs.readFileSync(file, 'utf-8'), path.relative(dist, file));
    findings.push(...res.dead);
    links += res.links;
  }

  const deadPages = new Set(findings.filter((f) => f.kind === 'dead').map((f) => f.page));
  const dupPages = new Set(findings.filter((f) => f.kind === 'duplicate-toc').map((f) => f.page));
  const deadLinks = findings.filter((f) => f.kind === 'dead').length;

  if (findings.length === 0) {
    console.log(
      `✓ Every one of ${links} in-page fragment link(s) across ${pages.length} page(s) resolves, ` +
        `and no table of contents repeats a fragment.`
    );
    return;
  }

  console.error(
    `✗ ${deadLinks} dead in-page link(s) on ${deadPages.size} of ${pages.length} page(s) ` +
      `(${((deadPages.size / pages.length) * 100).toFixed(1)}%), out of ${links} fragment link(s).`
  );
  if (dupPages.size > 0) {
    console.error(
      `  ${dupPages.size} page(s) also have a table of contents pointing at one fragment more than once.`
    );
  }
  console.error('');

  const byPage = new Map<string, DeadAnchor[]>();
  for (const f of findings) byPage.set(f.page, [...(byPage.get(f.page) ?? []), f]);
  for (const [page, list] of [...byPage]
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, maxReport)) {
    console.error(`  ${page}  (${list.length})`);
    for (const f of list.slice(0, 5)) {
      console.error(
        f.kind === 'dead'
          ? `    #${f.fragment} resolves to no element on this page`
          : `    #${f.fragment} appears ${f.count} times in the table of contents`
      );
    }
    if (list.length > 5) console.error(`    ... and ${list.length - 5} more`);
  }
  if (byPage.size > maxReport) console.error(`  ... and ${byPage.size - maxReport} more page(s)`);

  console.error(
    '\nHeading ids and TOC hrefs are produced by two different slug algorithms. Fix the\n' +
      'SOURCE of the fragment rather than the symptom: packages/www/src/utils/slug.ts has no\n' +
      '`u` flag, and packages/www/src/utils/sidebar-behavior.ts already captures the correct\n' +
      'id in its regex and then discards it.'
  );
  process.exit(1);
}

main();
