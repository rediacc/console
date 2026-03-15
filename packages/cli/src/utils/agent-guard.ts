import { t } from '../i18n/index.js';
import { ValidationError } from './errors.js';
import { isAgentByAncestry, isOverrideLegitimate } from './process-ancestry.js';

const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI'] as const;

// Cache results — ancestry walk is expensive, only need to do once per process.
let _isAgent: boolean | undefined;
let _isOverrideLegit: boolean | undefined;

/** Check process.env for agent env vars (fast path). */
function checkProcessEnvForAgent(): boolean {
  for (const v of AGENT_ENV_VARS) {
    if (process.env[v] === '1') return true;
  }
  return !!process.env.CURSOR_TRACE_ID;
}

/**
 * Detect if the current process is running inside an AI agent environment.
 * On Linux, also checks ancestor /proc/environ — catches agents that unset
 * their env vars to bypass detection.
 */
export function isAgentEnvironment(): boolean {
  if (_isAgent !== undefined) return _isAgent;

  // Fast path: check process.env
  if (checkProcessEnvForAgent()) {
    _isAgent = true;
    return true;
  }

  // Slow path: check ancestor chain (Linux only)
  // Catches: unset CLAUDECODE, env -i, script-based bypass
  _isAgent = isAgentByAncestry();
  return _isAgent;
}

/**
 * Check if the REDIACC_ALLOW_GRAND_REPO override is legitimate.
 * On Linux, verifies the override was set by the user (before the agent started)
 * by checking /proc ancestor environments. On other platforms, trusts process.env.
 */
function isOverrideAllowed(): boolean {
  if (_isOverrideLegit !== undefined) return _isOverrideLegit;
  _isOverrideLegit = isOverrideLegitimate();
  return _isOverrideLegit;
}

/**
 * Assert that the current agent is allowed to access a machine directly (no repository context).
 * Machine-level SSH is extremely powerful — agents should only connect to repository contexts.
 * Throws ValidationError unless REDIACC_ALLOW_GRAND_REPO=* is set by the user.
 */
export function assertAgentMachineAccess(machineName: string): void {
  if (!isAgentEnvironment()) return;
  if (process.env.REDIACC_ALLOW_GRAND_REPO === '*' && isOverrideAllowed()) return;

  throw new ValidationError(t('errors.agent.machineGuard', { machine: machineName }));
}

/**
 * Assert that the current agent is allowed to create a new repository.
 * Agents operate in fork-only mode — creating a grand repo is blocked because the agent
 * can't operate on it afterwards. Use `repo fork` instead.
 * Throws ValidationError unless REDIACC_ALLOW_GRAND_REPO=* is set by the user.
 */
export function assertAgentRepoCreate(repoName: string): void {
  if (!isAgentEnvironment()) return;
  if (process.env.REDIACC_ALLOW_GRAND_REPO === '*' && isOverrideAllowed()) return;

  throw new ValidationError(t('errors.agent.createGuard', { name: repoName }));
}

/** Reset cached state (for testing only). */
export function _resetCache(): void {
  _isAgent = undefined;
  _isOverrideLegit = undefined;
}
