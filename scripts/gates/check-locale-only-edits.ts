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
 * kind: shared-step
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
import { exitWithMainIfEntryPoint } from '../lib/entry-point.js';

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

/**
 * True when the edit ONLY restores German umlauts and eszett that an earlier run wrote as ASCII
 * transliterations (ae, oe, ue, ss): "Gewaehrleistungen" -> "Gewährleistungen" (found
 * 2026-10-31 across 94 de keys of the legal pages).
 *
 * Like the reference-marker repair, the fix is a locale-only edit with no English change, and
 * the gate's remedy cannot apply inside a PR, so without an exemption the correct spelling is
 * unshippable. NARROW BY CONSTRUCTION: transliterate the NEW value back (ä->ae, ö->oe, ü->ue,
 * ß->ss; a capital becomes AE/OE/UE when the next letter is upper case, else Ae/Oe/Ue) and the
 * result must equal the OLD value exactly. No other byte may move, so no wording, number or
 * fact can pass through here.
 */
export function isDiacriticRepair(was: string, now: string): boolean {
  if (was === now || !/[äöüÄÖÜß]/.test(now)) return false;
  const lower: Record<string, string> = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' };
  const upper: Record<string, string> = { Ä: 'A', Ö: 'O', Ü: 'U' };
  // Walk both values together: every character is either unchanged, or an umlaut / eszett in
  // NOW standing where OLD has its transliteration. A value that already mixed both is fine.
  let j = 0;
  for (let i = 0; i < now.length; i++) {
    const c = now[i];
    if (was[j] === c) {
      j += 1;
      continue;
    }
    let translit: string | undefined;
    if (c in lower) translit = lower[c];
    else if (c in upper) {
      const next = now[i + 1] ?? '';
      translit = upper[c] + (next !== next.toLowerCase() ? 'E' : 'e');
    }
    if (translit === undefined || was.slice(j, j + translit.length) !== translit) return false;
    j += translit.length;
  }
  return j === was.length;
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

/** A naturalization mask sentinel, `⟦0⟧`, as private/growth/i18n_pipeline/mask.py writes it. */
const SENTINEL = /\u27e6\d+\u27e7/g;

/** The shape of a restored product name: one whitespace-free token that starts with a capital, so a lowercase common word (`lisanslar`, `rakipler`) is not a name. Apostrophe suffixes (`Rediacc'ın`) stay allowed. */
const PRODUCT_NAME_TOKEN = /^\p{Lu}[\p{L}\p{N}'\u2019_-]*$/u;

/**
 * The masked invariants that CANNOT pass the capital-letter test, measured against the pipeline's
 * `PROPER_NOUNS` (private/growth/www_pipeline/adapters/json_adapter.py) and `spans.py`: the
 * lowercase and digit-bearing names, the two multi-word ones and a typographic double quote, each of which the mask restores byte for byte. A closed list, not a
 * looser shape, because a shape loose enough to take `btrfs` also takes `lisanslar`.
 */
const MASKED_LITERALS = new Set([
  'btrfs',
  'ext4',
  'aes-xts',
  'dm-crypt',
  'rdc',
  'renet',
  'SOC 2',
  'ISO 27001',
  '\u201c',
  '\u201d',
]);

/** At most this many characters may stand where one sentinel stood. */
const SENTINEL_REPLACEMENT_MAX = 40;

/**
 * True when the edit ONLY replaces leaked `⟦n⟧` mask sentinels with the words they stood
 * for (or removes them), and changes no other byte.
 *
 * THE CASE, found 2026-10-08. The naturalization pipeline masks product names as `⟦n⟧`
 * before the model call and restores them after; a sentinel the unit's own mask map did
 * not know survived the restore and shipped. ja
 * `pages.solutionPages.migrationSafety.techDiff.description` read "⟦0⟧は復号しません" and
 * tr `pages.resourcesBrief.verifiedBackups.toc.items.5` read "⟦0⟧ vs rakipler", each a
 * literal `⟦0⟧` on the page. check:ci-i18n-placeholders now refuses them, and the repair
 * is a locale-only edit to a key the base ledger vouches for, which this gate refuses: the
 * two gates were mutually unsatisfiable, exactly as with the em dash.
 *
 * NARROW BY CONSTRUCTION, like the reference-marker rule and unlike the em-dash one. The
 * OLD value is split at its sentinels, and the NEW value must be those literal segments,
 * byte for byte and in order, with only the gaps where the sentinels stood filled. Each
 * gap holds at most SENTINEL_REPLACEMENT_MAX characters of a name, never a sentence: no
 * sentence or clause punctuation, no line break, no sentinel, and it is either a span of
 * the English value verbatim or one whitespace-free capitalised token (a product name, which the mask
 * map restores and the English may not carry), so no run of words is written in. The English value must not
 * carry the sentinel (a real one would be English's own text), and the NEW value must
 * carry no leaked sentinel at all, so swapping `⟦0⟧` for `⟦1⟧` is not a repair. A rewrite
 * that also drops a sentinel moves a byte outside the gaps and stays red.
 */
export function isSentinelRepair(was: string, now: string, en: string): boolean {
  const enTokens = new Set(en.match(SENTINEL) ?? []);
  const wasTokens = was.match(SENTINEL) ?? [];
  if (wasTokens.length === 0) return false;
  if (wasTokens.some((t) => enTokens.has(t))) return false;
  if ((now.match(SENTINEL) ?? []).some((t) => !enTokens.has(t))) return false;
  const segments = was.split(SENTINEL);
  const escape = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const shape = new RegExp(
    `^${segments.map(escape).join(`([^\\n\\r\\u2028\\u2029]{0,${SENTINEL_REPLACEMENT_MAX}}?)`)}$`,
    'u'
  );
  const m = shape.exec(now);
  if (!m) return false;
  return m
    .slice(1)
    .every(
      (gap) =>
        !/[.!?;:,\u3002\uff01\uff1f\uff1b\uff1a\uff0c\u3001\u27e6\u27e7<>]/u.test(gap) &&
        (gap === '' || en.includes(gap) || PRODUCT_NAME_TOKEN.test(gap) || MASKED_LITERALS.has(gap))
    );
}

/**
 * True when the new locale value is BYTE-IDENTICAL to the English value at the same key,
 * with English unchanged between base and HEAD.
 *
 * THE CASE, found 2026-10-08. An i18n audit restored translated source and report titles
 * (`pages.solutionPages.kubernetesClusterMobility.problem.statCallouts.*.source`, 13 values
 * in ar, es, pt, ru and zh) to the exact English string, because a cited title must stay
 * findable under the name its publisher gave it. The keys were current at base, so the
 * correct fix was refused.
 *
 * WHY THIS CANNOT CARRY A FABRICATION: the new bytes are English's own bytes at the same
 * key, so no number, fact or word can enter that English does not already state. A string
 * one word away from English is not exempt.
 *
 * WHAT IT DOES WIDEN, stated rather than hidden: a run that overwrites a GOOD translation
 * with the English string passes here (the reference-marker rule above refused exactly
 * that convergence). That is an untranslated value, not an invented one, and every use is
 * printed as an advisory below so a wrongful revert is countable in the log.
 */
export function isRestoredToEnglish(
  now: string,
  enBase: string | undefined,
  enNow: string | undefined
): boolean {
  return enNow !== undefined && enBase === enNow && now === enNow;
}

/** Controls for the restore-to-English exemption, run with `--selftest`. */
const RESTORE_CONTROLS: {
  name: string;
  now: string;
  enBase?: string;
  enNow?: string;
  want: boolean;
}[] = [
  {
    name: 'the real case: a translated report title restored to the exact English title',
    now: 'Flexera 2024 State of the Cloud Report',
    enBase: 'Flexera 2024 State of the Cloud Report',
    enNow: 'Flexera 2024 State of the Cloud Report',
    want: true,
  },
  {
    name: 'CONTROL: a near-English string (one word differs) is NOT exempt',
    now: 'Flexera 2025 State of the Cloud Report',
    enBase: 'Flexera 2024 State of the Cloud Report',
    enNow: 'Flexera 2024 State of the Cloud Report',
    want: false,
  },
  {
    name: 'CONTROL: English absent at the key is NOT exempt',
    now: 'Flexera 2024 State of the Cloud Report',
    want: false,
  },
];

/** Controls for the sentinel exemption, run with `--selftest` through the same function. */
const SENTINEL_CONTROLS: { name: string; was: string; now: string; en: string; want: boolean }[] = [
  {
    name: 'the real tr case: ⟦0⟧ restored to the product name, nothing else moved',
    was: '\u27e60\u27e7 vs rakipler: teknik bazında (fiyat değil)',
    now: 'Rediacc vs rakipler: teknik bazında (fiyat değil)',
    en: 'How we stack up against other vendors on the tech, not the price tag',
    want: true,
  },
  {
    name: 'the real ja case: ⟦0⟧ inside a sentence restored',
    was: '露出ウィンドウを作ります。\u27e60\u27e7は復号しません。<span class="sp-emphasis">移行</span>。',
    now: '露出ウィンドウを作ります。Rediaccは復号しません。<span class="sp-emphasis">移行</span>。',
    en: 'That leaves a window. We never unlock anything. <span class="sp-emphasis">sealed blocks</span>.',
    want: true,
  },
  {
    name: 'a leaked sentinel removed outright, nothing else moved',
    was: 'Kurulum \u27e61\u27e7tamamlandı',
    now: 'Kurulum tamamlandı',
    en: 'Setup complete',
    want: true,
  },
  {
    name: 'CONTROL: a rewrite that also drops the sentinel is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler: teknik bazında (fiyat değil)',
    now: 'Rediacc ve rakipleri: fiyat değil',
    en: 'How we stack up against other vendors on the tech, not the price tag',
    want: false,
  },
  {
    name: 'CONTROL: sentinel restored AND a number changed elsewhere is NOT exempt',
    was: '\u27e60\u27e7 1 Floating-Lizenz',
    now: 'Rediacc 10 Floating-Lizenz',
    en: 'Rediacc 1 Floating license',
    want: false,
  },
  {
    name: 'CONTROL: a whole clause smuggled into the sentinel gap is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'Rediacc, 25 lisans dahil, vs rakipler',
    en: 'How we stack up against other vendors',
    want: false,
  },
  {
    name: 'CONTROL: words that are not in the English written into the sentinel gap are NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'Rediacc 25 lisans dahil vs rakipler',
    en: 'How we stack up against other vendors',
    want: false,
  },
  {
    name: 'a product name with a Turkish apostrophe suffix is exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: "Rediacc'ın vs rakipler",
    en: 'How we stack up against other vendors',
    want: true,
  },
  {
    name: 'CONTROL: one lowercase common word written into the sentinel gap is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'lisanslar vs rakipler',
    en: 'How we stack up against other vendors',
    want: false,
  },
  {
    name: 'a masked lowercase product name (btrfs) restored is exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'btrfs vs rakipler',
    en: 'How we stack up against other vendors',
    want: true,
  },
  {
    name: 'a masked multi-word proper noun (SOC 2) restored is exempt',
    was: '\u27e60\u27e7 uyumluluğu',
    now: 'SOC 2 uyumluluğu',
    en: 'Compliance',
    want: true,
  },
  {
    name: 'a masked {{var}} placeholder restored is exempt',
    was: '\u27e60\u27e7 lisans',
    now: '{{count}} lisans',
    en: '{{count}} licenses',
    want: true,
  },
  {
    name: 'CONTROL: a {{var}} placeholder the English never had is NOT exempt',
    was: '\u27e60\u27e7 lisans',
    now: '{{evil}} lisans',
    en: '{{count}} licenses',
    want: false,
  },
  {
    name: 'CONTROL: a lowercase word that is not a masked noun (rdcx) is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'rdcx vs rakipler',
    en: 'How we stack up against other vendors',
    want: false,
  },
  {
    name: 'a multi-word gap that is a verbatim span of the English is exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'other vendors vs rakipler',
    en: 'How we stack up against other vendors',
    want: true,
  },
  {
    name: 'CONTROL: a sentinel swapped for another sentinel is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: '\u27e61\u27e7 vs rakipler',
    en: 'How we stack up against other vendors',
    want: false,
  },
  {
    name: 'CONTROL: an edit with no sentinel at base is NOT exempt',
    was: '1 플로팅 라이선스',
    now: '10 플로팅 라이선스',
    en: '1 Floating license',
    want: false,
  },
  {
    name: 'CONTROL: a line break smuggled into the sentinel gap is NOT exempt',
    was: '\u27e60\u27e7 vs rakipler',
    now: 'Rediacc\r vs rakipler',
    en: 'How we stack up against other vendors',
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
  diacriticRepairs: string[];
  sentinelRepairs: string[];
  englishRestores: string[];
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
  const out: LocaleScan = {
    findings: [],
    emDashRepairs: [],
    refMarkerRepairs: [],
    diacriticRepairs: [],
    sentinelRepairs: [],
    englishRestores: [],
    checkedKeys: 0,
  };
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

    if (isSentinelRepair(was[key], now[key], enNow[key] ?? '')) {
      out.sentinelRepairs.push(`  ${loc}  ${key}`);
      continue;
    }

    if (isRestoredToEnglish(now[key], enBase[key], enNow[key])) {
      out.englishRestores.push(`  ${loc}  ${key}`);
      continue;
    }

    if (isDiacriticRepair(was[key], now[key])) {
      out.diacriticRepairs.push(`  ${loc}  ${key}`);
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

const DIACRITIC_CONTROLS: { name: string; was: string; now: string; want: boolean }[] = [
  {
    name: 'diacritic: Gewaehrleistungen -> Gewährleistungen is a repair',
    was: 'Keine Gewaehrleistungen fuer Ausfaelle.',
    now: 'Keine Gewährleistungen für Ausfälle.',
    want: true,
  },
  {
    name: 'diacritic: ausschliesslich and Groesse (ß, ö) are a repair',
    was: 'ausschliesslich die Groesse',
    now: 'ausschließlich die Größe',
    want: true,
  },
  {
    name: 'diacritic: ALL-CAPS AE -> Ä is a repair',
    was: 'GEWAEHRLEISTUNG',
    now: 'GEWÄHRLEISTUNG',
    want: true,
  },
  {
    name: 'CONTROL diacritic: a word changed beside the umlaut is not a repair',
    was: 'Keine Gewaehrleistungen fuer Ausfaelle.',
    now: 'Keine Garantien für Ausfälle.',
    want: false,
  },
  {
    name: 'CONTROL diacritic: a number changed beside the umlaut is not a repair',
    was: 'fuer 30 Tage',
    now: 'für 60 Tage',
    want: false,
  },
  {
    name: 'CONTROL diacritic: an unchanged value is not a repair',
    was: 'für alle',
    now: 'für alle',
    want: false,
  },
];

function selftest(): number {
  let bad = 0;
  for (const c of DIACRITIC_CONTROLS) {
    const got = isDiacriticRepair(c.was, c.now);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  for (const c of REF_MARKER_CONTROLS) {
    const got = isRefMarkerRepair(c.was, c.now, c.en);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  for (const c of SENTINEL_CONTROLS) {
    const got = isSentinelRepair(c.was, c.now, c.en);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  for (const c of RESTORE_CONTROLS) {
    const got = isRestoredToEnglish(c.now, c.enBase, c.enNow);
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  {
    const key = 'pricing.license';
    const vouched = { [key]: EN_HASH[key] };
    const restore = scanLocale(
      'xx',
      { [key]: '1 플로팅 라이선스' },
      { [key]: EN[key] },
      EN,
      EN,
      vouched,
      EN_HASH
    );
    const ok = restore.findings.length === 0 && restore.englishRestores.length === 1;
    if (!ok) bad++;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  restore-to-English on a vouched key is exempted by scanLocale\n`
    );
    const near = scanLocale(
      'xx',
      { [key]: '1 플로팅 라이선스' },
      { [key]: '10 Floating license' },
      EN,
      EN,
      vouched,
      EN_HASH
    );
    const red = near.findings.length === 1 && near.englishRestores.length === 0;
    if (!red) bad++;
    process.stdout.write(
      `  ${red ? 'PASS' : 'FAIL'}  CONTROL: a near-English rewrite is still RED through scanLocale\n`
    );
  }
  // Through scanLocale too: the exemption must be WIRED, not merely correct in isolation.
  {
    const key = 'pricing.license';
    const wired = scanLocale(
      'xx',
      { [key]: '\u27e60\u27e7 1 플로팅 라이선스' },
      { [key]: 'Rediacc 1 플로팅 라이선스' },
      EN,
      EN,
      { [key]: EN_HASH[key] },
      EN_HASH
    );
    const ok = wired.findings.length === 0 && wired.sentinelRepairs.length === 1;
    if (!ok) bad++;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  sentinel repair on a key the base ledger vouches for is exempted by scanLocale\n`
    );
    const rewrite = scanLocale(
      'xx',
      { [key]: '\u27e60\u27e7 1 플로팅 라이선스' },
      { [key]: 'Rediacc 10 플로팅 라이선스' },
      EN,
      EN,
      { [key]: EN_HASH[key] },
      EN_HASH
    );
    const red = rewrite.findings.length === 1 && rewrite.sentinelRepairs.length === 0;
    if (!red) bad++;
    process.stdout.write(
      `  ${red ? 'PASS' : 'FAIL'}  CONTROL: sentinel restored plus a rewrite is still RED through scanLocale\n`
    );
  }
  for (const p of LEDGER_PROBES) {
    const r = scanLocale('xx', p.was, p.now, EN, EN, p.ledger, EN_HASH);
    const got = r.findings
      .map((f) => f.trim().split(/\s+/)[1])
      .sort((a, b) => Number(a > b) - Number(a < b));
    const ok =
      JSON.stringify(got) ===
      JSON.stringify([...p.want].sort((a, b) => Number(a > b) - Number(a < b)));
    if (!ok) bad++;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  ${p.name}${ok ? '' : ` (reported ${JSON.stringify(got)})`}\n`
    );
  }
  if (bad > 0) {
    process.stderr.write(
      `check-locale-only-edits: ${bad} control(s) failed; an exemption (marker, sentinel, restore-to-English) or the base-ledger rule cannot be trusted\n`
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
  const diacriticRepairs: string[] = [];
  const sentinelRepairs: string[] = [];
  const englishRestores: string[] = [];
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
    diacriticRepairs.push(...r.diacriticRepairs);
    sentinelRepairs.push(...r.sentinelRepairs);
    englishRestores.push(...r.englishRestores);
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

  if (diacriticRepairs.length > 0) {
    process.stdout.write(
      `check-locale-only-edits: ${diacriticRepairs.length} locale value(s) exempted as ` +
        'diacritic repairs\n(ASCII transliterations ae/oe/ue/ss restored to ä/ö/ü/ß, and nothing ' +
        'else changed):\n' +
        `${diacriticRepairs.join('\n')}\n\n`
    );
  }

  if (englishRestores.length > 0) {
    // Printed: this is the widest of the exemptions, and a wrongful revert of a good
    // translation to English would pass through it, so every use stays countable.
    process.stdout.write(
      `check-locale-only-edits: ${englishRestores.length} locale value(s) exempted as ` +
        'restored to the exact English value at the same key\n(English unchanged; no byte ' +
        'English does not already carry; confirm each is a title or name meant to stay English):\n' +
        `${englishRestores.join('\n')}\n\n`
    );
  }

  if (sentinelRepairs.length > 0) {
    // Printed for the same reason as the two advisories around it.
    process.stdout.write(
      `check-locale-only-edits: ${sentinelRepairs.length} locale value(s) exempted as ` +
        'mask-sentinel repairs\n(a leaked `\u27e6n\u27e7` was replaced by a name or removed, ' +
        'and no other byte changed):\n' +
        `${sentinelRepairs.join('\n')}\n\n`
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

// Run only as the entry point: scanLocale and isProtectedAtBase are exported, and an
// unguarded call here exited the importing process the moment it loaded this module.
exitWithMainIfEntryPoint(import.meta.filename, main);
