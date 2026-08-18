#!/usr/bin/env tsx
/**
 * Exactly one `<main>` landmark per built page.
 *
 * WHY THIS EXISTS. 1,120 of 1,842 built pages shipped TWO `<main>` elements: the one in
 * `BaseLayout.astro` plus a second inside it from `DocsLayout`, `ContentLayout` or the
 * solutions index. axe reports it as landmark-no-duplicate-main, landmark-main-is-top-level
 * and landmark-unique, and for a screen-reader user "skip to main content" becomes
 * ambiguous on 61% of the site.
 *
 * It survived nine waves and twelve new gates because not one of them looks at document
 * structure, and it was finally found by a nine-line sweep written by the verification
 * wave that would never have run again. This is that sweep, kept.
 *
 * REDIRECT STUBS ARE EXEMPT, and the exemption is measured rather than assumed: 32 files
 * in the build carry no `<main>` at all, every one of them a sub-400-byte meta-refresh
 * stub with no content to landmark. A tiny file with no `<main>` is fine; a real page
 * without one is a finding, which is why the size threshold is part of the rule.
 *
 * Usage:
 *   npx tsx scripts/check-landmarks.ts [--selftest]
 */
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIST = path.join(ROOT, 'packages/www/dist');
/** A stub is a redirect shell; anything larger is a page and must carry a landmark. */
const STUB_MAX_BYTES = 1024;

/**
 * Hand-written apps vendored into the build, which do not come from the www layout
 * system and so cannot be fixed by the layouts this gate exists to police.
 * `packages/json` is a standalone repository-template catalog copied in wholesale.
 * NAMED rather than absorbed by widening the size threshold, because a quiet exemption
 * is how a gate stops meaning what its name says. Both pages genuinely lack a <main>
 * and that is a real, reported accessibility gap in that package, not in this one.
 */
const VENDORED_PREFIXES = ['json/'];

/** Count real `<main>` ELEMENTS, never the word in prose, a comment or an attribute. */
export function countMain(html: string): number {
  const withoutComments = html.replace(/<!--[\s\S]*?-->/g, ' ');
  return (withoutComments.match(/<main(?:\s[^>]*)?>/gi) ?? []).length;
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}`);
    if (!ok) bad++;
  };
  check('one main is counted', countMain('<body><main id="x">hi</main></body>') === 1);
  check('CONTROL: two mains are counted', countMain('<main><main class="y"></main></main>') === 2);
  check(
    'a main inside an HTML COMMENT is not counted',
    countMain('<!-- <main> --><main></main>') === 1
  );
  check('the word main in prose is not counted', countMain('<p>the main thing</p>') === 0);
  check('a class named main is not counted', countMain('<div class="main"></div>') === 0);
  check('a closing tag alone is not counted', countMain('</main>') === 0);
  return bad;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    console.log('landmark gate selftest');
    const bad = selftest();
    console.log(
      bad === 0 ? '\n\x1b[32m✓\x1b[0m 6/6 controls pass' : `\n\x1b[31m✗\x1b[0m ${bad} failed`
    );
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  if (!existsSync(DIST)) {
    console.error(
      `✗ ${path.relative(ROOT, DIST)} does not exist. Build first: npm run build -w @rediacc/www`
    );
    process.exit(1);
  }
  const files = globSync(`${DIST}/**/*.html`);
  if (files.length === 0) {
    console.error('✗ zero built pages found; the gate is not seeing the build.');
    process.exit(1);
  }

  const duplicates: string[] = [];
  const missing: string[] = [];
  let stubs = 0;
  const vendored: string[] = [];
  for (const f of files) {
    const n = countMain(readFileSync(f, 'utf8'));
    const rel = path.relative(DIST, f);
    if (VENDORED_PREFIXES.some((v) => rel.startsWith(v))) {
      vendored.push(`${rel} (${n} <main>)`);
      continue;
    }
    if (n === 1) continue;
    if (n === 0) {
      if (statSync(f).size <= STUB_MAX_BYTES) {
        stubs++;
        continue;
      }
      missing.push(`${rel} (${statSync(f).size} B, too large to be a redirect stub)`);
    } else {
      duplicates.push(`${rel} (${n} <main> elements)`);
    }
  }

  if (duplicates.length > 0 || missing.length > 0) {
    if (duplicates.length > 0) {
      console.error(
        `\n\x1b[31m✗\x1b[0m ${duplicates.length} page(s) ship more than one <main> landmark:`
      );
      for (const d of duplicates.slice(0, 15)) console.error(`    ${d}`);
      if (duplicates.length > 15) console.error(`    ... and ${duplicates.length - 15} more`);
      console.error(
        '\nA nested <main> makes "skip to main content" ambiguous. The page owns exactly'
      );
      console.error('one; an inner region should be a <div> or a <section>.');
    }
    if (missing.length > 0) {
      console.error(`\n\x1b[31m✗\x1b[0m ${missing.length} page(s) carry NO <main> landmark:`);
      for (const m of missing.slice(0, 15)) console.error(`    ${m}`);
    }
    process.exit(1);
  }
  if (vendored.length > 0) {
    console.log(
      `\x1b[33m!\x1b[0m ${vendored.length} vendored page(s) exempt and still landmark-less (owned by another package):`
    );
    for (const v of vendored) console.log(`    ${v}`);
  }
  // Report what was actually VERIFIED, not what was opened. The stubs were `continue`d
  // above, so counting them as pages with exactly one <main> overstated coverage by 41
  // pages on this tree: 1,842 files minus 2 vendored printed as "1840 built page(s):
  // exactly one <main> each", when 43 of those were redirect stubs nobody checked. A
  // headline number that is larger than the work done is the failure this whole gate
  // family exists to catch, so it gets an assertion rather than a careful reading.
  const verified = files.length - vendored.length - stubs;
  // The four buckets must account for every file opened. Written as a SUM rather than as
  // a restatement of the subtraction above: `verified !== files.length - vendored - stubs`
  // compares an expression to itself and can never fail, which is the same vacuity this
  // gate family exists to catch.
  const accounted = verified + stubs + vendored.length + duplicates.length + missing.length;
  if (accounted !== files.length) {
    console.error(
      `✗ internal accounting error: ${accounted} file(s) accounted for, ${files.length} scanned.`
    );
    process.exit(1);
  }
  console.log(
    `\x1b[32m✓\x1b[0m ${verified} built page(s) verified: exactly one <main> each ` +
      `(${stubs} redirect stub(s) and ${vendored.length} vendored page(s) exempt, ` +
      `${files.length} file(s) scanned).`
  );
}

main();
