#!/usr/bin/env tsx
/**
 * Placeholder parity: every locale's `{{placeholders}}` must match English's, exactly.
 *
 * ★ NOTHING CHECKED THIS. `cross-language-consistency` checks that a KEY EXISTS in every
 * locale; it never looks at what the value INTERPOLATES. So a translation could drop a
 * placeholder — or invent one that never interpolates and renders literally to the user as
 * the raw text `{{regions}}` — and every gate stayed green. A missing key is loud. A mangled
 * interpolation is silent.
 *
 * It had already happened. `errors.remoteNotFound` in pt, it and ko dropped `{{clusters}}`:
 *
 *   en: "{{name}}" is not a known machine, storage, or cluster.
 *       Machines: {{machines}}. Storages: {{storages}}. Clusters: {{clusters}}
 *   it: "{{name}}" non e una macchina o uno storage conosciuto.
 *       Macchine: {{machines}}. Storage: {{storages}}
 *
 * So the error whose entire job is to LIST THE VALID NAMES never listed the clusters — in
 * exactly the case where the name you typed was meant to be one. The message is least useful
 * precisely when it is most needed, and it does not even admit clusters exist.
 *
 * Two failure directions, both checked:
 *   DROPPED  — the locale omits a placeholder English has. Information is silently lost.
 *   INVENTED — the locale adds one English does not have. It never interpolates, so the user
 *              is shown the literal `{{foo}}`.
 *
 * Compared as SETS, not counts: a language may legitimately repeat or reorder a placeholder
 * ("{{name}} ... {{name}}"), but it may never introduce or lose one.
 *
 * MASK SENTINELS are a third interpolation-shaped token checked here. The naturalization
 * pipeline (private/growth/i18n_pipeline/mask.py) hides product names, HTML and code behind
 * `⟦n⟧` (U+27E6 digits U+27E7) before the model call and restores them after. A sentinel the
 * unit's own mask map does not know survives the restore, and it shipped: six ar values,
 * ja `pages.solutionPages.migrationSafety.techDiff.description` ("⟦0⟧は復号しません") and tr
 * `pages.resourcesBrief.verifiedBackups.toc.items.5` ("⟦0⟧ vs rakipler"), each rendering a
 * literal `⟦0⟧` where the product name belongs. No gate looked. Any `⟦n⟧` in a locale value
 * that English does not carry is now an INVENTED sentinel. The controls below run on EVERY
 * invocation, before the scan, so a regex that silently stopped matching fails the gate
 * instead of reporting a clean tree.
 *
 * Usage:
 *   npx tsx scripts/gates/check-i18n-placeholders.ts
 *
 * ---- gate ----
 * step: i18n placeholders
 * needs: node, submodules
 * lane: quality-i18n
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');

const SOURCE = 'en';

/**
 * Every translation set in the repo, not just the CLI's.
 *
 * This gate used to scan `packages/cli/src/i18n/locales` alone while its own
 * docstring promised placeholder parity for "every locale" — so www (3311 keys
 * x 12 locales) and the account portal (2254 x 12) were never checked at all.
 * Two real defects were sitting in www: ja and zh both INVENT a
 * {{companyName}} placeholder that English does not have, in a page meta
 * description. The call site passes only English's params, so those render to
 * the reader as the literal text "{{companyName}}".
 *
 * `flat` sets keep one JSON per locale (www/ja.json); `dir` sets keep a
 * directory per locale holding one or more JSON files (cli/ja/cli.json).
 */
interface LocaleSet {
  name: string;
  dir: string;
  layout: 'flat' | 'dir';
  /** The `.git` entry of the private submodule the set lives in; absent for in-tree sets. */
  submoduleMarker?: string;
}

const LOCALE_SETS: LocaleSet[] = [
  { name: 'cli', dir: path.join(ROOT, 'packages/cli/src/i18n/locales'), layout: 'dir' },
  { name: 'www', dir: path.join(ROOT, 'packages/www/src/i18n/translations'), layout: 'flat' },
  {
    name: 'account-web',
    dir: submodulePath('private/account/web/src/i18n/locales'),
    layout: 'dir',
    submoduleMarker: submodulePath('private/account/.git'),
  },
];

type Flat = Record<string, string>;

