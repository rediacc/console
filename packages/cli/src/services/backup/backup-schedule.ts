/**
 * Backup Schedule Service
 *
 * Pushes backup schedule configuration to remote machines via SSH.
 * Each strategy becomes one systemd service + timer pair per datastore of the
 * machine it reaches, plus one pair per per-repo cadence override
 * (backup-schedule-targets.ts). A run takes one snapshot whatever the number
 * of destinations.
 *
 * Deploy strategy: state-based reconciliation. Read remote state (existing
 * unit files + SHA-256 hashes + systemd status), diff against desired, only
 * touch what changed. In-flight backups are detected and block updates/
 * removes by default (`--force` to override). The mutation phase runs on the
 * machine as one `backup-schedule` job: writes are staged to `<path>.new` and
 * renamed, so a dropped connection never leaves a half-deployed unit, and
 * post-deploy the timers are re-queried to confirm they actually loaded.
 *
 * Implementation is split across:
 * - backup-schedule/unit-generator.ts, pure content generators
 * - backup-schedule/reconcile.ts     , read + diff + in-flight gate
 * - backup-schedule/execute.ts       , the job's payload + summary
 */

import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { BackupStrategyConfig } from '../../types/index.js';
import { getOutputFormat } from '../../utils/errors.js';
import { refreshRepoLicensesBatch } from '../account/license.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { setExitCode } from '../core/request-context.js';
import { pendingExitCode, runCommandJob } from '../jobs/command-job.js';
import type { PlannedStep } from '../jobs/steps.js';
import { machineConnections } from '../machine/machine-connection.js';
import { acquireRemoteRenet, readSSHKey } from '../renet/renet-execution.js';
import { REMOTE_INSTALL_PATH } from '../renet/renet-provisioner.js';
import {
  mayOfferReplacement,
  renetHoldReason,
  renetMayUpload,
} from '../renet/renet-upload-decision.js';
import { envFilePath, generateEnvFile } from './backup-env-file.js';
import {
  buildSchedulePayload,
  emitPlanSummary,
  printDryRunUnitBodies,
  type SchedulePayload,
} from './backup-schedule-execute.js';
import {
  applyInFlightGate,
  computeDesiredUnits,
  computeReconcilePlan,
  parseStrategyFromPath,
  parseSystemctlShow,
  type ReconcileOptions,
  readRemoteState,
  resolveMachineCpuCount,
} from './backup-schedule-reconcile.js';
import {
  buildScheduleStatusRows,
  type ExpectedScheduleUnit,
  parseFoldedSystemctlShow,
  type ScheduleStatusRow,
  scheduleStatusExitCode,
} from './backup-schedule-status.js';
import {
  machineUnitSpecs,
  type ScheduledStrategy,
  type ScheduleUnitSpec,
} from './backup-schedule-targets.js';
import {
  syncTocKeys,
  type TocKeyTransport,
  tocKeyTargetsFor,
  tocKeyWarnings,
} from './backup-schedule-toc-key.js';
import {
  buildBackupCommands,
  cronToOnCalendar,
  generateServiceUnit,
  generateTimerUnit,
  sanitizeBackupOutput,
  sha256Hex,
} from './backup-schedule-unit-generator.js';

type PushScheduleOptions = ReconcileOptions & {
  /** Client-side steps the apply job carries on its ticket (they run after it, whoever observes it). */
  steps?: PlannedStep[];
};

/**
 * What a push did: `dry-run` and `unchanged` made no job; `applied` ran the job to its end with `options.steps` run
 * after it; `pending` handed the ticket back, so the steps run when the job is observed finished.
 */
export type PushScheduleResult = 'dry-run' | 'unchanged' | 'applied' | 'pending';

