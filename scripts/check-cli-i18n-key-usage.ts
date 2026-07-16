#!/usr/bin/env node
/**
 * CLI Translation Key Usage Check (STATIC half)
 *
 * The www sibling (check-translation-key-usage.ts) scans packages/www against
 * packages/www/src/i18n/translations/en.json and never looks at the CLI. That
 * blind spot let `rdc machine status --help` ship a raw key
 * (`help.machine.containers`) with no gate to catch it — see
 * docs/design/spec/12-carried-debt.md, "Gates 10 and 11".
 *
 * This gate closes the static side in BOTH directions:
 *
 *   FORWARD (missing keys): every t('literal') / t("literal") in
 *   packages/cli/src must resolve to a leaf in the CLI's English catalogue
 *   (packages/cli/src/i18n/locales/en/cli.json). Unknown keys render as their own
 *   raw key string at runtime, exactly the failure this catches.
 *
 *   ORPHAN (dead keys): every leaf in en/cli.json should be reachable from some
 *   t('literal') in the source. Leaves that no literal call references are dead
 *   weight — they cost 13-locale translation effort and mask copy-paste debt
 *   (the migrate command inherited pull's `optionFrom` even though migrate has
 *   no --from flag; the machine is derived from the ref).
 *
 * Honesty about coverage (the check-lockfile.sh precedent — a gate that
 * silently skips half its subject overstates its coverage): keys built from
 * template literals (t(`commands.${x}`)) or variables (t(key)) CANNOT be
 * resolved statically. The FORWARD half skips them, but the skip is COUNTED and
 * printed so the reported coverage is honest. The RUNTIME half
 * (check-cli-i18n-help-render.ts) walks the live Commander tree and catches the
 * dynamically-built help keys this half must skip.
 *
 * The ORPHAN half has the mirror-image blind spot: a key referenced ONLY through
 * a dynamic t() call (t(`commands.sync.${mode}.completed`), t(successKey), ...)
 * looks unreferenced to a static scan and would be a FALSE orphan. Rather than
 * lie, the orphan half is BASELINED: `.cli-i18n-orphan-allowlist` lists the key
 * PREFIXES that dynamic call sites build at runtime, each carrying a substantive
 * `# BLOCKER:` reason (validated through scripts/lib/blocker-validator.ts, the
 * same suppression contract as .deps-upgrade-blocklist et al.). A leaf covered
 * by a baselined prefix is NOT reported. There are ~17 dynamic call sites; the
 * allowlist enumerates their prefixes so the orphan report never guesses.
 *
 * Scope note: packages/shared/src was surveyed and calls no t() against this
 * catalogue (its own translations live under the `shared` namespace, accessed
 * via getSharedTranslations, never t('literal')). So only packages/cli/src is
 * scanned. Revisit if shared ever imports the CLI's t().
 *
 * Usage:
 *   npx tsx scripts/check-cli-i18n-key-usage.ts
 *   npm run check:ci-i18n-cli-key-usage
 *
 * Exit codes:
 *   0 - All statically-resolvable keys exist AND no unbaselined orphan leaves
 *   1 - Some keys are missing from en/cli.json, OR orphan leaves exist, OR the
 *       allowlist has an invalid BLOCKER
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..');
const CLI_SRC = path.join(REPO_ROOT, 'packages/cli/src');
const EN_CLI_JSON = path.join(CLI_SRC, 'i18n/locales/en/cli.json');
const ORPHAN_ALLOWLIST = path.join(REPO_ROOT, '.cli-i18n-orphan-allowlist');
const WWW_SRC = path.join(REPO_ROOT, 'packages/www/src');

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

/** Resolve a dot-path in the catalogue. Returns the leaf value or undefined. */
function getNestedValue(obj: Record<string, JsonValue>, dotPath: string): JsonValue | undefined {
  let current: JsonValue = obj;
  for (const segment of dotPath.split('.')) {
    if (current && typeof current === 'object' && !Array.isArray(current) && segment in current) {
      current = (current as Record<string, JsonValue>)[segment];
    } else {
      return undefined;
    }
  }
  return current;
}

