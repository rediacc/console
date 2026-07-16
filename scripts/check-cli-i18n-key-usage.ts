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
 * This gate closes the static side: every t('literal') / t("literal") in
 * packages/cli/src must resolve to a leaf in the CLI's English catalogue
 * (packages/cli/src/i18n/locales/en/cli.json). Unknown keys render as their own
 * raw key string at runtime, exactly the failure this catches.
 *
 * Honesty about coverage (the check-lockfile.sh precedent — a gate that
 * silently skips half its subject overstates its coverage): keys built from
 * template literals (t(`commands.${x}`)) or variables (t(key)) CANNOT be
 * resolved statically. They are skipped, but the skip is COUNTED and printed so
 * the reported coverage is honest. The RUNTIME half
 * (check-cli-i18n-help-render.ts) walks the live Commander tree and catches the
 * dynamically-built help keys this half must skip.
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
 *   0 - All statically-resolvable keys exist
 *   1 - Some keys are missing from en/cli.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..');
const CLI_SRC = path.join(REPO_ROOT, 'packages/cli/src');
const EN_CLI_JSON = path.join(CLI_SRC, 'i18n/locales/en/cli.json');

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

  if (missing.length === 0) {
    console.log(`${GREEN}✓${RESET} All ${totalChecked} literal keys resolve in en/cli.json`);
    process.exit(0);
  }

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
  process.exit(1);
}

main();
