import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';
import type { MachineConfig, OutputFormat, S3Config } from '../types/index.js';
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
  const machine = await contextService.getLocalMachine(machineName);
  const keyscan = scanHostKeys(machine.ip, machine.port ?? DEFAULTS.SSH.PORT);
  if (keyscan) {
    await contextService.updateLocalMachine(machineName, {
      knownHosts: keyscan,
    });
    outputService.success(t('commands.context.scanKeys.keysScanned', { name: machineName }));
  } else {
    outputService.warn(t('commands.context.scanKeys.noKeys', { name: machineName }));
  }
}

async function scanAllMachines(): Promise<void> {
  const machines = await contextService.listLocalMachines();
  let scanned = 0;
  for (const m of machines) {
    try {
      const keyscan = scanHostKeys(m.config.ip, m.config.port ?? DEFAULTS.SSH.PORT);
      if (keyscan) {
        await contextService.updateLocalMachine(m.name, {
          knownHosts: keyscan,
        });
        outputService.info(t('commands.context.scanKeys.keysScanned', { name: m.name }));
        scanned++;
      }
    } catch {
      outputService.warn(t('commands.context.scanKeys.noKeys', { name: m.name }));
    }
  }
  outputService.success(
    t('commands.context.scanKeys.completed', {
      count: scanned,
      total: machines.length,
    })
  );
}

