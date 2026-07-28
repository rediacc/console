#!/usr/bin/env node
/**
 * Gate: a locale value must not change while its English value is unchanged.
 *
 * WHY THIS EXISTS. On 2026-07-28 a naturalization run over a 2-key delta was
 * given --reprocess, which widened its scope to the whole `pages.pricing`
 * group. The model then rewrote values that were already correct, and it
 * invented facts: Korean "1 Floating license" became "10", "Multi-machine
 * floating licenses" became "25 or more", and "Geo-redundant storage (3
 * regions)" became "implementation support included (launch offer)". 109 keys
 * across four locales were affected, on a customer-facing pricing page.
 *
 * Every existing i18n gate PASSED with those fabrications in place. Hash
 * checks, completeness, placeholder parity and the naturalization ledger all
 * ask "is the locale in step with English?", and a confidently-rewritten value
 * is in step: it has the same placeholders, the same structure, and a fresh
 * ledger stamp. What none of them ask is the question that catches this:
 *
 *   "This locale value changed. Did its English change too?"
 *
 * If English did not change, nothing downstream justified touching the
 * translation, and the edit is either an unrequested rewrite or a fabrication.
 *
 * WHAT IT DELIBERATELY ALLOWS. A key that was never naturalized may change
 * freely: that is backlog catch-up, not drift. Only keys the ledger already
 * considers naturalized are protected, because those are the ones a pipeline
 * has no business rewriting on its own.
 *
 * Usage:
 *   npx tsx scripts/check-locale-only-edits.ts [--base <ref>]
 *
 * Exit codes:
 *   0 - no locale-only edits to already-naturalized keys
 *   1 - locale-only edits found, or the base ref could not be resolved
 *   2 - usage error
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const DIR = 'packages/www/src/i18n/translations';
const LEDGER = path.join(REPO, DIR, '.naturalized-hashes.json');

type Flat = Record<string, string>;

function flatten(node: unknown, prefix = '', out: Flat = {}): Flat {
  if (node === null || node === undefined) return out;
  if (Array.isArray(node)) {
    // Arrays are the reason this gate exists in the shape it does: the
    // fabricated pricing values lived at `...features.1` and `...rows.2`, and
    // an earlier ad-hoc sweep missed every one of them by walking objects only.
    node.forEach((v, i) => flatten(v, prefix ? `${prefix}.${i}` : String(i), out));
  } else if (typeof node === 'object') {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      flatten(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else if (typeof node === 'string') {
    out[prefix] = node;
  }
  return out;
}

function gitShow(ref: string, rel: string): string | null {
  try {
    return execFileSync('git', ['show', `${ref}:${rel}`], {
      cwd: REPO,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    });
  } catch {
    return null;
  }
}

function resolveBase(explicit: string | null): string | null {
  const candidates = explicit ? [explicit] : ['origin/main', 'HEAD'];
  for (const ref of candidates) {
    try {
      execFileSync('git', ['rev-parse', '--verify', '--quiet', `${ref}^{commit}`], {
        cwd: REPO,
        stdio: 'ignore',
      });
      return ref;
    } catch {
      /* try the next candidate */
    }
  }
  return null;
}

