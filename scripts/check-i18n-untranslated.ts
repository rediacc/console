#!/usr/bin/env tsx
/**
 * A locale value that is byte-identical to English is an UNTRANSLATED PLACEHOLDER, not a
 * translation.
 *
 * ★ AND NO GATE COULD SEE IT, BECAUSE THE FALLBACK SATISFIES EVERY CHECK WE OWN. When a key is
 * missing, the sync/regen fills it with the ENGLISH TEXT so the key is PRESENT. Then:
 *
 *   - `cross-language-consistency` checks KEY PRESENCE          -> green
 *   - `check-i18n-placeholders` checks PLACEHOLDER PARITY       -> green (identical text has
 *                                                                  identical placeholders)
 *   - a diff-based translation delta (added keys + reworded English) -> BLIND: the key is
 *                                                                  neither new nor reworded
 *
 * ★★ "PRESENT" IS NOT "TRANSLATED." We were measuring presence and calling it coverage — the
 * same error as measuring that a call HAPPENED instead of WHERE it landed, and the same error as
 * a replica that comes up Ready and serves nothing.
 *
 * It shipped: `commands.repo.promote.confirm` — THE CONFIRMATION PROMPT FOR PROMOTING A FORK
 * INTO PRODUCTION — was English in all twelve locales. Users were asked to confirm a destructive
 * production cutover in a language they may not read.
 *
 * THE RULE: a locale value identical to English, whose English is longer than MIN_LENGTH, is a
 * failure. Short values (`OK`, `ID`, `Rediacc`) are legitimately identical and are below the
 * threshold. Anything else needs an ALLOWLIST ENTRY WITH A REASON — and the allowlist is itself
 * gated against the live key set, because an allowlist that names keys which no longer exist is
 * exactly the fail-open this repo has now found five times (#52, #53, #64, #65, #66).
 *
 * Usage:
 *   npx tsx scripts/check-i18n-untranslated.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = path.resolve(__dirname, '../packages/cli/src/i18n/locales');
const SOURCE = 'en';

/**
 * Below this, an identical value is not evidence of anything: "OK", "ID", "GUID", a bare flag
 * name, a product name. 30 characters is comfortably above every such string in the catalogue
 * and comfortably below the shortest real defect found (`repo.promote.revertHint`, 38).
 */
const MIN_LENGTH = 30;

/**
 * A value with NO NATURAL-LANGUAGE CONTENT cannot differ from English, ever.
 *
 * ★ A MECHANICAL PROPERTY, NOT AN ALLOWLIST. `errors.precondition.next.options.confirm.run` is
 * `rdc repo secret get {{repository}} --key {{key}}` — a pure command. Command paths, flags and
 * placeholders are ALL reproduced verbatim by the translation rules, so there is literally nothing
 * in the string to translate, and it is legitimately identical in all twelve locales BY
 * CONSTRUCTION. Same for `commands.subscription.repo.status.entry`, which is placeholders and
 * punctuation only.
 *
 * These could each be an allowlist entry. They should not be. ★★ AN ALLOWLIST YOU NEVER HAVE TO
 * MAINTAIN IS THE ONLY KIND THAT CANNOT GO STALE — and every exemption list in this repo that
 * failed open (#52, #53, #64, #65, #66) did so because it was maintained by hand and then was not.
 * So the gate DETECTS the property instead of enumerating its instances.
 *
 * The test: strip the placeholders, then look for any alphabetic word that is not `rdc`, not a live
 * command name, and not the body of a flag. If none remains, the string is pure command/format and
 * is exempt. If ANY prose word remains — "To revert:", "Examples:", "Subscription token is not
 * ready" — it is a translatable string and an identical value is the untranslated fallback.
 */
