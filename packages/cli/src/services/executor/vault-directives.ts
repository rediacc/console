/**
 * The start directives a call writes into its built vault (see local-executor.ts).
 */

import { runsOutsideJob } from './detached-execution.js';
import type { ExecuteOptions } from './types.js';

/** The network_id value that asks `job start` to allocate the ID (private/renet/pkg/functions/network_auto.go). */
const NETWORK_ID_AUTO = 'auto';

function isPositiveId(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

type ParsedVault = {
  expect?: string;
  task?: { repository?: string };
  params?: Record<string, unknown>;
  repositories?: Record<string, Record<string, unknown>>;
};

/** Give the task repository's entry an auto network ID, or carry its existing ID into a params "auto". */
function applyNetworkIdAuto(
  parsed: ParsedVault,
  paramsAuto: boolean,
  repositoryConfigs: Record<string, { networkId?: number }> | undefined
): void {
  const entry = parsed.repositories?.[parsed.task?.repository ?? ''];
  if (!entry) return;
  if (isPositiveId(entry.network_id)) {
    if (paramsAuto && parsed.params) parsed.params.network_id = entry.network_id;
    return;
  }
  entry.network_id = NETWORK_ID_AUTO;
  entry.network_id_exclude = [
    ...new Set(
      Object.values(repositoryConfigs ?? {})
        .map((config) => config.networkId)
        .filter(isPositiveId)
    ),
  ].sort((a, b) => a - b);
}

/**
 * Write the call's start directives into a built vault (agent/plans/PLAN-detached-jobs.md
 * section 14), on the job path only: `renet execute` evaluates neither, and refuses an
 * unresolved "auto".
 *
 *   - `expect` lands at the vault root, where `job start` checks it before any unit exists.
 *   - `network_id: "auto"` (asked by `networkIdAuto`, or by a caller's `params.network_id`)
 *     lands on the task repository's entry when that entry has no ID, with every ID the
 *     caller's config holds as `network_id_exclude`: the machine cannot see the IDs this
 *     config placed on other machines. An entry that already has an ID keeps it, and a
 *     params "auto" beside it is replaced by that ID, which renet would otherwise refuse.
 */
export function applyVaultDirectives(
  vault: string,
  options: Pick<ExecuteOptions, 'functionName' | 'params' | 'expect' | 'networkIdAuto'>,
  repositoryConfigs: Record<string, { networkId?: number }> | undefined
): string {
  const paramsAuto = options.params?.network_id === NETWORK_ID_AUTO;
  if (runsOutsideJob(options) || (!options.expect && !options.networkIdAuto && !paramsAuto)) {
    return vault;
  }
  const parsed = JSON.parse(vault) as ParsedVault;
  if (options.expect) parsed.expect = options.expect;
  if (options.networkIdAuto || paramsAuto)
    applyNetworkIdAuto(parsed, paramsAuto, repositoryConfigs);
  return JSON.stringify(parsed);
}