function main(argv: string[]): number {
  let explicitBase: string | null = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--base') explicitBase = argv[++i] ?? null;
    else {
      process.stderr.write(`unknown argument: ${argv[i]}\n`);
      return 2;
    }
  }

  const base = resolveBase(explicitBase);
  if (!base) {
    // Fail rather than skip. A diff gate with no baseline measures nothing, and
    // "measured nothing" must never be reported as "found nothing".
    process.stderr.write(
      'check-locale-only-edits: could not resolve a base ref (tried origin/main, HEAD).\n' +
        'Pass one explicitly with --base <ref>. Refusing to run without a baseline.\n'
    );
    return 1;
  }

  const enRel = `${DIR}/en.json`;
  const enNowRaw = fs.readFileSync(path.join(REPO, enRel), 'utf8');
  const enBaseRaw = gitShow(base, enRel);
  if (!enBaseRaw) {
    process.stderr.write(`check-locale-only-edits: cannot read ${enRel} at ${base}\n`);
    return 1;
  }
  const enNow = flatten(JSON.parse(enNowRaw));
  const enBase = flatten(JSON.parse(enBaseRaw));

  // The ledger nests under `languages`, alongside a `$meta` block. Reading the
  // top level directly yields undefined for every locale, which silently makes
  // the protected set EMPTY and the gate incapable of firing. That is exactly
  // what happened on the first draft of this file, and only a planted control
  // caught it, so the shape is asserted rather than assumed.
  let ledger: Record<string, Record<string, unknown>> = {};
  try {
    const raw = JSON.parse(fs.readFileSync(LEDGER, 'utf8')) as {
      languages?: Record<string, Record<string, unknown>>;
    };
    if (!raw.languages || typeof raw.languages !== 'object') {
      process.stderr.write(
        `check-locale-only-edits: ${LEDGER} has no "languages" object.\n` +
          'The ledger shape changed. Refusing to run, because with no protected keys\n' +
          'this gate reports OK on everything, including fabricated values.\n'
      );
      return 1;
    }
    ledger = raw.languages;
  } catch (e) {
    process.stderr.write(
      `check-locale-only-edits: cannot read the naturalization ledger at ${LEDGER}: ${
        (e as Error).message
      }\n` + 'Refusing to run without it: an absent ledger protects nothing.\n'
    );
    return 1;
  }

  const locales = fs
    .readdirSync(path.join(REPO, DIR))
    .filter((f) => f.endsWith('.json') && !f.startsWith('.') && f !== 'en.json')
    .map((f) => f.replace(/\.json$/, ''));

  const findings: string[] = [];
  let checkedKeys = 0;

  for (const loc of locales) {
    const rel = `${DIR}/${loc}.json`;
    const baseRaw = gitShow(base, rel);
    if (!baseRaw) continue; // new locale file: nothing to compare against
    const now = flatten(JSON.parse(fs.readFileSync(path.join(REPO, rel), 'utf8')));
    const was = flatten(JSON.parse(baseRaw));
    const naturalized = (ledger[loc] ?? {}) as Record<string, unknown>;

    for (const key of Object.keys(now)) {
      if (was[key] === undefined || now[key] === was[key]) continue;
      checkedKeys++;
      const englishChanged = enNow[key] !== enBase[key];
      if (englishChanged) continue; // the whole point of a re-naturalization
      if (!(key in naturalized)) continue; // backlog catch-up, allowed
      findings.push(
        `  ${loc}  ${key}\n` +
          `      en (unchanged): ${JSON.stringify(enNow[key] ?? '<absent>').slice(0, 100)}\n` +
          `      was:            ${JSON.stringify(was[key]).slice(0, 100)}\n` +
          `      now:            ${JSON.stringify(now[key]).slice(0, 100)}`
      );
    }
  }

  if (findings.length > 0) {
    process.stderr.write(
      `check-locale-only-edits: ${findings.length} locale value(s) changed while their English did not.\n\n` +
        `${findings.join('\n')}\n\n` +
        'Each of these rewrote an already-naturalized translation with no English change\n' +
        'to justify it. That is the signature of an over-scoped naturalization run: on\n' +
        '2026-07-28 exactly this rewrote correct Korean pricing facts into invented ones\n' +
        '("1 Floating license" became "10"), and every other i18n gate passed it.\n\n' +
        'If the rewrite is genuinely wanted (a quality fix to awkward phrasing), make it\n' +
        'in a commit that touches only translations and say so in the message, then\n' +
        're-run with --base pointing past it.\n'
    );
    return 1;
  }

  process.stdout.write(
    `check-locale-only-edits: OK - ${checkedKeys} changed locale value(s) vs ${base}, ` +
      'each either backed by an English change or not yet naturalized.\n'
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
