/**
 * The runtime converge pass as one executor session runs it (PLAN-renet-runtime-converge D5): the
 * deps bound to the session, the vault a `runtime_converge` call carries, and the converge-if-stale
 * step every other function takes first (it reads the runtime only after a renet upload, and it
 * still repays a deferred router refresh without one). Split out of local-executor.ts, which owns
 * the session itself.
 */
import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { renetProvisioner } from '../renet/renet-provisioner.js';
import {
  type AutoConvergeDeps,
  CONVERGE_FUNCTION,
  convergeIfStale,
  prepareConvergeVault,
  type RuntimeStatus,
  readRuntimeStatus,
  shouldCheckRuntimeAfterUpload,
} from '../renet/runtime-converge.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';

/** The datastore renet resolves for this run: the caller's, else the machine's, else the default. */
function sessionDatastore(options: ExecuteOptions, machine: { datastore?: string }): string {
  return options.datastore ?? machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
}

/** The remote effects of the runtime converge pass, bound to one session. */
export function sessionConvergeDeps(session: {
  sftp: SFTPClient;
  remoteRenetPath: string;
  machine: { datastore?: string };
  options: ExecuteOptions;
  buildVault: (params: Record<string, unknown>) => string;
  runRemote: (vault: string, options: ExecuteOptions) => Promise<ExecuteResult>;
}): AutoConvergeDeps {
  const { sftp, remoteRenetPath, options } = session;
  return {
    sftp,
    remoteRenetPath,
    machineName: options.machineName,
    datastore: sessionDatastore(options, session.machine),
    debug: options.debug,
    buildBaseVault: (params) => session.buildVault(params),
    run: (convergeVault, params) =>
      session.runRemote(convergeVault, {
        functionName: CONVERGE_FUNCTION,
        machineName: options.machineName,
        params,
        debug: options.debug,
        captureOutput: true,
      }),
    refreshRouter: () => renetProvisioner.refreshRouter(sftp, remoteRenetPath),
  };
}

/**
 * The runtime status a converge vault is scoped by. A dry run never replaced the machine's renet, so
 * a renet too old for `runtime status` is reported with the real commands that update it.
 */
export async function readConvergeStatus(
  sftp: SFTPClient,
  deps: AutoConvergeDeps,
  dryRun: boolean
): Promise<RuntimeStatus> {
  try {
    return await readRuntimeStatus(sftp, deps.remoteRenetPath, deps.datastore);
  } catch (error) {
    // Only a renet that does not know the command is "too old"; an SSH, SFTP or timeout failure keeps its own error.
    if (!dryRun || !isUnknownRuntimeCommand(error)) throw error;
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(
      `A dry run plans with the renet already on ${deps.machineName} and does not upload one, ` +
        `and that renet cannot report its runtime (${detail}). ` +
        `Run 'rdc machine setup ${deps.machineName}' or 'rdc machine converge ${deps.machineName}' (without --dry-run) to update it.`,
      { cause: error }
    );
  }
}

/** True for cobra's refusal of what buildRuntimeStatusCommand sends (`runtime`, `runtime status`, or one of its long flags --json, --datastore, --policy), the signature of a renet older than the converge commands; the call uses no shorthand flags. */
function isUnknownRuntimeCommand(error: unknown): boolean {
  const text = error instanceof Error ? error.message : String(error);
  return /unknown command "runtime" for "renet"|unknown command "status" for "renet runtime"|unknown flag: --(datastore|json|policy)\b/.test(
    text
  );
}

/**
 * The vault this session's function runs with. A `runtime_converge` call carries env secrets only
 * for the repos the machine reports; any other function first moves stale repo daemons, then the
 * router, because a new renet may change the runtime layout (PLAN-renet-runtime-converge D5, decision 2).
 */
export async function prepareSessionVault(
  sftp: SFTPClient,
  deps: AutoConvergeDeps,
  options: ExecuteOptions,
  vault: string,
  upload: { renetUploaded: boolean; routerRefreshDue: boolean }
): Promise<string> {
  if (options.functionName === CONVERGE_FUNCTION) {
    const status = await readConvergeStatus(sftp, deps, options.params?.dry_run === true);
    return prepareConvergeVault(vault, status);
  }
  await convergeIfStale(deps, {
    checkRuntime: shouldCheckRuntimeAfterUpload(options.functionName, upload.renetUploaded),
    routerRefreshDue: upload.routerRefreshDue,
    skipRouterRestart: options.skipRouterRestart,
  });
  return vault;
}
