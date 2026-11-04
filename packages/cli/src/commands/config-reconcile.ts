import { randomUUID } from 'node:crypto';
import { t } from '../i18n/index.js';
import type { ReconcileDeps } from '../services/config/config-reconcile.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import type { ScratchRecord } from '../services/jobs/scratch-store.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';

export interface ReconcileCliOptions {
  machine?: string[];
  dryRun?: boolean;
  acceptObserved?: boolean;
}

/**
 * `config reconcile` body (extracted so the action stays thin). Rebuilds the
 * state half from machine truth; under --accept-observed it also rewrites an
 * unambiguous machine-arm placement drift (spec/04 §4.3) through the
 * version-bumping resources writer, distinct from the state writer.
 */
export async function runReconcile(options: ReconcileCliOptions): Promise<void> {
  try {
    await runReconcileInner(options);
  } catch (error) {
    handleError(error);
  }
}

/** The machines a reconcile covers: the current config's, narrowed by `--machine`. */
function reconcileFilter(config: RdcConfig | null | undefined, filter: string[] | undefined) {
  if (!config || !filter?.length) return config;
  const machines = Object.fromEntries(
    Object.entries(config.resources?.machines ?? {}).filter(([n]) => filter.includes(n))
  );
  return { ...config, resources: { ...(config.resources ?? {}), machines } };
}

/**
 * Build the reconcile DI deps: a config loader filtered to `--machine`, the listings the group's machine jobs recorded
 * (a machine with no record is unreachable, with the error its job recorded when it recorded one), and the two writers
 * (state-half and version-bumping resources), both no-ops under --dry-run.
 */
async function buildReconcileDeps(
  cfgName: string,
  filter: string[] | undefined,
  dryRun: boolean | undefined,
  listings: Map<string, ScratchRecord>
): Promise<ReconcileDeps> {
  const { parseMachineStatus } = await import('../services/machine/machine-status.js');
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const { updateSyncedConfig } = await import('../services/config/synced-write.js');
  const noop = async () => {};
  return {
    loadConfig: async () => reconcileFilter(await configService.getCurrent(), filter) ?? null,
    fetchStatus: (m) => {
      const record = listings.get(m);
      if (!record) {
        return Promise.reject(new Error(t('commands.config.reconcile.noListing', { machine: m })));
      }
      if (!record.ok) return Promise.reject(new Error(record.error));
      return Promise.resolve(parseMachineStatus(record.value));
    },
    writeState: dryRun
      ? noop
      : async (updater) => {
          await configFileStorage.updateState(cfgName, updater);
        },
    writeResources: dryRun
      ? noop
      : async (updater) => {
          await updateSyncedConfig(cfgName, updater);
        },
  };
}

/** What the group's final step needs, as step params (all scalars). */
interface ReconcileGroup {
  group: string;
  acceptObserved: boolean;
  dryRun: boolean;
  /** The `--machine` filter as a comma list; empty covers every machine. */
  machines: string;
  /** Every machine with a job in the group, as a comma list; the reconcile waits for all of them. */
  expected: string;
}

function groupOf(params: Record<string, string | number | boolean>): ReconcileGroup {
  return {
    group: String(params.group),
    acceptObserved: params.acceptObserved === true,
    dryRun: params.dryRun === true,
    machines: String(params.machines),
    expected: String(params.expected),
  };
}

/** The group's one reconcile: read every recorded listing, reconcile, print the report, drop the scratch records. */
async function settleReconcileGroup(params: ReconcileGroup): Promise<void> {
  const { reconcileState } = await import('../services/config/config-reconcile.js');
  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  const cfgName = configService.getEffectiveConfigName();
  const scratch = new ScratchStore(cfgName);
  const listings = scratch.read(params.group);
  const filter = params.machines ? params.machines.split(',') : undefined;
  const deps = await buildReconcileDeps(cfgName, filter, params.dryRun, listings);
  const report = await reconcileState(deps, { acceptObserved: params.acceptObserved });
  scratch.drop(params.group);
  printReconcileReport(report, params.dryRun, getOutputFormat());
}

// Per machine: keep the listing the job captured (a job whose output was not seen records nothing, so the machine reads as unreachable).
bindStepHandler('recordMachineListing', async ({ machine, output, params }) => {
  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  const group = String(params.group);
  if (!group || output === undefined) return;
  new ScratchStore(configService.getEffectiveConfigName()).write(group, machine, {
    ok: true,
    value: output,
  });
});

/**
 * Reconcile once every machine of the group has finished, whichever order the jobs end in: a machine still running
 * would otherwise read as unreachable, and its record would land in a dropped group. The claim keeps two observers
 * that finish together from reconciling twice.
 */
