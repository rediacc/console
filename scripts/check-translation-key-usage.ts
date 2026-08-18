#!/usr/bin/env node
/**
 * Translation Key Usage Check
 *
 * Validates that t(), ta(), and to() calls in www source files reference keys
 * that actually exist in en.json. Catches missing keys that would render as
 * raw key strings at runtime.
 *
 * Handles:
 * - Direct string keys: t('foo.bar'), ta("foo.bar"), to('foo.bar')
 * - Template literals with `ns` / `PAGE_KEY` prefix: t(`${ns}.hero.title`)
 * - Skips dynamic interpolation: t(`${ns}.plans.${plan.id}.name`)
 *
 * Usage:
 *   npx tsx scripts/check-translation-key-usage.ts
 *   npm run check:i18n:key-usage
 *
 * Exit codes:
 *   0 - All referenced keys exist
 *   1 - Some keys are missing from en.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WWW_SRC = path.join(__dirname, '../packages/www/src');
const EN_JSON = path.join(WWW_SRC, 'i18n/translations/en.json');

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

/**
 * Check if a key exists as an array in the original JSON tree.
 */
function getNestedValue(obj: Record<string, JsonValue>, dotPath: string): JsonValue | undefined {
  let current: JsonValue = obj;
  for (const segment of dotPath.split('.')) {
    if (current && typeof current === 'object') {
      if (Array.isArray(current)) {
        const idx = Number(segment);
        if (Number.isInteger(idx) && idx >= 0 && idx < current.length) {
          current = current[idx];
        } else {
          return undefined;
        }
      } else if (segment in current) {
        current = (current as Record<string, JsonValue>)[segment];
      } else {
        return undefined;
      }
    } else {
      return undefined;
    }
  }
  return current;
}

// ─── Extract translation calls ───────────────────────────────────────────────

interface TranslationCall {
  fn: 't' | 'ta' | 'to';
  key: string;
  line: number;
  file: string;
}

/**
 * Every `const <IDENT> = '<dotted.string>'` in the file, as a prefix candidate.
 *
 * This used to accept exactly two names, `ns` and `PAGE_KEY`, and that hard-coded
 * pair was a blind spot, not a simplification. PartnerApplicationForm.tsx declares
 * `const NS = 'pages.partners.form'` — uppercase, neither spelling — so EVERY
 * t(`${NS}...`) call in it was invisible here. One of those keys,
 * pages.partners.form.fields.howHeardPlaceholder, existed in no locale at all
 * (not even English), rendered blank in production, and logged
 * "Translation key not found" once per page for as long as it shipped, while
 * this gate reported success the whole time.
 *
 * Deriving the names from the file instead of listing them means a third
 * convention costs nothing. The dot requirement is what keeps it honest: a
 * namespace is always dotted, so `const TITLE = 'Partners'` is not mistaken for
 * one.
 */
function findNamespaceVars(content: string): Map<string, string> {
  const found = new Map<string, string>();
  const re = /\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*['"]([^'"\s]*\.[^'"\s]*)['"]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    if (!found.has(m[1])) found.set(m[1], m[2]);
  }
  return found;
}

/**
 * Returns true if a template literal suffix contains additional ${...} interpolations,
 * meaning the key is fully dynamic and can't be statically checked.
 */
