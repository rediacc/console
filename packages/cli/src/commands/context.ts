import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { Command } from 'commander';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { apiClient } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askPassword, askText } from '../utils/prompt.js';
import type { LocalMachineConfig, NamedContext, OutputFormat, S3Config } from '../types/index.js';

export function registerContextCommands(program: Command): void {
  const context = program.command('context').description(t('commands.context.description'));

  // context list - List all contexts
  context
    .command('list')
    .alias('ls')
    .description(t('commands.context.list.description'))
    .action(async () => {
      try {
        const contexts = await contextService.list();
        const format = program.opts().output as OutputFormat;

        if (contexts.length === 0) {
          outputService.info(t('commands.context.list.noContexts'));
          return;
        }

        const displayData = contexts.map((ctx) => {
          let apiUrl: string | undefined;
          if (ctx.mode === 'local') {
            apiUrl = '-';
          } else if (ctx.mode === 's3') {
            apiUrl = ctx.s3?.endpoint ?? '-';
          } else {
            apiUrl = ctx.apiUrl;
          }

          return {
            name: ctx.name,
            mode: ctx.mode ?? DEFAULTS.CONTEXT.MODE,
            apiUrl,
            userEmail: ctx.userEmail ?? '-',
            team: ctx.team ?? '-',
            machines:
              ctx.mode === 'local' || ctx.mode === 's3'
                ? Object.keys(ctx.machines ?? {}).length.toString()
                : '-',
          };
        });

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context create - Create a new context
  context
    .command('create <name>')
    .description(t('commands.context.create.description'))
    .option('-u, --api-url <url>', t('options.apiUrl'))
    .action(async (name, options) => {
      try {
        // If no API URL provided, prompt for it, then normalize
        const rawUrl =
          options.apiUrl ??
          (await askText(t('prompts.apiUrl'), { default: 'https://www.rediacc.com/api' }));
        const apiUrl = apiClient.normalizeApiUrl(rawUrl);

        const newContext: NamedContext = {
          name,
          apiUrl,
        };

        await contextService.create(newContext);
        outputService.success(t('commands.context.create.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context delete - Delete a context
  context
    .command('delete <name>')
    .alias('rm')
    .description(t('commands.context.delete.description'))
    .action(async (name) => {
      try {
        await contextService.delete(name);
        outputService.success(t('commands.context.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context rename - Rename a context
  context
    .command('rename <oldName> <newName>')
    .description(t('commands.context.rename.description'))
    .action(async (oldName, newName) => {
      try {
        await contextService.rename(oldName, newName);
        outputService.success(t('commands.context.rename.success', { oldName, newName }));
      } catch (error) {
        handleError(error);
      }
    });

  // context current - Show current context name (for scripting)
  // Returns the context that would be used: from --context flag or "default"
  context
    .command('current')
    .description(t('commands.context.current.description'))
    .action(() => {
      try {
        const name = contextService.getCurrentName();
        // eslint-disable-next-line no-console -- Raw output for scripting
        console.log(name);
      } catch (error) {
        handleError(error);
      }
    });

  // context show - Show current context details
  context
    .command('show')
    .description(t('commands.context.show.description'))
    .action(async () => {
      try {
        const ctx = await contextService.getCurrent();
        const format = program.opts().output as OutputFormat;

        if (!ctx) {
          outputService.info(t('commands.context.show.noContext'));
          return;
        }

        // Don't show sensitive fields
        let display: Record<string, unknown>;
        if (ctx.mode === 's3') {
          display = {
            name: ctx.name,
            mode: 's3',
            endpoint: ctx.s3?.endpoint ?? '-',
            bucket: ctx.s3?.bucket ?? '-',
            region: ctx.s3?.region ?? '-',
            prefix: ctx.s3?.prefix ?? '-',
            sshKey: ctx.ssh?.privateKeyPath ?? '-',
            renetPath: ctx.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
            machines: Object.keys(ctx.machines ?? {}).length,
            defaultMachine: ctx.machine ?? '-',
          };
        } else if (ctx.mode === 'local') {
          display = {
            name: ctx.name,
            mode: 'local',
            sshKey: ctx.ssh?.privateKeyPath ?? '-',
            renetPath: ctx.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
            machines: Object.keys(ctx.machines ?? {}).length,
            defaultMachine: ctx.machine ?? '-',
          };
        } else {
          display = {
            name: ctx.name,
            mode: 'cloud',
            apiUrl: ctx.apiUrl,
            userEmail: ctx.userEmail ?? '-',
            team: ctx.team ?? '-',
            region: ctx.region ?? '-',
            bridge: ctx.bridge ?? '-',
            machine: ctx.machine ?? '-',
            authenticated: ctx.token ? 'yes' : 'no',
          };
        }

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context set - Set a default value
  context
    .command('set <key> <value>')
    .description(t('commands.context.set.description'))
    .action(async (key, value) => {
      try {
        const validKeys = ['team', 'region', 'bridge', 'machine'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
        }

        await contextService.set(key as 'team' | 'region' | 'bridge' | 'machine', value);
        outputService.success(t('commands.context.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // context clear - Clear defaults
  context
    .command('clear [key]')
    .description(t('commands.context.clear.description'))
    .action(async (key) => {
      try {
        if (key) {
          const validKeys = ['team', 'region', 'bridge', 'machine'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
          }
          await contextService.remove(key as 'team' | 'region' | 'bridge' | 'machine');
          outputService.success(t('commands.context.clear.keyCleared', { key }));
        } else {
          await contextService.clearDefaults();
          outputService.success(t('commands.context.clear.allCleared'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // ============================================================================
  // Local Mode Commands
  // ============================================================================

  // context create-local - Create a new local context
  context
    .command('create-local <name>')
    .description(t('commands.context.createLocal.description'))
    .requiredOption('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .action(async (name, options) => {
      try {
        // Expand ~ in path
        const sshKeyPath = options.sshKey.startsWith('~')
          ? path.join(os.homedir(), options.sshKey.slice(1))
          : options.sshKey;

        // Verify SSH key exists
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

  // ============================================================================
  // S3 Mode Commands
  // ============================================================================

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
        // Expand ~ in SSH key path
        const sshKeyPath = options.sshKey.startsWith('~')
          ? path.join(os.homedir(), options.sshKey.slice(1))
          : options.sshKey;

        // Verify SSH key exists
        try {
          await fs.access(sshKeyPath);
        } catch {
          throw new ValidationError(t('errors.sshKeyNotFound', { path: sshKeyPath }));
        }

        // Prompt for secret access key if not provided
        const secretAccessKey =
          options.secretAccessKey ??
          (await askPassword(t('commands.context.createS3.promptSecretAccessKey')));

        if (!secretAccessKey) {
          throw new ValidationError(t('commands.context.createS3.errorSecretAccessKeyRequired'));
        }

        // Master password is optional — omitting it means no encryption
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

        // Verify S3 access before saving
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

        // Initialize bucket with metadata
        await testClient.putJson('_meta.json', {
          schemaVersion: 1,
          createdAt: new Date().toISOString(),
          createdBy: 'rdc',
        });

        // Upload initial team vault with SSH keys
        const { S3VaultService } = await import('../services/s3-vault.js');
        const vaultService = new S3VaultService(testClient, masterPassword ?? null);

        const sshPrivateKey = await fs.readFile(sshKeyPath, 'utf-8');
        let sshPublicKey = '';
        try {
          sshPublicKey = await fs.readFile(`${sshKeyPath}.pub`, 'utf-8');
        } catch {
          // Public key is optional
        }

        await vaultService.setTeamVault({
          SSH_PRIVATE_KEY: sshPrivateKey,
          SSH_PUBLIC_KEY: sshPublicKey,
        });

        // Create the S3 config
        const s3Config: S3Config = {
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey: storedSecretAccessKey,
          prefix: options.prefix,
        };

        // Save the context
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
        const config: LocalMachineConfig = {
          ip: options.ip,
          user: options.user,
          port: Number.parseInt(options.port, 10),
          datastore: options.datastore,
        };

        await contextService.addLocalMachine(name, config);
        outputService.success(
          t('commands.context.addMachine.success', { name, user: config.user, ip: config.ip })
        );
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
