/**
 * Machine Status Service
 *
 * Fetches full machine status as one `list-all` command-kind job (`renet list all --json`).
 * Returns the parsed ListResult for display by the command layer.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { isListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import {
  type RuntimeRepoLicenseStatus,
  readRuntimeRepoLicenseStatuses,
} from '../account/license.js';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';
import { acquireRemoteRenet } from '../renet/renet-execution.js';
import { machineConnections } from './machine-connection.js';

interface FetchStatusOptions {
  debug?: boolean;
  /** When provided, only gather these renet sections (system,repositories,containers,services,network,block). */
  sections?: string[];
}

/**
 * Fetch full machine status as one `list-all` job (PLAN-detached-jobs J18).
 *
 * Flow:
 * 1. Load machine config from local context
 * 2. One `list-all` command-kind job: the executor resolves the remote renet read-only (never replaces it) and
 *    renet runs `list all --datastore <path> --json` inside the job
 * 3. Parse the captured JSON output as ListResult
 *
 * The sections filter rides the job's `--args`. A read has no ticket steps, the caller renders.
 */
export async function fetchMachineStatus(
  machineName: string,
  options: FetchStatusOptions = {}
): Promise<ListResult> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const args: Record<string, string> = {
    datastore: machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
  };
  if (options.sections && options.sections.length > 0) args.sections = options.sections.join(',');

  const result = await getExecutor().execute({
    functionName: 'list-all',
    machineName,
    commandKind: { name: 'list-all', args },
    debug: options.debug,
    captureOutput: true,
    // The caller reads the listing now: `--background` must not hand back a ticket in its place.
    probe: true,
  });
  if (!result.success) {
    throw new Error(
      `renet list all failed (exit ${result.exitCode}): ${result.stderr ?? result.error ?? ''}`
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(result.stdout ?? '');
  } catch {
    throw new Error('Failed to parse renet output: not JSON');
  }
  if (!isListResult(parsed)) {
    throw new Error('Failed to parse renet output: unexpected format');
  }
  return parsed;
}

/**
 * The licensing detail `renet list` does not carry: which datastore each repo's
 * license lives in, the blocked-backup marker, and what the last unattended
 * renewal did.
 *
 * It is a second, deliberately separate read because `list`'s licenses section
 * is a generated contract shared with other consumers, while these three fields
 * come from `repository license-status`, which is also the only reader of the
 * machine-wide marker tree and renewal state. It runs over the SAME pooled
 * connection, so the cost is one exec of a local-only command.
 *
 * Best-effort by contract: an older renet that does not know `--all-datastores`
 * (or a machine with an unreadable datastore) must degrade the license table,
 * never fail `machine status`.
 */
export async function fetchRepoLicenseDetail(
  machineName: string
): Promise<RuntimeRepoLicenseStatus[]> {
  try {
    const lease = await machineConnections.acquire(machineName);
    try {
      const { remotePath } = await acquireRemoteRenet(
        'read-only',
        await configService.getLocalConfig(),
        lease.machine,
        lease.sshPrivateKey,
        { machineName }
      );
      return await readRuntimeRepoLicenseStatuses(
        lease.machine,
        lease.sshPrivateKey,
        remotePath,
        await lease.ensure()
      );
    } finally {
      lease.release();
    }
  } catch {
    return [];
  }
}
