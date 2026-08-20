#!/usr/bin/env tsx
/**
 * Every class a component RENDERS must still have a rule somewhere.
 *
 * WHY THIS EXISTS. `.metric-label` sat at `main.css:2119-2124`, inside an otherwise
 * dead metrics-bar block, while `PricingComparison.astro:60` still rendered
 * `class="metric-label"`. A range deletion of that block would have silently unstyled a
 * live table header. It was caught by one agent reading across two files by hand, and
 * nothing in the repo would have caught it twice.
 *
 * Dead-CSS detection cannot see this: it scans structure and asks "is this rule used",
 * which is the opposite question. This asks "is this USE still styled".
 *
 * SHRINK-ONLY BASELINE, deliberately. Plenty of classes are legitimately unstyled today:
 * JS hooks, test handles, classes styled in a scoped `<style>` block this scanner does
 * not read. Demanding zero would mean an allowlist nobody maintains. Instead the current
 * set is frozen and the gate fails when it GROWS, which is exactly the deletion case.
 * Drain it with --write-baseline; it only ever shrinks.
 *
 * KNOWN LIMIT, stated rather than hidden: only STATIC class literals are collected.
 * A runtime-built name like `cf-badge-${variant}` is invisible to both sides, so it can
 * neither trip nor protect this gate. That is a false-negative, never a false-positive.
 *
 * Usage:
 *   npx tsx scripts/check-css-dom-refs.ts [--write-baseline] [--selftest]
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';

import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WWW = path.join(ROOT, 'packages/www');
const BASELINE = path.join(ROOT, 'scripts/data/css-dom-refs-baseline.json');

/** Class names appearing in a static class / className literal. */
export function usedClasses(source: string): Set<string> {
  const out = new Set<string>();
  const add = (raw: string) => {
    for (const name of raw.split(/\s+/)) {
      if (name && /^[a-zA-Z][\w-]*$/.test(name)) out.add(name);
    }
  };

  const attr = /\b(?:class|className)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  let m: RegExpExecArray | null;
  while ((m = attr.exec(source)) !== null) {
    const raw = m[1] ?? m[2] ?? '';
    // A literal containing an interpolation is only partly knowable; take the
    // static fragments and drop anything adjacent to a placeholder.
    if (/[{$]/.test(raw)) continue;
    add(raw);
  }

  // Astro's `class:list={['a', cond && 'b', x]}`. The string entries in that
  // array are as static as a class attribute, and there are 8 files and 20
  // class names in this tree that appear ONLY this way. Missing them is not a
  // harmless false-negative: `.billing-toggle-wrapper` was rendered through
  // `class:list` and its rule was deleted, and this gate passed while the
  // pricing page shipped an unstyled label against the viewport edge.
  // Non-string entries are variables and stay invisible, as above.
  const list = /class:list\s*=\s*\{\s*\[([\s\S]*?)\]\s*\}/g;
  while ((m = list.exec(source)) !== null) {
    for (const lit of m[1].matchAll(/'([^'{}$]*)'|"([^"{}$]*)"/g)) {
      add(lit[1] ?? lit[2] ?? '');
    }
  }
  return out;
}

/** Class names that some rule actually selects. */
export function styledClasses(css: string): Set<string> {
  const out = new Set<string>();
  // Strip comments and declaration bodies so a value like `content: '.foo'` cannot
  // masquerade as a selector.
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, ' ');
  const selectorText = withoutComments.replace(/\{[^{}]*\}/g, '{}');
  for (const m of selectorText.matchAll(/\.([a-zA-Z][\w-]*)/g)) out.add(m[1]);
  return out;
}

function collect(): { used: Map<string, string>; styled: Set<string> } {
  const used = new Map<string, string>();
  const markup = [
    ...globSync(`${WWW}/src/**/*.astro`),
    ...globSync(`${WWW}/src/**/*.tsx`),
    ...globSync(`${WWW}/public/**/*.html`),
  ];
  for (const file of markup) {
    const rel = path.relative(ROOT, file);
    for (const name of usedClasses(readFileSync(file, 'utf8'))) {
      if (!used.has(name)) used.set(name, rel);
    }
  }
  const styled = new Set<string>();
  const sheets = [
    ...globSync(`${WWW}/public/styles/**/*.css`),
    ...globSync(`${WWW}/src/styles/**/*.css`),
    ...globSync(`${WWW}/src/**/*.astro`), // scoped <style> blocks live inline
  ];
  for (const file of sheets) {
    for (const name of styledClasses(readFileSync(file, 'utf8'))) styled.add(name);
  }
  return { used, styled };
}

