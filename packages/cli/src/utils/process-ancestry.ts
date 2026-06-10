/**
 * Process ancestry verification for agent security hardening.
 *
 * The guards must prove that an override env var (REDIACC_ALLOW_GRAND_REPO /
 * REDIACC_ALLOW_CONFIG_EDIT) was set by the human BEFORE the agent started,
 * not injected by the agent itself. The proof is the exec-time environment of
 * the "agent boundary" process (the highest ancestor carrying an agent var).
 *
 * Platform witnesses:
 *   - linux:   /proc/<pid>/environ read in-process (exec-time, kernel-served)
 *   - darwin:  renet `process-ancestry` helper → kern.procargs2 (exec-time)
 *   - win32:   renet `process-ancestry` helper → PEB env block (live memory,
 *     weaker tier — a process can rewrite its own block, ancestors cannot be
 *     rewritten through any normal channel)
 *   - others:  verification unavailable; overrides fail closed
 */

import { readFileSync } from 'node:fs';
import { runAncestryHelper } from './ancestry-helper.js';

const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI'] as const;
const AGENT_TRACE_VAR = 'CURSOR_TRACE_ID';

/** Override verified by default (grand-repo guards). */
export const OVERRIDE_VAR_GRAND = 'REDIACC_ALLOW_GRAND_REPO';
/** Override for the config-edit guards (rdc config edit / --apply / rotate). */
export const OVERRIDE_VAR_CONFIG_EDIT = 'REDIACC_ALLOW_CONFIG_EDIT';

/**
 * Every key the ancestry walk witnesses — one walk (one helper spawn on
 * macOS/Windows) covers every guard in the process.
 */
const WITNESS_KEYS: readonly string[] = [
  ...AGENT_ENV_VARS,
  AGENT_TRACE_VAR,
  OVERRIDE_VAR_GRAND,
  OVERRIDE_VAR_CONFIG_EDIT,
];

// Maximum ancestors to walk (prevent infinite loops on circular references)
const MAX_WALK_DEPTH = 64;

export interface AncestorEnv {
  pid: number;
  /** The witnessed variables present in this process (filtered to WITNESS_KEYS). */
  env: Map<string, string>;
}

interface AncestryResult {
  /**
   * False when this platform/installation cannot verify ancestry at all
   * (unsupported platform, helper missing or failed). Overrides fail closed.
   */
  available: boolean;
  ancestors: AncestorEnv[];
}

// ─── Linux /proc primitives ──────────────────────────────────────────────

/**
 * Read a process's initial environment from /proc/<pid>/environ.
 * This is immutable — set at exec time by the kernel, cannot be modified
 * by the process itself (export/unset only changes the live heap copy).
 * Returns null if the file can't be read (permissions, non-Linux, etc.).
 */
export function readProcEnviron(pid: number | 'self'): Map<string, string> | null {
  if (process.platform !== 'linux') return null;

  try {
    const data = readFileSync(`/proc/${pid}/environ`);
    const env = new Map<string, string>();
    // /proc/<pid>/environ is null-separated: KEY1=val1\0KEY2=val2\0
    const entries = data.toString().split('\0');
    for (const entry of entries) {
      if (!entry) continue;
      const eqIdx = entry.indexOf('=');
      if (eqIdx > 0) {
        env.set(entry.slice(0, eqIdx), entry.slice(eqIdx + 1));
      }
    }
    return env;
  } catch {
    return null;
  }
}

/**
 * Get the parent PID of a given process.
 * Linux: reads /proc/<pid>/stat (field 4 is PPID).
 * Other platforms: returns process.ppid for current process, null otherwise.
 */
function getLinuxParentPid(pid: number): number | null {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, 'utf-8');
    // Format: pid (comm) state ppid ...
    // The comm field can contain spaces and parens, so find the LAST ')' first
    const closeParen = stat.lastIndexOf(')');
    if (closeParen === -1) return null;
    const fields = stat.slice(closeParen + 2).split(' ');
    // fields[0] = state, fields[1] = ppid
    const ppid = Number.parseInt(fields[1], 10);
    return Number.isNaN(ppid) || ppid <= 0 ? null : ppid;
  } catch {
    return null;
  }
}

export function getParentPid(pid: number): number | null {
  if (pid <= 1) return null;

  if (process.platform === 'linux') {
    return getLinuxParentPid(pid);
  }

  // Non-Linux: can only get our own PPID
  if (pid === process.pid) {
    return process.ppid > 0 ? process.ppid : null;
  }
  return null;
}

/**
 * Check if an environment map contains any agent env var.
 */
export function hasAgentEnvVar(env: Map<string, string>): boolean {
  for (const v of AGENT_ENV_VARS) {
    if (env.get(v) === '1') return true;
  }
  return !!env.get(AGENT_TRACE_VAR);
}