/** Validate no duplicate destination names across strategies. */
function assertNoDuplicateDestinations(strategies: { config: BackupStrategyConfig }[]): void {
  const destNames = new Set<string>();
  for (const { config } of strategies) {
    for (const dest of config.destinations) {
      if (destNames.has(dest.name)) {
        throw new Error(
          `Duplicate destination name "${dest.name}" across strategies. Each destination name must be unique.`
        );
      }
      destNames.add(dest.name);
    }
  }
}

async function loadAndValidateStrategies(
  strategyNames: string[]
): Promise<{ name: string; config: ScheduledStrategy }[]> {
  const strategies: { name: string; config: ScheduledStrategy }[] = [];
  for (const stratName of strategyNames) {
    const config = await configService.getBackupStrategy(stratName);
    if (!config) {
      throw new Error(`Backup strategy "${stratName}" not found in config`);
    }
    if (config.enabled === false) continue;
    strategies.push({ name: stratName, config });
  }
  if (strategies.length === 0) {
    throw new Error('All bound backup strategies are disabled');
  }
  assertNoDuplicateDestinations(strategies);
  return strategies;
}

interface LocalMachine {
  ip: string;
  user: string;
  port?: number;
  datastore?: string;
}

/**
 * Provision renet + refresh licenses. Skipped in dry-run so the command
 * is purely read-only against the remote.
 */
async function preDeployProvisioning(
  machineName: string,
  localConfig: Awaited<ReturnType<typeof configService.getLocalConfig>>,
  machine: LocalMachine,
  sshPrivateKey: string,
  options: PushScheduleOptions
): Promise<string> {
  if (options.dryRun) {
    // Use the version-specific install path so dry-run's expected
    // ExecStart= matches exactly what a real deploy would write (and
    // therefore hashes match against previously-deployed unit files).
    return REMOTE_INSTALL_PATH;
  }
  if (renetMayUpload('provision')) {
    outputService.info(`Provisioning renet to ${machine.ip}...`);
  } else if (!mayOfferReplacement('provision')) {
    outputService.info(`Using the installed renet on ${machine.ip} (${renetHoldReason()}).`);
  }
  const { remotePath } = await acquireRemoteRenet(
    'provision',
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug: options.debug }
  );
  const repoRefresh = await refreshRepoLicensesBatch(
    machineName,
    machine,
    sshPrivateKey,
    remotePath
  );
  if (repoRefresh.scanned > 0 && repoRefresh.valid === 0) {
    throw new Error(
      'Backup deployment aborted: no valid repo licenses are available on target machine'
    );
  }
  if (repoRefresh.scanned > 0) {
    outputService.info(
      `Repo licenses refreshed: scanned ${repoRefresh.scanned}, issued ${repoRefresh.issued}, refreshed ${repoRefresh.refreshed}, unchanged ${repoRefresh.unchanged}, failed ${repoRefresh.failed}`
    );
  }
  return remotePath;
}

/**
 * Warn about enabled strategies that no machine binds.
 *
 * The silent case this exists for is PARTIAL binding: with one strategy bound
 * and another orphaned, the deploy reported "unchanged" for the bound one and
 * exited 0, never mentioning that the other was configured but would never run.
 * The operator's only clue was a backup that silently did not happen.
 *
 * A warning rather than an error on purpose, a strategy staged before its
 * machine exists is legitimate, and throwing here would block deploys to
 * unrelated machines over a strategy that has nothing to do with them.
 */
async function warnAboutUnboundStrategies(
  machines: Record<string, { backupStrategies?: string[] } | undefined>
): Promise<void> {
  const bound = new Set<string>();
  for (const machine of Object.values(machines)) {
    for (const name of machine?.backupStrategies ?? []) bound.add(name);
  }

  const strategies = await configService.listBackupStrategies();
  const orphaned = Object.entries(strategies)
    .filter(([name, strategy]) => strategy.enabled !== false && !bound.has(name))
    .map(([name]) => name);

  for (const name of orphaned) {
    outputService.warn(
      `Backup strategy "${name}" is enabled but bound to no machine, so it will never run. ` +
        `Bind it with: rdc backup strategy bind ${name} -m <machine>`
    );
  }
}