/**
 * Collect every cli.<dotpath> key that the www documentation references through
 * its `{{t:cli.<key>}}` template mechanism. The CLI's English catalogue is a
 * SECOND consumer surface: packages/www/src/content/docs/<locale>/cli-application.md
 * renders help text and the error-meanings table straight out of cli.json via
 * this templating (see the `docs.*` namespace, authored purely for the website,
 * and the `errors.*` meanings table). A key used ONLY by www is NOT a CLI t()
 * literal, so leaving www out would report the entire `docs.*` namespace (and
 * doc-only error rows) as false orphans. Locales carry identical keys, so one
 * pass over the whole www/src tree covers them all.
 */
function collectWwwCliRefs(): Set<string> {
  const refs = new Set<string>();
  if (!fs.existsSync(WWW_SRC)) return refs;
  const files = globSync('**/*.{md,mdx,astro,ts,tsx,json}', { cwd: WWW_SRC, absolute: true });
  const re = /\{\{t:cli\.([a-zA-Z0-9_.]+)\}\}/g;
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
    let m: RegExpExecArray | null;
    while ((m = re.exec(content)) !== null) refs.add(m[1]!);
  }
  return refs;
}

/**
 * Enumerate every leaf dot-path in the catalogue. A leaf is any value that is
 * NOT a plain object: strings (the overwhelming majority), plus numbers,
 * booleans, null, and arrays (a value is either a nested namespace or a
 * translatable leaf — an array is a leaf, not a namespace to recurse into).
 */
function collectLeafPaths(obj: Record<string, JsonValue>, prefix = ''): string[] {
  const leaves: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const dotPath = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      leaves.push(...collectLeafPaths(value as Record<string, JsonValue>, dotPath));
    } else {
      leaves.push(dotPath);
    }
  }
  return leaves;
}

interface TranslationCall {
  key: string;
  line: number;
  file: string;
}

/**
 * Blank out //-line and block comments, replacing comment characters with
 * spaces so line numbers and column offsets are preserved. Tracks string and
 * template-literal state so a `//` or `/*` inside a string literal is left
 * intact. Without this, t() calls that appear inside JSDoc examples (the i18n
 * module documents its own usage with t('auth.loginSuccess')) are scanned as
 * real calls and reported as false positives.
 */
function stripComments(src: string): string {
  const out: string[] = [];
  let i = 0;
  const n = src.length;
  type State = 'code' | 'line' | 'block' | 'squote' | 'dquote' | 'template';
  let state: State = 'code';
  while (i < n) {
    const c = src[i];
    const c2 = i + 1 < n ? src[i + 1] : '';
    if (state === 'code') {
      if (c === '/' && c2 === '/') {
        state = 'line';
        out.push('  ');
        i += 2;
      } else if (c === '/' && c2 === '*') {
        state = 'block';
        out.push('  ');
        i += 2;
      } else if (c === "'") {
        state = 'squote';
        out.push(c);
        i++;
      } else if (c === '"') {
        state = 'dquote';
        out.push(c);
        i++;
      } else if (c === '`') {
        state = 'template';
        out.push(c);
        i++;
      } else {
        out.push(c);
        i++;
      }
    } else if (state === 'line') {
      if (c === '\n') {
        state = 'code';
        out.push(c);
      } else {
        out.push(c === '\t' ? '\t' : ' ');
      }
      i++;
    } else if (state === 'block') {
      if (c === '*' && c2 === '/') {
        state = 'code';
        out.push('  ');
        i += 2;
      } else {
        out.push(c === '\n' ? '\n' : c === '\t' ? '\t' : ' ');
        i++;
      }
    } else {
      // Inside a string / template literal: copy verbatim, honoring escapes.
      if (c === '\\') {
        out.push(c, c2);
        i += 2;
        continue;
      }
      const closer = state === 'squote' ? "'" : state === 'dquote' ? '"' : '`';
      if (c === closer) state = 'code';
      out.push(c);
      i++;
    }
  }
  return out.join('');
}

