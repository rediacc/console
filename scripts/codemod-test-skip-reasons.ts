#!/usr/bin/env node
/**
 * Codemod: expand short `test.skip(cond, reason)` reasons to BLOCKER-quality
 * strings that the new eslint-rules/test-skip-blocker rule will accept.
 *
 * Only the CONDITIONAL form is touched: `test.skip(cond, '<reason>')` where
 * `cond` is NOT a string literal. The declaration form
 * `test.skip('<name>', fn)` is left alone (its first arg is the test title,
 * not a skip reason).
 *
 * Idempotent — running twice produces the same output.
 *
 * Usage: npx tsx scripts/codemod-test-skip-reasons.ts [--check]
 *   --check: report counts without writing; exits 1 if any replacements would be made.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

// Map: old short reason (exact match, no quotes) → BLOCKER-quality expansion.
const REASON_MAP: ReadonlyArray<[RegExp, string]> = [
  // 'E2E not configured' — 18 chars; occurs ~66 times
  [
    /^E2E not configured$/,
    'E2E not configured: RDC_E2E_ENABLED unset or bridge-test env missing required secrets',
  ],
  // 'Ceph not configured' — 19 chars; occurs ~29 times
  [
    /^Ceph not configured$/,
    'Ceph not configured: VM_CEPH_NODES empty or RustFS S3 endpoint unavailable in this env',
  ],
  // 'E2E VMs not configured' — 22 chars; occurs ~6 times
  [
    /^E2E VMs not configured$/,
    'E2E VMs not configured: bridge-test VM_DEPLOYMENT=true required to provision real VMs',
  ],
  // 'No <Distro> images built yet' — 28/27 chars; occurs 3 times in bridge-tests/20-image-build.test.ts
  [
    /^No (Debian|RHEL|SUSE) images built yet$/,
    'No $1 images built yet: bridge-test image-build pipeline has not produced $1 variants in this env',
  ],
];

interface Change {
  file: string;
  line: number;
  before: string;
  after: string;
}

// Regex for conditional `test.skip(cond, 'reason')` / `it.skip(cond, "reason")`.
// Anchored such that the first argument is NOT a string literal (checked by
// requiring the first char inside the parens to not be ' or ").
const SKIP_RE =
  /\b(test|it)\.skip\(\s*([^'"`][^,]*?)\s*,\s*(['"])([^'"`]+?)\3\s*\)/g;

function collectTestFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (
        entry.name === 'node_modules' ||
        entry.name === 'dist' ||
        entry.name === 'bin' ||
        entry.name === 'out' ||
        entry.name === '.git' ||
        entry.name === 'coverage' ||
        entry.name === 'test-results' ||
        entry.name === '.venv' ||
        entry.name === '__pycache__'
      )
        continue;
      collectTestFiles(full, acc);
    } else if (
      entry.isFile() &&
      /\.(test|spec)\.(ts|tsx)$/.test(entry.name)
    ) {
      acc.push(full);
    }
  }
  return acc;
}

function transformFile(file: string, check: boolean): Change[] {
  const raw = fs.readFileSync(file, 'utf-8');
  const lines = raw.split('\n');
  const changes: Change[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    const newLine = line.replace(
      SKIP_RE,
      (match, fn: string, cond: string, q: string, reason: string) => {
        for (const [pat, replacement] of REASON_MAP) {
          if (pat.test(reason)) {
            const expanded = reason.replace(pat, replacement);
            return `${fn}.skip(${cond.trim()}, ${q}${expanded}${q})`;
          }
        }
        return match;
      },
    );
    if (newLine !== line) {
      changes.push({ file, line: i + 1, before: line.trim(), after: newLine.trim() });
      lines[i] = newLine;
    }
  }
  if (changes.length > 0 && !check) {
    fs.writeFileSync(file, lines.join('\n'));
  }
  return changes;
}

function main(): number {
  const check = process.argv.includes('--check');
  const packages = path.join(CONSOLE_ROOT, 'packages');
  const files = collectTestFiles(packages);
  const allChanges: Change[] = [];
  for (const f of files) {
    const changes = transformFile(f, check);
    allChanges.push(...changes);
  }

  if (allChanges.length === 0) {
    console.log(
      `✓ ${files.length} test file(s) scanned — no short reasons to expand`,
    );
    return 0;
  }

  if (check) {
    console.error(`✗ ${allChanges.length} short test.skip reason(s) need expansion:`);
    for (const c of allChanges.slice(0, 10)) {
      console.error(`  ${path.relative(CONSOLE_ROOT, c.file)}:${c.line}`);
      console.error(`    - ${c.before}`);
      console.error(`    + ${c.after}`);
    }
    if (allChanges.length > 10) {
      console.error(`  ... and ${allChanges.length - 10} more`);
    }
    return 1;
  }
  console.log(
    `✓ Expanded ${allChanges.length} short test.skip reason(s) across ${
      new Set(allChanges.map((c) => c.file)).size
    } file(s)`,
  );
  return 0;
}

process.exit(main());
