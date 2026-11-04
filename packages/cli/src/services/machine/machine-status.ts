/**
 * Machine Status Service
 *
 * Fetches full machine status as one `list-all` command-kind job (`renet list all --json`).
 * Returns the parsed ListResult for display by the command layer.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { isListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';

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
