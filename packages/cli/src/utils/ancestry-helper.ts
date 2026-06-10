/**
 * Synchronous bridge to the renet `process-ancestry` helper.
 *
 * On macOS/Windows the CLI cannot read ancestor process environments itself
 * (there is no /proc), so it spawns the platform-native renet Go binary,
 * which reads kern.procargs2 (darwin, exec-time snapshot) or the PEB
 * environment block (windows, live memory). The spawn is synchronous because
 * the guard chain (isAgentEnvironment, mutation gate, config-edit refusal)
 * is synchronous; process-ancestry.ts caches the result once per process.
 *
 * Every failure path returns null and the caller fails closed: an override
 * that cannot be verified is never honored.
 */

import { spawnSync } from 'node:child_process';
import { accessSync } from 'node:fs';
import { extractRenetToLocalSync, isSEA } from '../services/embedded-assets.js';

const HELPER_TIMEOUT_MS = 5000;

/** One ancestor as reported by `renet process-ancestry` (child→root order). */
export interface RawAncestor {
  pid: number;
  /** Only the requested keys that were present in the process environment. */
  env: Record<string, string>;
}

/**
 * Resolve a local renet binary without async I/O.
 * SEA: extract (or verify and reuse) the embedded host-platform binary.
 * Dev: PATH lookup via which/where — a missing or outdated renet means the
 * helper cannot run and the guards fail closed.
 */
export function resolveRenetSyncPath(): string | null {
  try {
    if (isSEA()) {
      return extractRenetToLocalSync();
    }
    const lookup = process.platform === 'win32' ? 'where' : 'which';
    const result = spawnSync(lookup, ['renet'], {
      encoding: 'utf-8',
      timeout: HELPER_TIMEOUT_MS,
      windowsHide: true,
    });
    if (result.error || result.status !== 0) return null;
    const candidate = result.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean);
    if (!candidate) return null;
    accessSync(candidate);
    return candidate;
  } catch {
    return null;
  }
}

/**
 * Spawn `renet process-ancestry --pid <ours> --keys <csv>` and parse its JSON.
 * Returns null on any failure: binary unresolvable, spawn error, non-zero
 * exit (including an old renet without the subcommand), timeout, or output
 * that does not match the expected shape.
 */
export function runAncestryHelper(keys: readonly string[]): RawAncestor[] | null {
  const bin = resolveRenetSyncPath();
  if (!bin) return null;

  const result = spawnSync(
    bin,
    ['process-ancestry', '--pid', String(process.pid), '--keys', keys.join(',')],
    {
      encoding: 'utf-8',
      timeout: HELPER_TIMEOUT_MS,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );
  if (result.error || result.status !== 0 || typeof result.stdout !== 'string') {
    return null;
  }
  return parseHelperOutput(result.stdout);
}

function parseHelperOutput(stdout: string): RawAncestor[] | null {
  try {
    const parsed: unknown = JSON.parse(stdout);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const ancestors = (parsed as { ancestors?: unknown }).ancestors;
    if (!Array.isArray(ancestors)) return null;

    const out: RawAncestor[] = [];
    for (const entry of ancestors) {
      const ancestor = parseAncestorEntry(entry);
      if (!ancestor) return null;
      out.push(ancestor);
    }
    return out;
  } catch {
    return null;
  }
}

function parseAncestorEntry(entry: unknown): RawAncestor | null {
  if (typeof entry !== 'object' || entry === null) return null;
  const { pid, env } = entry as { pid?: unknown; env?: unknown };
  if (typeof pid !== 'number' || typeof env !== 'object' || env === null) return null;
  const envOut: Record<string, string> = {};
  for (const [key, value] of Object.entries(env)) {
    if (typeof value !== 'string') return null;
    envOut[key] = value;
  }
  return { pid, env: envOut };
}
