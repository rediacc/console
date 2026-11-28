import type { Placement } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { ValidationError } from './errors.js';
import { isGrandEnvWildcard, isRepoAllowedByGrandEnv } from './grand-env.js';
import { isOpsVmMachine, isOpsVmPlacement } from './ops-vm.js';
import {
  _resetAncestryCache,
  isAgentByAncestry,
  isAncestryVerificationAvailable,
  isOverrideLegitimate,
  OVERRIDE_VAR_GRAND,
} from './process-ancestry.js';

const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI'] as const;

// Cache results, ancestry walk is expensive, only need to do once per process.
let _isAgent: boolean | undefined;
const _overrideLegit = new Map<string, boolean>();

/** Check process.env for agent env vars (fast path). */
function checkProcessEnvForAgent(): boolean {
  for (const v of AGENT_ENV_VARS) {
    if (process.env[v] === '1') return true;
  }
  return !!process.env.CURSOR_TRACE_ID;
}

/**
 * Detect if the current process is running inside an AI agent environment.
 * On Linux, also checks ancestor /proc/environ, catches agents that unset
 * their env vars to bypass detection.
 */
export function isAgentEnvironment(): boolean {
  if (_isAgent !== undefined) return _isAgent;

  // Fast path: check process.env
  if (checkProcessEnvForAgent()) {
    _isAgent = true;
    return true;
  }

  // Slow path: check ancestor chain (Linux only) Catches: unset CLAUDECODE, env -i, script-based bypass
  _isAgent = isAgentByAncestry();
  return _isAgent;
}

/**
 * Check if an override env var is legitimate: set by the user before the
 * agent started, proven via the exec-time environment of the agent-boundary
 * process (/proc on Linux, the renet ancestry helper on macOS/Windows).
 * When ancestry verification is unavailable, the override is rejected.
 */
function isOverrideAllowed(overrideVar: string = OVERRIDE_VAR_GRAND): boolean {
  const cached = _overrideLegit.get(overrideVar);
  if (cached !== undefined) return cached;
  const legit = isOverrideLegitimate(overrideVar);
  _overrideLegit.set(overrideVar, legit);
  return legit;
}

/**
 * True when the human set REDIACC_ALLOW_GRAND_REPO=* before the agent started.
 * Used by guards that should yield to an explicit machine-level authorization
 * (same trust level as assertAgentMachineAccess).
 */
export function isLegitimateWildcardOverride(): boolean {
  return isGrandEnvWildcard() && isOverrideAllowed();
}

/**
 * Assert that the current agent is allowed to access a machine directly (no repository context).
 * Machine-level SSH is extremely powerful, agents should only connect to repository contexts.
 * Throws ValidationError unless REDIACC_ALLOW_GRAND_REPO=* is set by the user, or the
 * machine's configured address is on the development-only ops VM network (ops-vm.ts).
 */
export async function assertAgentMachineAccess(machineName: string): Promise<void> {
  if (!isAgentEnvironment()) return;
  if (await isOpsVmMachine(machineName)) return;
  if (isGrandEnvWildcard()) {
    if (isOverrideAllowed()) return;
    const errorKey = isAncestryVerificationAvailable()
      ? 'errors.agent.machineGuardOverride'
      : 'errors.agent.machineGuardOverrideNonLinux';
    throw new ValidationError(t(errorKey, { machine: machineName, platform: process.platform }));
  }
  throw new ValidationError(t('errors.agent.machineGuard', { machine: machineName }));
}

/**
 * Assert that the current agent is allowed to create a new repository.
 * Agents operate in fork-only mode, creating a grand repo is blocked because the agent
 * can't operate on it afterwards. Use `repo fork` instead.
 * Throws ValidationError unless the user authorized this repo by name (or `*`)
 * via REDIACC_ALLOW_GRAND_REPO, set before the agent started, or the placement the
 * repo is created on executes on the development-only ops VM network (ops-vm.ts).
 */
export async function assertAgentRepoCreate(
  repoName: string,
  placement: Placement | undefined
): Promise<void> {
  if (!isAgentEnvironment()) return;
  if (await isOpsVmPlacement(placement)) return;
  if (isRepoAllowedByGrandEnv(repoName)) {
    if (isOverrideAllowed()) return;
    const errorKey = isAncestryVerificationAvailable()
      ? 'errors.agent.createGuardOverride'
      : 'errors.agent.createGuardOverrideNonLinux';
    throw new ValidationError(t(errorKey, { name: repoName, platform: process.platform }));
  }
  throw new ValidationError(t('errors.agent.createGuard', { name: repoName }));
}

/** Reset cached state (for testing only). */
export function _resetCache(): void {
  _isAgent = undefined;
  _overrideLegit.clear();
  _resetAncestryCache();
}
