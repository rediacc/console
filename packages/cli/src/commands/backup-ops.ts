import { BACKUP_DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import type { SFTPClient } from '../remote/sftp/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet/renet-execution.js';
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
      if (debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (exitCode === 0) {
    outputService.success(`Triggered ${serviceName}`);
  } else {
    outputService.warn(`Failed to trigger ${serviceName} (exit ${exitCode})`);
  }
}

/** Run an ad-hoc backup via systemd-run when no deployed unit exists. */
async function triggerAdhocBackup(
  sftp: SFTPClient,
  name: string,
  config: import('../types/index.js').BackupStrategyConfig,
  datastore: string,
  remoteRenetPath: string,
  debug?: boolean
): Promise<void> {
  outputService.info(`No deployed unit for "${name}", running ad-hoc...`);
  const { _testing } = await import('../services/backup/backup-schedule.js');

  const enabledDests = config.destinations.filter((d) => d.enabled !== false);
  // INVERTED 2026-08-15. This used to require the rclone `storage` kind and
  // refuse hosted-service; the rclone path has been removed, so the chunk store
  // is the only destination an ad-hoc run can drive. Left as-is, this function
  // would now refuse every destination there is.
  for (const dest of enabledDests) {
    if (dest.kind !== 'hosted-service') {
      throw new Error(
        `Backup destination "${dest.name}" has kind "${(dest as { kind?: string }).kind ?? BACKUP_DEFAULTS.DESTINATION_KIND}". The ` +
          'rclone/OneDrive path was removed on 2026-08-15; change it to a ' +
          '`hosted-service` destination to run it.'
      );
    }
  }

  const { commands, envVars } = _testing.buildBackupCommands(
    config,
    enabledDests,
    datastore,
    remoteRenetPath
  );

  const adhocUnit = `rediacc-backup-${name}-adhoc`;
  const fullCmd = commands.join(' && ');
  // Pass credentials via systemd-run --setenv= so JSON tokens never appear in
  // the unit's on-disk ExecStart= line (or in `systemctl show` output as the
  // persistent units do). Each value is single-quote-wrapped so the outer
  // shell hands systemd-run exactly `KEY=value`.
  const shQuote = (v: string): string => `'${v.replaceAll("'", "'\\''")}'`;
  const setenvArgs = Object.entries(envVars)
    .map(([k, v]) => `--setenv=${k}=${shQuote(v)}`)
    .join(' ');
  const setenvPart = setenvArgs ? `${setenvArgs} ` : '';
  const systemdRunCmd = `sudo systemd-run --unit=${adhocUnit} ${setenvPart}--remain-after-exit /bin/bash -c '${fullCmd.replaceAll("'", "'\\''")}'`;

  if (debug) {
    const { sanitizeBackupOutput } = await import('../services/backup/backup-schedule.js');
    outputService.info(`Running: ${sanitizeBackupOutput(systemdRunCmd)}`);
  }

  const exitCode = await sftp.execStreaming(systemdRunCmd, {
    onStdout: (data) => {
      if (debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });

  if (exitCode === 0) {
    outputService.success(`Ad-hoc backup started: ${adhocUnit}.service`);
  } else {
    outputService.warn(`Failed to start ad-hoc backup for "${name}" (exit ${exitCode})`);
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

  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet to get the remote path
  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug }
  );

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;

  try {
    for (const { name, config } of strategies) {
      const serviceName = `rediacc-backup-${name}.service`;

      // Check if the systemd unit is deployed
      let checkOutput = '';
      await sftp.execStreaming(`systemctl cat ${serviceName} 2>/dev/null`, {
        onStdout: (data) => {
          checkOutput += data;
        },
        onStderr: () => {},
      });

      if (checkOutput.length > 0) {
        await triggerDeployedUnit(sftp, serviceName, debug);
      } else {
        await triggerAdhocBackup(sftp, name, config, datastore, remoteRenetPath, debug);
      }
    }
  } finally {
    lease.release();
  }
}

/** Try to cancel a single systemd unit if active. Returns true if cancelled. */
async function tryCancelUnit(sftp: SFTPClient, unit: string, debug?: boolean): Promise<boolean> {
  // Only a running unit is worth stopping — a failed one has already exited, so
  // `systemctl stop` on it would be a no-op reported as a cancellation.
  const state = await readServiceState(sftp, unit);
  if (state !== 'active' && state !== 'activating') return false;
  outputService.info(t('commands.backup.cancel.cancelling', { name: unit }));
  const exitCode = await sftp.execStreaming(`sudo systemctl stop ${unit}`, {
    onStdout: (data) => {
      if (debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
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
      await cancelStrategyUnits(lease.sftp, name, debug);
    }
  } finally {
    lease.release();
  }
}

/** Try to cancel both scheduled and ad-hoc units for a strategy. */
async function cancelStrategyUnits(sftp: SFTPClient, name: string, debug?: boolean): Promise<void> {
  const units = [`rediacc-backup-${name}.service`, `rediacc-backup-${name}-adhoc.service`];
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
 * "idle" — the string systemd hands back already said `failed`, and the old code
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
 * Map a systemd ActiveState to what an operator needs to see.
 *
 * `failed` must never be presentable as "nothing to see here"; an unknown state
 * is passed through rather than bucketed, so a systemd state this code has not
 * met yet shows up as itself instead of being silently normalised away.
 */
export function describeServiceState(state: string): string {
  switch (state) {
    case 'active':
    case 'activating':
      return 'RUNNING';
    case 'failed':
      return 'FAILED';
    case 'inactive':
    case '':
      return 'idle';
    default:
      return state;
  }
}

/** Build status row for a single backup strategy. */
async function buildStatusRow(sftp: SFTPClient, name: string): Promise<Record<string, string>> {
  const serviceName = `rediacc-backup-${name}.service`;
  const state = await readServiceState(sftp, serviceName);
  const strategy = await configService.getBackupStrategy(name);
  return {
    strategy: name,
    mode: strategy?.mode ?? BACKUP_DEFAULTS.MODE,
    schedule: strategy?.schedule ?? '-',
    status: describeServiceState(state),
  };
}

async function showBackupStatus(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet (needed for SSH connection)
  outputService.info(`Connecting to ${machine.ip}...`);
  await provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, sshPrivateKey, {
    debug,
  });

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;

  try {
    const configuredStrategies = machine.backupStrategies ?? [];
    const namesToCheck = strategyFilter ? [strategyFilter] : configuredStrategies;

    const rows: Record<string, string>[] = [];
    for (const name of namesToCheck) {
      rows.push(await buildStatusRow(sftp, name));
    }

    outputService.print(rows, 'table');

    // Show journal for specific strategy
    if (strategyFilter) {
      outputService.info(`\nRecent logs (${strategyFilter}):`);
      await sftp.execStreaming(
        `journalctl -u rediacc-backup-${strategyFilter}.service --no-pager -n 20 2>/dev/null || echo "(no logs)"`,
        {
          onStdout: (data) => {
            process.stdout.write(data);
          },
          onStderr: () => {},
        }
      );
    }
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
          // DR nudge: enabling backups without config-storage enrollment leaves
          // the repo credentials (LUKS passphrases) host-local (spec/02 dec 14).
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
        await showBackupStatus(options.machine, strategy, options.debug);
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
