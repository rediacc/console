/**
 * Backup Schedule Service
 *
 * Pushes backup schedule configuration to remote machines via SSH.
 * Each strategy becomes one systemd service + timer pair. A strategy may
 * have multiple destinations (upload to all from the same snapshot).
 *
 * Deploy strategy: state-based reconciliation. Read remote state (existing
 * unit files + SHA-256 hashes + systemd status), diff against desired, only
 * touch what changed. In-flight backups are detected and block updates/
 * removes by default (`--force` to override). Writes are staged to
 * `<path>.new` and `mv`-committed so a partial SSH failure never leaves
 * the machine with a half-deployed unit. Post-deploy, timers are
 * re-queried to confirm they actually loaded.
 *
 * Implementation is split across:
 * - backup-schedule/unit-generator.ts — pure content generators
 * - backup-schedule/reconcile.ts      — read + diff + in-flight gate
 * - backup-schedule/execute.ts        — mutations + verification + summary
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { BackupStrategyConfig } from '../../types/index.js';
import { refreshRepoLicensesBatch } from '../account/license.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { machineConnections } from '../machine/machine-connection.js';
import { provisionRenetToRemote, readSSHKey } from '../renet/renet-execution.js';
import { REMOTE_INSTALL_PATH } from '../renet/renet-provisioner.js';
import { envFilePath, generateEnvFile } from './backup-env-file.js';
import {
  emitPlanSummary,
  executePlan,
  printDryRunUnitBodies,
  verifyPostDeploy,
} from './backup-schedule-execute.js';
import {
  applyInFlightGate,
  computeDesiredUnits,
  computeReconcilePlan,
  parseStrategyFromPath,
  parseSystemctlShow,
  type ReconcileOptions,
  readRemoteState,
} from './backup-schedule-reconcile.js';
import {
  buildBackupCommands,
  buildDestinationCommand,
  cronToOnCalendar,
  generateServiceUnit,
  generateTimerUnit,
  sanitizeBackupOutput,
  sha256Hex,
} from './backup-schedule-unit-generator.js';

type PushScheduleOptions = ReconcileOptions;

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
): Promise<{ name: string; config: BackupStrategyConfig }[]> {
  const strategies: { name: string; config: BackupStrategyConfig }[] = [];
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
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  const { remotePath } = await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug: options.debug }
  );
  const repoRefresh = await refreshRepoLicensesBatch(machine, sshPrivateKey, remotePath);
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
 * A warning rather than an error on purpose — a strategy staged before its
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
 * Push backup schedule to a remote machine.
 *
 * Reads machine.backupStrategies[] to determine which strategies to deploy.
 * See the module header for reconciliation semantics.
 */
export async function pushBackupSchedule(
  machineName: string,
  options: PushScheduleOptions = {}
): Promise<void> {
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
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const remoteRenetPath = await preDeployProvisioning(localConfig, machine, sshPrivateKey, options);

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;

  try {
    const desired = await computeDesiredUnits(strategies, datastore, remoteRenetPath);
    const remote = await readRemoteState(sftp, Array.from(desired.keys()));
    const plan = computeReconcilePlan(desired, remote);
    applyInFlightGate(plan, options.force ?? false);

    if (options.dryRun) {
      outputService.info(`Dry-run: plan for ${machineName}`);
      emitPlanSummary(plan);
      if (options.debug) printDryRunUnitBodies(plan);
      return;
    }

    emitPlanSummary(plan);
    if (!plan.daemonReloadNeeded) {
      outputService.info(`No changes needed on ${machineName}`);
      return;
    }

    await executePlan(sftp, plan, options);
    await verifyPostDeploy(sftp, plan);
  } finally {
    lease.release();
  }
}

/** @internal Exported for unit tests and ad-hoc backup execution. */
export const _testing = {
  generateServiceUnit,
  generateTimerUnit,
  cronToOnCalendar,
  buildBackupCommands,
  buildDestinationCommand,
  generateEnvFile,
  envFilePath,
  sha256Hex,
  computeReconcilePlan,
  applyInFlightGate,
  parseStrategyFromPath,
  parseSystemctlShow,
};
export { sanitizeBackupOutput };
