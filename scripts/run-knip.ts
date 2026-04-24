#!/usr/bin/env node
/**
 * Thin wrapper around `knip` that merges `.knip-ignores` (sidecar text file
 * with BLOCKER-gated rationale per entry) into knip.json's `ignoreDependencies`
 * at runtime.
 *
 * Why: knip.json is JSON and cannot carry per-entry rationale. The sidecar
 * pattern (mirroring `.audit-*-allowlist`) lets each ignore entry carry a
 * substantive BLOCKER reason that is validated every time `check:unused`
 * runs.
 *
 * Usage:
 *   tsx scripts/run-knip.ts [--treat-config-hints-as-errors] [--fix ...]
 *
 * Forwards all CLI args to knip unchanged. The merged config is written to
 * a temp file and passed via `knip --config <temp>`.
 */

import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseBlockeredList,
  verifyAllBlockers,
} from './lib/blocker-validator.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const KNIP_JSON = path.join(CONSOLE_ROOT, 'knip.json');
const SIDECAR = path.join(CONSOLE_ROOT, '.knip-ignores');

function loadSidecarEntries(): string[] {
  const parsed = parseBlockeredList(SIDECAR);
  const failures = verifyAllBlockers(parsed, SIDECAR);
  if (failures.length > 0) {
    console.error('✗ .knip-ignores entries failed BLOCKER validation:');
    for (const f of failures) console.error(f);
    process.exit(1);
  }
  return parsed.map((r) => r.entry);
}

function main(): number {
  if (!fs.existsSync(KNIP_JSON)) {
    console.error(`knip.json not found at ${KNIP_JSON}`);
    return 1;
  }

  const base = JSON.parse(fs.readFileSync(KNIP_JSON, 'utf-8')) as Record<
    string,
    unknown
  >;

  const existing =
    (base.ignoreDependencies as string[] | undefined) ?? [];
  const sidecar = loadSidecarEntries();
  // Union, preserving order: sidecar first (authoritative), then any
  // remaining entries from knip.json that were not moved yet.
  const merged = Array.from(new Set([...sidecar, ...existing]));
  base.ignoreDependencies = merged;

  const tmpConfig = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), 'knip-')),
    'knip.json',
  );
  fs.writeFileSync(tmpConfig, JSON.stringify(base, null, 2));

  const args = process.argv.slice(2);
  // knip accepts --config before other args.
  const knipArgs = ['--config', tmpConfig, ...args];
  const result = spawnSync('npx', ['knip', ...knipArgs], {
    cwd: CONSOLE_ROOT,
    stdio: 'inherit',
  });

  try {
    fs.rmSync(path.dirname(tmpConfig), { recursive: true, force: true });
  } catch {
    // ignore
  }

  return result.status ?? 1;
}

process.exit(main());