function flatten(node: unknown, prefix = '', out: Flat = {}): Flat {
  if (typeof node === 'string') {
    out[prefix] = node;
    return out;
  }
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      flatten(value, prefix ? `${prefix}.${key}` : key, out);
    }
  }
  return out;
}

/** Load one locale from a set, merging every JSON file a `dir` layout holds. */
function load(set: LocaleSet, locale: string): Flat {
  if (set.layout === 'flat') {
    return flatten(JSON.parse(fs.readFileSync(path.join(set.dir, `${locale}.json`), 'utf-8')));
  }
  const localeDir = path.join(set.dir, locale);
  const out: Flat = {};
  for (const file of fs.readdirSync(localeDir).filter((f) => f.endsWith('.json'))) {
    const stem = file.replace(/\.json$/, '');
    flatten(JSON.parse(fs.readFileSync(path.join(localeDir, file), 'utf-8')), stem, out);
  }
  return out;
}

/** Locale names in a set, excluding English. */
function localesOf(set: LocaleSet): string[] {
  if (set.layout === 'flat') {
    return fs
      .readdirSync(set.dir)
      .filter((f) => f.endsWith('.json') && f !== `${SOURCE}.json`)
      .map((f) => f.replace(/\.json$/, ''))
      .sort();
  }
  return fs
    .readdirSync(set.dir)
    .filter((name) => name !== SOURCE)
    .filter((name) => fs.statSync(path.join(set.dir, name)).isDirectory())
    .sort();
}

/** The set of `{{placeholder}}` names in a string. */
export function placeholders(value: string): Set<string> {
  return new Set([...value.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]));
}

/** The set of naturalization mask sentinels (`⟦0⟧`, `⟦12⟧`) in a string, as written. */
export function sentinels(value: string): Set<string> {
  return new Set([...value.matchAll(/\u27e6\d+\u27e7/g)].map((m) => m[0]));
}

export interface Verdict {
  dropped: string[];
  invented: string[];
  /** Mask sentinels in the locale value that English does not carry. */
  leakedSentinels: string[];
}

/** The per-value comparison, shared by the real scan and the controls. */
export function compareValue(source: string, value: string): Verdict {
  const want = placeholders(source);
  const got = placeholders(value);
  const enSentinels = sentinels(source);
  return {
    dropped: [...want].filter((p) => !got.has(p)).sort((a, b) => Number(a > b) - Number(a < b)),
    invented: [...got].filter((p) => !want.has(p)).sort((a, b) => Number(a > b) - Number(a < b)),
    leakedSentinels: [...sentinels(value)]
      .filter((t) => !enSentinels.has(t))
      .sort((a, b) => Number(a > b) - Number(a < b)),
  };
}

/** True when the verdict is a finding. */
function isViolation(v: Verdict): boolean {
  return v.dropped.length + v.invented.length + v.leakedSentinels.length > 0;
}

/**
 * Controls, run on every invocation through `compareValue` itself. Both directions: the
 * planted sentinel must fire, and the same value with the product name restored, or with
 * look-alike brackets that are not a sentinel, must stay silent.
 */
const CONTROLS: { name: string; en: string; loc: string; fires: boolean }[] = [
  {
    name: 'planted: the shipped tr leak "⟦0⟧ vs rakipler" fires',
    en: 'How we stack up against other vendors on the tech, not the price tag',
    loc: '\u27e60\u27e7 vs rakipler: teknik bazında (fiyat değil)',
    fires: true,
  },
  {
    name: 'planted: a multi-digit sentinel beside a correct placeholder fires',
    en: 'Hello {{name}}',
    loc: 'Merhaba {{name}} \u27e612\u27e7',
    fires: true,
  },
  {
    name: 'control: the same tr value with the product name restored is silent',
    en: 'How we stack up against other vendors on the tech, not the price tag',
    loc: 'Rediacc vs rakipler: teknik bazında (fiyat değil)',
    fires: false,
  },
  {
    name: 'control: look-alike brackets without digits, and plain [0], are silent',
    en: 'See note [0]',
    loc: 'Nota bakın [0] \u27e6x\u27e7',
    fires: false,
  },
  {
    name: 'planted: a dropped {{placeholder}} still fires (the original rule)',
    en: 'Clusters: {{clusters}}',
    loc: 'Kümeler:',
    fires: true,
  },
];