function selftest(): number {
  let failures = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}`);
    if (!ok) failures++;
  };
  check('a static class literal is collected', usedClasses('<p class="alpha beta">').has('alpha'));
  check(
    'an interpolated literal is SKIPPED, not half-read',
    !usedClasses('<p class={`cf-${v}`}>').has('cf-')
  );
  check(
    'a string inside class:list is collected',
    usedClasses("<div class:list={['zeta', extra]}>").has('zeta')
  );
  check(
    'CONTROL: a VARIABLE inside class:list is not invented as a class',
    !usedClasses("<div class:list={['zeta', extra]}>").has('extra')
  );
  check(
    'CONTROL: an interpolated entry in class:list is not half-read',
    !usedClasses('<div class:list={[`cf-${v}`]}>').has('cf-')
  );
  check('a rule selector is collected', styledClasses('.gamma { color: red }').has('gamma'));
  check(
    'a class inside a DECLARATION VALUE is not mistaken for a selector',
    !styledClasses(".x { content: '.delta' }").has('delta')
  );
  check(
    'a class inside a COMMENT is not mistaken for a selector',
    !styledClasses('/* .epsilon */ .x {}').has('epsilon')
  );
  // The control that matters: the real defect shape.
  const used = usedClasses('<th class="metric-label">');
  const styled = styledClasses('.other {}');
  check(
    'CONTROL: a used-but-unstyled class IS detected',
    used.has('metric-label') && !styled.has('metric-label')
  );
  // THE SHRINK-ONLY COMPOSITION RULE, shared with every other baselined gate here.
  for (const c of sharedSelftestCases()) check(c.name, c.ok);

  return failures;
}

function main(): void {
  const argv = process.argv.slice(2);
  if (argv.includes('--selftest')) {
    console.log('CSS/DOM reference gate selftest');
    const failures = selftest();
    console.log(
      failures === 0
        ? '\n\x1b[32m✓\x1b[0m 9/9 controls pass'
        : `\n\x1b[31m✗\x1b[0m ${failures} control(s) failed`
    );
    process.exit(failures === 0 ? 0 : 1);
  }

  const { used, styled } = collect();
  const orphans = [...used.keys()].filter((c) => !styled.has(c)).sort();

  if (argv.includes('--write-baseline')) {
    // COMPOSITION. The header two dozen lines up says this baseline "only ever shrinks",
    // and until now nothing enforced that on the WRITE path: a reseed could drop ten
    // orphans, absorb one fresh one, and print a smaller number while doing it. The ids
    // here carry the SELECTOR text, so rewriting a rule re-keys the entry; hand-edit the
    // one line rather than reseeding when that happens.
    const had = existsSync(BASELINE);
    const previous: string[] = had ? JSON.parse(readFileSync(BASELINE, 'utf8')).orphans : [];
    const verdict = writeBaselineVerdict({
      baselineExists: had,
      firstSeedFlag: argv.includes('--first-seed'),
      additions: had ? baselineAdditions(previous, orphans) : [],
    });
    if (verdict !== null) {
      console.error(
        `\n\x1b[31m✗\x1b[0m ${renderRefusal(verdict, {
          baselineLabel: path.relative(ROOT, BASELINE),
          noun: 'orphan',
          previousCount: previous.length,
          newCount: orphans.length,
          rekeyHint: true,
        })}`
      );
      process.exit(1);
    }
    writeFileSync(
      BASELINE,
      `${JSON.stringify({ note: 'shrink-only; see scripts/check-css-dom-refs.ts', orphans }, null, 2)}\n`
    );
    console.log(
      `baseline written: ${orphans.length} entr(ies) (${previous.length} before, ` +
        `${previous.filter((o) => !orphans.includes(o)).length} drained, 0 added)`
    );
    return;
  }

  const baseline: string[] = existsSync(BASELINE)
    ? JSON.parse(readFileSync(BASELINE, 'utf8')).orphans
    : [];
  const known = new Set(baseline);
  const added = orphans.filter((c) => !known.has(c));
  const fixed = baseline.filter((c) => !orphans.includes(c));

  console.log(
    `Rendered classes: ${used.size}. Styled: ${styled.size}. Unstyled: ${orphans.length} (baseline ${baseline.length}).`
  );
  if (added.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${added.length} class(es) are RENDERED but no longer STYLED:`
    );
    for (const c of added) console.error(`    .${c}  first rendered in ${used.get(c)}`);
    console.error('\nA rule was probably deleted while its markup survived. Restore the rule,');
    console.error('or remove the class from the markup, or baseline it if it is styled elsewhere.');
    process.exit(1);
  }
  if (fixed.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${fixed.length} baselined entr(ies) are already fixed. The baseline only shrinks:`
    );
    console.error('    npx tsx scripts/check-css-dom-refs.ts --write-baseline');
    process.exit(1);
  }
  console.log('\x1b[32m✓\x1b[0m every rendered class still has a rule');
}

main();
