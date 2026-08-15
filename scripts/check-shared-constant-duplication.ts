/**
 * check:ci-shared-constant-duplication — one source of truth for exported
 * constants shared between the account service and packages/shared.
 *
 * The class this catches: a constant exported from BOTH
 * private/account/src/** and packages/shared/src/** under the same name. Both
 * paths resolve, both typecheck, and every existing gate is blind to it, so the
 * two copies drift silently until one caller reads a stale plan limit. This is
 * exactly how STORAGE_QUOTA_BYTES_BY_PLAN came to exist twice during the
 * backup-storage program: packages/shared grew the canonical PLAN_LIMITS entry
 * while private/account kept its own byte-identical copy, and nothing failed.
 *
 * Scope is deliberately narrow: SCREAMING_SNAKE_CASE consts and the
 * get*ForPlan accessor shape, which is where plan/quota configuration lives.
 * Type-only exports, interfaces, and ordinary functions are not policed here;
 * duplicating a type is a typecheck problem, duplicating a VALUE is a silent
 * behavior problem.
 *
 * Run: npx tsx scripts/check-shared-constant-duplication.ts
 *
 * Every run first proves the instrument on a control pair (a synthetic duplicate
 * that MUST be reported) — a gate that cannot fire is worse than no gate.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/**
 * Names allowed to exist on both sides. Every entry needs a BLOCKER reason
 * naming why one source of truth is impossible, not merely inconvenient.
 * Empty by design: the fix for a duplicate is to import the shared one.
 */
const ALLOWLIST: Record<string, string> = {};

/** SCREAMING_SNAKE consts and get<Something>ForPlan accessors. */
const EXPORT_RE =
  /^export\s+(?:const|function)\s+([A-Z][A-Z0-9_]{2,}|get[A-Za-z0-9]*ForPlan)\b/gm;

interface Found {
  name: string;
  file: string;
}

function exportsIn(globs: string[]): Found[] {
  const out: Found[] = [];
  for (const file of globSync(globs, { cwd: ROOT, absolute: false })) {
    if (file.includes('node_modules') || file.includes('/dist/')) continue;
    if (/\.(test|spec)\.ts$/.test(file)) continue;
    const text = readFileSync(join(ROOT, file), 'utf8');
    for (const m of text.matchAll(EXPORT_RE)) out.push({ name: m[1], file });
  }
  return out;
}

function duplicates(account: Found[], shared: Found[]): string[] {
  const sharedByName = new Map<string, string>();
  for (const s of shared) if (!sharedByName.has(s.name)) sharedByName.set(s.name, s.file);

  const rows: string[] = [];
  for (const a of account) {
    const sharedFile = sharedByName.get(a.name);
    if (!sharedFile) continue;
    if (a.name in ALLOWLIST) continue;
    rows.push(`    ${a.name}\n      account: ${a.file}\n      shared:  ${sharedFile}`);
  }
  return rows;
}

// ── Control: the detector must report a planted duplicate ──────────────────
const CONTROL_NAME = 'CONTROL_DUPLICATED_CONSTANT';
const controlRows = duplicates(
  [{ name: CONTROL_NAME, file: 'control/account.ts' }],
  [{ name: CONTROL_NAME, file: 'control/shared.ts' }]
);
if (controlRows.length !== 1) {
  console.error(
    `✗ instrument control did not fire: a planted duplicate (${CONTROL_NAME}) was not reported.\n` +
      '  The detector cannot see duplicates, so a green run below would mean nothing.'
  );
  process.exit(1);
}

// ── Real run ───────────────────────────────────────────────────────────────
const accountExports = exportsIn(['private/account/src/**/*.ts']);
const sharedExports = exportsIn(['packages/shared/src/**/*.ts']);

if (accountExports.length === 0 || sharedExports.length === 0) {
  // A missing submodule (or a bad glob) would otherwise read as "no duplicates".
  console.error(
    '✗ nothing scanned: ' +
      `account exports=${accountExports.length}, shared exports=${sharedExports.length}.\n` +
      '  Expected both trees to be present; a zero here is an unrun check, not a pass.'
  );
  process.exit(1);
}

const rows = duplicates(accountExports, sharedExports);
if (rows.length > 0) {
  console.error(
    `✗ constant defined on BOTH sides (${rows.length}):\n${rows.join('\n')}\n\n` +
      '  Both copies resolve and typecheck, so they drift silently until a caller\n' +
      '  reads a stale value. Delete the account-local copy and import from\n' +
      '  @rediacc/shared, or add an ALLOWLIST entry with a BLOCKER reason in\n' +
      '  scripts/check-shared-constant-duplication.ts.'
  );
  process.exit(1);
}

console.log(
  `✓ no account/shared constant duplication ` +
    `(${accountExports.length} account, ${sharedExports.length} shared exports scanned; control fired)`
);