/**
 * The unit specs for a machine's bound strategies, resolved through the active config: names become
 * GUIDs, only repositories placed on each datastore reach that datastore's unit, and per-repo cadence
 * overrides get units of their own.
 */
async function resolveUnitSpecs(
  machineName: string,
  strategies: { name: string; config: ScheduledStrategy }[]
): Promise<ScheduleUnitSpec[]> {
  const config = await configService.getCurrent();
  if (!config) throw new Error('No active config to resolve backup strategy repositories from');
  return machineUnitSpecs(strategies, config, machineName);
}

/**
 * The commands one strategy runs on a machine, resolved the way `backup schedule` resolves them.
 * For an on-demand run of a strategy that has no deployed unit.
 */
export async function buildStrategyCommandsForMachine(
  machineName: string,
  strategyName: string,
  strategy: ScheduledStrategy,
  remoteRenetPath: string
): Promise<string[]> {
  const specs = await resolveUnitSpecs(machineName, [{ name: strategyName, config: strategy }]);
  const commands: string[] = [];
  for (const spec of specs) {
    const enabled = spec.strategy.destinations.filter((d) => d.enabled !== false);
    commands.push(
      ...buildBackupCommands(
        spec.strategy,
        enabled,
        spec.datastore.path,
        remoteRenetPath,
        spec.scope
      ).commands
    );
  }
  return commands;
}

/**
 * Re-render a machine's backup units after a repository was created, deleted, forked or renamed.
 *
 * A strategy that names a family covers its forks, and include/exclude lists resolve to GUIDs at
 * render time, so the unit text moves when the repository set does. The reconciler redeploys only
 * what changed (hash diff). Best-effort: the repository operation already happened, so a failure here
 * is reported, never thrown, and a backup running right now keeps its unit until the next attempt.
 */
export async function reconcileSchedulesAfterRepoChange(
  machineName: string,
  options: { debug?: boolean } = {}
): Promise<boolean> {
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine?.backupStrategies?.length) return false;
    await pushBackupSchedule(machineName, { debug: options.debug });
    return true;
  } catch (error) {
    outputService.warn(
      `Backup schedule on ${machineName} was not re-rendered after the repository change: ${error instanceof Error ? error.message : String(error)}. Re-run: rdc backup schedule -m ${machineName}`
    );
    return false;
  }
}

/**
 * The units the config expects on a machine: its bound, enabled strategies rendered to unit specs.
 * A bound strategy whose specs cannot be resolved (an unknown repo name) is still listed under its
 * own name, so status reports it as not scheduled instead of dropping it.
 */
export async function expectedScheduleUnits(machineName: string): Promise<ExpectedScheduleUnit[]> {
  const config = await configService.getCurrent();
  const machine = config?.resources?.machines?.[machineName];
  if (!config || !machine) throw new Error(`Machine "${machineName}" not found`);
  const all = config.resources?.backupStrategies ?? {};
  const expected: ExpectedScheduleUnit[] = [];
  for (const name of machine.backupStrategies ?? []) {
    if (!(name in all)) continue;
    const strategy: ScheduledStrategy = all[name];
    if (strategy.enabled === false) continue;
    let specs: ScheduleUnitSpec[];
    try {
      specs = machineUnitSpecs([{ name, config: strategy }], config, machineName);
    } catch {
      specs = [];
    }
    if (specs.length === 0) {
      expected.push({ unitName: name, strategyName: name, schedule: strategy.schedule });
      continue;
    }
    for (const spec of specs) {
      expected.push({ unitName: spec.unitName, strategyName: name, schedule: spec.schedule });
    }
  }
  return expected;
}

/**
 * The units `backup status` reads: the machine's expected scheduled units, narrowed to one strategy. A named
 * strategy with no unit spec is still listed under its own name, so status reports it as not scheduled.
 */
