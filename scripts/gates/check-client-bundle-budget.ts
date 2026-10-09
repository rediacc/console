#!/usr/bin/env tsx
/**
 * How much JavaScript the homepage makes a visitor download and parse.
 *
 * THE NUMBER TODAY: 576,294 decoded bytes, 1.15x the budget. Wave 1's locale chunking
 * brought this down from 7,043,755 B, so the header's old "red by a factor of fourteen"
 * is long spent -- but the figure was ALSO wrong in the other direction for as long as
 * this gate has been green. See below.
 *
 * IT WAS UNDER-REPORTING BY 124,673 B, and that is why this comment is rewritten rather
 * than retouched. `importSpecifiers` required whitespace after `import`, which minified
 * side-effect imports do not have, so the walk stopped at a 129-byte facade chunk and
 * never saw the 122,110 B `TutorialVideoPlayer` (plyr) that every homepage visitor in
 * every locale downloads. The gate passed at 451,621 B over a page shipping 576,294 B.
 * Fixed 2026-09-03; see agent/plans/PLAN-www-bundle-determinism.md for the full arithmetic,
 * including how it reconciles to the byte with CI run 33708505104.
 *
 * THE BUDGET IS 500,000 B AND IT IS DELIBERATELY SET WHERE THE FIX LANDS, not where the
 * site is. A budget set just above today's figure would be a gate that ratifies the
 * defect, which is exactly what raising it now would do.
 *
 * IT WALKS THE IMPORT GRAPH, WHICH IS THE ONLY WAY THE FIGURE IS TRUE. The homepage's own
 * HTML references six small scripts totalling about 41 kB and not one byte of React. The
 * 6.7 MB arrives transitively: an `<astro-island component-url="/assets/Navigation.*.js">`
 * imports a chunk, which imports the React chunk. Summing the `<script src>` tags would
 * report 41 kB and pass a 500 kB budget while the page shipped seven megabytes -- a green
 * gate over the exact defect it was written for.
 *
 * EVERY LOCALE IS BUDGETED, not just English. The locale set comes from `@rediacc/locales`,
 * and a homepage missing for a declared locale is a hard error rather than a locale that
 * quietly scores zero.
 *
 * Usage:
 *   tsx scripts/gates/check-client-bundle-budget.ts [--dist <dir>] [--budget <bytes>] [--selftest]
 *
 * ---- gate ----
 * kind: shared-step
 * step: SEO
 * needs: node
 * lane: quality-www-build
 * slow: true
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';
import { printTruncated } from '../lib/findings-report.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const DEFAULT_DIST = 'packages/www/dist';

/**
 * The scorecard target for this program: homepage decoded JavaScript under 500,000 B.
 * Wave 1 (locale chunking) is what brings the figure under it.
 */
const DEFAULT_BUDGET = 500_000;

/**
 * THE DEFERRED CEILING, and why a second number rather than one bigger budget.
 *
 * Measured on the 2026-09-03 build: eager 454,184 B / 29 files, deferred 122,110 B / 1
 * (`TutorialVideoPlayer`, i.e. plyr). That deferred figure then went UNMEASURED: the bundler
 * began emitting dynamic imports with BACKTICKS (import(`./X.<hash>.js`)), which the
 * quote-only matcher below did not read, so every build reported "deferred 0 B" against this
 * ceiling until 2026-10-08. See `importSpecifiers`. Folding the deferred chunk into one 600 kB budget
 * would hide it; dropping it from the report entirely would let it grow without limit
 * behind an `import()`. So it is measured, named, and held to its own line.
 *
 * This split is only honest because the deferral is REAL. Until 2026-09-03 the hydrator
 * mounted on DOMContentLoaded, so every homepage visitor fetched the player whether or
 * not they watched anything -- calling that "deferred" would have been a fudge, and the
 * plan that proposed this split (agent/plans/PLAN-www-bundle-determinism.md section 3a) said
 * so in those words. What earns it: SPSolutionVideo.astro now server-renders a poster
 * and tutorial-video-hydrate.ts builds the player on first CLICK. A visitor who never
 * presses play never pays these bytes.
 *
 * 300,000 B SINCE 2026-10-08, by operator ruling ("Raise ceiling to 300 KB"), when the player
 * moved from Plyr to Video.js 10 (agent/plans/PLAN-plyr-to-videojs.md). Measured on that
 * build: the `TutorialVideoPlayer` chunk is 272,097 B (75,501 B at gzip -9) against plyr's
 * 120,598 B, and the floor is the packaged skin itself -- `VideoSkin` alone bundles to
 * 260,864 B with React external, 272,185 B with its `I18nProvider`; the Neutral and Compat
 * skins land within 1,100 B of it. The provider also brings 53 lazily imported Video.js
 * locale packs (153,471 B in the graph), of which a visitor fetches the ONE for the page's
 * locale: those are charged as their largest member (`te`, 5,193 B, on that build), see
 * `localeAlternatives`. Deferred total as this gate reports it: 277,290 B. Ejecting the skin to shed weight was measured at 2,786 lines plus a
 * Tailwind 4.3 toolchain this site does not have.
 */