/**
 * Linux walk: read /proc/<pid>/environ at each level, filtered to the
 * witness keys for shape parity with the helper-based platforms.
 */
function walkAncestorsLinux(): AncestorEnv[] {
  const ancestors: AncestorEnv[] = [];
  let pid: number | null = process.pid;
  let depth = 0;

  while (pid !== null && pid > 1 && depth < MAX_WALK_DEPTH) {
    const env = readProcEnviron(pid);
    if (!env) break; // Can't read — stop walk (permission denied, etc.)

    const filtered = new Map<string, string>();
    for (const key of WITNESS_KEYS) {
      const value = env.get(key);
      if (value !== undefined) filtered.set(key, value);
    }
    ancestors.push({ pid, env: filtered });

    pid = getParentPid(pid);
    depth++;
  }

  return ancestors;
}

// ─── Platform dispatch + cache ───────────────────────────────────────────

let _ancestry: AncestryResult | undefined;

/**
 * Collect the ancestry chain once per process.
 * Linux walks /proc in-process; macOS/Windows spawn the renet helper
 * (synchronously, ~once per process, only when a guard actually asks).
 */
function collectAncestry(): AncestryResult {
  if (_ancestry) return _ancestry;

  if (process.platform === 'linux') {
    _ancestry = { available: true, ancestors: walkAncestorsLinux() };
  } else if (process.platform === 'darwin' || process.platform === 'win32') {
    const raw = runAncestryHelper(WITNESS_KEYS);
    _ancestry = raw
      ? {
          available: true,
          ancestors: raw.map((a) => ({ pid: a.pid, env: new Map(Object.entries(a.env)) })),
        }
      : { available: false, ancestors: [] };
  } else {
    _ancestry = { available: false, ancestors: [] };
  }
  return _ancestry;
}

/**
 * Walk the process ancestor chain and collect environment info.
 * Returns empty array when ancestry data is unavailable.
 */
export function walkAncestors(): AncestorEnv[] {
  return collectAncestry().ancestors;
}

/**
 * True when this platform/installation can verify override ancestry.
 * Drives the guard error message: a verification-capable system reports
 * "agent-injected override"; an incapable one reports "cannot verify".
 */
export function isAncestryVerificationAvailable(): boolean {
  return collectAncestry().available;
}

/**
 * Hardened agent detection — checks ancestor chain for agent env vars.
 * Even if the current process unset CLAUDECODE, an ancestor's /proc/environ
 * still has it (immutable).
 *
 * Linux only by design: this runs at CLI startup (isAgentEnvironment slow
 * path), and spawning the ancestry helper there would cost every
 * macOS/Windows invocation a process spawn. Override *legitimacy* — the
 * actual security gate — does use the helper on all platforms.
 */
export function isAgentByAncestry(): boolean {
  if (process.platform !== 'linux') return false;
  return collectAncestry().ancestors.some((a) => hasAgentEnvVar(a.env));
}

/**
 * Verify that an override env var was set by the user (before the agent
 * started), not injected by the agent itself.
 *
 * Algorithm:
 * 1. Walk ancestors to find the agent boundary (highest ancestor with agent env var)
 * 2. Check if the override existed in the boundary's exec-time environment
 * 3. If yes → user set it before the agent, legitimate
 * 4. If no → injected at or below agent boundary, illegitimate
 *
 * When ancestry verification is unavailable (unsupported platform, helper
 * missing/failed): fail closed — can't verify, don't trust.
 */
export function isOverrideLegitimate(overrideVar: string = OVERRIDE_VAR_GRAND): boolean {
  const { available, ancestors } = collectAncestry();
  if (!available) return false;

  if (ancestors.length === 0) {
    // Linux: /proc itself unreadable (exotic containers) — historical fail
    // open. A helper that ran but reported nothing is not trusted.
    return process.platform === 'linux';
  }

  // Find the agent boundary: the HIGHEST ancestor (last in array, closest to init)
  // that has an agent env var. We walk from current process upward, so the last
  // match in the array is the highest in the tree.
  let agentBoundaryIdx = -1;
  for (let i = ancestors.length - 1; i >= 0; i--) {
    if (hasAgentEnvVar(ancestors[i].env)) {
      agentBoundaryIdx = i;
      break;
    }
  }

  // No agent boundary found — not in agent mode, override is always legitimate
  if (agentBoundaryIdx === -1) return true;

  // Check: does the agent boundary process's exec-time environment have the
  // override? If the override is in the same process that introduced the
  // agent env var, it was present when the agent started → set by user.
  // If the override is NOT in the agent boundary but IS in a descendant,
  // it was injected below the boundary.
  return ancestors[agentBoundaryIdx].env.has(overrideVar);
}

/** Reset the cached walk (for testing only). */
export function _resetAncestryCache(): void {
  _ancestry = undefined;
}
