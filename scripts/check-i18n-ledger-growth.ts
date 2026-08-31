#!/usr/bin/env node
/**
 * Gate: a NEW English key must not enlarge the staleness blind spot.
 *
 * WHAT THE BLIND SPOT IS, measured rather than argued. `check:ci-i18n-naturalization`
 * answers "has this key's English moved since its translation was fingerprinted?" It can
 * only answer that for keys the naturalization ledger has a fingerprint FOR. Today the
 * hash manifest carries 6,014 www keys, `pages.*` alone is 5,741, and the ledger covers
 * 1,180 per locale -- so 55,825 locale/key pairs under `pages.*` have no fingerprint at
 * all, and for every one of them the staleness question is not merely unanswered, it is
 * unaskable.
 *
 * WHAT IT COST, on this repo, in the change that motivated this file. Nine
 * `pages.solutionPages.*.techDiff.description` values had their English rewritten to drop
 * a shared explainer. All twelve locale values stayed on the previous English. Every i18n
 * gate passed: the keys were absent from the ledger so naturalization could not flag them,
 * and `check-locale-only-edits.ts` asks the MIRROR question (a locale that moved while its
 * English did not), so it looks the other way by construction. The drift was found by
 * reading German prose, which is not a mechanism.
 *
 * WHY THIS GATE STOPS AT GROWTH, and says so rather than pretending to more. Requiring
 * coverage for the existing 55,825 would mean a multi-megabyte baseline nobody drains --
 * the shape `check-pipefail-grep-q.sh` refuses in its own header, where a baseline "would
 * have recorded ten provably-safe sites as debt and left three real risks sitting in a
 * list that says known, fine". So the invariant here is strictly non-retroactive and
 * therefore has ZERO existing debt and no baseline file: a key that is NEW in `en.json`
 * relative to the base must arrive with a ledger fingerprint in every locale. The hole may
 * not get bigger.
 *
 * RESIDUE, stated because a green here is narrower than it looks: an English change to a
 * key that was ALREADY unfingerprinted is still invisible to every gate in this repo,
 * including this one. Closing that needs the pipeline to fingerprint the backlog, which is
 * a paid run and an operator decision, not a check.
 *
 * Usage:
 *   npx tsx scripts/check-i18n-ledger-growth.ts [--base <ref>] [--selftest]
 *
 * Exit codes:
 *   0 - no new key enlarged the blind spot
 *   1 - a new key has no ledger fingerprint, or the base/ledger could not be read
 *   2 - usage error
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const DIR = 'packages/www/src/i18n/translations';
const LEDGER = path.join(REPO, DIR, '.naturalized-hashes.json');

type Flat = Record<string, string>;

/** Same walk as check-locale-only-edits.ts: arrays are keys too (`...rows.2`). */
function flatten(node: unknown, prefix = '', out: Flat = {}): Flat {
  if (node === null || node === undefined) return out;
  if (Array.isArray(node)) {
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
  for (const ref of explicit ? [explicit] : ['origin/main', 'HEAD']) {
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

/**
 * The whole judgement, pure so the controls drive the SAME function the real scan does.
 * Returns `<locale>:<key>` for every new key with no fingerprint.
 */
export function unfingerprintedNewKeys(input: {
  enBase: readonly string[];
  enNow: readonly string[];
  locales: readonly string[];
  ledger: Readonly<Record<string, Readonly<Record<string, unknown>>>>;
}): string[] {
  const had = new Set(input.enBase);
  const fresh = input.enNow.filter((k) => !had.has(k));
  const out: string[] = [];
  for (const loc of input.locales) {
    const stamped = input.ledger[loc] ?? {};
    for (const k of fresh) if (!(k in stamped)) out.push(`${loc}:${k}`);
  }
  return out.sort();
}

const CONTROLS: {
  name: string;
  input: Parameters<typeof unfingerprintedNewKeys>[0];
  want: number;
}[] = [
  {
    name: 'the real case: a new key with no fingerprint is reported once per locale',
    input: {
      enBase: ['a.b'],
      enNow: ['a.b', 'solutions.mechanism.cow'],
      locales: ['de', 'tr'],
      ledger: { de: { 'a.b': 1 }, tr: { 'a.b': 1 } },
    },
    want: 2,
  },
  {
    name: 'CONTROL: a new key fingerprinted in every locale is silent',
    input: {
      enBase: ['a.b'],
      enNow: ['a.b', 'a.c'],
      locales: ['de', 'tr'],
      ledger: { de: { 'a.b': 1, 'a.c': 1 }, tr: { 'a.b': 1, 'a.c': 1 } },
    },
    want: 0,
  },
  {
    name: 'CONTROL: fingerprinted in ONE locale and not the other reports only the gap',
    input: {
      enBase: ['a.b'],
      enNow: ['a.b', 'a.c'],
      locales: ['de', 'tr'],
      ledger: { de: { 'a.b': 1, 'a.c': 1 }, tr: { 'a.b': 1 } },
    },
    want: 1,
  },
  {
    name: 'CONTROL: a PRE-EXISTING unfingerprinted key is NOT reported (non-retroactive)',
    input: {
      enBase: ['a.b', 'old.unstamped'],
      enNow: ['a.b', 'old.unstamped'],
      locales: ['de', 'tr'],
      ledger: { de: { 'a.b': 1 }, tr: { 'a.b': 1 } },
    },
    want: 0,
  },
  {
    name: 'CONTROL: a locale missing from the ledger entirely still reports its new keys',
    input: {
      enBase: [],
      enNow: ['a.c'],
      locales: ['de'],
      ledger: {},
    },
    want: 1,
  },
  {
    name: 'CONTROL: a DELETED English key is not a finding',
    input: {
      enBase: ['a.b', 'gone'],
      enNow: ['a.b'],
      locales: ['de'],
      ledger: { de: { 'a.b': 1 } },
    },
    want: 0,
  },
];

function selftest(): number {
  let bad = 0;
  for (const c of CONTROLS) {
    const got = unfingerprintedNewKeys(c.input).length;
    const ok = got === c.want;
    if (!ok) bad += 1;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  ${c.name}${ok ? '' : ` (want ${c.want}, got ${got})`}\n`
    );
  }
  if (bad > 0) {
    process.stderr.write(
      `check-i18n-ledger-growth: ${bad} control(s) failed; this gate cannot be trusted\n`
    );
    return 1;
  }
  return 0;
}

function main(argv: string[]): number {
  let explicitBase: string | null = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--base') explicitBase = argv[++i] ?? null;
    else if (argv[i] === '--selftest') {
      const rc = selftest();
      if (rc !== 0) return rc;
    } else {
      process.stderr.write(`unknown argument: ${argv[i]}\n`);
      return 2;
    }
  }

  const base = resolveBase(explicitBase);
  if (!base) {
    // Fail rather than skip. With no base every key looks new, or none does; either way
    // "measured nothing" must never be reported as "found nothing".
    process.stderr.write(
      'check-i18n-ledger-growth: could not resolve a base ref (tried origin/main, HEAD).\n' +
        'Pass one with --base <ref>. Refusing to run without a baseline.\n'
    );
    return 1;
  }

  const enRel = `${DIR}/en.json`;
  const enBaseRaw = gitShow(base, enRel);
  if (!enBaseRaw) {
    process.stderr.write(`check-i18n-ledger-growth: cannot read ${enRel} at ${base}\n`);
    return 1;
  }
  const enBase = Object.keys(flatten(JSON.parse(enBaseRaw)));
  const enNow = Object.keys(flatten(JSON.parse(fs.readFileSync(path.join(REPO, enRel), 'utf8'))));

  // FLOOR. A collapsed read makes every key look new (or none), and both directions are a
  // broken instrument reporting confidently.
  if (enBase.length < 1000 || enNow.length < 1000) {
    process.stderr.write(
      `check-i18n-ledger-growth: en.json flattened to ${enBase.length} keys at ${base} and ` +
        `${enNow.length} now; both must exceed 1000.\n  The read is broken, so this verdict ` +
        'would be vacuous.\n'
    );
    return 1;
  }

  let ledger: Record<string, Record<string, unknown>>;
  try {
    const raw = JSON.parse(fs.readFileSync(LEDGER, 'utf8')) as {
      languages?: Record<string, Record<string, unknown>>;
    };
    if (!raw.languages || typeof raw.languages !== 'object') {
      process.stderr.write(
        `check-i18n-ledger-growth: ${LEDGER} has no "languages" object. Refusing to run:\n` +
          'with no fingerprints this gate reports OK over every new key.\n'
      );
      return 1;
    }
    ledger = raw.languages;
  } catch (e) {
    process.stderr.write(
      `check-i18n-ledger-growth: cannot read ${LEDGER}: ${(e as Error).message}\n` +
        'Refusing to run without it: an absent ledger measures nothing.\n'
    );
    return 1;
  }

  const locales = fs
    .readdirSync(path.join(REPO, DIR))
    .filter((f) => f.endsWith('.json') && !f.startsWith('.') && f !== 'en.json')
    .map((f) => f.replace(/\.json$/, ''));
  if (locales.length < 10) {
    process.stderr.write(
      `check-i18n-ledger-growth: found ${locales.length} locale file(s), expected 12.\n` +
        '  The directory read is broken; a green here would be vacuous.\n'
    );
    return 1;
  }

  const findings = unfingerprintedNewKeys({ enBase, enNow, locales, ledger });
  const freshKeys = new Set(findings.map((f) => f.slice(f.indexOf(':') + 1)));

  if (findings.length > 0) {
    process.stderr.write(
      `check-i18n-ledger-growth: ${freshKeys.size} new English key(s) have no naturalization\n` +
        `fingerprint, in ${findings.length} locale/key pair(s) vs ${base}:\n\n`
    );
    for (const f of findings) process.stderr.write(`  ${f}\n`);
    process.stderr.write(
      '\nA key with no fingerprint can never be reported stale: check:ci-i18n-naturalization\n' +
        'compares the recorded English CRC to the live one, and there is no recorded CRC to\n' +
        'compare. Its translation can drift from English forever with every gate green.\n\n' +
        '  Translate it, then stamp it, SCOPED to the group you touched:\n' +
        '    cd private/growth/i18n_pipeline\n' +
        '    ./run.sh --mark-done --lang <locale> --group <selector>\n\n' +
        '  Never --all-stale to close a named key: it means "every key not in the ledger",\n' +
        '  which on this catalog is ~1,965 per locale. See docs/agent-reference/TRAPS.md.\n'
    );
    return 1;
  }

  process.stdout.write(
    `✓ ${enNow.length - enBase.length >= 0 ? enNow.filter((k) => !new Set(enBase).has(k)).length : 0} ` +
      `new English key(s) vs ${base}, each fingerprinted in all ${locales.length} locales. ` +
      'The staleness blind spot did not grow.\n'
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