interface Violation extends Verdict {
  set: string;
  locale: string;
  key: string;
}

/** The scan. Run only as the entry point, so importing the exported helpers never exits. */
function main(): void {
  let controlFailures = 0;
  for (const c of CONTROLS) {
    const fired = isViolation(compareValue(c.en, c.loc));
    if (fired !== c.fires) {
      controlFailures++;
      console.error(`  FAIL  ${c.name} (fired=${fired})`);
    }
  }
  if (controlFailures > 0) {
    console.error(
      `\x1b[31m✗ ${controlFailures} of ${CONTROLS.length} control(s) failed; ` +
        'this gate cannot be trusted to see placeholders or mask sentinels.\x1b[0m'
    );
    process.exit(1);
  }

  const violations: Violation[] = [];
  let scannedLocales = 0;
  let scannedSets = 0;
  const missingSets: string[] = [];

  for (const set of LOCALE_SETS) {
    // A private submodule that is not checked out skips LOCALLY and is a hard failure in CI (scripts/lib/submodule-presence.ts): a CI checkout that lost it would otherwise report parity for a set it never read.
    if (
      set.submoduleMarker &&
      !requireSubmodule(`${set.name} placeholder parity`, [set.submoduleMarker])
    ) {
      continue;
    }
    if (!fs.existsSync(set.dir)) {
      // An in-tree set, or a set inside a checked-out submodule, that is missing was moved or deleted. Skipping it would report parity for a tree nobody read.
      missingSets.push(`[${set.name}] ${path.relative(ROOT, set.dir)} does not exist`);
      continue;
    }
    scannedSets++;
    const english = load(set, SOURCE);
    for (const locale of localesOf(set)) {
      scannedLocales++;
      const strings = load(set, locale);
      for (const [key, value] of Object.entries(strings)) {
        const source = english[key];
        // A key the source does not have is `cross-language-consistency`'s business, not ours.
        if (source === undefined) continue;

        const verdict = compareValue(source, value);
        if (isViolation(verdict)) {
          violations.push({ set: set.name, locale, key, ...verdict });
        }
      }
    }
  }

  if (missingSets.length > 0) {
    console.error('\x1b[31m✗ Configured locale set(s) missing\x1b[0m\n');
    for (const line of missingSets) console.error(`  ${line}`);
    console.error(
      '\n  The tree was moved, renamed or deleted; update LOCALE_SETS in ' +
        'scripts/gates/check-i18n-placeholders.ts to match it.\n'
    );
    process.exit(1);
  }

  if (scannedLocales === 0) {
    console.error('\x1b[31m✗ no locale file was scanned; this gate is not seeing the tree.\x1b[0m');
    process.exit(1);
  }

  if (violations.length > 0) {
    console.error('\x1b[31m✗ Placeholder parity violations\x1b[0m\n');
    for (const { set, locale, key, dropped, invented, leakedSentinels } of violations) {
      const parts: string[] = [];
      if (dropped.length > 0) {
        parts.push(
          `DROPPED ${dropped.map((p) => `{{${p}}}`).join(', ')} (information silently lost)`
        );
      }
      if (invented.length > 0) {
        parts.push(
          `INVENTED ${invented.map((p) => `{{${p}}}`).join(', ')} (renders literally to the user)`
        );
      }
      if (leakedSentinels.length > 0) {
        parts.push(
          `UNRESTORED mask sentinel ${leakedSentinels.join(', ')} (renders literally; ` +
            'replace it with the words English has at that spot, usually the product name)'
        );
      }
      console.error(`  [${set}] ${locale}  ${key}\n      ${parts.join('\n      ')}`);
    }
    console.error(
      `\n  ${violations.length} violation(s). A locale's placeholders must match English's exactly,\n` +
        '  and no naturalization mask sentinel may survive into a shipped value.\n'
    );
    process.exit(1);
  }

  console.log(
    `\x1b[32m✓\x1b[0m Placeholder parity holds, no mask sentinel leaked ` +
      `(${scannedSets} of ${LOCALE_SETS.length} sets, ${scannedLocales} locale files scanned, ` +
      `${CONTROLS.length} controls passed)`
  );
}

if (path.resolve(process.argv[1] ?? '') === path.resolve(fileURLToPath(import.meta.url))) {
  main();
}
