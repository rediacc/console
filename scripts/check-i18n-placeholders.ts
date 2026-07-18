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
 * Usage:
 *   npx tsx scripts/check-i18n-placeholders.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

/** Every locale directory holding a cli.json, English first. */
const LOCALES_DIR = path.join(ROOT, 'packages/cli/src/i18n/locales');
const SOURCE = 'en';

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

function load(locale: string): Flat {
  const file = path.join(LOCALES_DIR, locale, 'cli.json');
  return flatten(JSON.parse(fs.readFileSync(file, 'utf-8')));
}

/** The set of `{{placeholder}}` names in a string. */
function placeholders(value: string): Set<string> {
  return new Set([...value.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]));
}

const english = load(SOURCE);
const locales = fs
  .readdirSync(LOCALES_DIR)
  .filter((name) => name !== SOURCE)
  .filter((name) => fs.existsSync(path.join(LOCALES_DIR, name, 'cli.json')))
  .sort();

interface Violation {
  locale: string;
  key: string;
  dropped: string[];
  invented: string[];
}

const violations: Violation[] = [];

for (const locale of locales) {
  const strings = load(locale);
  for (const [key, value] of Object.entries(strings)) {
    const source = english[key];
    // A key the source does not have is `cross-language-consistency`'s business, not ours.
    if (source === undefined) continue;

    const want = placeholders(source);
    const got = placeholders(value);
    const dropped = [...want].filter((p) => !got.has(p)).sort();
    const invented = [...got].filter((p) => !want.has(p)).sort();

    if (dropped.length > 0 || invented.length > 0) {
      violations.push({ locale, key, dropped, invented });
    }
  }
}

if (violations.length > 0) {
  console.error('\x1b[31m✗ Placeholder parity violations\x1b[0m\n');
  for (const { locale, key, dropped, invented } of violations) {
    const parts: string[] = [];
    if (dropped.length > 0) {
      parts.push(`DROPPED ${dropped.map((p) => `{{${p}}}`).join(', ')} (information silently lost)`);
    }
    if (invented.length > 0) {
      parts.push(
        `INVENTED ${invented.map((p) => `{{${p}}}`).join(', ')} (renders literally to the user)`
      );
    }
    console.error(`  ${locale}  ${key}\n      ${parts.join('\n      ')}`);
  }
  console.error(
    `\n  ${violations.length} violation(s). A locale's placeholders must match English's exactly.\n`
  );
  process.exit(1);
}

const checked = locales.length * Object.keys(english).length;
console.log(
  `\x1b[32m✓\x1b[0m Placeholder parity holds ` +
    `(${locales.length} locales, ${Object.keys(english).length} keys, ${checked} comparisons)`
);
