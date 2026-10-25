import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import type { SFTPClient } from '../remote/sftp/index.js';
import { hasAccountToken, pushStrategyRetention } from '../services/backup/backup-retention.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { writeStderr, writeStdout } from '../services/core/request-context.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { acquireRemoteRenet, readSSHKey } from '../services/renet/renet-execution.js';
import { handleError } from '../utils/errors.js';

/** Resolve which strategy names to trigger. */
function resolveStrategyNames(
  strategyFilter: string | undefined,
  boundNames: string[],
  allStrategyNames: string[]
): string[] {
  if (strategyFilter) return [strategyFilter];
  if (boundNames.length > 0) return boundNames;
  return allStrategyNames;
}

/** Trigger a deployed systemd backup service. */
async function triggerDeployedUnit(
  sftp: SFTPClient,
  serviceName: string,
  debug?: boolean
): Promise<void> {
  outputService.info(`Triggering ${serviceName}...`);
  const exitCode = await sftp.execStreaming(`sudo systemctl start ${serviceName}`, {
    onStdout: (data) => {
      if (debug) writeStdout(data);
    },
    onStderr: (data) => {
      writeStderr(data);
    },
  });
  if (exitCode === 0) {
    outputService.success(`Triggered ${serviceName}`);
  } else {
    outputService.warn(`Failed to trigger ${serviceName} (exit ${exitCode})`);
  }
}

/**
 * The unit names a strategy runs as on a machine: the base unit, one per datastore (`.ds.`) and one per
 * repository with its own cadence (`.repo.`), as `backup schedule` renders them. A strategy that is not
 * bound to the machine, or whose units cannot be resolved, falls back to its bare name.
 */
async function strategyUnitNames(machineName: string, strategyName: string): Promise<string[]> {
  const { expectedScheduleUnits } = await import('../services/backup/backup-schedule.js');
  let units: string[] = [];
  try {
    units = (await expectedScheduleUnits(machineName))
      .filter((u) => u.strategyName === strategyName)
      .map((u) => u.unitName);
  } catch {
    units = [];
  }
  return units.length > 0 ? units : [strategyName];
}

/** Whether `rediacc-backup-<unit>.service` is installed on the machine. */
async function isUnitDeployed(sftp: SFTPClient, unit: string): Promise<boolean> {
  let checkOutput = '';
  await sftp.execStreaming(`systemctl cat rediacc-backup-${unit}.service 2>/dev/null`, {
    onStdout: (data) => {
      checkOutput += data;
    },
    onStderr: () => {},
  });
  return checkOutput.length > 0;
}

/** Run an ad-hoc backup via systemd-run when no deployed unit exists. */
async function triggerAdhocBackup(
  sftp: SFTPClient,
  machineName: string,
  name: string,
  config: import('../types/index.js').BackupStrategyConfig,
  remoteRenetPath: string,
  debug?: boolean
): Promise<void> {
  outputService.info(`No deployed unit for "${name}", running ad-hoc...`);
  const { buildStrategyCommandsForMachine, sanitizeBackupOutput } = await import(
    '../services/backup/backup-schedule.js'
  );
  const commands = await buildStrategyCommandsForMachine(
    machineName,
    name,
    config,
    remoteRenetPath
  );
  if (commands.length === 0) {
    outputService.warn(`Backup strategy "${name}" covers no repository on ${machineName}`);
    return;
  }

  const adhocUnit = `rediacc-backup-${name}-adhoc`;
  const fullCmd = commands.join(' && ');
  const systemdRunCmd = `sudo systemd-run --unit=${adhocUnit} --remain-after-exit /bin/bash -c '${fullCmd.replaceAll("'", "'\\''")}'`;

  if (debug) {
    outputService.info(`Running: ${sanitizeBackupOutput(systemdRunCmd)}`);
  }

  const exitCode = await sftp.execStreaming(systemdRunCmd, {
    onStdout: (data) => {
      if (debug) writeStdout(data);
    },
    onStderr: (data) => {
      writeStderr(data);
    },
  });

  if (exitCode === 0) {
    outputService.success(`Ad-hoc backup started: ${adhocUnit}.service`);
  } else {
    outputService.warn(`Failed to start ad-hoc backup for "${name}" (exit ${exitCode})`);
  }
}