export function registerLocalCommands(context: Command, program: Command): void {
  // context create-local - Create a new local context
  context
    .command('create-local <name>')
    .description(t('commands.context.createLocal.description'))
    .requiredOption('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .action(async (name, options) => {
      try {
        const sshKeyPath = options.sshKey.startsWith('~')
          ? path.join(os.homedir(), options.sshKey.slice(1))
          : options.sshKey;

        try {
          await fs.access(sshKeyPath);
        } catch {
          throw new ValidationError(t('errors.sshKeyNotFound', { path: sshKeyPath }));
        }

        await contextService.createLocal(name, options.sshKey, {
          renetPath: options.renetPath,
        });
        outputService.success(t('commands.context.createLocal.success', { name }));
        outputService.info(t('commands.context.createLocal.nextStep'));
      } catch (error) {
        handleError(error);
      }
    });

  // context create-s3 - Create a new S3 context
  context
    .command('create-s3 <name>')
    .description(t('commands.context.createS3.description'))
    .requiredOption('--endpoint <url>', t('commands.context.createS3.optionEndpoint'))
    .requiredOption('--bucket <name>', t('commands.context.createS3.optionBucket'))
    .requiredOption('--access-key-id <key>', t('commands.context.createS3.optionAccessKeyId'))
    .requiredOption('--ssh-key <path>', t('commands.context.createS3.optionSshKey'))
    .option('--secret-access-key <key>', t('commands.context.createS3.optionSecretAccessKey'))
    .option('--region <region>', t('commands.context.createS3.optionRegion'), 'auto')
    .option('--prefix <prefix>', t('commands.context.createS3.optionPrefix'))
    .option('--renet-path <path>', t('commands.context.createS3.optionRenetPath'))
    .option('--master-password <password>', t('commands.context.createS3.optionMasterPassword'))
    .action(async (name, options) => {
      try {
        const sshKeyPath = options.sshKey.startsWith('~')
          ? path.join(os.homedir(), options.sshKey.slice(1))
          : options.sshKey;

        try {
          await fs.access(sshKeyPath);
        } catch {
          throw new ValidationError(t('errors.sshKeyNotFound', { path: sshKeyPath }));
        }

        const secretAccessKey =
          options.secretAccessKey ??
          (await askPassword(t('commands.context.createS3.promptSecretAccessKey')));

        if (!secretAccessKey) {
          throw new ValidationError(t('commands.context.createS3.errorSecretAccessKeyRequired'));
        }

        const masterPassword: string | undefined = options.masterPassword;

        let storedSecretAccessKey: string;
        let encryptedMasterPassword: string | undefined;

        if (masterPassword) {
          storedSecretAccessKey = await nodeCryptoProvider.encrypt(secretAccessKey, masterPassword);
          encryptedMasterPassword = await nodeCryptoProvider.encrypt(
            masterPassword,
            masterPassword
          );
        } else {
          storedSecretAccessKey = secretAccessKey;
          encryptedMasterPassword = undefined;
        }

        outputService.info(t('commands.context.createS3.verifyingAccess'));
        const { S3ClientService } = await import('../services/s3-client.js');
        const testClient = new S3ClientService({
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey,
          prefix: options.prefix,
        });
        await testClient.verifyAccess();
        outputService.success(t('commands.context.createS3.accessVerified'));

        await testClient.putJson('_meta.json', {
          schemaVersion: 2,
          createdAt: new Date().toISOString(),
          createdBy: 'rdc',
        });

        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(testClient, masterPassword ?? null);

        const sshPrivateKey = await fs.readFile(sshKeyPath, 'utf-8');
        let sshPublicKey = '';
        try {
          sshPublicKey = await fs.readFile(`${sshKeyPath}.pub`, 'utf-8');
        } catch {
          // Public key is optional
        }
        await stateService.setSSH({
          privateKey: sshPrivateKey.trim(),
          publicKey: sshPublicKey.trim() || undefined,
        });

        const s3Config: S3Config = {
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey: storedSecretAccessKey,
          prefix: options.prefix,
        };

        await contextService.createS3(name, s3Config, options.sshKey, {
          renetPath: options.renetPath,
          masterPassword: encryptedMasterPassword,
        });

        outputService.success(t('commands.context.createS3.success', { name }));
        outputService.info(t('commands.context.createS3.nextStep'));
      } catch (error) {
        handleError(error);
      }
    });

  // context add-machine - Add a machine to local/s3 context
  context
    .command('add-machine <name>')
    .description(t('commands.context.addMachine.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <username>', t('options.sshUser'))
    .option('--port <port>', t('options.sshPort'), '22')
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .action(async (name, options) => {
      try {
        const config: MachineConfig = {
          ip: options.ip,
          user: options.user,
          port: Number.parseInt(options.port, 10),
          datastore: options.datastore,
        };

        await contextService.addLocalMachine(name, config);
        outputService.success(
          t('commands.context.addMachine.success', {
            name,
            user: config.user,
            ip: config.ip,
          })
        );

        try {
          const keyscan = scanHostKeys(config.ip, config.port ?? DEFAULTS.SSH.PORT);
          if (keyscan) {
            await contextService.updateLocalMachine(name, {
              knownHosts: keyscan,
            });
            outputService.info(t('commands.context.scanKeys.keysScanned', { name }));
          }
        } catch {
          /* non-fatal */
        }
      } catch (error) {
        handleError(error);
      }
    });

  // context scan-keys [machine] - Scan SSH host keys for machines
  context
    .command('scan-keys [machine]')
    .description(t('commands.context.scanKeys.description'))
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

  // context remove-machine - Remove a machine from local context
  context
    .command('remove-machine <name>')
    .description(t('commands.context.removeMachine.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalMachine(name);
        outputService.success(t('commands.context.removeMachine.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context machines - List machines in local context
  context
    .command('machines')
    .description(t('commands.context.machines.description'))
    .action(async () => {
      try {
        const machines = await contextService.listLocalMachines();
        const format = program.opts().output as OutputFormat;

        if (machines.length === 0) {
          outputService.info(t('commands.context.machines.noMachines'));
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

  // context set-ssh - Update SSH configuration
  context
    .command('set-ssh')
    .description(t('commands.context.setSsh.description'))
    .requiredOption('--private-key <path>', t('options.sshPrivateKey'))
    .option('--public-key <path>', t('options.sshPublicKey'))
    .action(async (options) => {
      try {
        await contextService.setLocalSSH({
          privateKeyPath: options.privateKey,
          publicKeyPath: options.publicKey,
        });
        outputService.success(t('commands.context.setSsh.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // context set-renet - Set renet binary path
  context
    .command('set-renet <path>')
    .description(t('commands.context.setRenet.description'))
    .action(async (renetPath) => {
      try {
        await contextService.setRenetPath(renetPath);
        outputService.success(t('commands.context.setRenet.success', { path: renetPath }));
      } catch (error) {
        handleError(error);
      }
    });
}
