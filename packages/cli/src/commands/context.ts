import { execSync } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { Command } from 'commander';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { validateNetworkId } from '@rediacc/shared/queue-vault';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { apiClient } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askPassword, askText } from '../utils/prompt.js';
import type { MachineConfig, RepositoryConfig, NamedContext, OutputFormat, S3Config } from '../types/index.js';

/**
 * Scan SSH host keys for a machine using ssh-keyscan.
 * Returns the host keys string, or empty string if scan fails.
 */
function scanHostKeys(ip: string, port: number): string {
  try {
    const result = execSync(`ssh-keyscan -p ${port} ${ip} 2>/dev/null`, {
      encoding: 'utf-8',
      timeout: 10_000,
    });
    return result.trim();
  } catch {
    return '';
  }
}

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
            storages: Object.keys(ctx.storages ?? {}).length,
            repositories: Object.keys(ctx.repositories ?? {}).length,
            defaultMachine: ctx.machine ?? '-',
          };
        } else if (ctx.mode === 'local') {
          display = {
            name: ctx.name,
            mode: 'local',
            sshKey: ctx.ssh?.privateKeyPath ?? '-',
            renetPath: ctx.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
            machines: Object.keys(ctx.machines ?? {}).length,
            storages: Object.keys(ctx.storages ?? {}).length,
            repositories: Object.keys(ctx.repositories ?? {}).length,
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
          schemaVersion: 2,
          createdAt: new Date().toISOString(),
          createdBy: 'rdc',
        });

        // Initialize state.json and store SSH key content
        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(testClient, masterPassword ?? null);

        // Read SSH keys and store content in state.json for portability
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
        const config: MachineConfig = {
          ip: options.ip,
          user: options.user,
          port: Number.parseInt(options.port, 10),
          datastore: options.datastore,
        };

        await contextService.addLocalMachine(name, config);
        outputService.success(
          t('commands.context.addMachine.success', { name, user: config.user, ip: config.ip })
        );

        // Auto-scan host keys
        try {
          const keyscan = scanHostKeys(config.ip, config.port ?? 22);
          if (keyscan) {
            await contextService.updateLocalMachine(name, { knownHosts: keyscan });
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
          const machine = await contextService.getLocalMachine(machineName);
          const keyscan = scanHostKeys(machine.ip, machine.port ?? 22);
          if (keyscan) {
            await contextService.updateLocalMachine(machineName, { knownHosts: keyscan });
            outputService.success(t('commands.context.scanKeys.keysScanned', { name: machineName }));
          } else {
            outputService.warn(t('commands.context.scanKeys.noKeys', { name: machineName }));
          }
        } else {
          const machines = await contextService.listLocalMachines();
          let scanned = 0;
          for (const m of machines) {
            try {
              const keyscan = scanHostKeys(m.config.ip, m.config.port ?? 22);
              if (keyscan) {
                await contextService.updateLocalMachine(m.name, { knownHosts: keyscan });
                outputService.info(t('commands.context.scanKeys.keysScanned', { name: m.name }));
                scanned++;
              }
            } catch {
              outputService.warn(t('commands.context.scanKeys.noKeys', { name: m.name }));
            }
          }
          outputService.success(
            t('commands.context.scanKeys.completed', { count: scanned, total: machines.length })
          );
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

  // ============================================================================
  // Local Storage Commands
  // ============================================================================

  // context import-storage - Import storages from rclone config file
  context
    .command('import-storage <file>')
    .description(t('commands.context.importStorage.description'))
    .option('--name <name>', t('commands.context.importStorage.optionName'))
    .action(async (file, options) => {
      try {
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/queue-vault'
        );

        // Expand ~ in path
        const filePath = file.startsWith('~')
          ? path.join(os.homedir(), file.slice(1))
          : file;

        // Read and parse config file
        const content = await fs.readFile(filePath, 'utf-8');
        const configs = parseRcloneConfig(content);

        if (configs.length === 0) {
          throw new Error(t('commands.context.importStorage.noConfigs'));
        }

        // If --name is specified, only import that one section
        const toImport = options.name
          ? configs.filter((c: { name: string }) => c.name === options.name)
          : configs;

        if (toImport.length === 0) {
          throw new Error(
            t('commands.context.importStorage.notFound', { name: options.name })
          );
        }

        let imported = 0;
        for (const config of toImport) {
          const mapped = mapRcloneToStorageProvider(config);
          if (!mapped) {
            outputService.warn(
              t('commands.context.importStorage.unsupported', {
                name: config.name,
                type: config.type,
              })
            );
            continue;
          }

          await contextService.addLocalStorage(config.name, {
            provider: PROVIDER_MAPPING[config.type] ?? (mapped.provider as string),
            vaultContent: mapped,
          });
          outputService.success(
            t('commands.context.importStorage.imported', { name: config.name, type: config.type })
          );
          imported++;
        }

        outputService.info(t('commands.context.importStorage.summary', { count: imported }));
      } catch (error) {
        handleError(error);
      }
    });

  // context remove-storage - Remove a storage from local context
  context
    .command('remove-storage <name>')
    .description(t('commands.context.removeStorage.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalStorage(name);
        outputService.success(t('commands.context.removeStorage.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context storages - List storages in local context
  context
    .command('storages')
    .description(t('commands.context.storages.description'))
    .action(async () => {
      try {
        const storages = await contextService.listLocalStorages();
        const format = program.opts().output as OutputFormat;

        if (storages.length === 0) {
          outputService.info(t('commands.context.storages.noStorages'));
          return;
        }

        const displayData = storages.map((s) => ({
          name: s.name,
          provider: s.config.provider,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // ============================================================================
  // Local Repository Commands
  // ============================================================================

  // context add-repository - Add a repository GUID mapping
  context
    .command('add-repository <name>')
    .description(t('commands.context.addRepository.description'))
    .requiredOption('--guid <guid>', t('commands.context.addRepository.optionGuid'))
    .option('--tag <tag>', t('commands.context.addRepository.optionTag'), DEFAULTS.REPOSITORY.TAG)
    .option('--credential <credential>', t('commands.context.addRepository.optionCredential'))
    .option('--network-id <id>', t('commands.context.addRepository.optionNetworkId'))
    .action(async (name, options) => {
      try {
        let networkId: number | undefined;

        if (options.networkId !== undefined) {
          networkId = Number.parseInt(options.networkId, 10);
          const validation = validateNetworkId(networkId);
          if (!validation.valid) {
            throw new ValidationError(validation.error!);
          }
        } else {
          networkId = await contextService.allocateNetworkId();
        }

        const config: RepositoryConfig = {
          repositoryGuid: options.guid,
          tag: options.tag,
          credential: options.credential,
          networkId,
        };

        await contextService.addLocalRepository(name, config);
        outputService.success(
          t('commands.context.addRepository.success', {
            name,
            guid: config.repositoryGuid,
            tag: config.tag ?? DEFAULTS.REPOSITORY.TAG,
          })
        );
        outputService.info(t('commands.context.addRepository.networkIdAssigned', { networkId }));
      } catch (error) {
        handleError(error);
      }
    });

  // context remove-repository - Remove a repository mapping
  context
    .command('remove-repository <name>')
    .description(t('commands.context.removeRepository.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalRepository(name);
        outputService.success(t('commands.context.removeRepository.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context repositories - List repository mappings
  context
    .command('repositories')
    .description(t('commands.context.repositories.description'))
    .action(async () => {
      try {
        const repos = await contextService.listLocalRepositories();
        const format = program.opts().output as OutputFormat;

        if (repos.length === 0) {
          outputService.info(t('commands.context.repositories.noRepositories'));
          return;
        }

        const displayData = repos.map((r) => ({
          name: r.name,
          guid: r.config.repositoryGuid,
          tag: r.config.tag ?? DEFAULTS.REPOSITORY.TAG,
          credential: r.config.credential ? 'set' : '-',
          networkId: r.config.networkId ?? '-',
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // ============================================================================
  // Migration Commands
  // ============================================================================

  // context to-s3 - Migrate a local context to S3 mode
  context
    .command('to-s3')
    .description('Migrate the current local context to S3 mode')
    .requiredOption('--endpoint <url>', 'S3 endpoint URL')
    .requiredOption('--bucket <name>', 'S3 bucket name')
    .requiredOption('--access-key-id <key>', 'S3 access key ID')
    .option('--secret-access-key <key>', 'S3 secret access key (prompted if omitted)')
    .option('--region <region>', 'S3 region', 'auto')
    .option('--prefix <prefix>', 'Key prefix in bucket')
    .option('--master-password <password>', 'Enable encryption with this master password')
    .action(async (options) => {
      try {
        const ctxName = contextService.getCurrentName();
        const context = await contextService.getCurrent();
        if (!context) throw new ValidationError('No active context');
        if (context.mode !== 'local') {
          throw new ValidationError(`Context "${ctxName}" is not in local mode (current: ${context.mode ?? 'cloud'})`);
        }

        // Prompt for secret access key if not provided
        const secretAccessKey =
          options.secretAccessKey ??
          (await askPassword('Enter S3 secret access key:'));
        if (!secretAccessKey) {
          throw new ValidationError('Secret access key is required');
        }

        const masterPassword: string | undefined = options.masterPassword;

        // Verify S3 access
        outputService.info('Verifying S3 access...');
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
        outputService.success('S3 access verified');

        // Initialize bucket metadata
        await s3Client.putJson('_meta.json', {
          schemaVersion: 2,
          createdAt: new Date().toISOString(),
          createdBy: 'rdc',
          migratedFrom: 'local',
        });

        // Initialize state.json and populate with current local data
        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(s3Client, masterPassword ?? null);

        // Migrate machines
        if (context.machines && Object.keys(context.machines).length > 0) {
          await stateService.setMachines(context.machines);
        }

        // Migrate storages
        if (context.storages && Object.keys(context.storages).length > 0) {
          await stateService.setStorages(context.storages);
        }

        // Migrate repositories
        if (context.repositories && Object.keys(context.repositories).length > 0) {
          await stateService.setRepositories(context.repositories);
        }

        // Migrate SSH key content
        if (context.ssh?.privateKeyPath) {
          const sshKeyPath = context.ssh.privateKeyPath.startsWith('~')
            ? path.join(os.homedir(), context.ssh.privateKeyPath.slice(1))
            : context.ssh.privateKeyPath;
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
        }

        // Encrypt S3 secret and master password if needed
        let storedSecretAccessKey: string;
        let encryptedMasterPassword: string | undefined;
        if (masterPassword) {
          storedSecretAccessKey = await nodeCryptoProvider.encrypt(secretAccessKey, masterPassword);
          encryptedMasterPassword = await nodeCryptoProvider.encrypt(masterPassword, masterPassword);
        } else {
          storedSecretAccessKey = secretAccessKey;
        }

        // Update config.json: switch to S3 mode, remove local data
        const s3Config: S3Config = {
          endpoint: options.endpoint,
          bucket: options.bucket,
          region: options.region,
          accessKeyId: options.accessKeyId,
          secretAccessKey: storedSecretAccessKey,
          prefix: options.prefix,
        };

        await contextService.update(ctxName, {
          mode: 's3',
          apiUrl: 's3://',
          s3: s3Config,
          masterPassword: encryptedMasterPassword,
          machines: undefined,
          storages: undefined,
          repositories: undefined,
        });

        const machineCount = Object.keys(context.machines ?? {}).length;
        const storageCount = Object.keys(context.storages ?? {}).length;
        const repoCount = Object.keys(context.repositories ?? {}).length;
        outputService.success(
          `Migrated to S3 mode: ${machineCount} machines, ${storageCount} storages, ${repoCount} repositories`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // context to-local - Migrate an S3 context to local mode
  context
    .command('to-local')
    .description('Migrate the current S3 context to local mode')
    .option('--ssh-key-path <path>', 'Where to write SSH private key (default: existing path)')
    .action(async (options) => {
      try {
        const ctxName = contextService.getCurrentName();
        const context = await contextService.getCurrent();
        if (!context) throw new ValidationError('No active context');
        if (context.mode !== 's3') {
          throw new ValidationError(`Context "${ctxName}" is not in S3 mode (current: ${context.mode ?? 'cloud'})`);
        }
        if (!context.s3) {
          throw new ValidationError(`Context "${ctxName}" has no S3 configuration`);
        }

        // Decrypt S3 secret
        let decryptedSecret: string;
        let masterPassword: string | null = null;
        if (context.masterPassword) {
          const { authService } = await import('../services/auth.js');
          masterPassword = await authService.requireMasterPassword();
          decryptedSecret = await nodeCryptoProvider.decrypt(
            context.s3.secretAccessKey,
            masterPassword
          );
        } else {
          decryptedSecret = context.s3.secretAccessKey;
        }

        // Load state from S3
        outputService.info('Loading state from S3...');
        const { S3ClientService } = await import('../services/s3-client.js');
        const s3Client = new S3ClientService({
          ...context.s3,
          secretAccessKey: decryptedSecret,
        });
        const { S3StateService } = await import('../services/s3-state.js');
        const stateService = await S3StateService.load(s3Client, masterPassword);

        const machines = stateService.getMachines();
        const storages = stateService.getStorages();
        const repositories = stateService.getRepositories();
        const sshContent = stateService.getSSH();

        // Write SSH key to filesystem if available
        const sshKeyPath = options.sshKeyPath ?? context.ssh?.privateKeyPath;
        if (sshContent?.privateKey && sshKeyPath) {
          const expandedPath = sshKeyPath.startsWith('~')
            ? path.join(os.homedir(), sshKeyPath.slice(1))
            : sshKeyPath;
          await fs.writeFile(expandedPath, sshContent.privateKey + '\n', { mode: 0o600 });
          if (sshContent.publicKey) {
            await fs.writeFile(`${expandedPath}.pub`, sshContent.publicKey + '\n', { mode: 0o644 });
          }
          outputService.info(`SSH key written to ${expandedPath}`);
        }

        // Update config.json: switch to local mode, add data, remove S3 config
        await contextService.update(ctxName, {
          mode: 'local',
          apiUrl: 'local://',
          machines: Object.keys(machines).length > 0 ? machines : {},
          storages: Object.keys(storages).length > 0 ? storages : {},
          repositories: Object.keys(repositories).length > 0 ? repositories : {},
          ssh: sshKeyPath
            ? { privateKeyPath: sshKeyPath, publicKeyPath: `${sshKeyPath}.pub` }
            : context.ssh,
          s3: undefined,
          masterPassword: undefined,
        });

        const machineCount = Object.keys(machines).length;
        const storageCount = Object.keys(storages).length;
        const repoCount = Object.keys(repositories).length;
        outputService.success(
          `Migrated to local mode: ${machineCount} machines, ${storageCount} storages, ${repoCount} repositories`
        );
        outputService.info('State.json remains in S3 bucket (non-destructive)');
      } catch (error) {
        handleError(error);
      }
    });
}
