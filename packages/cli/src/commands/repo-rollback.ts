/**
 * WB6 (agent/plans/PLAN-rmcp-writeback.md Design 6): a command that registered a repo before its job rolls the
 * registration back only on a definitive failure. A timeout or a lost connection on the dispatch leaves the job's
 * state unknown (it may be running on the host), so the entry stays and the job's own failure step settles it. A
 * request that provably never reached the executor (connection refused, a name that did not resolve, a failed TLS
 * handshake) started nothing, so it is a refused start and rolls back (review 9a8dc910.1).
 */

import { ProxyRequestError } from '../services/executor/proxy-client-support.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';

/**
 * True when the dispatch failed in a way that cannot say whether the job started: a timeout, a connection lost after
 * the request may have been delivered, or any other NETWORK_ERROR not marked as never reaching the executor (an
 * SSH-mapped, forensics or teardown failure). Only a ProxyRequestError with `mayHaveReached` false is definitive.
 */
export function jobStateUnknown(error: unknown): boolean {
  if (!(error instanceof CliExitError) || error.code !== ERROR_CODES.NETWORK_ERROR) return false;
  return !(error instanceof ProxyRequestError && !error.mayHaveReached);
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
