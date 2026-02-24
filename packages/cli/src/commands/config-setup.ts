import { execFileSync } from 'node:child_process';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { handleError } from '../utils/errors.js';
import type { MachineConfig, OutputFormat } from '../types/index.js';
import type { Command } from 'commander';

function scanHostKeys(ip: string, port: number): string {
  try {
    const result = execFileSync('ssh-keyscan', ['-p', String(port), ip], {
      encoding: 'utf-8',
      timeout: 10_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return result.trim();
  } catch {
    return '';
  }
}

async function scanSingleMachine(machineName: string): Promise<void> {
  const machine = await configService.getLocalMachine(machineName);
  const keyscan = scanHostKeys(machine.ip, machine.port ?? DEFAULTS.SSH.PORT);
  if (keyscan) {
    await configService.updateMachine(machineName, {
      knownHosts: keyscan,
    });
    outputService.success(t('commands.config.scanKeys.keysScanned', { name: machineName }));
  } else {
    outputService.warn(t('commands.config.scanKeys.noKeys', { name: machineName }));
  }
}

async function scanAllMachines(): Promise<void> {
  const machines = await configService.listMachines();
  let scanned = 0;
  for (const m of machines) {
    try {
      const keyscan = scanHostKeys(m.config.ip, m.config.port ?? DEFAULTS.SSH.PORT);
      if (keyscan) {
        await configService.updateMachine(m.name, {
          knownHosts: keyscan,
        });
        outputService.info(t('commands.config.scanKeys.keysScanned', { name: m.name }));
        scanned++;
      }
    } catch {
      outputService.warn(t('commands.config.scanKeys.noKeys', { name: m.name }));
    }
  }
  outputService.success(
    t('commands.config.scanKeys.completed', {
      count: scanned,
      total: machines.length,
    })
  );
}

export function registerSetupCommands(config: Command, program: Command): void {
  // config add-machine
  config
    .command('add-machine <name>')
    .description(t('commands.config.addMachine.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <username>', t('options.sshUser'))
    .option('--port <port>', t('options.sshPort'), '22')
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .action(async (name, options) => {
      try {
        const machineConfig: MachineConfig = {
          ip: options.ip,
          user: options.user,
          port: Number.parseInt(options.port, 10),
          datastore: options.datastore,
        };

        await configService.addMachine(name, machineConfig);
        outputService.success(
          t('commands.config.addMachine.success', {
            name,
            user: machineConfig.user,
            ip: machineConfig.ip,
          })
        );

        try {
          const keyscan = scanHostKeys(machineConfig.ip, machineConfig.port ?? DEFAULTS.SSH.PORT);
          if (keyscan) {
            await configService.updateMachine(name, {
              knownHosts: keyscan,
            });
            outputService.info(t('commands.config.scanKeys.keysScanned', { name }));
          }
        } catch {
          /* non-fatal */
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config scan-keys [machine]
  config
    .command('scan-keys [machine]')
    .description(t('commands.config.scanKeys.description'))
    .action(async (machineName?: string) => {
      try {
        if (machineName) {
          await scanSingleMachine(machineName);
        } else {
          await scanAllMachines();
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config remove-machine
  config
    .command('remove-machine <name>')
    .description(t('commands.config.removeMachine.description'))
    .action(async (name) => {
      try {
        await configService.removeMachine(name);
        outputService.success(t('commands.config.removeMachine.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config machines
  config
    .command('machines')
    .description(t('commands.config.machines.description'))
    .action(async () => {
      try {
        const machines = await configService.listMachines();
        const format = program.opts().output as OutputFormat;

        if (machines.length === 0) {
          outputService.info(t('commands.config.machines.noMachines'));
          return;
        }

        const displayData = machines.map((m) => ({
          name: m.name,
          ip: m.config.ip,
          user: m.config.user,
          port: m.config.port ?? DEFAULTS.SSH.PORT,
          datastore: m.config.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config set-ssh
  config
    .command('set-ssh')
    .description(t('commands.config.setSsh.description'))
    .requiredOption('--private-key <path>', t('options.sshPrivateKey'))
    .option('--public-key <path>', t('options.sshPublicKey'))
    .action(async (options) => {
      try {
        await configService.setLocalSSH({
          privateKeyPath: options.privateKey,
          publicKeyPath: options.publicKey,
        });
        outputService.success(t('commands.config.setSsh.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // config set-renet
  config
    .command('set-renet <path>')
    .description(t('commands.config.setRenet.description'))
    .action(async (renetPath) => {
      try {
        await configService.setRenetPath(renetPath);
        outputService.success(t('commands.config.setRenet.success', { path: renetPath }));
      } catch (error) {
        handleError(error);
      }
    });

  // config setup-machine
  config
    .command('setup-machine <name>')
    .description(t('commands.config.setupMachine.description'))
    .option('--datastore <path>', t('commands.config.setupMachine.datastoreOption'), '/mnt/rediacc')
    .option('--datastore-size <size>', t('commands.config.setupMachine.datastoreSizeOption'), '95%')
    .option('--debug', t('options.debug'))
    .action(async (name, options) => {
      try {
        const localConfig = await configService.getLocalConfig();
        const machine = await configService.getLocalMachine(name);
        const sshPrivateKey =
          localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

        outputService.info(t('commands.config.setupMachine.starting', { machine: name }));

        await provisionRenetToRemote(localConfig, machine, sshPrivateKey, { debug: options.debug });

        const sftp = new SFTPClient({
          host: machine.ip,
          port: machine.port ?? DEFAULTS.SSH.PORT,
          username: machine.user,
          privateKey: sshPrivateKey,
        });
        await sftp.connect();

        try {
          const cmd = `sudo renet setup --auto --datastore ${options.datastore} --datastore-size ${options.datastoreSize}`;

          if (options.debug) {
            outputService.info(`[setup] Running: ${cmd}`);
          }

          const exitCode = await sftp.execStreaming(cmd, {
            onStdout: (data) => process.stdout.write(data),
            onStderr: (data) => process.stderr.write(data),
          });

          if (exitCode === 0) {
            outputService.success(t('commands.config.setupMachine.completed', { machine: name }));
          } else {
            outputService.error(
              t('commands.config.setupMachine.failed', {
                machine: name,
                error: `exit code ${exitCode}`,
              })
            );
            process.exitCode = exitCode;
          }
        } finally {
          sftp.close();
        }
      } catch (error) {
        handleError(error);
      }
    });
}