function hasDynamicParts(suffix: string): boolean {
  return /\$\{/.test(suffix);
}

/**
 * Blank out comments while preserving every byte position and every newline.
 *
 * WHY THIS IS NEEDED. `extractCalls` below is LINE-BASED and matched `t('...')` anywhere
 * on a line, comments included. An explanatory comment naming a key that no longer exists
 * -- exactly the comment someone writes while removing the key -- reddened this gate and
 * pointed at a line with no call on it. The reader then has to prove a negative, which is
 * the most expensive kind of false positive a gate can produce.
 *
 * IT REPLACES RATHER THAN DELETES, because the gate reports LINE NUMBERS. Stripping the
 * text would renumber every line below the comment and send the reader to the wrong place,
 * which trades one confusing diagnostic for another.
 *
 * STRINGS ARE TRACKED FIRST, and that ordering is the whole correctness argument: `//` is
 * three characters into every `https://` URL in the tree, and a URL sits inside a string
 * literal. A stripper that blanked from the first `//` it saw would delete the rest of the
 * line -- including any real `t()` call after it -- and turn a false POSITIVE into a false
 * NEGATIVE, which is strictly worse. An escape outside a string is consumed too, so the
 * `\/` pairs inside a regex literal such as /^https:\/\// cannot be misread as a comment.
 */
export function stripComments(content: string): string {
  const out = content.split('');
  let quote: string | null = null;
  for (let i = 0; i < content.length; i++) {
    const c = content[i];
    if (quote) {
      if (c === '\\') i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }
    if (c === '\\') {
      i++;
      continue;
    }
    // HTML comments, because .astro files are markup and this gate scans them.
    // The JS-comment branches below never see `<!-- ... -->`, so an explanatory
    // comment written in Astro markup still reddened the gate after the JS fix
    // landed. Same blanking rule, so line numbers survive. Checked outside a
    // string for the same reason as `//`: `<!--` can legitimately appear inside
    // a string literal.
    if (c === '<' && content.startsWith('<!--', i)) {
      const end = content.indexOf('-->', i + 4);
      const stop = end < 0 ? content.length : end + 3;
      for (let j = i; j < stop; j++) if (out[j] !== '\n') out[j] = ' ';
      i = stop - 1;
      continue;
    }
    if (c !== '/') continue;
    const next = content[i + 1];
    if (next === '/') {
      let j = i;
      while (j < content.length && content[j] !== '\n') out[j++] = ' ';
      i = j - 1;
    } else if (next === '*') {
      const end = content.indexOf('*/', i + 2);
      const stop = end < 0 ? content.length : end + 2;
      for (let j = i; j < stop; j++) if (out[j] !== '\n') out[j] = ' ';
      i = stop - 1;
    }
  }
  return out.join('');
}

/**
 * CONTROL for the stripper, inline on every invocation.
 *
 * Both directions, because each failure mode is worse than the bug it replaces: a
 * comment must be blanked (the false positive this fixes), and a string containing `//`
 * must survive intact (a false negative, which would hide a genuinely missing key).
 */
function controlStripComments(): void {
  const failures: string[] = [];
  const expect = (name: string, ok: boolean, detail = '') => {
    if (!ok) failures.push(`${name}${detail ? ` -- ${detail}` : ''}`);
  };
  const keys = (src: string) => extractCalls('control.tsx', stripComments(src)).map((c) => c.key);

  expect(
    'a call inside a // comment is not extracted',
    keys("// the old code called to('pages.gone.away')\n").length === 0
  );
  expect(
    'a call inside a /* */ block is not extracted',
    keys("/* was: t('pages.gone.away') */\n").length === 0
  );
  expect(
    'a call inside a JSX {/* */} comment is not extracted',
    keys("<div>{/* t('pages.gone.away') */}</div>\n").length === 0
  );
  expect(
    'a real call is still extracted',
    keys("<p>{t('pages.real.key')}</p>\n").join(',') === 'pages.real.key',
    keys("<p>{t('pages.real.key')}</p>\n").join(',')
  );
  // The dangerous direction. `//` appears inside every URL in the tree.
  expect(
    'a // inside a string does NOT blank the rest of the line',
    keys("const u = 'https://x.example'; const a = t('pages.real.key');\n").join(',') ===
      'pages.real.key',
    keys("const u = 'https://x.example'; const a = t('pages.real.key');\n").join(',')
  );
  expect(
    'an escaped slash in a regex does NOT start a comment',
    keys("const r = /^https:\\/\\//; const a = t('pages.real.key');\n").join(',') ===
      'pages.real.key',
    keys("const r = /^https:\\/\\//; const a = t('pages.real.key');\n").join(',')
  );
  // Line numbers must survive, or the diagnostic sends the reader to the wrong line.
  const numbered = extractCalls(
    'control.tsx',
    stripComments("// a\n// b\n<p>{t('pages.real.key')}</p>\n")
  );
  expect('line numbers are preserved', numbered[0]?.line === 3, String(numbered[0]?.line));
  // A namespace constant declared inside a comment must not be resolvable either.
  expect(
    'a namespace constant inside a comment is not resolved',
    keys("// const ns = 'pages.gone';\nconst x = t(`${ns}.away`);\n").length === 0
  );

  if (failures.length > 0) {
    console.error('\x1b[31m✗\x1b[0m CONTROL FAILED: the comment stripper is broken, so this');
    console.error('  gate is either reporting keys that appear only in comments, or silently');
    console.error('  dropping real calls that follow a URL.');
    for (const f of failures) console.error(`    ${f}`);
    process.exit(1);
  }
}

function extractCalls(filePath: string, content: string): TranslationCall[] {
  const calls: TranslationCall[] = [];
  const lines = content.split('\n');

  // Pre-resolve namespace variables, whatever this file happens to call them
  const nsVars = findNamespaceVars(content);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Pattern 1: Direct string keys — t('key'), ta("key"), to('key')
    const directRe = /\b(t[ao]?)\(\s*['"]([^'"]+)['"]\s*[,)]/g;
    let m: RegExpExecArray | null;
    while ((m = directRe.exec(line)) !== null) {
      calls.push({ fn: m[1] as 't' | 'ta' | 'to', key: m[2], line: i + 1, file: filePath });
    }

    // Pattern 2: Template literals with a namespace variable — t(`${NS}.suffix`)
    const tmplRe = /\b(t[ao]?)\(\s*`\$\{([A-Za-z_$][\w$]*)\}\.([^`]+)`\s*[,)]/g;
    while ((m = tmplRe.exec(line)) !== null) {
      const fn = m[1] as 't' | 'ta' | 'to';
      const varName = m[2];
      const suffix = m[3];

      // Skip if suffix has more interpolations (dynamic key)
      if (hasDynamicParts(suffix)) continue;

      const prefix = nsVars.get(varName);
      if (!prefix) continue; // Not a dotted string constant in this file, skip

      calls.push({ fn, key: `${prefix}.${suffix}`, line: i + 1, file: filePath });
    }
  }

  return calls;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function main(): void {
  console.log('Translation Key Usage Check');
  console.log('============================================================\n');

  // CONTROL FIRST. If the stripper is wrong in either direction the verdict below is not
  // evidence: a broken blank hides real calls, a missing blank invents them.
  controlStripComments();

  // Load en.json
  const enJson = JSON.parse(fs.readFileSync(EN_JSON, 'utf-8')) as Record<string, JsonValue>;

  // Scan all .astro and .tsx files
  const files = globSync('**/*.{astro,tsx}', { cwd: WWW_SRC, absolute: true });

  // A leftover control fixture is NOT a missing key, and saying so is the whole point.
  // scripts/__tests__/check-translation-key-usage.control.ts writes __control_probe__.tsx
  // into real source and unlinks it in a `finally`, so an ordinary failure cleans up but a
  // SIGKILL mid-run does not. That control already refuses to run against a leftover; this
  // scan did not, and reported the probe's deliberately-nonexistent key as a genuine
  // defect. It cost a session real time chasing it, and it will happen again to whoever's
  // run dies next, so the diagnosis belongs here rather than in anyone's memory.
  // The control itself sets REDIACC_KEY_USAGE_PROBE while its fixture is legitimately on
  // disk, so a live probe scans normally and only an ORPHAN is diagnosed. Without that
  // opt-in this check refuses the control's own nine cases.
  const probing = process.env.REDIACC_KEY_USAGE_PROBE === '1';
  const leftover = probing
    ? undefined
    : files.find((f) => path.basename(f) === '__control_probe__.tsx');
  if (leftover !== undefined) {
    console.error(`\x1b[31m✗\x1b[0m ${path.relative(WWW_SRC, leftover)} is a leftover TEST FIXTURE, not source.`);
    console.error('  A control run was killed before its `finally` could unlink it. The key it');
    console.error('  references is meant not to exist. Delete the file and re-run:');
    console.error(`    rm ${path.relative(process.cwd(), leftover)}`);
    process.exit(1);
  }

  console.log(`Scanning ${files.length} files...\n`);

  const missing: TranslationCall[] = [];
  let totalChecked = 0;

  for (const file of files) {
    // Comments are blanked before extraction: a key named only in an explanatory comment
    // is not a reference, and reporting one sends the reader to a line with no call on it.
    const content = stripComments(fs.readFileSync(file, 'utf-8'));
    const calls = extractCalls(file, content);

    for (const call of calls) {
      totalChecked++;

      // Use getNestedValue for all checks — it handles array index access (e.g., items.0)
      const val = getNestedValue(enJson, call.key);
      if (val === undefined) {
        missing.push(call);
      }
    }
  }

  // Report results
  const relPath = (f: string) => path.relative(path.join(__dirname, '..'), f);

  if (missing.length === 0) {
    console.log(`\x1b[32m✓\x1b[0m All ${totalChecked} translation keys verified against en.json`);
    process.exit(0);
  }

  console.log(`\x1b[31m✗\x1b[0m Found ${missing.length} missing translation key(s):\n`);

  // Group by file for readability
  const byFile = new Map<string, TranslationCall[]>();
  for (const call of missing) {
    const rel = relPath(call.file);
    if (!byFile.has(rel)) byFile.set(rel, []);
    byFile.get(rel)!.push(call);
  }

  for (const [file, calls] of byFile) {
    console.log(`  ${file}`);
    for (const call of calls) {
      console.log(`    L${call.line}: ${call.fn}('${call.key}') — key not found in en.json`);
    }
    console.log('');
  }

  console.log(`Checked ${totalChecked} key references across ${files.length} files.`);
  console.log('Fix: add missing keys to packages/www/src/i18n/translations/en.json\n');
  process.exit(1);
}

main();
