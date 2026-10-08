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
 * WHAT IT DELIBERATELY ALLOWS. Backlog catch-up, which is not drift. A key is
 * protected only when the naturalization ledger AT THE BASE holds an entry for
 * it that is CURRENT for the base's English: the recorded CRC32 equals the hash
 * of the base English value, computed by the same `flattenAndHash` that
 * check:ci-i18n-naturalization uses. Two shapes are therefore free to change:
 *
 *   - ABSENT at the base: the key was never naturalized. A run that stamps it
 *     in this same diff does not make it protected, because the HEAD ledger is
 *     the thing a resync rewrites and cannot be the witness for its own edit.
 *   - STALE at the base: English moved in an earlier merged PR and the locale
 *     was never resynced, so the translation is known to lag. Refusing its
 *     resync because English is "unchanged between base and HEAD" made the
 *     catch-up unshippable: the nine `pages.solutionPages.*.techDiff.description`
 *     keys x 12 locales (agent/plans/PLAN-locale-techdiff-resync.md) had their
 *     English change already in origin/main.
 *
 * Only a translation the base ledger vouches for, against the English it still
 * shows, is one a pipeline has no business rewriting on its own.
 *
 * Usage:
 *   npx tsx scripts/gates/check-locale-only-edits.ts [--base <ref>]
 *
 * Exit codes:
 *   0 - no locale-only edits to already-naturalized keys
 *   1 - locale-only edits found, or the base ref could not be resolved
 *   2 - usage error
 *
 * ---- gate ----
 * kind: battery
 * step: i18n
 * needs: node
 * id: check:ci-i18n-locale-only
 * run: tsx scripts/gates/check-locale-only-edits.ts --selftest
 * lane: quality-i18n
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { flattenAndHash } from '../lib/crc32.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const DIR = 'packages/www/src/i18n/translations';
const LEDGER_REL = `${DIR}/.naturalized-hashes.json`;

type Flat = Record<string, string>;

