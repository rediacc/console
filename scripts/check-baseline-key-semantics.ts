#!/usr/bin/env tsx
/**
 * A shrink-only baseline's promise is that its entries are STABLE identities for
 * unresolved debt: fixing one shrinks the set, moving unrelated code around it does not.
 * A key built from structural position (a line number, a byte offset) breaks that
 * promise silently -- the ID drifts when anything ABOVE it in the file changes, which
 * desyncs into a simultaneous false "new" and false "fixed" for the same real finding.
 *
 * WHY THIS EXISTS. scripts/data/docker-image-freshness-baseline.json was keyed
 * `<file>:<line>  <image>:<tag>` until this session found and fixed it (measured
 * 2026-08-28): the four real debts were correct, but the identity was one line-number
 * shift away from a phantom drain-and-regrow. Re-keyed to `<image>:<tag>` alone, the
 * semantic content, proven globally unique by the gate's own pre-existing `seen` dedup.
 * Nothing caught this before a session happened to read the file by hand, and nothing
 * stopped a FUTURE baseline from repeating the shape -- this gate is that stop.
 *
 * WHAT IT FLAGS. A baseline entry (or the first colon-delimited segment pair within one)
 * whose final `:`-delimited component is a BARE base-10 integer -- `<anything>:<digits>`
 * with nothing else in that component. That shape is a line number or byte offset in
 * every baseline in this repo that was ever built that way; a genuinely semantic suffix
 * (an i18n key path, a CSS selector, a command name, a content hash) always carries at
 * least one non-digit character. A 12-hex-char content hash is not flagged: the odds of
 * 12 independently random hex digits landing all-decimal are ~0.7%, and the one gate that
 * uses that shape (check-em-dash-surfaces.ts) can move to a documented non-numeric prefix
 * if it is ever hit.
 *
 * SCOPE. Every `scripts/data/*-baseline.json` and `.ci/scripts/quality/*-baseline.json`
 * file, git-tracked (a baseline CI cannot see cannot be enforced by CI either -- the
 * same reasoning check-docker-image-freshness.ts already applies to gitignored roots).
 *
 * Usage:
 *   npx tsx scripts/check-baseline-key-semantics.ts [--selftest]
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { globSync } from 'glob';

const REPO_ROOT = path.resolve(import.meta.dirname, '..');

/**
 * A component is a line-number-shaped suffix iff it is nothing but base-10 digits AND
 * short enough to plausibly BE a line/offset number. The cap matters: this repo's one
 * sanctioned numeric-looking id shape is a SHA1 hex digest sliced to 12 characters
 * (check-em-dash-surfaces.ts:267), and roughly 1-in-140 of those are all-decimal by pure
 * chance -- caught live in this gate's first real run, five entries in
 * em-dash-surfaces-baseline.json, all exactly 12 digits. No file in this repo has
 * anywhere near 999,999 lines, so 6 digits is generous headroom for a real line number
 * while staying clear of the 12-char hash length.
 */
const isBareInteger = (s: string): boolean => /^[0-9]{1,6}$/.test(s);

/**
 * Extract candidate `<...>:<suffix>` strings out of one baseline value. Baselines here
 * hold either bare strings (`"file:where"`), tab-delimited pairs (`"file\tcmd"`, no colon
 * risk), or nested structures (`{ orphans: [...] }`, `{ entries: [...] }`). We only ever
 * need the STRING leaves; walk arbitrary JSON and collect every string found anywhere.
 */
function collectStrings(value: unknown, out: string[]): void {
  if (typeof value === 'string') {
    out.push(value);
  } else if (Array.isArray(value)) {
    for (const v of value) collectStrings(v, out);
  } else if (value && typeof value === 'object') {
    for (const v of Object.values(value)) collectStrings(v, out);
  }
}

/** Returns the offending suffix if `s` ends in a bare-integer `:`-delimited component. */
function lineNumberSuffix(s: string): string | null {
  const idx = s.lastIndexOf(':');
  if (idx === -1) return null;
  const suffix = s.slice(idx + 1);
  if (suffix.length === 0) return null;
  return isBareInteger(suffix) ? suffix : null;
}

/**
 * Whitespace-separated tokens, each checked independently. The real defect this gate
 * exists for was `<file>:<line>  <image>:<tag>` -- a compound record where the line
 * number is a MIDDLE token, not the string's own trailing suffix, so checking only the
 * whole string's last colon would have missed it. Caught by this gate's own first
 * control run: it failed the fixture reproducing that exact shape before this fix.
 */
