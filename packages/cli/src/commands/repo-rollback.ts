/**
 * WB6 (agent/plans/PLAN-rmcp-writeback.md Design 6): a command that registered a repo before its job rolls the
 * registration back only on a definitive failure. A timeout or a lost connection on the dispatch leaves the job's
 * state unknown (it may be running on the host), so the entry stays and the job's own failure step settles it.
 */

import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';

/** True when the dispatch failed in a way that cannot say whether the job started: a timeout or an unreachable host. */
export function jobStateUnknown(error: unknown): boolean {
  return error instanceof CliExitError && error.code === ERROR_CODES.NETWORK_ERROR;
}

/** Run `rollback` for a start that was definitively refused; an unknown outcome keeps the registration. Returns whether it ran. */
export async function rollbackRefusedStart<A extends unknown[]>(
  error: unknown,
  rollback: (...args: A) => Promise<void>,
  ...args: A
): Promise<boolean> {
  if (jobStateUnknown(error)) return false;
  await rollback(...args);
  return true;
}
