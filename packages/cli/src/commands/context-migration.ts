import * as fs from 'node:fs/promises';
import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { S3Config } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';

export function registerMigrationCommands(context: Command): void {
  // context to-s3 - Migrate the current local context to S3 mode
  context
    .command('to-s3')
    .description(t('commands.context.toS3.description'))
    .requiredOption('--endpoint <url>', t('commands.context.toS3.optionEndpoint'))
    .requiredOption('--bucket <name>', t('commands.context.toS3.optionBucket'))
    .requiredOption('--access-key-id <key>', t('commands.context.toS3.optionAccessKeyId'))
    .option('--secret-access-key <key>', t('commands.context.toS3.optionSecretAccessKey'))
    .option('--region <region>', t('commands.context.toS3.optionRegion'), 'auto')
    .option('--prefix <prefix>', t('commands.context.toS3.optionPrefix'))
    .option('--master-password <password>', t('commands.context.toS3.optionMasterPassword'))
    .action(async (options) => {
      try {
        const ctx = await contextService.getCurrent();
        if (!ctx) throw new Error(t('errors.noContext'));
        if (ctx.mode !== 'local') {
          throw new ValidationError(
            t('commands.context.toS3.errorNotLocal', {
              name: ctx.name,
              mode: ctx.mode ?? DEFAULTS.CONTEXT.MODE,
            })
          );
        }

        const secretAccessKey =
          options.secretAccessKey ??
          (await askPassword(t('commands.context.toS3.promptSecretAccessKey')));
        if (!secretAccessKey) {
          throw new ValidationError(t('commands.context.toS3.errorSecretRequired'));
        }

        const masterPassword: string | undefined = options.masterPassword;

        // Verify S3 access
        outputService.info(t('commands.context.toS3.verifying'));
        const { S3ClientService } = await import('../services/s3-client.js');
        const s3Client = new S3ClientService({
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey,
          prefix: options.prefix,
        });
        await s3Client.verifyAccess();
        outputService.success(t('commands.context.toS3.verified'));

        // Read local data via ResourceState (handles encrypted contexts)
        const { LocalResourceState } = await import('../services/resource-state.js');
        const localState = await LocalResourceState.load(ctx, masterPassword ?? null);
        const machines = localState.getMachines();
        const storages = localState.getStorages();
        const repositories = localState.getRepositories();

        // Initialize state.json with local data
        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(s3Client, masterPassword ?? null);

        await stateService.setMachines(machines);
        await stateService.setStorages(storages);
        await stateService.setRepositories(repositories);

        // Upload SSH keys
        if (ctx.ssh?.privateKeyPath) {
          const sshPrivateKey = await fs.readFile(ctx.ssh.privateKeyPath, 'utf-8');
          let sshPublicKey = '';
          try {
            const pubPath = ctx.ssh.publicKeyPath ?? `${ctx.ssh.privateKeyPath}.pub`;
            sshPublicKey = await fs.readFile(pubPath, 'utf-8');
          } catch {
            // Public key is optional
          }
          await stateService.setSSH({
            privateKey: sshPrivateKey.trim(),
            publicKey: sshPublicKey.trim() || undefined,
          });
        }

        // Encrypt S3 secret if master password provided
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
        }

        const s3Config: S3Config = {
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey: storedSecretAccessKey,
          prefix: options.prefix,
        };

        // Update context: switch to S3 mode, remove local data
        await contextService.update(ctx.name, {
          mode: 's3',
          s3: s3Config,
          masterPassword: encryptedMasterPassword,
          machines: undefined,
          storages: undefined,
          repositories: undefined,
        });

        outputService.success(
          t('commands.context.toS3.success', {
            machines: Object.keys(machines).length,
            storages: Object.keys(storages).length,
            repos: Object.keys(repositories).length,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // context to-local - Migrate the current S3 context to local mode
  context
    .command('to-local')
    .description(t('commands.context.toLocal.description'))
    .option('--ssh-key-path <path>', t('commands.context.toLocal.optionSshKeyPath'))
    .action(async (options) => {
      try {
        const ctx = await contextService.getCurrent();
        if (!ctx) throw new Error(t('errors.noContext'));
        if (ctx.mode !== 's3') {
          throw new ValidationError(
            t('commands.context.toLocal.errorNotS3', {
              name: ctx.name,
              mode: ctx.mode ?? DEFAULTS.CONTEXT.MODE,
            })
          );
        }
        if (!ctx.s3) {
          throw new ValidationError(
            t('commands.context.toLocal.errorNoS3Config', { name: ctx.name })
          );
        }

        // Load state from S3
        outputService.info(t('commands.context.toLocal.loading'));

        let decryptedSecret: string;
        let masterPassword: string | null = null;

        if (ctx.masterPassword) {
          const { authService } = await import('../services/auth.js');
          masterPassword = await authService.requireMasterPassword();
          decryptedSecret = await nodeCryptoProvider.decrypt(
            ctx.s3.secretAccessKey,
            masterPassword
          );
        } else {
          decryptedSecret = ctx.s3.secretAccessKey;
        }

        const { S3ClientService } = await import('../services/s3-client.js');
        const s3Client = new S3ClientService({
          ...ctx.s3,
          secretAccessKey: decryptedSecret,
        });

        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(s3Client, masterPassword);

        const machines = stateService.getMachines();
        const storages = stateService.getStorages();
        const repositories = stateService.getRepositories();

        // Write SSH key to filesystem
        const sshContent = stateService.getSSH();
        const sshKeyPath =
          options.sshKeyPath ?? ctx.ssh?.privateKeyPath ?? DEFAULTS.CONTEXT.SSH_KEY_PATH;

        if (sshContent?.privateKey) {
          await fs.writeFile(sshKeyPath, `${sshContent.privateKey}\n`, {
            mode: 0o600,
          });
          if (sshContent.publicKey) {
            await fs.writeFile(`${sshKeyPath}.pub`, `${sshContent.publicKey}\n`, { mode: 0o644 });
          }
          outputService.info(t('commands.context.toLocal.sshWritten', { path: sshKeyPath }));
        }

        // Update context: switch to local mode
        await contextService.update(ctx.name, {
          mode: 'local',
          apiUrl: 'local://',
          ssh: {
            privateKeyPath: sshKeyPath,
            publicKeyPath: `${sshKeyPath}.pub`,
          },
          machines,
          storages,
          repositories,
          s3: undefined,
          masterPassword: undefined,
        });

        outputService.success(
          t('commands.context.toLocal.success', {
            machines: Object.keys(machines).length,
            storages: Object.keys(storages).length,
            repos: Object.keys(repositories).length,
          })
        );
        outputService.info(t('commands.context.toLocal.nonDestructive'));
      } catch (error) {
        handleError(error);
      }
    });
}
