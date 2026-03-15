/**
 * Process ancestry verification for agent security hardening.
 *
 * On Linux, reads /proc/<pid>/environ (immutable, kernel-controlled) to verify
 * that agent env vars and overrides were set by the user, not injected by the agent.
 * On macOS/Windows, falls back to process.env (can't read ancestor environments).
 */

import { readFileSync } from 'node:fs';

const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI'] as const;
const AGENT_TRACE_VAR = 'CURSOR_TRACE_ID';
const OVERRIDE_VAR = 'REDIACC_ALLOW_GRAND_REPO';

// Maximum ancestors to walk (prevent infinite loops on circular references)
const MAX_WALK_DEPTH = 64;

interface AncestorEnv {
  pid: number;
  hasAgentVar: boolean;
  hasGrandOverride: boolean;
  grandOverrideValue?: string;
}

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
 * Walk the process ancestor chain and collect environment info.
 * Linux only — reads /proc/<pid>/environ at each level.
 * Returns empty array on non-Linux or if /proc is unavailable.
 */
export function walkAncestors(): AncestorEnv[] {
  if (process.platform !== 'linux') return [];

  const ancestors: AncestorEnv[] = [];
  let pid: number | null = process.pid;
  let depth = 0;

  while (pid !== null && pid > 1 && depth < MAX_WALK_DEPTH) {
    const env = readProcEnviron(pid);
    if (!env) break; // Can't read — stop walk (permission denied, etc.)

    const overrideValue = env.get(OVERRIDE_VAR);
    ancestors.push({
      pid,
      hasAgentVar: hasAgentEnvVar(env),
      hasGrandOverride: overrideValue !== undefined,
      grandOverrideValue: overrideValue,
    });

    pid = getParentPid(pid);
    depth++;
  }

  return ancestors;
}

/**
 * Hardened agent detection — checks ancestor chain for agent env vars.
 * Even if the current process unset CLAUDECODE, an ancestor's /proc/environ
 * still has it (immutable). Returns false on non-Linux (falls back to process.env).
 */
export function isAgentByAncestry(): boolean {
  const ancestors = walkAncestors();
  return ancestors.some((a) => a.hasAgentVar);
}

/**
 * Verify that REDIACC_ALLOW_GRAND_REPO was set by the user (before the agent
 * started), not injected by the agent itself.
 *
 * Algorithm (Linux):
 * 1. Walk ancestors to find the agent boundary (highest ancestor with agent env var)
 * 2. Check if the override existed in the agent boundary's parent
 * 3. If yes → user set it before the agent, legitimate
 * 4. If no → injected at or below agent boundary, illegitimate
 *
 * On non-Linux: returns true (fail open — can't verify, trust process.env).
 */
export function isOverrideLegitimate(): boolean {
  if (process.platform !== 'linux') return true;

  const ancestors = walkAncestors();
  if (ancestors.length === 0) return true; // Can't read /proc, fail open

  // Find the agent boundary: the HIGHEST ancestor (last in array, closest to init)
  // that has an agent env var. We walk from current process upward, so the last
  // match in the array is the highest in the tree.
  let agentBoundaryIdx = -1;
  for (let i = ancestors.length - 1; i >= 0; i--) {
    if (ancestors[i].hasAgentVar) {
      agentBoundaryIdx = i;
      break;
    }
  }

  // No agent boundary found — not in agent mode, override is always legitimate
  if (agentBoundaryIdx === -1) return true;

  // Check: does the agent boundary process's /proc/environ have the override?
  // If the override is in the same process that introduced the agent env var,
  // it was set in the same shell session — that means the user set both.
  // If the override is NOT in the agent boundary but IS in a descendant,
  // it was injected below the boundary.
  //
  // We check the agent boundary itself: if the override exists there,
  // it was present when the agent process started → set by user.
  const boundary = ancestors[agentBoundaryIdx];
  return boundary.hasGrandOverride;
}
