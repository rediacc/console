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
 * Find the value of `const ns = '...'` or `const PAGE_KEY = '...'` in file content.
 */
function findNamespaceVar(content: string, varName: string): string | null {
  // Match: const ns = 'pages.pricing'  or  const PAGE_KEY = "pages.refundPolicy"
  const re = new RegExp(`const\\s+${varName}\\s*=\\s*['"]([^'"]+)['"]`);
  const m = content.match(re);
  return m ? m[1] : null;
}

/**
 * Returns true if a template literal suffix contains additional ${...} interpolations,
 * meaning the key is fully dynamic and can't be statically checked.
 */
function hasDynamicParts(suffix: string): boolean {
  return /\$\{/.test(suffix);
}

function extractCalls(filePath: string, content: string): TranslationCall[] {
  const calls: TranslationCall[] = [];
  const lines = content.split('\n');

  // Pre-resolve namespace variables
  const nsValue = findNamespaceVar(content, 'ns');
  const pageKeyValue = findNamespaceVar(content, 'PAGE_KEY');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Pattern 1: Direct string keys — t('key'), ta("key"), to('key')
    const directRe = /\b(t[ao]?)\(\s*['"]([^'"]+)['"]\s*[,)]/g;
    let m: RegExpExecArray | null;
    while ((m = directRe.exec(line)) !== null) {
      calls.push({ fn: m[1] as 't' | 'ta' | 'to', key: m[2], line: i + 1, file: filePath });
    }

    // Pattern 2: Template literals with namespace variable — t(`${ns}.suffix`)
    const tmplRe = /\b(t[ao]?)\(\s*`\$\{(ns|PAGE_KEY)\}\.([^`]+)`\s*[,)]/g;
    while ((m = tmplRe.exec(line)) !== null) {
      const fn = m[1] as 't' | 'ta' | 'to';
      const varName = m[2];
      const suffix = m[3];

      // Skip if suffix has more interpolations (dynamic key)
      if (hasDynamicParts(suffix)) continue;

      const prefix = varName === 'ns' ? nsValue : pageKeyValue;
      if (!prefix) continue; // Can't resolve, skip

      calls.push({ fn, key: `${prefix}.${suffix}`, line: i + 1, file: filePath });
    }
  }

  return calls;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function main(): void {
  console.log('Translation Key Usage Check');
  console.log('============================================================\n');

  // Load en.json
  const enJson = JSON.parse(fs.readFileSync(EN_JSON, 'utf-8')) as Record<string, JsonValue>;

  // Scan all .astro and .tsx files
  const files = globSync('**/*.{astro,tsx}', { cwd: WWW_SRC, absolute: true });
  console.log(`Scanning ${files.length} files...\n`);

  const missing: TranslationCall[] = [];
  let totalChecked = 0;

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
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