async function settleWhenComplete(group: ReconcileGroup): Promise<void> {
  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  const scratch = new ScratchStore(configService.getEffectiveConfigName());
  const expected = group.expected ? group.expected.split(',') : [];
  if (!scratch.allFinished(group.group, expected)) return;
  if (scratch.claim(group.group)) await settleReconcileGroup(group);
}

// Each ticket: its own record step ran first, so this machine is finished, and the last one to finish reconciles.
bindStepHandler('reconcileConfigState', async ({ machine, params }) => {
  const group = groupOf(params);
  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  new ScratchStore(configService.getEffectiveConfigName()).finish(group.group, machine);
  await settleWhenComplete(group);
});
bindStepHandler('reconcileConfigStateFailed', async ({ machine, params, exitCode }) => {
  const group = groupOf(params);
  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  const scratch = new ScratchStore(configService.getEffectiveConfigName());
  scratch.write(group.group, machine, {
    ok: false,
    error: t('commands.config.reconcile.listFailed', { exitCode: String(exitCode ?? 1) }),
  });
  scratch.finish(group.group, machine);
  await settleWhenComplete(group);
});

function printReconcileReport(
  report: Awaited<
    ReturnType<typeof import('../services/config/config-reconcile.js').reconcileState>
  >,
  dryRun: boolean,
  format: OutputFormat
): void {
  outputService.print(
    {
      dryRun,
      reconciledAt: report.reconciledAt,
      machinesSeen: report.machinesSeen,
      unreachable: report.machinesUnreachable,
      placementsFilled: report.placementsFilled,
      placementsAccepted: report.placementsAccepted,
      conflicts: report.conflicts,
      networkIdsRebuilt: report.networkIdsRebuilt,
      networkIdsDiverged: report.networkIdsDiverged,
    },
    format
  );
  // D4(a): the machine's ID replaced a differing recorded one; one line per repo says so.
  for (const d of report.networkIdsDiverged) {
    outputService.info(
      t('errors.repo.networkIdDiverged', {
        repository: d.repository,
        localId: d.previous,
        machineId: d.networkId,
        machine: d.machine,
      })
    );
  }
  // Exit 6 (NETWORK) when nothing was reachable but machines were tried.
  if (report.machinesSeen.length === 0 && report.machinesUnreachable.length > 0) {
    setExitCode(6);
  }
}

/** Start one machine's list-all job; a job that cannot start leaves its error as the machine's record and counts as finished. */
async function startMachineJob(
  machine: string,
  steps: ReturnType<typeof planStep>[],
  group: ReconcileGroup,
  scratch: InstanceType<typeof import('../services/jobs/scratch-store.js').ScratchStore>
): Promise<void> {
  const { runCommandJob, pendingExitCode } = await import('../services/jobs/command-job.js');
  const { machineStatusJob } = await import('../services/machine/machine-status.js');
  try {
    const outcome = await runCommandJob('config reconcile', await machineStatusJob(machine), steps);
    if (outcome.kind === 'pending') {
      const code = pendingExitCode(outcome);
      if (code !== undefined) setExitCode(code);
    }
  } catch (error) {
    scratch.write(group.group, machine, {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    });
    scratch.finish(group.group, machine);
  }
}

async function runReconcileInner(options: ReconcileCliOptions): Promise<void> {
  const cfgName = configService.getEffectiveConfigName();
  const filter = options.machine;

  // --accept-observed rewrites a declaration from "observed on exactly one machine", which is meaningless when --machine scanned only a subset: rewriting from partial evidence is a guess. Refuse the combination (spec/04 §4.3); run it unfiltered instead.
  if (options.acceptObserved && filter?.length) {
    throw new ValidationError(t('commands.config.reconcile.acceptObservedUnfiltered'));
  }

  const { ScratchStore } = await import('../services/jobs/scratch-store.js');
  const machines = Object.keys(
    reconcileFilter(await configService.getCurrent(), filter)?.resources?.machines ?? {}
  );
  const group: ReconcileGroup = {
    group: randomUUID(),
    acceptObserved: options.acceptObserved === true,
    dryRun: options.dryRun === true,
    machines: filter?.join(',') ?? '',
    expected: machines.join(','),
  };
  const scratch = new ScratchStore(cfgName);

  // One list-all job per machine under one group. Every ticket carries the reconcile step, which runs only once all the machines have finished. A machine whose job could not start leaves its error as its record and counts as finished, so the command checks once more after the loop for the case where no ticket is left to do it.
  const steps = [
    planStep('recordMachineListing', { group: group.group }),
    planStep('reconcileConfigState', { ...group }),
    planStep('reconcileConfigStateFailed', { ...group }),
  ];
  for (const machine of machines) await startMachineJob(machine, steps, group, scratch);
  await settleWhenComplete(group);
}