const DEFERRED_CEILING = 300_000;

/** A homepage that pulls in less than this is not a lean page, it is an unresolved graph. */
const MIN_BYTES = 5_000;

export interface BundleMeasurement {
  page: string;
  /** The whole reachable closure: eager + deferred. Reported, never budgeted. */
  bytes: number;
  /** What a visitor downloads before interacting. THIS is what the budget applies to. */
  eagerBytes: number;
  /** Behind a dynamic import: fetched only if the visitor asks. Has its own ceiling. */
  deferredBytes: number;
  files: { url: string; bytes: number; deferred: boolean; alternative?: string }[];
  missing: string[];
  /** Dynamic imports whose target is a `${...}` template: unknown bytes, so a refusal. */
  unresolvable: string[];
  /** Locale-alternative maps: what each costs as charged (its largest member) and in total. */
  alternatives: {
    importer: string;
    members: number;
    chargedBytes: number;
    totalBytes: number;
    largest: string;
  }[];
}

/** An import edge, and whether crossing it costs the visitor bytes before they interact. */
interface Edge {
  spec: string;
  /** `import("./x")` -- fetched on demand, so it is not part of the eager cost. */
  dynamic: boolean;
  /** A template-literal specifier with `${...}` in it: its target cannot be known statically. */
  interpolated?: boolean;
}

/** Static and dynamic import specifiers of a built ES module or an inline module script.
 *
 * THE THREE REGEXES ARE DISJOINT, which is what makes the eager/deferred tag trustworthy:
 * `import(` cannot match the bare-specifier form (a paren is not a quote) and cannot match
 * `from` (no `from` keyword), so no edge is ever classified twice or missed by the split.
 */
