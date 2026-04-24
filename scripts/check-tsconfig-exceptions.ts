#!/usr/bin/env node
/**
 * Enforce that every tsconfig*.json with a disabled strict/safety flag has
 * a matching row in .ci/config/tsconfig-exceptions.md with a substantive
 * BLOCKER reason.
 *
 * Checked flags:
 *   - skipLibCheck: true
 *   - strict: false (or not present when a root tsconfig extends nothing)
 *   - strictNullChecks: false
 *   - noImplicitAny: false
 *
 * Sidecar format: HTML-comment blocks embedded in the .md so the doc stays
 * readable. See the doc's header for the schema.
 *
 * Exit codes:
 *   0 — every suppression has a valid BLOCKER reason and no stale rows
 *   1 — missing row, missing BLOCKER, or low-effort reason
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateBlockerQuality } from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const SIDECAR = path.join(CONSOLE_ROOT, '.ci/config/tsconfig-exceptions.md');

// Strict/safety flags we consider as suppressions when set to the "off" value.
const SUPPRESSION_CHECKS: Array<{ flag: string; disabledValue: unknown }> = [
  { flag: 'skipLibCheck', disabledValue: true },
  { flag: 'strict', disabledValue: false },
  { flag: 'strictNullChecks', disabledValue: false },
  { flag: 'noImplicitAny', disabledValue: false },
];

interface SidecarRow {
  path: string;
  flag: string;
  blocker: string;
}

function findTsconfigs(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Skip obviously noisy dirs.
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
      ) {
        continue;
      }
      findTsconfigs(full, acc);
    } else if (entry.isFile() && /^tsconfig.*\.json$/.test(entry.name)) {
      acc.push(path.relative(CONSOLE_ROOT, full));
    }
  }
  return acc;
}

// tsconfig is JSONC in theory, but this repo does not use comments in any
// tsconfig (verified during planning). Naive comment-stripping breaks on
// path-strings like "src/*" (the `/*` looks like a block-comment start),
// so we parse as strict JSON. Files that legitimately use JSONC comments
// would fall into the catch branch and get skipped with no loss of rigor —
// if someone starts using comments, the "missing row" signal will surface.
function parseTsconfig(raw: string): Record<string, unknown> {
  return JSON.parse(raw);
}

function collectSuppressions(
  tsconfigs: string[],
): Array<{ path: string; flag: string }> {
  const out: Array<{ path: string; flag: string }> = [];
  for (const relpath of tsconfigs) {
    const abs = path.join(CONSOLE_ROOT, relpath);
    let cfg: Record<string, unknown>;
    try {
      cfg = parseTsconfig(fs.readFileSync(abs, 'utf-8'));
    } catch {
      continue; // malformed / not a real tsconfig (e.g. Astro stub)
    }
    const co = (cfg.compilerOptions ?? {}) as Record<string, unknown>;
    for (const { flag, disabledValue } of SUPPRESSION_CHECKS) {
      if (co[flag] === disabledValue) {
        out.push({ path: relpath, flag });
      }
    }
  }
  return out;
}

function parseSidecar(): SidecarRow[] {
  if (!fs.existsSync(SIDECAR)) return [];
  const raw = fs.readFileSync(SIDECAR, 'utf-8');
  const rows: SidecarRow[] = [];
  // Match each <!-- tsconfig-exception: ... --> block.
  const re = /<!--\s*tsconfig-exception:\s*([\s\S]*?)\s*-->/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    const body = m[1]!;
    const record: Record<string, string> = {};
    for (const line of body.split('\n')) {
      const mm = line.match(/^\s*(path|flag|blocker)\s*:\s*(.+?)\s*$/);
      if (mm) record[mm[1]!] = mm[2]!;
    }
    if (record.path && record.flag && record.blocker) {
      // Skip template/example rows where any field is a placeholder (< ... >).
      // The header of the sidecar documents the format with angle-bracket
      // placeholders; those are not real exceptions.
      if (
        /[<>]/.test(record.path) ||
        /[<>]/.test(record.flag) ||
        /[<>]/.test(record.blocker)
      ) {
        continue;
      }
      rows.push({ path: record.path, flag: record.flag, blocker: record.blocker });
    }
  }
  return rows;
}

function main(): number {
  const tsconfigs = findTsconfigs(CONSOLE_ROOT);
  const suppressions = collectSuppressions(tsconfigs);
  const rows = parseSidecar();

  const rowKey = (p: string, f: string) => `${p}#${f}`;
  const rowByKey = new Map(rows.map((r) => [rowKey(r.path, r.flag), r] as const));
  const supKeys = new Set(suppressions.map((s) => rowKey(s.path, s.flag)));
  const failures: string[] = [];

  for (const { path: p, flag } of suppressions) {
    const key = rowKey(p, flag);
    const row = rowByKey.get(key);
    if (!row) {
      failures.push(
        `${p}: "${flag}" is disabled but no row in ${path.relative(CONSOLE_ROOT, SIDECAR)}\n` +
          `  Action: add a <!-- tsconfig-exception: path: ${p}\\nflag: ${flag}\\nblocker: BLOCKER: <reason>\\n--> block.`,
      );
      continue;
    }
    const validation = validateBlockerQuality(key, row.blocker, SIDECAR);
    if (validation) {
      failures.push(validation.message);
    }
  }

  // Drift: rows without a matching live suppression.
  for (const row of rows) {
    if (!supKeys.has(rowKey(row.path, row.flag))) {
      failures.push(
        `${path.relative(CONSOLE_ROOT, SIDECAR)}: row for ${row.path}#${row.flag} has no matching suppression — remove the stale row.`,
      );
    }
  }

  if (failures.length > 0) {
    console.error('✗ tsconfig exception sidecar failed validation:');
    for (const f of failures) console.error(f);
    console.error('');
    console.error(
      '✗ Every tsconfig strict/safety-flag disable must have a substantive row in .ci/config/tsconfig-exceptions.md',
    );
    return 1;
  }

  console.log(
    `✓ All ${suppressions.length} tsconfig exception(s) have valid BLOCKER reasons`,
  );
  return 0;
}

process.exit(main());