/**
 * Declare each strategy's retention on the lineages it covers, filling only lineages that have no
 * policy of their own (a per-repo `backup retention set` stays). Best-effort: the schedule or run it
 * rides on matters more than the policy push, and the server enforces its default meanwhile.
 */
async function seedStrategyRetention(names: string[], machineName: string): Promise<void> {
  if (!hasAccountToken()) return;
  const all = await configService.listBackupStrategies();
  for (const name of names) {
    const strategy = all[name] as (typeof all)[string] | undefined;
    if (!strategy?.retention) continue;
    try {
      const { pushed } = await pushStrategyRetention(strategy, { overwrite: false, machineName });
      if (pushed > 0) {
        outputService.info(
          t('commands.backup.retention.seeded', { strategy: name, count: pushed })
        );
      }
    } catch (error) {
      outputService.warn(
        t('commands.backup.retention.seedFailed', {
          strategy: name,
          reason: error instanceof Error ? error.message : String(error),
        })
      );
    }
  }
}

async function runBackupNow(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }

  // Allow triggering strategies bound to the machine OR any strategy in config
  const allStrategies = await configService.listBackupStrategies();
  const boundNames = machine.backupStrategies ?? [];
  const toTrigger = resolveStrategyNames(strategyFilter, boundNames, Object.keys(allStrategies));

  if (toTrigger.length === 0) {
    throw new Error(
      'No backup strategies found. Create one with: rdc backup strategy set <name> --cron "..."'
    );
  }

  // Load strategy configs (cast to handle Record index access)
  const strategies: { name: string; config: (typeof allStrategies)[string] }[] = [];
  for (const stratName of toTrigger) {
    const config = allStrategies[stratName] as (typeof allStrategies)[string] | undefined;
    if (!config) {
      throw new Error(`Backup strategy "${stratName}" not found in config`);
    }
    strategies.push({ name: stratName, config });
  }

  await seedStrategyRetention(toTrigger, machineName);

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet to get the remote path
  const { remotePath: remoteRenetPath } = await acquireRemoteRenet(
    'provision',
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug }
  );

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;

  try {
    for (const { name, config } of strategies) {
      const deployed: string[] = [];
      for (const unit of await strategyUnitNames(machineName, name)) {
        if (await isUnitDeployed(sftp, unit)) deployed.push(unit);
      }
      if (deployed.length === 0) {
        await triggerAdhocBackup(sftp, machineName, name, config, remoteRenetPath, debug);
        continue;
      }
      for (const unit of deployed) {
        await triggerDeployedUnit(sftp, `rediacc-backup-${unit}.service`, debug);
      }
    }
  } finally {
    lease.release();
  }
}

/** Try to cancel a single systemd unit if active. Returns true if cancelled. */
async function tryCancelUnit(sftp: SFTPClient, unit: string, debug?: boolean): Promise<boolean> {
  // Only a running unit is worth stopping, a failed one has already exited, so `systemctl stop` on it would be a no-op reported as a cancellation.
  const state = await readServiceState(sftp, unit);
  if (state !== 'active' && state !== 'activating') return false;
  outputService.info(t('commands.backup.cancel.cancelling', { name: unit }));
  const exitCode = await sftp.execStreaming(`sudo systemctl stop ${unit}`, {
    onStdout: (data) => {
      if (debug) writeStdout(data);
    },
    onStderr: (data) => {
      writeStderr(data);
    },
  });
  if (exitCode === 0) {
    outputService.success(t('commands.backup.cancel.cancelled', { name: unit }));
    return true;
  }
  return false;
}

async function cancelBackup(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }

  const boundNames = machine.backupStrategies ?? [];
  const toCheck = strategyFilter ? [strategyFilter] : boundNames;

  if (toCheck.length === 0) {
    throw new Error(`No backup strategies bound to "${machineName}"`);
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);

  try {
    for (const name of toCheck) {
      await cancelStrategyUnits(lease.sftp, machineName, name, debug);
    }
  } finally {
    lease.release();
  }
}

