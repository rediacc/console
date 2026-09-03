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
 * Fixed 2026-09-03; see agent/PLAN-www-bundle-determinism.md for the full arithmetic,
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
 *   tsx scripts/check-client-bundle-budget.ts [--dist <dir>] [--budget <bytes>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
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
 * (`TutorialVideoPlayer`, i.e. plyr). Folding the deferred chunk into one 600 kB budget
 * would hide it; dropping it from the report entirely would let it grow without limit
 * behind an `import()`. So it is measured, named, and held to its own line.
 *
 * This split is only honest because the deferral is REAL. Until 2026-09-03 the hydrator
 * mounted on DOMContentLoaded, so every homepage visitor fetched the player whether or
 * not they watched anything -- calling that "deferred" would have been a fudge, and the
 * plan that proposed this split (agent/PLAN-www-bundle-determinism.md section 3a) said
 * so in those words. What earns it: SPSolutionVideo.astro now server-renders a poster
 * and tutorial-video-hydrate.ts builds the player on first CLICK. A visitor who never
 * presses play never pays these bytes.
 */
const DEFERRED_CEILING = 150_000;

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
  files: { url: string; bytes: number; deferred: boolean }[];
  missing: string[];
}

/** An import edge, and whether crossing it costs the visitor bytes before they interact. */
interface Edge {
  spec: string;
  /** `import("./x")` -- fetched on demand, so it is not part of the eager cost. */
  dynamic: boolean;
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
  for (const m of source.matchAll(/\bimport\s*\(\s*["']([^"']+)["']/g))
    out.push({ spec: m[1], dynamic: true });
  // `\s*`, NOT `\s+`, and the difference was worth 124,673 B. Rollup emits bare
  // side-effect imports with no whitespace at all -- `import"./x.js";import"./y.js";` --
  // and `\s+` matched none of them. The homepage's script entry is a 129-BYTE FACADE
  // whose only three edges are all of that form, so this walk dead-ended there and the
  // gate reported 451,621 B while the page shipped 576,294 B. Note the two lines above
  // already use `\s*`; only this one demanded a space.
  for (const m of source.matchAll(/\bimport\s*["']([^"']+)["']/g))
    out.push({ spec: m[1], dynamic: false });
  return out;
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
  const files: { url: string; bytes: number; deferred: boolean }[] = [];

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
  const seen = new Set<string>();
  const dynamicTargets = new Set<string>(deferredEntries);

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
      for (const e of importSpecifiers(fs.readFileSync(abs, 'utf-8'))) {
        const resolved = resolveSpecifier(e.spec, url);
        if (!resolved) continue;
        if (e.dynamic) {
          if (collectDynamic) dynamicTargets.add(resolved);
          else stack.push(resolved);
        } else {
          stack.push(resolved);
        }
      }
    }
  };

  walk(entries, false, true);
  // Anything phase 1 already claimed is eager and stays eager: `seen` is not reset.
  walk(dynamicTargets, true, false);

  const sum = (want: boolean) => files.reduce((a, f) => a + (f.deferred === want ? f.bytes : 0), 0);

  return {
    page: pageRel,
    bytes: files.reduce((a, f) => a + f.bytes, 0),
    eagerBytes: sum(false),
    deferredBytes: sum(true),
    files: files.sort((a, b) => b.bytes - a.bytes),
    missing,
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
  // in .ci/scripts/test/gates/test-client-bundle-budget.sh is what caught that.
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

  // The locale universe is @rediacc/locales. A homepage missing for a declared locale is a
  // hard error: scoring zero for a locale nobody built reads exactly like scoring well.
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
    console.log(
      `✓ Deferred (behind an import(), fetched only on interaction): worst is ` +
        `${worstDef.locale} at ${worstDef.deferredBytes.toLocaleString()} B, ceiling ` +
        `${DEFERRED_CEILING.toLocaleString()} B. Full closure ` +
        `${worst.bytes.toLocaleString()} B -- reported, not budgeted.`
    );
    console.log(
      `  Blind spot: this counts what the graph makes REACHABLE. It cannot see whether a ` +
        `deferred chunk is in practice fetched by every visitor anyway; that is a property ` +
        `of the hydration trigger, which scripts/check-player-css-scope.ts pins separately.`
    );
    return;
  }

  if (missing.length > 0) {
    console.error(`✗ ${missing.length} referenced chunk(s) do not exist in the build:`);
    for (const m of missing.slice(0, 10)) console.error(`    ${m}`);
    console.error('');
  }

  if (overDeferred.length > 0) {
    console.error(
      `✗ ${overDeferred.length} of ${measured.length} locale homepage(s) exceed the ` +
        `${DEFERRED_CEILING.toLocaleString()} B DEFERRED ceiling:\n`
    );
    for (const m of overDeferred.sort((a, b) => b.deferredBytes - a.deferredBytes)) {
      const chunks = m.files.filter((f) => f.deferred);
      console.error(
        `  /${m.locale}/  ${m.deferredBytes.toLocaleString()} B across ${chunks.length} chunk(s)`
      );
      for (const f of chunks.slice(0, 5)) {
        console.error(`      ${f.bytes.toLocaleString()} B  ${f.url}`);
      }
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