function findOffenders(strings: readonly string[]): string[] {
  const offenders: string[] = [];
  for (const s of strings) {
    for (const token of s.split(/\s+/)) {
      const suffix = lineNumberSuffix(token);
      if (suffix !== null) {
        offenders.push(`${s}  (token "${token}" has bare-integer suffix ":${suffix}")`);
        break;
      }
    }
  }
  return offenders;
}

function selftest(): number {
  let failures = 0;
  const check = (name: string, ok: boolean) => {
    if (ok) {
      console.log(`ok   control: ${name}`);
    } else {
      console.log(`FAIL control: ${name}`);
      failures++;
    }
  };

  check(
    'a file:line baseline entry is detected',
    findOffenders(['private/renet/Dockerfile:133  ubuntu:24.04']).length === 1
  );
  check(
    'a semantic CSS-class suffix is not flagged',
    findOffenders(['packages/www/public/styles/main.css:btn--block']).length === 0
  );
  check(
    'a dotted i18n key suffix is not flagged',
    findOffenders(['packages/www/src/components/ContactForm.tsx:contactModal.success']).length === 0
  );
  check(
    'a 12-char hex content hash is not flagged (contains a non-digit hex letter)',
    findOffenders([
      'packages/cli/src/adapters/__tests__/remote-config-adapter.real-crypto.test.ts:1d4a18272d3e',
    ]).length === 0
  );
  check(
    'a 12-char hex content hash that is coincidentally ALL-DECIMAL is not flagged',
    findOffenders(['packages/cli/src/commands/config/audit.ts:752775144672']).length === 0
  );
  check(
    'a pure image:tag pair (no path prefix at all) is not flagged',
    findOffenders(['golang:1.26-bookworm']).length === 0
  );
  check(
    'a bare dotted key with no colon at all is not flagged',
    findOffenders(['pages.solutionPages.downloadGated.title']).length === 0
  );
  check(
    'nested JSON (orphans/entries wrapper) is still walked',
    (() => {
      const found: string[] = [];
      collectStrings({ note: 'shrink-only', entries: ['a/b.css:.chip', 'c/d.tsx:99'] }, found);
      return findOffenders(found).length === 1;
    })()
  );

  return failures;
}

function main(): number {
  if (process.argv.includes('--selftest')) {
    console.log('baseline key semantics selftest');
    const bad = selftest();
    console.log(bad === 0 ? 'selftest: all controls passed' : `selftest: ${bad} control(s) FAILED`);
    return bad === 0 ? 0 : 1;
  }

  if (selftest() !== 0) {
    console.error('x the rule itself is broken, so no verdict it produces means anything.');
    return 1;
  }

  const tracked = new Set(
    execFileSync(
      'git',
      ['ls-files', 'scripts/data/*-baseline.json', '.ci/scripts/quality/*-baseline.json'],
      {
        cwd: REPO_ROOT,
        encoding: 'utf8',
      }
    )
      .split('\n')
      .filter(Boolean)
  );

  const candidates = [
    ...globSync('scripts/data/*-baseline.json', { cwd: REPO_ROOT }),
    ...globSync('.ci/scripts/quality/*-baseline.json', { cwd: REPO_ROOT }),
  ].filter((f) => tracked.has(f));

  if (candidates.length === 0) {
    console.error('x found zero baseline files -- the scope glob is broken, not the tree clean.');
    return 1;
  }

  let anyOffenders = false;
  for (const rel of candidates.sort()) {
    const abs = path.join(REPO_ROOT, rel);
    if (!existsSync(abs)) continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(abs, 'utf8'));
    } catch (e) {
      console.error(`x ${rel}: not valid JSON (${(e as Error).message})`);
      return 1;
    }
    const strings: string[] = [];
    collectStrings(parsed, strings);
    const offenders = findOffenders(strings);
    if (offenders.length > 0) {
      anyOffenders = true;
      console.error(`x ${rel}: ${offenders.length} line-number-shaped key(s):`);
      for (const o of offenders.slice(0, 10)) console.error(`    ${o}`);
      if (offenders.length > 10) console.error(`    ... and ${offenders.length - 10} more`);
    }
  }

  if (anyOffenders) {
    console.error('');
    console.error('A baseline entry keyed on a raw line/offset number desyncs the moment');
    console.error('unrelated code above it moves. Re-key on semantic content instead: an');
    console.error('i18n key path, a selector/identifier name, or a content hash.');
    return 1;
  }

  console.log(`✓ ${candidates.length} baseline file(s) scanned, no line-number-shaped keys found`);
  return 0;
}

process.exit(main());