/** Try to cancel every scheduled unit of a strategy (base, `.ds.`, `.repo.`) and its ad-hoc unit. */
async function cancelStrategyUnits(
  sftp: SFTPClient,
  machineName: string,
  name: string,
  debug?: boolean
): Promise<void> {
  const unitNames = new Set([name, ...(await strategyUnitNames(machineName, name))]);
  const units = [
    ...[...unitNames].map((u) => `rediacc-backup-${u}.service`),
    `rediacc-backup-${name}-adhoc.service`,
  ];
  let cancelled = false;
  for (const unit of units) {
    if (await tryCancelUnit(sftp, unit, debug)) cancelled = true;
  }
  if (!cancelled) {
    outputService.info(t('commands.backup.cancel.notRunning', { name }));
  }
}

/**
 * Read a backup unit's systemd state.
 *
 * Returns the state verbatim rather than a boolean. Collapsing it to
 * active-or-not made a FAILED unit render exactly like a healthy idle one, which
 * is how a backup stayed broken for six days while this command kept reporting
 * "idle", the string systemd hands back already said `failed`, and the old code
 * threw it away one line later.
 */
async function readServiceState(sftp: SFTPClient, serviceName: string): Promise<string> {
  let statusText = '';
  await sftp.execStreaming(`systemctl is-active ${serviceName} 2>/dev/null || true`, {
    onStdout: (data) => {
      statusText += data;
    },
    onStderr: () => {},
  });
  return statusText.trim();
}

/**
 * `backup status`: one row per scheduled unit (base, `.ds.`, `.repo.`) with timer presence, last run
 * and result, next run and a missed-run verdict, then the recent journal of a named strategy's units.
 */
async function showBackupStatus(machineName: string, strategyFilter?: string): Promise<void> {
  const { reportBackupScheduleStatus } = await import('../services/backup/backup-schedule.js');
  await reportBackupScheduleStatus(machineName, strategyFilter);
  if (!strategyFilter) return;

  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  try {
    outputService.info(`\nRecent logs (${strategyFilter}):`);
    await lease.sftp.execStreaming(
      `journalctl -u 'rediacc-backup-${strategyFilter}.service' -u 'rediacc-backup-${strategyFilter}.*.service' --no-pager -n 20 2>/dev/null || echo "(no logs)"`,
      {
        onStdout: (data) => {
          writeStdout(data);
        },
        onStderr: () => {},
      }
    );
  } finally {
    lease.release();
  }
}

/** Register the machine-scoped backup ops: schedule, run, status, cancel. */
export function registerBackupOpsCommands(backup: Command): void {
  backup
    .command('schedule')
    .description(t('commands.backup.schedule.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--dry-run', t('commands.backup.schedule.optionDryRun'))
    .option('--force', t('commands.backup.schedule.optionForce'))
    .option('--reset-failed', t('commands.backup.schedule.optionResetFailed'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const machineName = options.machine;
        const { pushBackupSchedule } = await import('../services/backup/backup-schedule.js');
        await pushBackupSchedule(machineName, {
          debug: options.debug,
          dryRun: options.dryRun,
          force: options.force,
          resetFailed: options.resetFailed,
        });
        if (!options.dryRun) {
          outputService.success(t('commands.backup.schedule.success', { machine: machineName }));
          const bound = (await configService.getLocalConfig()).machines[machineName];
          await seedStrategyRetention(bound?.backupStrategies ?? [], machineName);
          // DR nudge: enabling backups without config-storage enrollment leaves the repo credentials (LUKS passphrases) host-local (spec/02 dec 14).
          const { warnIfConfigStorageUnenrolled } = await import('../services/backup/dr-nudge.js');
          await warnIfConfigStorageUnenrolled();
        }
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('run')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.run.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await runBackupNow(options.machine, strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('status')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.status.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await showBackupStatus(options.machine, strategy);
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('cancel')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.cancel.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await cancelBackup(options.machine, strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}