export async function expectedStatusUnits(
  machineName: string,
  strategyFilter?: string
): Promise<ExpectedScheduleUnit[]> {
  const localConfig = await configService.getLocalConfig();
  if (!localConfig.machines[machineName]) throw new Error(`Machine "${machineName}" not found`);
  const expected = (await expectedScheduleUnits(machineName)).filter(
    (u) => strategyFilter === undefined || u.strategyName === strategyFilter
  );
  if (strategyFilter !== undefined && expected.length === 0) {
    const strategy = await configService.getBackupStrategy(strategyFilter);
    expected.push({
      unitName: strategyFilter,
      strategyName: strategyFilter,
      schedule: strategy?.schedule ?? '',
    });
  }
  return expected;
}

/**
 * `backup status` render: per unit, scheduled or not, last run and result, next run, and a missed-run verdict, from
 * the `systemctl show` text a `backup-status` job returned. Prints the table and sets exit code 2 when any unit could
 * not be read, else 1 when any unit is unscheduled or missed a run ({@link scheduleStatusExitCode}).
 */
export function renderBackupScheduleStatus(
  machineName: string,
  expected: ExpectedScheduleUnit[],
  showOutput: string
): ScheduleStatusRow[] {
  const unreadCause = showOutput.trim() === '' ? 'the read returned no output' : undefined;
  const rows = buildScheduleStatusRows(
    expected,
    parseFoldedSystemctlShow(showOutput),
    Date.now(),
    unreadCause
  );
  if (rows.length === 0) {
    outputService.warn(
      `No backup strategy is bound to ${machineName}, so nothing is scheduled. Bind one with: rdc backup strategy bind <name> -m ${machineName}`
    );
    setExitCode(1);
    return rows;
  }
  outputService.print(
    rows.map((r) => ({
      strategy: r.strategy,
      unit: r.unit,
      status: statusLabel(r),
      lastRun: r.lastRun,
      result: r.result,
      nextRun: r.nextRun,
      missed: r.missed ? (r.reason ?? BACKUP_DEFAULTS.MISSED_REASON_FALLBACK) : '-',
    })),
    getOutputFormat()
  );
  const unread = rows.filter((r) => r.unread);
  if (unread.length > 0) {
    outputService.error(
      `Could not read the backup schedule status of ${unread.length} unit(s) on ${machineName}${unread[0].reason ? `: ${unread[0].reason}` : ''}. This is not a verdict that no timer exists.`
    );
  }
  const code = scheduleStatusExitCode(rows);
  if (code !== 0) setExitCode(code);
  return rows;
}

function statusLabel(r: ScheduleStatusRow): string {
  if (r.unread) return 'unreadable';
  return r.scheduled ? 'scheduled' : 'not scheduled';
}

function sftpTocKeyTransport(sftp: SFTPClient): TocKeyTransport {
  return {
    async run(command, stdin) {
      let stdout = '';
      const exitCode = await sftp.execStreaming(command, {
        ...(stdin === undefined ? {} : { stdin }),
        onStdout: (data) => {
          stdout += data.toString();
        },
        onStderr: () => {},
      });
      return { exitCode, stdout };
    },
  };
}

/**
 * Install the browse-listing public key of every repository the deploy covers. Best-effort: the schedule is the
 * deliverable, so a failure here is a warning, never a thrown deploy. A dry run reads and writes nothing.
 */