function liveCommandWords(): Set<string> {
  const treePath = path.resolve(__dirname, '../packages/cli/scripts/command-tree.json');
  const words = new Set<string>(['rdc']);
  const walk = (node: { name?: string; subcommands?: unknown[] }): void => {
    if (node.name) words.add(node.name.toLowerCase());
    for (const sub of (node.subcommands ?? []) as { name?: string; subcommands?: unknown[] }[]) {
      walk(sub);
    }
  };
  walk(JSON.parse(fs.readFileSync(treePath, 'utf-8')));
  return words;
}

const COMMAND_WORDS = liveCommandWords();

/** True when the string contains no translatable prose at all. */
function isPureCommandOrFormat(value: string): boolean {
  const withoutPlaceholders = value.replace(/\{\{\w+\}\}/g, ' ');

  // Flag bodies (`--key`, `-m`) are contract tokens, not prose.
  const withoutFlags = withoutPlaceholders.replace(/(^|\s)-{1,2}[a-zA-Z][\w-]*/g, ' ');

  for (const [word] of withoutFlags.matchAll(/[A-Za-z]{2,}/g)) {
    if (!COMMAND_WORDS.has(word.toLowerCase())) return false;
  }
  return true;
}

/**
 * Long values that are legitimately identical for a reason the detector above CANNOT see.
 *
 * ★ EMPTY, and that is the goal. Every entry here is a rule the gate stops enforcing, and it must
 * still be a live key (asserted below) so an exemption cannot outlive the string it exempts.
 */
const ALLOWED: Record<string, string> = {};

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

const load = (locale: string): Flat =>
  flatten(JSON.parse(fs.readFileSync(path.join(LOCALES_DIR, locale, 'cli.json'), 'utf-8')));

const english = load(SOURCE);
const locales = fs
  .readdirSync(LOCALES_DIR)
  .filter((name) => name !== SOURCE)
  .filter((name) => fs.existsSync(path.join(LOCALES_DIR, name, 'cli.json')))
  .sort();

const problems: string[] = [];

// The allowlist must not outlive the keys it exempts.
for (const key of Object.keys(ALLOWED)) {
  if (!(key in english)) {
    problems.push(
      `ALLOWED["${key}"] is stale: no such key in English. An exemption for a key that does not ` +
        'exist is a fail-open waiting for someone to reuse the name.'
    );
  }
  if (ALLOWED[key].trim().length < 30) {
    problems.push(`ALLOWED["${key}"] needs a real reason, not a placeholder.`);
  }
}

const untranslated = new Map<string, string[]>(); // key -> locales

for (const locale of locales) {
  for (const [key, value] of Object.entries(load(locale))) {
    const source = english[key];
    if (source === undefined) continue;
    if (key in ALLOWED) continue;
    if (source.length < MIN_LENGTH) continue;
    if (value !== source) continue;
    // Nothing in it to translate: it cannot differ from English, so an identical value is correct.
    if (isPureCommandOrFormat(source)) continue;

    const bucket = untranslated.get(key) ?? [];
    bucket.push(locale);
    untranslated.set(key, bucket);
  }
}

if (untranslated.size > 0 || problems.length > 0) {
  console.error('\x1b[31m✗ Untranslated locale values (identical to English)\x1b[0m\n');
  for (const problem of problems) console.error(`  ${problem}\n`);

  for (const [key, where] of [...untranslated].sort()) {
    const preview = english[key].replace(/\s+/g, ' ').slice(0, 88);
    console.error(`  ${key}\n      ${where.length}/${locales.length} locales: ${where.join(' ')}`);
    console.error(`      en (${english[key].length} chars): "${preview}${english[key].length > 88 ? '…' : ''}"\n`);
  }

  const values = [...untranslated.values()].reduce((sum, where) => sum + where.length, 0);
  console.error(
    `  ${untranslated.size} key(s), ${values} value(s). A value identical to English is the ` +
      'FALLBACK, not a translation.\n'
  );
  process.exit(1);
}

console.log(
  `\x1b[32m✓\x1b[0m No untranslated placeholders ` +
    `(${locales.length} locales, ${Object.keys(english).length} keys, min length ${MIN_LENGTH})`
);