interface FileScan {
  calls: TranslationCall[];
  /** t() invocations whose key is a template literal or variable — unverifiable. */
  skipped: number;
}

/**
 * Collect every single/double-quoted string literal value in a file (after
 * comment-stripping). Used ONLY by the orphan direction: a catalogue key is
 * "referenced" if it appears as a literal string anywhere in source, even when
 * it is forwarded through a variable to t() rather than passed to t() directly
 * (e.g. checkToolVersion(cmd, args, extract, 'commands.doctor.checks.goInstalled',
 * hint) → t(nameKey)). Restricting references to t() first-args alone would
 * report hundreds of these forwarded keys as false orphans. Template literals
 * (`...`) are deliberately NOT collected — their runtime-concatenated keys are
 * what the dynamic-prefix baseline exists to cover.
 */
function scanStringLiterals(content: string): string[] {
  const stripped = stripComments(content);
  const literals: string[] = [];
  const re = /(['"])((?:\\.|(?!\1).)*)\1/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(stripped)) !== null) {
    literals.push(m[2]!);
  }
  return literals;
}

/**
 * Extract t() calls from one file.
 *
 * Literal keys — t('a.b'), t("a.b"), including t('a.b', { opts }) — are
 * collected for resolution. Template-literal and variable-first-argument calls
 * are counted as skipped (they cannot be resolved without evaluating code).
 */
function scanFile(filePath: string, content: string): FileScan {
  const calls: TranslationCall[] = [];
  let skipped = 0;
  const lines = stripComments(content).split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Every t( invocation. \bt\( matches a bare t( and a member .t( (i18n.t(),
    // the exported binding), but not identifiers ending in t like format( or
    // print( (the preceding word char defeats the \b boundary).
    const callRe = /\bt\(\s*/g;
    let m: RegExpExecArray | null;
    while ((m = callRe.exec(line)) !== null) {
      const next = line[m.index + m[0].length];
      if (next === "'" || next === '"') {
        // Literal key — resolvable.
        const quote = next;
        const rest = line.slice(m.index + m[0].length + 1);
        const end = rest.indexOf(quote);
        if (end === -1) {
          // Quote opens but does not close on this line — treat as unverifiable.
          skipped++;
          continue;
        }
        const key = rest.slice(0, end);
        calls.push({ key, line: i + 1, file: filePath });
      } else if (next === '`' || next !== undefined) {
        // Template literal (`) or a variable/expression first arg — unverifiable.
        skipped++;
      }
    }
  }

  return { calls, skipped };
}

function main(): void {
  console.log('CLI Translation Key Usage Check (static)');
  console.log('============================================================\n');

  const enJson = JSON.parse(fs.readFileSync(EN_CLI_JSON, 'utf-8')) as Record<string, JsonValue>;

  const files = globSync('**/*.ts', {
    cwd: CLI_SRC,
    absolute: true,
    ignore: ['**/__tests__/**', 'i18n/locales/**'],
  });
  console.log(`Scanning ${files.length} files in packages/cli/src ...\n`);

  const missing: TranslationCall[] = [];
  // Orphan direction: a key is "referenced" if the CLI mentions it as any string
  // literal OR the www docs template it via {{t:cli.<key>}} (a second consumer).
  const referenced = collectWwwCliRefs();
  let totalChecked = 0;
  let totalSkipped = 0;

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
    const { calls, skipped } = scanFile(file, content);
    totalSkipped += skipped;
    for (const call of calls) {
      totalChecked++;
      if (getNestedValue(enJson, call.key) === undefined) missing.push(call);
    }
    // Orphan direction: a key counts as referenced if it appears as ANY string
    // literal in source (forwarded-to-t() included), not only as a t() first-arg.
    for (const literal of scanStringLiterals(content)) referenced.add(literal);
  }

  const relPath = (f: string) => path.relative(REPO_ROOT, f);
  const GREEN = '\x1b[32m';
  const RED = '\x1b[31m';
  const RESET = '\x1b[0m';

  // Coverage honesty: always report what was verified AND what was skipped.
  console.log(
    `Verified ${totalChecked} literal key(s). ` +
      `Skipped ${totalSkipped} template-literal/variable key(s) — NOT statically ` +
      `verifiable; the runtime help-render gate covers the help subset of these.\n`
  );

  // ── FORWARD direction: unresolved (missing) keys ──────────────────────────
  let forwardFailed = false;
  if (missing.length === 0) {
    console.log(`${GREEN}✓${RESET} All ${totalChecked} literal keys resolve in en/cli.json`);
  } else {
    forwardFailed = true;
    console.log(`${RED}✗${RESET} Found ${missing.length} unresolved translation key(s):\n`);

    const byFile = new Map<string, TranslationCall[]>();
    for (const call of missing) {
      const rel = relPath(call.file);
      if (!byFile.has(rel)) byFile.set(rel, []);
      byFile.get(rel)!.push(call);
    }
    for (const [file, calls] of byFile) {
      console.log(`  ${file}`);
      for (const call of calls) {
        console.log(`    L${call.line}: t('${call.key}') — key not found in en/cli.json`);
      }
      console.log('');
    }

    console.log('Fix: add the key to packages/cli/src/i18n/locales/en/cli.json (English),');
    console.log('then run the 12-locale naturalization pass so the other locales carry it.\n');
  }

  // ── ORPHAN direction: catalogue leaves no literal call references ──────────
  const orphanFailed = reportOrphans(enJson, referenced, relPath);

  process.exit(forwardFailed || orphanFailed ? 1 : 0);
}

/**
 * Report en/cli.json leaves that no literal t() call references and that no
 * baselined dynamic prefix covers. Returns true when the check should FAIL —
 * either a genuine orphan exists, or the allowlist has an invalid BLOCKER.
 */
function reportOrphans(
  enJson: Record<string, JsonValue>,
  referenced: Set<string>,
  relPath: (f: string) => string
): boolean {
  const GREEN = '\x1b[32m';
  const RED = '\x1b[31m';
  const RESET = '\x1b[0m';

  console.log('\n────────────────────────────────────────────────────────────');
  console.log('Orphan check: en/cli.json leaves never referenced by a t() literal\n');

  // Validate the dynamic-prefix allowlist through the shared BLOCKER contract.
  const entries = parseBlockeredList(ORPHAN_ALLOWLIST, '#');
  const blockerFailures = verifyAllBlockers(entries, relPath(ORPHAN_ALLOWLIST));
  if (blockerFailures.length > 0) {
    console.log(`${RED}✗${RESET} ${relPath(ORPHAN_ALLOWLIST)} has invalid BLOCKER(s):\n`);
    for (const failure of blockerFailures) console.log(failure + '\n');
    return true;
  }
  const dynamicPrefixes = entries.map((e) => e.entry);
  console.log(
    `Baselined ${dynamicPrefixes.length} dynamic key prefix(es) from ` +
      `${relPath(ORPHAN_ALLOWLIST)} (keys built at runtime, not statically visible).\n`
  );

  const leaves = collectLeafPaths(enJson);
  const orphans = leaves.filter(
    (leaf) => !referenced.has(leaf) && !dynamicPrefixes.some((p) => leaf.startsWith(p))
  );

  if (orphans.length === 0) {
    console.log(`${GREEN}✓${RESET} All ${leaves.length} leaves are referenced (or baselined)`);
    return false;
  }

  console.log(`${RED}✗${RESET} Found ${orphans.length} orphan leaf key(s) in en/cli.json:\n`);
  for (const orphan of orphans) {
    console.log(`    ${orphan} — no t('${orphan}') literal anywhere in packages/cli/src`);
  }
  console.log('');
  console.log('Fix (pick one):');
  console.log('  • DELETE the key from en/cli.json AND all 12 locale cli.json files (parity).');
  console.log('  • If the key IS used via a dynamic t() call (template literal / variable),');
  console.log(`    add its PREFIX to ${relPath(ORPHAN_ALLOWLIST)} with a '# BLOCKER: <reason>'.`);
  console.log('');
  return true;
}

main();
