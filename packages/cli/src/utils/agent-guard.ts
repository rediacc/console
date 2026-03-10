import { t } from '../i18n/index.js';
import { ValidationError } from './errors.js';

const AGENT_ENV_VARS = ['REDIACC_AGENT', 'CLAUDECODE', 'GEMINI_CLI', 'COPILOT_CLI'] as const;

/**
 * Detect if the current process is running inside an AI agent environment.
 */
export function isAgentEnvironment(): boolean {
  for (const v of AGENT_ENV_VARS) {
    if (process.env[v] === '1') return true;
  }
  return !!process.env.CURSOR_TRACE_ID;
}

/**
 * Assert that the current agent is allowed to access a machine directly (no repository context).
 * Machine-level SSH is extremely powerful — agents should only connect to repository contexts.
 * Throws ValidationError unless REDIACC_ALLOW_GRAND_REPO=* is set.
 */
export function assertAgentMachineAccess(machineName: string): void {
  if (!isAgentEnvironment()) return;
  if (process.env.REDIACC_ALLOW_GRAND_REPO === '*') return;

  throw new ValidationError(t('errors.agent.machineGuard', { machine: machineName }));
}