function flatten(node: unknown, prefix = '', out: Flat = {}): Flat {
  if (node === null || node === undefined) return out;
  if (Array.isArray(node)) {
    // Arrays are the reason this gate exists in the shape it does: the fabricated pricing values lived at `...features.1` and `...rows.2`, and an earlier ad-hoc sweep missed every one of them by walking objects only.
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

/**
 * True when the base value carried an em dash and the new one does not.
 *
 * check:ci-em-dash-surfaces is a blocking gate in the same chain and REQUIRES the dash to
 * go. Removing one correctly is usually not a character deletion: Russian uses the dash as
 * a copula, so the repair supplies the missing verb, and other locales substitute a comma,
 * colon or clause. Those rewordings are mandated, so a rule that only tolerated
 * punctuation-level edits would make the two gates mutually unsatisfiable.
 *
 * The exemption is therefore wider than the rest of this gate, and that is stated rather
 * than hidden: an over-scoped rewrite of a value that HAPPENED to contain an em dash would
 * pass here. The exempted values are printed as an advisory below so the widening stays
 * visible, and the set is bounded by "had a dash", not open-ended.
 */
function isEmDashRepair(was: string, now: string): boolean {
  return was.includes('\u2014') && !now.includes('\u2014');
}

/** A superscript reference marker, `[1]`, `[12]`, with any space in front of it. */
const REF_MARKER = /\s*\[\d+\]/g;

/**
 * True when the edit ONLY removes `[n]` reference markers that English never carried.
 *
 * THE CASE, found 2026-08-31. Eight locales held
 * `"Flexera 2024 [1] / Thales 2025 [2]"` and `"Cloud provider pricing [4]"` at
 * `pages.solutionPages.migrationSafety.problem.statCallouts[0,2].source`, against an
 * English that has read `"Flexera 2024 / Thales 2025"` and `"Cloud provider pricing"`
 * for as long as the base knows. They are markers from a superseded English value that
 * survived translation and were never cleaned when English dropped them, and they RENDER
 * -- a visitor on /de sees a literal `[1]` in the source tooltip, pointing at nothing.
 *
 * Removing them is a locale-only edit with no English change to justify it, which is
 * precisely what this gate exists to refuse, and the gate's own remedy ("commit
 * translations alone, re-run with --base past it") does not apply inside a PR: the base
 * is `origin/main`, so the finding survives every commit until merge. Without an
 * exemption the correct fix is unshippable.
 *
 * NARROW BY CONSTRUCTION, and narrower than the em-dash exemption above. It is not
 * "the value converged to English", which would let a bad run overwrite a good German
 * sentence with the English one. It is: delete the markers from the OLD value, and what
 * is left must equal the NEW value exactly, once whitespace is collapsed. Every other
 * byte must be untouched, so no wording, number or fact can move through here. The
 * markers must also be absent from English, so a marker English genuinely carries is
 * still protected.
 */
function isRefMarkerRepair(was: string, now: string, en: string): boolean {
  REF_MARKER.lastIndex = 0;
  if (!REF_MARKER.test(was)) return false;
  REF_MARKER.lastIndex = 0;
  if (REF_MARKER.test(en)) return false;
  const collapse = (t: string) => t.replace(REF_MARKER, '').replace(/\s+/g, ' ').trim();
  return collapse(was) === collapse(now) && collapse(now) === now.replace(/\s+/g, ' ').trim();
}

/**
 * Controls for the exemption above, run with `--selftest`.
 *
 * An exemption is a hole in a gate, and a hole nobody has watched close is not a hole
 * anyone can reason about. These drive the SAME function the real scan calls; a control
 * that re-implements the rule proves only that the reimplementation agrees with itself.
 */
const REF_MARKER_CONTROLS: { name: string; was: string; now: string; en: string; want: boolean }[] =
  [
    {
      name: 'the real case: two markers English never carried are dropped',
      was: 'Flexera 2024 [1] / Thales 2025 [2]',
      now: 'Flexera 2024 / Thales 2025',
      en: 'Flexera 2024 / Thales 2025',
      want: true,
    },
    {
      name: 'CONTROL: a marker removed AND the wording changed is NOT exempt',
      was: 'Flexera 2024 [1] / Thales 2025',
      now: 'Flexera 2025 / Thales 2025',
      en: 'Flexera 2024 / Thales 2025',
      want: false,
    },
    {
      name: 'CONTROL: a rewrite with no marker at all is NOT exempt',
      was: '1 Floating-Lizenz',
      now: '10 Floating-Lizenzen',
      en: '1 Floating license',
      want: false,
    },
    {
      name: 'CONTROL: a marker ENGLISH also carries is protected, not exempt',
      was: 'IBM 2024 [3]',
      now: 'IBM 2024',
      en: 'IBM 2024 [3]',
      want: false,
    },
    {
      name: 'CONTROL: dropping a marker AND a whole clause is NOT exempt',
      was: 'Cloud provider pricing [4], as of June',
      now: 'Cloud provider pricing',
      en: 'Cloud provider pricing',
      want: false,
    },
  ];

/**
 * True when the base ledger vouches for this (locale, key) against the base English.
 *
 * Same comparison check:ci-i18n-naturalization makes (`current[key] !== recordedCrc` is
 * its "stale"), applied to the BASE: the ledger's recorded CRC must equal the CRC32 of the
 * base English value. Absent entry, absent English, or a different hash all mean the
 * translation is not one the ledger currently stands behind, so changing it is catch-up.
 */
export function isProtectedAtBase(
  ledgerAtBase: Record<string, unknown>,
  key: string,
  enBaseHash: Record<string, string>
): boolean {
  const recorded = ledgerAtBase[key];
  const want = enBaseHash[key];
  return typeof recorded === 'string' && want !== undefined && recorded === want;
}

export interface LocaleScan {
  findings: string[];
  emDashRepairs: string[];
  refMarkerRepairs: string[];
  checkedKeys: number;
}

/** The per-locale verdict, shared by the real scan and the selftest probes. */
export function scanLocale(
  loc: string,
  was: Flat,
  now: Flat,
  enBase: Flat,
  enNow: Flat,
  ledgerAtBase: Record<string, unknown>,
  enBaseHash: Record<string, string>
): LocaleScan {
  const out: LocaleScan = { findings: [], emDashRepairs: [], refMarkerRepairs: [], checkedKeys: 0 };
  for (const key of Object.keys(now)) {
    if (was[key] === undefined || now[key] === was[key]) continue;
    out.checkedKeys++;
    const englishChanged = enNow[key] !== enBase[key];
    if (englishChanged) continue; // the whole point of a re-naturalization
    if (!isProtectedAtBase(ledgerAtBase, key, enBaseHash)) continue; // absent or stale at base: backlog catch-up, allowed

    // Backlog catch-up the LEDGER lied about. A key whose base value is byte-identical to its base English was never actually translated, whatever the ledger claims, and the ledger does make that claim: 369 keys across 12 locales were stamped naturalized while still holding the English string. Trusting the stamp over the data turns "translate the untranslated" into a gate
    // failure, which is the exact opposite of this gate's stated allowance in the header.
    //
    // This cannot hide a fabrication. A fabricated rewrite replaces a REAL translation, so its base value is not English and this check does not apply to it. Proven on the run that motivated it: 411 genuine rewrites were still reported and reverted
    // while these passed.
    if (was[key] === enBase[key]) continue;

    // An edit that ONLY removes an em dash is required by check:ci-em-dash-surfaces, which is a blocking gate in the same chain. Without this the two gates are mutually unsatisfiable: one demands the dash go, the other calls its removal an unjustified rewrite. Deliberately narrow -- the values must be identical once the dash and its surrounding spaces are normalised away, so a
    // rewrite that also changes wording is still reported.
    if (isRefMarkerRepair(was[key], now[key], enNow[key] ?? '')) {
      out.refMarkerRepairs.push(`  ${loc}  ${key}`);
      continue;
    }

    if (isEmDashRepair(was[key], now[key])) {
      out.emDashRepairs.push(`  ${loc}  ${key}`);
      continue;
    }
    out.findings.push(
      `  ${loc}  ${key}\n` +
        `      en (unchanged): ${JSON.stringify(enNow[key] ?? '<absent>').slice(0, 100)}\n` +
        `      was:            ${JSON.stringify(was[key]).slice(0, 100)}\n` +
        `      now:            ${JSON.stringify(now[key]).slice(0, 100)}`
    );
  }
  return out;
}

/**
 * Probes for the base-ledger rule, run with `--selftest` through `scanLocale` itself.
 * Each names the keys it expects reported; anything else reported, or missing, fails.
 */
const EN = {
  'pricing.license': '1 Floating license',
  'pages.solutionPages.failoverTesting.techDiff.description':
    'Rediacc clones a whole setup in seconds. The test runs on the copy.',
  'pages.solutionPages.migrationSafety.techDiff.description': 'Move a whole setup safely.',
};
const EN_PREV_TECHDIFF =
  'Rediacc uses btrfs copy-on-write snapshots to clone your whole infrastructure in seconds.';
const EN_HASH = flattenAndHash(EN);
const STALE_HASH = flattenAndHash({ k: EN_PREV_TECHDIFF }).k;
const FAILOVER = 'pages.solutionPages.failoverTesting.techDiff.description';
const MIGRATION = 'pages.solutionPages.migrationSafety.techDiff.description';

const LEDGER_PROBES: {
  name: string;
  was: Flat;
  now: Flat;
  ledger: Record<string, unknown>;
  want: string[];
}[] = [
  {
    name: 'the 2026-07-28 shape: ledger current at base, English unchanged, locale rewritten -> RED',
    was: { 'pricing.license': '1 플로팅 라이선스' },
    now: { 'pricing.license': '10 플로팅 라이선스' },
    ledger: { 'pricing.license': EN_HASH['pricing.license'] },
    want: ['pricing.license'],
  },
  {
    name: 'ledger STALE at base (English moved in an earlier PR) + locale resync -> silent',
    was: { [FAILOVER]: 'Rediacc nutzt btrfs Copy-on-Write-Snapshots, um in Sekunden zu klonen.' },
    now: {
      [FAILOVER]: 'Rediacc klont ein ganzes Setup in Sekunden. Der Test läuft auf der Kopie.',
    },
    ledger: { [FAILOVER]: STALE_HASH },
    want: [],
  },
  {
    name: 'ledger ABSENT at base (never naturalized) + locale change -> silent',
    was: { [FAILOVER]: 'Rediacc nutzt btrfs Copy-on-Write-Snapshots, um in Sekunden zu klonen.' },
    now: {
      [FAILOVER]: 'Rediacc klont ein ganzes Setup in Sekunden. Der Test läuft auf der Kopie.',
    },
    ledger: {},
    want: [],
  },
  {
    name: 'CONTROL: one key stale at base, but the edit is to a DIFFERENT key that is current -> RED on that key only',
    was: {
      [FAILOVER]: 'Rediacc nutzt btrfs Copy-on-Write-Snapshots, um in Sekunden zu klonen.',
      [MIGRATION]: 'Ein ganzes Setup sicher umziehen.',
    },
    now: {
      [FAILOVER]: 'Rediacc nutzt btrfs Copy-on-Write-Snapshots, um in Sekunden zu klonen.',
      [MIGRATION]: 'Ein ganzes Setup mit 25 Klicks sicher umziehen.',
    },
    ledger: { [FAILOVER]: STALE_HASH, [MIGRATION]: EN_HASH[MIGRATION] },
    want: [MIGRATION],
  },
];

function selftest(): number {
  let bad = 0;
  for (const c of REF_MARKER_CONTROLS) {
    const got = isRefMarkerRepair(c.was, c.now, c.en);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  for (const p of LEDGER_PROBES) {
    const r = scanLocale('xx', p.was, p.now, EN, EN, p.ledger, EN_HASH);
    const got = r.findings.map((f) => f.trim().split(/\s+/)[1]).sort();
    const ok = JSON.stringify(got) === JSON.stringify([...p.want].sort());
    if (!ok) bad++;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  ${p.name}${ok ? '' : ` (reported ${JSON.stringify(got)})`}\n`
    );
  }
  if (bad > 0) {
    process.stderr.write(
      `check-locale-only-edits: ${bad} control(s) failed; the marker exemption or the base-ledger rule cannot be trusted\n`
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
    // Fail rather than skip. A diff gate with no baseline measures nothing, and "measured nothing" must never be reported as "found nothing".
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

  // The ledger is read AT THE BASE, not from the working tree: the question is whether the base vouched for a translation, and a resync rewrites the HEAD ledger in the same diff, so the HEAD copy would witness its own edit.
  // The ledger nests under `languages`, alongside a `$meta` block. Reading the top level directly yields undefined for every locale, which silently makes the protected set EMPTY and the gate incapable of firing. That is exactly what happened on the first draft of this file, and only a planted control caught it, so the shape is asserted rather than assumed.
  let ledger: Record<string, Record<string, unknown>> = {};
  const ledgerRaw = gitShow(base, LEDGER_REL);
  if (!ledgerRaw) {
    process.stderr.write(
      `check-locale-only-edits: cannot read the naturalization ledger ${LEDGER_REL} at ${base}.\n` +
        'Refusing to run without it: an absent ledger protects nothing.\n'
    );
    return 1;
  }
  try {
    const raw = JSON.parse(ledgerRaw) as {
      languages?: Record<string, Record<string, unknown>>;
    };
    if (!raw.languages || typeof raw.languages !== 'object') {
      process.stderr.write(
        `check-locale-only-edits: ${LEDGER_REL} at ${base} has no "languages" object.\n` +
          'The ledger shape changed. Refusing to run, because with no protected keys\n' +
          'this gate reports OK on everything, including fabricated values.\n'
      );
      return 1;
    }
    ledger = raw.languages;
  } catch (e) {
    process.stderr.write(
      `check-locale-only-edits: cannot parse the naturalization ledger ${LEDGER_REL} at ${base}: ${
        (e as Error).message
      }\n` + 'Refusing to run without it: an unreadable ledger protects nothing.\n'
    );
    return 1;
  }
  const enBaseHash = flattenAndHash(JSON.parse(enBaseRaw) as Record<string, unknown>);
  let protectedAtBase = 0;
  let staleAtBase = 0;
  for (const entries of Object.values(ledger)) {
    for (const [k, v] of Object.entries(entries ?? {})) {
      if (enBaseHash[k] === undefined) continue; // orphan, as check:ci-i18n-naturalization counts it
      if (v === enBaseHash[k]) protectedAtBase++;
      else staleAtBase++;
    }
  }
  if (protectedAtBase === 0) {
    process.stderr.write(
      `check-locale-only-edits: the ledger at ${base} vouches for ZERO keys against its English.\n` +
        'Refusing to run: with nothing protected this gate passes every rewrite, fabrications included.\n'
    );
    return 1;
  }

  const locales = fs
    .readdirSync(path.join(REPO, DIR))
    .filter((f) => f.endsWith('.json') && !f.startsWith('.') && f !== 'en.json')
    .map((f) => f.replace(/\.json$/, ''));

  const findings: string[] = [];
  const emDashRepairs: string[] = [];
  const refMarkerRepairs: string[] = [];
  let checkedKeys = 0;

  for (const loc of locales) {
    const rel = `${DIR}/${loc}.json`;
    const baseRaw = gitShow(base, rel);
    if (!baseRaw) continue; // new locale file: nothing to compare against
    const now = flatten(JSON.parse(fs.readFileSync(path.join(REPO, rel), 'utf8')));
    const was = flatten(JSON.parse(baseRaw));
    const r = scanLocale(loc, was, now, enBase, enNow, ledger[loc] ?? {}, enBaseHash);
    findings.push(...r.findings);
    emDashRepairs.push(...r.emDashRepairs);
    refMarkerRepairs.push(...r.refMarkerRepairs);
    checkedKeys += r.checkedKeys;
  }

  if (refMarkerRepairs.length > 0) {
    // Printed for the same reason the em-dash advisory is: an exemption nobody can see is how an exemption becomes a blind spot.
    process.stdout.write(
      `check-locale-only-edits: ${refMarkerRepairs.length} locale value(s) exempted as ` +
        'reference-marker repairs\n(a locale-only `[n]` that English does not carry was ' +
        'removed, and nothing else changed):\n' +
        `${refMarkerRepairs.join('\n')}\n\n`
    );
  }

  if (emDashRepairs.length > 0) {
    // Printed, not silent. A widened exemption nobody can see is how an exemption becomes
    // a blind spot; this makes each use of it countable in the log.
    process.stdout.write(
      `check-locale-only-edits: ${emDashRepairs.length} locale value(s) exempted as em-dash repairs\n` +
        `(the dash was present at base and is gone now; check:ci-em-dash-surfaces requires this):\n` +
        `${emDashRepairs.join('\n')}\n\n`
    );
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
      'each backed by an English change or catch-up on a key the base ledger did not vouch for ' +
      `(${protectedAtBase} (locale, key) pairs protected at base, ${staleAtBase} stale there).\n`
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
