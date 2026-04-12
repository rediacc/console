import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import { provisionRenetToRemote, readSSHKey } from '../../services/renet-execution.js';
import { handleError } from '../../utils/errors.js';

export function registerDeployBackupCommand(machine: Command): void {
  const backup = machine.command('backup').description(t('commands.machine.backup.description'));

  // machine backup list
  backup
    .command('list')
    .description(t('commands.machine.backup.list.description'))
    .action(async () => {
      try {
        const localConfig = await configService.getLocalConfig();
        const strategies = await configService.listBackupStrategies();
        const machines = localConfig.machines;
        const machineNames = Object.keys(machines);

        if (machineNames.length === 0) {
          outputService.info('No machines configured');
          return;
        }

        const rows: Record<string, string>[] = [];
        for (const machineName of machineNames) {
          const machine = machines[machineName];
          if (!machine) continue;
          const bound = machine.backupStrategies ?? [];
          if (bound.length === 0) {
            rows.push({ machine: machineName, strategy: '-', schedule: '-', mode: '-', destinations: '-' });
            continue;
          }
          for (const stratName of bound) {
            const strat = strategies[stratName];
            if (!strat) {
              rows.push({ machine: machineName, strategy: stratName, schedule: '?', mode: '?', destinations: 'missing from config' });
              continue;
            }
            rows.push({
              machine: machineName,
              strategy: stratName,
              schedule: strat.schedule,
              mode: strat.mode ?? 'hot',
              destinations: strat.destinations.map((d: { name: string }) => d.name).join(', '),
            });
          }
        }

        outputService.print(rows, 'table');
      } catch (error) {
        handleError(error);
      }
    });

  // machine backup schedule
  backup
    .command('schedule')
    .description(t('commands.machine.backup.schedule.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--dry-run', t('commands.machine.backup.schedule.optionDryRun'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const machineName = options.machine;
        const { pushBackupSchedule } = await import('../../services/backup-schedule.js');
        await pushBackupSchedule(machineName, {
          debug: options.debug,
          dryRun: options.dryRun,
        });
        if (!options.dryRun) {
          outputService.success(
            t('commands.machine.backup.schedule.success', { machine: machineName })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // machine backup now
  backup
    .command('now')
    .description(t('commands.machine.backup.now.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--strategy <name>', t('commands.machine.backup.now.optionStrategy'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        await triggerBackupNow(options.machine, options.strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  // machine backup status
  backup
    .command('status')
    .description(t('commands.machine.backup.status.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--strategy <name>', t('commands.machine.backup.status.optionStrategy'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        await showBackupStatus(options.machine, options.strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  // machine backup cancel
  backup
    .command('cancel')
    .description(t('commands.machine.backup.cancel.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--strategy <name>', t('commands.machine.backup.cancel.optionStrategy'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        await cancelBackup(options.machine, options.strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}

async function triggerBackupNow(
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
  const toTrigger = strategyFilter
    ? [strategyFilter]
    : boundNames.length > 0
      ? boundNames
      : Object.keys(allStrategies);

  if (toTrigger.length === 0) {
    throw new Error('No backup strategies found. Create one with: rdc config backup-strategy set --name <name> --cron "..."');
  }

  // Load strategy configs
  const strategies: { name: string; config: (typeof allStrategies)[string] }[] = [];
  for (const name of toTrigger) {
    const config = allStrategies[name];
    if (!config) {
      throw new Error(`Backup strategy "${name}" not found in config`);
    }
    strategies.push({ name, config });
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

  const { SFTPClient } = await import('@rediacc/shared-desktop/sftp');
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    for (const { name, config } of strategies) {
      const serviceName = `rediacc-backup-${name}.service`;

      // Check if the systemd unit is deployed
      let unitDeployed = false;
      let checkOutput = '';
      await sftp.execStreaming(`systemctl cat ${serviceName} 2>/dev/null`, {
        onStdout: (data) => { checkOutput += data; },
        onStderr: () => {},
      });
      unitDeployed = checkOutput.length > 0;

      if (unitDeployed) {
        // Deployed: trigger via systemctl
        outputService.info(`Triggering ${serviceName}...`);
        const exitCode = await sftp.execStreaming(`sudo systemctl start ${serviceName}`, {
          onStdout: (data) => { if (debug) process.stdout.write(data); },
          onStderr: (data) => { process.stderr.write(data); },
        });
        if (exitCode !== 0) {
          outputService.warn(`Failed to trigger ${serviceName} (exit ${exitCode})`);
        } else {
          outputService.success(`Triggered ${serviceName}`);
        }
      } else {
        // Not deployed: build command from config and run via systemd-run
        outputService.info(`No deployed unit for "${name}", running ad-hoc...`);
        const { buildRcloneArgs } = await import('@rediacc/shared/queue-vault');
        const { _testing } = await import('../../services/backup-schedule.js');

        const enabledDests = config.destinations.filter((d) => d.enabled !== false);
        const rcloneArgsByDest = new Map<string, { remote: string; params: string[] }>();
        for (const dest of enabledDests) {
          const storageCfg = await configService.getStorage(dest.storage);
          rcloneArgsByDest.set(dest.name, buildRcloneArgs(storageCfg.vaultContent));
        }

        const commands = _testing.buildBackupCommands(
          config, enabledDests, rcloneArgsByDest, datastore, remoteRenetPath
        );

        const adhocUnit = `rediacc-backup-${name}-adhoc`;
        const fullCmd = commands.join(' && ');
        const systemdRunCmd = `sudo systemd-run --unit=${adhocUnit} --remain-after-exit /bin/bash -c '${fullCmd.replace(/'/g, "'\\''")}'`;

        if (debug) {
          const { sanitizeBackupOutput } = await import('../../services/backup-schedule.js');
          outputService.info(`Running: ${sanitizeBackupOutput(systemdRunCmd)}`);
        }

        const exitCode = await sftp.execStreaming(systemdRunCmd, {
          onStdout: (data) => { if (debug) process.stdout.write(data); },
          onStderr: (data) => { process.stderr.write(data); },
        });

        if (exitCode !== 0) {
          outputService.warn(`Failed to start ad-hoc backup for "${name}" (exit ${exitCode})`);
        } else {
          outputService.success(`Ad-hoc backup started: ${adhocUnit}.service`);
        }
      }
    }
  } finally {
    sftp.close();
  }
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

  const { SFTPClient } = await import('@rediacc/shared-desktop/sftp');
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    for (const name of toCheck) {
      // Try both scheduled and ad-hoc unit names
      const units = [
        `rediacc-backup-${name}.service`,
        `rediacc-backup-${name}-adhoc.service`,
      ];

      let cancelled = false;
      for (const unit of units) {
        let isActive = '';
        await sftp.execStreaming(`systemctl is-active ${unit} 2>/dev/null || true`, {
          onStdout: (data) => { isActive += data; },
          onStderr: () => {},
        });

        if (isActive.trim() === 'active' || isActive.trim() === 'activating') {
          outputService.info(t('commands.machine.backup.cancel.cancelling', { name: unit }));
          const exitCode = await sftp.execStreaming(`sudo systemctl stop ${unit}`, {
            onStdout: (data) => { if (debug) process.stdout.write(data); },
            onStderr: (data) => { process.stderr.write(data); },
          });
          if (exitCode === 0) {
            outputService.success(t('commands.machine.backup.cancel.cancelled', { name: unit }));
            cancelled = true;
          }
        }
      }

      if (!cancelled) {
        outputService.info(t('commands.machine.backup.cancel.notRunning', { name }));
      }
    }
  } finally {
    sftp.close();
  }
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
  await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug }
  );

  const { SFTPClient } = await import('@rediacc/shared-desktop/sftp');
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    const configuredStrategies = machine.backupStrategies ?? [];
    const namesToCheck = strategyFilter ? [strategyFilter] : configuredStrategies;

    // Build status table
    const rows: Record<string, string>[] = [];
    for (const name of namesToCheck) {
      const serviceName = `rediacc-backup-${name}.service`;
      let statusText = '';
      await sftp.execStreaming(`systemctl is-active ${serviceName} 2>/dev/null || true`, {
        onStdout: (data) => { statusText += data; },
        onStderr: () => {},
      });
      const isActive = statusText.trim() === 'active' || statusText.trim() === 'activating';

      const strategy = await configService.getBackupStrategy(name);
      rows.push({
        strategy: name,
        mode: strategy?.mode ?? 'hot',
        schedule: strategy?.schedule ?? '-',
        status: isActive ? 'RUNNING' : 'idle',
      });
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
    sftp.close();
  }
}
