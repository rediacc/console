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

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '../shared-desktop/sftp/index.js';
import type { BackupStrategyConfig } from '../types/index.js';
import {
  emitPlanSummary,
  executePlan,
  printDryRunUnitBodies,
  verifyPostDeploy,
} from './backup-schedule/execute.js';
import {
  applyInFlightGate,
  computeDesiredUnits,
  computeReconcilePlan,
  parseStrategyFromPath,
  parseSystemctlShow,
  readRemoteState,
  type ReconcileOptions,
} from './backup-schedule/reconcile.js';
import {
  buildBackupCommands,
  buildDestinationCommand,
  cronToOnCalendar,
  generateServiceUnit,
  generateTimerUnit,
  sanitizeBackupOutput,
  sha256Hex,
} from './backup-schedule/unit-generator.js';
import { envFilePath, generateEnvFile } from './backup-env-file.js';
import { configService } from './config-resources.js';
import { refreshRepoLicensesBatch } from './license.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';
import { REMOTE_INSTALL_PATH } from './renet-provisioner.js';

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
      `No backup strategies bound to machine "${machineName}". Bind with: rdc config machine set --name ${machineName} --backup-strategy <name>`
    );
  }

  const strategies = await loadAndValidateStrategies(strategyNames);
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const remoteRenetPath = await preDeployProvisioning(localConfig, machine, sshPrivateKey, options);

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

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
    sftp.close();
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