async function installTocKeys(
  sftp: SFTPClient,
  machineName: string,
  specs: ScheduleUnitSpec[],
  remoteRenetPath: string,
  options: PushScheduleOptions
): Promise<void> {
  try {
    const config = await configService.getCurrent();
    if (!config) return;
    const targets = tocKeyTargetsFor(config, machineName, specs);
    if (targets.length === 0) return;
    if (options.dryRun) {
      outputService.info(
        `Dry-run: would compare the TOC key of ${targets.length} repositor${targets.length === 1 ? 'y' : 'ies'}; nothing was read or written`
      );
      return;
    }
    const results = await syncTocKeys(sftpTocKeyTransport(sftp), remoteRenetPath, targets, {});
    for (const line of tocKeyWarnings(results)) outputService.warn(line);
  } catch (error) {
    outputService.warn(
      `TOC keys were not checked on ${machineName}: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Push backup schedule to a remote machine.
 *
 * Reads machine.backupStrategies[] to determine which strategies to deploy.
 * See the module header for reconciliation semantics.
 */
export async function pushBackupSchedule(
  machineName: string,
  options: PushScheduleOptions = {}
): Promise<PushScheduleResult> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const strategyNames = machine.backupStrategies ?? [];
  if (strategyNames.length === 0) {
    throw new Error(
      `No backup strategies bound to machine "${machineName}". Bind with: rdc backup strategy bind <name> -m ${machineName}`
    );
  }

  const strategies = await loadAndValidateStrategies(strategyNames);
  await warnAboutUnboundStrategies(localConfig.machines);
  // Resolved BEFORE anything touches the machine: an unknown repo name or a placement-less repo fails the deploy here, not inside a timer at 03:00.
  const specs = await resolveUnitSpecs(machineName, strategies);
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const remoteRenetPath = await preDeployProvisioning(
    machineName,
    localConfig,
    machine,
    sshPrivateKey,
    options
  );

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;
  let released = false;

  try {
    const cpuCount = await resolveMachineCpuCount(sftp);
    await installTocKeys(sftp, machineName, specs, remoteRenetPath, options);
    const desired = computeDesiredUnits(specs, remoteRenetPath, cpuCount);
    const remote = await readRemoteState(sftp, Array.from(desired.keys()));
    const plan = computeReconcilePlan(desired, remote);
    applyInFlightGate(plan, options.force ?? false);

    if (options.dryRun) {
      outputService.info(`Dry-run: plan for ${machineName}`);
      emitPlanSummary(plan);
      if (options.debug) printDryRunUnitBodies(plan);
      return 'dry-run';
    }

    emitPlanSummary(plan);
    if (!plan.daemonReloadNeeded) {
      outputService.info(`No changes needed on ${machineName}`);
      return 'unchanged';
    }

    // The reads are done: release the connection before the job opens its own.
    lease.release();
    released = true;
    return await applyScheduleJob(machineName, buildSchedulePayload(plan, options), options);
  } finally {
    if (!released) lease.release();
  }
}

/**
 * Apply the plan as ONE `backup-schedule` job. The unit bodies (env files carry credentials) ride the job's stdin
 * payload, never an argument or a step param.
 */
async function applyScheduleJob(
  machineName: string,
  payload: SchedulePayload,
  options: PushScheduleOptions
): Promise<PushScheduleResult> {
  const outcome = await runCommandJob(
    'backup schedule',
    {
      functionName: 'backup-schedule',
      machineName,
      commandKind: { name: 'backup-schedule', payload: JSON.stringify(payload) },
      debug: options.debug,
      captureOutput: true,
    },
    options.steps ?? []
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return 'pending';
  }
  if (!outcome.result.success) {
    const detail = outcome.result.error ?? outcome.result.stderr?.trim() ?? '';
    throw new Error(
      `Applying the backup schedule on ${machineName} failed${detail ? `: ${detail}` : ''}`
    );
  }
  if (options.debug && outcome.result.stdout) outputService.info(outcome.result.stdout.trimEnd());
  return 'applied';
}

/** @internal Exported for unit tests and ad-hoc backup execution. */
export const _testing = {
  generateServiceUnit,
  generateTimerUnit,
  cronToOnCalendar,
  buildBackupCommands,
  generateEnvFile,
  envFilePath,
  sha256Hex,
  computeReconcilePlan,
  applyInFlightGate,
  parseStrategyFromPath,
  parseSystemctlShow,
  preDeployProvisioning,
};
export { sanitizeBackupOutput };