function importSpecifiers(source: string): Edge[] {
  const out: Edge[] = [];
  for (const m of source.matchAll(/\bfrom\s*["']([^"']+)["']/g))
    out.push({ spec: m[1], dynamic: false });
  // BACKTICKS TOO, and their absence was worth every deferred byte on the page. The bundler emits dynamic imports as template literals -- import(`./TutorialVideoPlayer.<hash>.js`) -- and this matcher once accepted only `"` and `'`, so phase 2 below never started and "deferred" printed 0 B on every build, the plyr one included, against a ceiling that was therefore never consulted.
  // A template with `${...}` in it names no file; it is returned as `interpolated` so the caller can refuse it rather than score it zero.
  for (const m of source.matchAll(/\bimport\s*\(\s*(["'`])([^"'`]+)\1/g))
    out.push({ spec: m[2], dynamic: true, interpolated: m[1] === '`' && m[2].includes('${') });
  // `\s*`, NOT `\s+`, and the difference was worth 124,673 B. Rollup emits bare side-effect imports with no whitespace at all -- `import"./x.js";import"./y.js";` -- and `\s+` matched none of them. The homepage's script entry is a 129-BYTE FACADE whose only three edges are all of that form, so this walk dead-ended there and the gate reported 451,621 B while the page shipped 576,294
  // B. Note the two lines above already use `\s*`; only this one demanded a space.
  for (const m of source.matchAll(/\bimport\s*["']([^"']+)["']/g))
    out.push({ spec: m[1], dynamic: false });
  return out;
}

const LANGUAGE_NAMES = new Intl.DisplayNames(['en'], { type: 'language', fallback: 'none' });

/** True when `key` is a language tag ICU knows by name: `de`, `pt-br`, `zh-tw`; not `open`. */
export function isLanguageTag(key: string): boolean {
  try {
    return LANGUAGE_NAMES.of(key) !== undefined;
  } catch {
    return false;
  }
}

/**
 * The dynamic imports in `source` that are KEYED ALTERNATIVES: entries of one object literal
 * whose every key is a language tag and whose every value is `() => ... import(<chunk>)`.
 * Returns each such map as a list of specifiers; a map of fewer than two is not one.
 *
 * WHY THESE ARE CHARGED AS THEIR LARGEST MEMBER, NOT THEIR SUM. Video.js's `I18nProvider`
 * ships a pack per locale as exactly this shape (`{ar:()=>l(()=>import(`./ar.<hash>.js`)),
 * ...}`) and loads the ONE for the locale it is given, which is the page's. A visitor on
 * /de/ fetches de.js and nothing else; summing all 53 packs would charge every visitor
 * 153,471 B for a choice of which they make exactly one. The largest member is the honest
 * upper bound on what that one choice costs.
 *
 * WHY THE KEYS MUST ALL BE LANGUAGE TAGS. A keyed map of lazy routes (`{ open: () => import
 * ('./dialog.js'), help: () => import('./help.js') }`) has the same syntax and its members
 * are NOT exclusive: one visitor can open both. Undercounting is the costly direction for a
 * budget, so anything not recognisably a per-locale choice is charged in full; an ICU build
 * that does not know a key charges that map in full, which fails loud rather than flattering.
 */
export function localeAlternatives(source: string): string[][] {
  const groups: string[][] = [];
  let run: { keys: string[]; specs: string[] } = { keys: [], specs: [] };
  let lastEnd = -1;
  const close = () => {
    if (run.specs.length >= 2 && run.keys.every(isLanguageTag)) groups.push(run.specs);
    run = { keys: [], specs: [] };
  };
  const ENTRY =
    /(?<=[{,])\s*([\w$]+|"[^"\\]*"|'[^'\\]*')\s*:\s*\(\s*\)\s*=>[^,;{}]*?\bimport\s*\(\s*(["'`])([^"'`$]+)\2/g;
  for (const m of source.matchAll(ENTRY)) {
    const start = m.index ?? 0;
    // Two entries belong to ONE literal only when nothing between them could end it or start a statement: the tail of the previous value (`),[])` or `),__vite__mapDeps([0,1]))`) and a comma, never a brace, a semicolon, a colon or an assignment.
    if (lastEnd >= 0 && !/^[^{};:=]*$/.test(source.slice(lastEnd, start))) close();
    run.keys.push(m[1].replace(/^["']|["']$/g, '').toLowerCase());
    run.specs.push(m[3]);
    lastEnd = start + m[0].length;
  }
  close();
  return groups;
}

/** Resolve a specifier seen inside `fromUrl` to a site-absolute URL, or null if external. */
function resolveSpecifier(spec: string, fromUrl: string): string | null {
  if (spec.startsWith('/')) return spec;
  if (spec.startsWith('./') || spec.startsWith('../')) {
    return `/${path.posix.normalize(path.posix.join(path.posix.dirname(fromUrl.slice(1)), spec))}`;
  }
  // A bare specifier or an absolute URL: not served from this build.
  return null;
}

export function measurePage(dist: string, pageRel: string): BundleMeasurement {
  const html = fs.readFileSync(path.join(dist, pageRel), 'utf-8');
  const entries = new Set<string>();

  // THREE ENTRY SHAPES, and the last two are where the weight is.
  //   `src="..."`            classic scripts
  //   `component-url="..."`  the island's component chunk
  //   `renderer-url="..."`   the client renderer (React) the island boots with
  for (const m of html.matchAll(/(?:src|component-url|renderer-url)\s*=\s*"([^"]+\.m?js)"/g)) {
    if (m[1].startsWith('/')) entries.add(m[1]);
  }
  // Inline module scripts import their chunks by URL. An inline `import()` is a deferred
  // entry, not an eager one -- the same distinction the two-phase walk below makes.
  const deferredEntries = new Set<string>();
  for (const m of html.matchAll(/<script[^>]*type="module"[^>]*>([\s\S]*?)<\/script>/g)) {
    for (const e of importSpecifiers(m[1])) {
      if (!e.spec.startsWith('/')) continue;
      (e.dynamic ? deferredEntries : entries).add(e.spec);
    }
  }

  const missing: string[] = [];
  const unresolvable: string[] = [];
  const files: BundleMeasurement['files'] = [];

  // TWO PHASES, AND THE ORDER IS THE WHOLE POINT.
  //
  // Phase 1 walks ONLY static edges, so it reaches exactly what a visitor downloads
  // before touching anything. Phase 2 starts from the dynamic-import targets phase 1
  // collected and walks everything.
  //
  // Running eager first is what makes a chunk reachable BY BOTH ROUTES count as eager,
  // which is the conservative answer and the only honest one: a page that also imports a
  // chunk statically pays for it whether or not some other site pulls it dynamically. The
  // reverse order would let any dynamic edge anywhere launder a chunk out of the budget,
  // and this gate has already been fooled once by a measurement that flattered the page.
  //
  // A THIRD PHASE runs last for the same reason: a locale-alternative member is charged as
  // one of a choice only when NEITHER earlier phase reached it by an ordinary edge.
  const seen = new Set<string>();
  const dynamicTargets = new Set<string>(deferredEntries);
  /** group id -> member URLs, collected while phases 1 and 2 read their importers. */
  const groups = new Map<string, { importer: string; members: string[] }>();

  /** Every edge out of `url`, each tagged with the alternatives group it belongs to, if any. */
  const edgesOf = (url: string, source: string) => {
    const memberOf = new Map<string, string>();
    localeAlternatives(source).forEach((specs, i) => {
      const id = `${url}#${i}`;
      const members: string[] = [];
      for (const spec of specs) {
        const resolved = resolveSpecifier(spec, url);
        if (!resolved) continue;
        memberOf.set(resolved, id);
        members.push(resolved);
      }
      groups.set(id, { importer: url, members });
    });
    const out: { url: string; dynamic: boolean; group?: string }[] = [];
    for (const e of importSpecifiers(source)) {
      if (e.interpolated) {
        unresolvable.push(`${url}: import(\`${e.spec}\`)`);
        continue;
      }
      const resolved = resolveSpecifier(e.spec, url);
      if (!resolved) continue;
      out.push({
        url: resolved,
        dynamic: e.dynamic,
        group: e.dynamic ? memberOf.get(resolved) : undefined,
      });
    }
    return out;
  };

  const walk = (roots: Iterable<string>, deferred: boolean, collectDynamic: boolean) => {
    const stack = [...roots];
    while (stack.length > 0) {
      const url = stack.pop()!;
      if (seen.has(url)) continue;
      seen.add(url);
      const abs = path.join(dist, url.replace(/^\//, ''));
      if (!fs.existsSync(abs)) {
        missing.push(url);
        continue;
      }
      files.push({ url, bytes: fs.statSync(abs).size, deferred });
      for (const e of edgesOf(url, fs.readFileSync(abs, 'utf-8'))) {
        // An alternatives member is left for phase 3 from either phase; its group recorded it.
        if (e.group) continue;
        if (e.dynamic) {
          if (collectDynamic) dynamicTargets.add(e.url);
          else stack.push(e.url);
        } else {
          stack.push(e.url);
        }
      }
    }
  };

  walk(entries, false, true);
  // Anything phase 1 already claimed is eager and stays eager: `seen` is not reset.
  walk(dynamicTargets, true, false);

  // PHASE 3: each locale-alternative group, charged as its LARGEST member's closure. A
  // member's closure is every file it reaches by ANY edge that no earlier phase claimed, so
  // a pack importing a shared base (pt -> pt-br) is charged with that base included.
  const alternatives: BundleMeasurement['alternatives'] = [];
  for (const [id, g] of groups) {
    const closures = g.members.map((member) => {
      const local = new Map<string, number>();
      const stack = [member];
      while (stack.length > 0) {
        const url = stack.pop()!;
        if (seen.has(url) || local.has(url)) continue;
        const abs = path.join(dist, url.replace(/^\//, ''));
        if (!fs.existsSync(abs)) {
          if (!missing.includes(url)) missing.push(url);
          local.set(url, 0);
          continue;
        }
        local.set(url, fs.statSync(abs).size);
        for (const e of edgesOf(url, fs.readFileSync(abs, 'utf-8'))) stack.push(e.url);
      }
      return { member, local, bytes: [...local.values()].reduce((a, b) => a + b, 0) };
    });
    const union = new Map<string, number>();
    for (const c of closures) for (const [u, b] of c.local) union.set(u, b);
    if (union.size === 0) continue;
    for (const [url, bytes] of union) {
      seen.add(url);
      if (bytes > 0) files.push({ url, bytes, deferred: true, alternative: id });
    }
    const largest = closures.reduce((a, b) => (b.bytes > a.bytes ? b : a));
    alternatives.push({
      importer: g.importer,
      members: g.members.length,
      chargedBytes: largest.bytes,
      totalBytes: [...union.values()].reduce((a, b) => a + b, 0),
      largest: largest.member,
    });
  }

  const sum = (want: boolean) =>
    files.reduce((a, f) => a + (f.deferred === want && !f.alternative ? f.bytes : 0), 0);

  return {
    page: pageRel,
    bytes: files.reduce((a, f) => a + f.bytes, 0),
    eagerBytes: sum(false),
    deferredBytes: sum(true) + alternatives.reduce((a, g) => a + g.chargedBytes, 0),
    files: files.sort((a, b) => b.bytes - a.bytes),
    missing,
    unresolvable,
    alternatives,
  };
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

  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'bundle-budget-'));
  fs.mkdirSync(path.join(dist, 'assets'), { recursive: true });
  fs.mkdirSync(path.join(dist, 'en'), { recursive: true });

  const write = (rel: string, body: string) => fs.writeFileSync(path.join(dist, rel), body);
  // A leaf chunk that is ONLY reachable transitively, and is by far the largest thing on
  // the page. This is the fixture's whole point: it stands in for react.*.js, which no
  // <script src> on the real homepage names.
  write('assets/heavy.js', `export const x = "${'x'.repeat(50_000)}";`);
  write(
    'assets/mid.js',
    'import { x } from "./heavy.js";\nimport "./dual.js";\nexport const y = x;'
  );
  // REACHABLE BY BOTH ROUTES: statically from mid.js, dynamically from facade-dyn.js.
  // It must be counted EAGER. See the laundering control below.
  write('assets/dual.js', `export const d = "${'d'.repeat(10_000)}";`);
  write('assets/island.js', 'import { y } from "./mid.js";\nexport default () => y;');
  write('assets/client.js', 'export const boot = 1;');
  // THE FACADE, and it is the shape that hid 124,673 B for as long as this gate was
  // green. Rollup emits an entry like this for an Astro page script: no whitespace, no
  // `from`, nothing but side-effect edges. The real one is 129 bytes. If the walk cannot
  // cross it, everything behind it is invisible and the gate reports a fraction of the
  // page while printing a checkmark.
  // Everything past this facade must be reachable ONLY through its no-space edges.
  // The first draft of these plants pointed at `mid.js`, which the island chain above
  // already reaches, and at a dynamic import the `import(` regex catches on its own --
  // so both passed against the very defect they were written for, and the mutant control
  // in .ci/rediacc_ci/tests/gates/test_gate_client_bundle_budget.py is what caught that.
  write('assets/facade.js', 'import"./facade-only.js";import"./facade-dyn.js";');
  write('assets/facade-only.js', `export const q = "${'q'.repeat(30_000)}";`);
  write('assets/facade-deferred.js', `export const z = "${'z'.repeat(20_000)}";`);
  write('assets/facade-dyn.js', 'import("./facade-deferred.js");import("./dual.js");');
  fs.mkdirSync(path.join(dist, 'scripts'), { recursive: true });
  write('scripts/small.js', 'console.log(1);');
  write(
    'en/index.html',
    `<html><body>
      <script src="/scripts/small.js"></script>
      <astro-island component-url="/assets/island.js" renderer-url="/assets/client.js"></astro-island>
      <script type="module">import "/assets/client.js";</script>
      <script src="/assets/facade.js"></script>
    </body></html>`
  );

  const m = measurePage(dist, 'en/index.html');
  const heavy = m.files.find((f) => f.url === '/assets/heavy.js');
  // Both plants assert on a chunk BEHIND a no-space facade. They fail on the pre-2026-09-03
  // gate, whose regex demanded whitespace after `import`, and that failure is the whole
  // reason the defect existed: the old fixture only ever wrote `import { x } from "..."`.
  check(
    'PLANT: a no-space side-effect facade (import"./x.js") is crossed, not dead-ended',
    m.files.some((f) => f.url === '/assets/facade-only.js'),
    `reached: ${m.files.map((f) => f.url).join(', ')}`
  );
  check(
    'PLANT: a dynamic import reachable ONLY through such a facade is followed',
    m.files.some((f) => f.url === '/assets/facade-deferred.js'),
    `reached: ${m.files.map((f) => f.url).join(', ')}`
  );
  const tagged = (u: string) => m.files.find((f) => f.url === u);
  check(
    'PLANT: a chunk behind import() is tagged DEFERRED, not eager',
    tagged('/assets/facade-deferred.js')?.deferred === true,
    JSON.stringify(tagged('/assets/facade-deferred.js'))
  );
  check(
    'PLANT: the eager total EXCLUDES it -- this is the discriminating assertion',
    m.eagerBytes < m.bytes && m.eagerBytes + m.deferredBytes === m.bytes,
    `eager=${m.eagerBytes} deferred=${m.deferredBytes} total=${m.bytes}`
  );
  // THE LAUNDERING CONTROL. Without phase ordering, any dynamic edge anywhere would move
  // a chunk out of the eager budget even when the page also imports it statically. That
  // would let the budget be defeated by adding an import() nobody calls, so it is proven
  // on a fixture rather than argued.
  check(
    'CONTROL: a chunk reachable BOTH statically and dynamically counts as EAGER',
    tagged('/assets/dual.js')?.deferred === false,
    JSON.stringify(tagged('/assets/dual.js'))
  );
  check(
    'PLANT: a chunk reachable ONLY through two levels of import is counted',
    Boolean(heavy),
    JSON.stringify(m.files.map((f) => f.url))
  );
  check(
    'the total is the sum of the whole graph, not of the <script src> tags',
    m.bytes > 50_000,
    String(m.bytes)
  );
  check(
    'an island component-url is an entry point',
    m.files.some((f) => f.url === '/assets/island.js')
  );
  check(
    'a renderer-url is an entry point',
    m.files.some((f) => f.url === '/assets/client.js')
  );
  check(
    'a classic script tag is an entry point',
    m.files.some((f) => f.url === '/scripts/small.js')
  );
  check('nothing is double counted', new Set(m.files.map((f) => f.url)).size === m.files.length);
  check('nothing resolved is reported missing', m.missing.length === 0, JSON.stringify(m.missing));

  // The measured figure must sit strictly between the two budgets the real gate could be
  // given, so the `bytes > budget` comparison in main() has a true and a false case on
  // this very fixture rather than only on the repo's build.
  check(
    'the fixture measures ABOVE a tight budget (the fire case)',
    m.bytes > 40_000,
    String(m.bytes)
  );
  check(
    'the fixture measures BELOW a loose budget (the pass case)',
    m.bytes < 10_000_000,
    String(m.bytes)
  );

  // An external script must not be counted or reported as missing.
  write(
    'en/external.html',
    '<html><body><script src="https://plausible.example.com/js/p.js"></script></body></html>'
  );
  const ext = measurePage(dist, 'en/external.html');
  check(
    'a third-party script is neither counted nor reported missing (control)',
    ext.bytes === 0 && ext.missing.length === 0,
    JSON.stringify(ext)
  );

  // A referenced chunk that does not exist must be LOUD, not silently zero.
  write('en/broken.html', '<html><body><script src="/assets/gone.js"></script></body></html>');
  check(
    'a referenced chunk that is absent is reported, not counted as zero',
    measurePage(dist, 'en/broken.html').missing.includes('/assets/gone.js')
  );

  // BACKTICK DYNAMIC IMPORTS AND LOCALE ALTERNATIVES. Every edge out of loc-entry.js into the deferred graph is a template literal, which is what the real bundler emits; under the quote-only matcher this page measured 0 B deferred, exactly as every real build did.
  const size = (rel: string) => fs.statSync(path.join(dist, rel)).size;
  write('assets/loc-entry.js', 'import"./fr.js";const go=()=>import(`./loc-player.js`);');
  write(
    'assets/loc-player.js',
    'var me={de:()=>l(()=>import(`./de.js`),[]),fr:()=>l(()=>import(`./fr.js`),[]),' +
      '"pt-br":()=>l(()=>import(`./pt-br.js`),[]),pt:()=>l(()=>import(`./pt.js`),__vite__mapDeps([0,1]))};' +
      'var routes={open:()=>import(`./dialog.js`),help:()=>import(`./help.js`)};' +
      'var mixed={de:()=>import(`./mixed-a.js`),open:()=>import(`./mixed-b.js`)};'
  );
  write('assets/de.js', `export default "${'d'.repeat(4_000)}";`);
  write('assets/fr.js', `export default "${'f'.repeat(3_000)}";`);
  write('assets/pt-br.js', `export default "${'b'.repeat(2_000)}";`);
  // pt is the LARGEST CLOSURE (3,000 + pt-br's 2,000) but not the largest FILE (de), so a
  // charge of de's size would mean the member's own imports were never followed.
  write('assets/pt.js', `import b from "./pt-br.js";export default b+"${'p'.repeat(3_000)}";`);
  write('assets/dialog.js', `export default "${'o'.repeat(5_000)}";`);
  write('assets/help.js', `export default "${'h'.repeat(6_000)}";`);
  write('assets/mixed-a.js', `export default "${'a'.repeat(700)}";`);
  write('assets/mixed-b.js', `export default "${'m'.repeat(800)}";`);
  write('en/locale.html', '<html><body><script src="/assets/loc-entry.js"></script></body></html>');
  const loc = measurePage(dist, 'en/locale.html');
  const locTag = (u: string) => loc.files.find((f) => f.url === u);
  check(
    'PLANT: a backtick dynamic import (import(`./x.js`)) is followed and tagged DEFERRED',
    locTag('/assets/loc-player.js')?.deferred === true,
    JSON.stringify(loc.files.map((f) => f.url))
  );
  // A placeholder when no group was found, so the checks below report FAIL rather than throw.
  const g = loc.alternatives[0] ?? {
    importer: '',
    members: 0,
    chargedBytes: -1,
    totalBytes: -1,
    largest: '',
  };
  const ptClosure = size('assets/pt.js') + size('assets/pt-br.js');
  check(
    'PLANT: a locale-keyed import map is ONE choice, charged as its largest member closure',
    loc.alternatives.length === 1 &&
      g.members === 4 &&
      g.largest === '/assets/pt.js' &&
      g.chargedBytes === ptClosure,
    JSON.stringify(loc.alternatives)
  );
  check(
    'CONTROL: a member the page ALSO imports statically stays EAGER and outside the choice',
    locTag('/assets/fr.js')?.deferred === false && !locTag('/assets/fr.js')?.alternative,
    JSON.stringify(locTag('/assets/fr.js'))
  );
  const fullyCharged =
    size('assets/loc-player.js') +
    size('assets/dialog.js') +
    size('assets/help.js') +
    size('assets/mixed-a.js') +
    size('assets/mixed-b.js');
  check(
    'CONTROL: a keyed map whose keys are not ALL language tags is charged in FULL, member by member',
    loc.deferredBytes === fullyCharged + ptClosure,
    `deferred=${loc.deferredBytes} expected=${fullyCharged + ptClosure}`
  );
  check(
    'the reachable closure still counts every pack, charged or not',
    loc.bytes === loc.eagerBytes + fullyCharged + g.totalBytes &&
      g.totalBytes === size('assets/de.js') + ptClosure,
    `bytes=${loc.bytes} eager=${loc.eagerBytes} total=${g.totalBytes}`
  );
  check(
    'isLanguageTag knows a region tag and refuses a route name',
    isLanguageTag('zh-tw') &&
      isLanguageTag('pt-br') &&
      !isLanguageTag('open') &&
      !isLanguageTag('app')
  );
  write('assets/interp.js', 'const f=(n)=>import(`./packs/${n}.js`);');
  write('en/interp.html', '<html><body><script src="/assets/interp.js"></script></body></html>');
  check(
    'an interpolated dynamic import is reported as UNRESOLVABLE, not scored zero',
    measurePage(dist, 'en/interp.html').unresolvable.length === 1
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
  const budget = Number(arg('--budget') ?? DEFAULT_BUDGET);

  if (!fs.existsSync(dist)) {
    console.error(
      `✗ Refusing to run: no build output at ${dist}. Run \`npm run build:www\` first.\n` +
        `  An absent build weighs nothing, which is not the same as a light page.`
    );
    process.exit(1);
  }

  // The locale universe is @rediacc/locales. A homepage missing for a declared locale is a hard error: scoring zero for a locale nobody built reads exactly like scoring well.
  const pages = SITE_LOCALES.map((l) => ({
    locale: l,
    rel: path.join(l, 'index.html'),
  }));
  const absent = pages.filter((p) => !fs.existsSync(path.join(dist, p.rel)));
  if (absent.length > 0) {
    console.error(
      `✗ Refusing to run: ${absent.length} declared locale(s) have no homepage in the build: ` +
        `${absent.map((a) => a.locale).join(', ')}.`
    );
    process.exit(1);
  }

  const measured = pages.map((p) => ({
    locale: p.locale,
    ...measurePage(dist, p.rel),
  }));

  const starved = measured.filter((m) => m.eagerBytes < MIN_BYTES);
  if (starved.length > 0) {
    console.error(
      `✗ Refusing to run: ${starved.length} homepage(s) resolved to under ${MIN_BYTES} bytes of ` +
        `JavaScript (${starved.map((s) => `${s.locale}=${s.eagerBytes}`).join(', ')}).\n` +
        `  The import graph did not resolve; a near-zero figure is a broken measurement, not ` +
        `a lean page.`
    );
    process.exit(1);
  }

  const missing = measured.flatMap((m) => m.missing.map((u) => `${m.locale}: ${u}`));
  // A dynamic import whose target is a `${...}` template has unknown bytes, and unknown is not light.
  const unresolvable = [...new Set(measured.flatMap((m) => m.unresolvable))];
  if (unresolvable.length > 0) {
    console.error(
      `✗ ${unresolvable.length} dynamic import(s) name no file (a \`\${...}\` template), so their bytes are UNKNOWN:`
    );
    printTruncated(unresolvable, { limit: 10 });
    console.error(
      '\n  Unknown is not zero. Give the import a literal specifier per target, or teach this gate the shape.'
    );
    process.exit(1);
  }
  const over = measured.filter((m) => m.eagerBytes > budget);
  const overDeferred = measured.filter((m) => m.deferredBytes > DEFERRED_CEILING);

  if (over.length === 0 && overDeferred.length === 0 && missing.length === 0) {
    const worst = measured.reduce((a, b) => (a.eagerBytes > b.eagerBytes ? a : b));
    const worstDef = measured.reduce((a, b) => (a.deferredBytes > b.deferredBytes ? a : b));
    console.log(
      `✓ Every locale homepage is within the ${budget.toLocaleString()} B eager budget ` +
        `(worst: ${worst.locale} at ${worst.eagerBytes.toLocaleString()} B across ` +
        `${worst.files.filter((f) => !f.deferred).length} file(s)).`
    );
    const defFiles = worstDef.files.filter((f) => f.deferred && !f.alternative);
    console.log(
      `✓ Deferred (behind an import(), fetched only on interaction): worst is ` +
        `${worstDef.locale} at ${worstDef.deferredBytes.toLocaleString()} B ` +
        `(${defFiles.length} file(s), largest ${defFiles[0]?.url ?? 'none'}), ceiling ` +
        `${DEFERRED_CEILING.toLocaleString()} B. Full closure ` +
        `${worstDef.bytes.toLocaleString()} B -- reported, not budgeted.`
    );
    for (const a of worstDef.alternatives)
      console.log(
        `  Locale alternatives in ${a.importer}: ${a.members} pack(s), ${a.totalBytes.toLocaleString()} B ` +
          `in the graph, charged ${a.chargedBytes.toLocaleString()} B (the largest, ${a.largest}): ` +
          `a visitor loads the one for the page's locale.`
      );
    console.log(
      `  Blind spot: this counts what the graph makes REACHABLE. It cannot see whether a ` +
        `deferred chunk is in practice fetched by every visitor anyway; that is a property ` +
        `of the hydration trigger, which scripts/gates/check-player-css-scope.ts pins separately.`
    );
    return;
  }

  if (missing.length > 0) {
    console.error(`✗ ${missing.length} referenced chunk(s) do not exist in the build:`);
    printTruncated(missing, { limit: 10 });
    console.error('');
  }

  if (overDeferred.length > 0) {
    console.error(
      `✗ ${overDeferred.length} of ${measured.length} locale homepage(s) exceed the ` +
        `${DEFERRED_CEILING.toLocaleString()} B DEFERRED ceiling:\n`
    );
    for (const m of overDeferred.sort((a, b) => b.deferredBytes - a.deferredBytes)) {
      const chunks = m.files.filter((f) => f.deferred && !f.alternative);
      console.error(
        `  /${m.locale}/  ${m.deferredBytes.toLocaleString()} B = ${chunks.length} chunk(s)` +
          m.alternatives
            .map(
              (a) =>
                ` + ${a.chargedBytes.toLocaleString()} B (the largest of ${a.members} locale packs)`
            )
            .join('')
      );
      printTruncated(chunks, {
        limit: 5,
        indent: '      ',
        format: (f) => `${f.bytes.toLocaleString()} B  ${f.url}`,
      });
    }
    console.error(
      `\n  Deferred is not free -- it is paid by whoever interacts. This ceiling exists so\n` +
        `  moving weight behind an import() is a decision with a limit, not an escape hatch.\n`
    );
  }

  if (over.length > 0) {
    console.error(
      `✗ ${over.length} of ${measured.length} locale homepage(s) exceed the ` +
        `${budget.toLocaleString()} B EAGER decoded-JavaScript budget:\n`
    );
    for (const m of over.sort((a, b) => b.eagerBytes - a.eagerBytes)) {
      console.error(
        `  /${m.locale}/  ${m.eagerBytes.toLocaleString()} B eager  ` +
          `(${(m.eagerBytes / budget).toFixed(1)}x budget, ` +
          `${m.files.filter((f) => !f.deferred).length} file(s); ` +
          `+${m.deferredBytes.toLocaleString()} B deferred)`
      );
    }
    const worst = over.reduce((a, b) => (a.eagerBytes > b.eagerBytes ? a : b));
    console.error(`\n  Largest EAGER chunks on /${worst.locale}/:`);
    for (const f of worst.files.filter((f) => !f.deferred).slice(0, 5)) {
      console.error(`    ${f.bytes.toLocaleString()} B  ${f.url}`);
    }
    console.error(
      `\npackages/www/src/i18n/utils.ts imports all thirteen locale catalogs STATICALLY, so\n` +
        `every visitor downloads every language. Chunk them per locale and this figure drops\n` +
        `by roughly the twelve catalogs nobody on the page can read.`
    );
  }
  process.exit(1);
}

main();
