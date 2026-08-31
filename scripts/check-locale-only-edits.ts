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

function selftest(): number {
  let bad = 0;
  for (const c of REF_MARKER_CONTROLS) {
    const got = isRefMarkerRepair(c.was, c.now, c.en);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  if (bad > 0) {
    process.stderr.write(
      `check-locale-only-edits: ${bad} control(s) failed; the marker exemption cannot be trusted\n`
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
  const emDashRepairs: string[] = [];
  const refMarkerRepairs: string[] = [];
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

      // Backlog catch-up the LEDGER lied about. A key whose base value is byte-identical
      // to its base English was never actually translated, whatever the ledger claims,
      // and the ledger does make that claim: 369 keys across 12 locales were stamped
      // naturalized while still holding the English string. Trusting the stamp over the
      // data turns "translate the untranslated" into a gate failure, which is the exact
      // opposite of this gate's stated allowance two paragraphs up.
      //
      // This cannot hide a fabrication. A fabricated rewrite replaces a REAL translation,
      // so its base value is not English and this check does not apply to it. Proven on
      // the run that motivated it: 411 genuine rewrites were still reported and reverted
      // while these passed.
      if (was[key] === enBase[key]) continue;

      // An edit that ONLY removes an em dash is required by check:ci-em-dash-surfaces,
      // which is a blocking gate in the same chain. Without this the two gates are
      // mutually unsatisfiable: one demands the dash go, the other calls its removal an
      // unjustified rewrite. Deliberately narrow -- the values must be identical once the
      // dash and its surrounding spaces are normalised away, so a rewrite that also
      // changes wording is still reported.
      if (isRefMarkerRepair(was[key], now[key], enNow[key] ?? '')) {
        refMarkerRepairs.push(`  ${loc}  ${key}`);
        continue;
      }

      if (isEmDashRepair(was[key], now[key])) {
        emDashRepairs.push(`  ${loc}  ${key}`);
        continue;
      }
      findings.push(
        `  ${loc}  ${key}\n` +
          `      en (unchanged): ${JSON.stringify(enNow[key] ?? '<absent>').slice(0, 100)}\n` +
          `      was:            ${JSON.stringify(was[key]).slice(0, 100)}\n` +
          `      now:            ${JSON.stringify(now[key]).slice(0, 100)}`
      );
    }
  }

  if (refMarkerRepairs.length > 0) {
    // Printed for the same reason the em-dash advisory is: an exemption nobody can see
    // is how an exemption becomes a blind spot.
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
      'each either backed by an English change or not yet naturalized.\n'
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
