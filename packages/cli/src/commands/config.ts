import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import { registerLocalDataCommands } from './config-data.js';
import { registerInfraCommands } from './config-infra.js';
import { registerSetupCommands } from './config-setup.js';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { hasCloudCredentials } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';

/** Build display data for a self-hosted config (local or S3 mode). */
async function buildSelfHostedDisplay(
  config: RdcConfig,
  name: string
): Promise<Record<string, unknown>> {
  let machineCount = 0;
  let storageCount = 0;
  let repoCount = 0;
  try {
    const state = await configService.getResourceState();
    machineCount = Object.keys(state.getMachines()).length;
    storageCount = Object.keys(state.getStorages()).length;
    repoCount = Object.keys(state.getRepositories()).length;
  } catch {
    machineCount = Object.keys(config.machines ?? {}).length;
    storageCount = Object.keys(config.storages ?? {}).length;
    repoCount = Object.keys(config.repositories ?? {}).length;
  }

  return {
    name,
    id: config.id,
    version: config.version,
    adapter: 'local',
    ...(config.s3
      ? {
          s3State: 'yes',
          endpoint: config.s3.endpoint,
          bucket: config.s3.bucket,
          s3Region: config.s3.region,
          prefix: config.s3.prefix ?? '-',
        }
      : {}),
    encrypted: config.encrypted ? 'yes' : 'no',
    sshKey: config.ssh?.privateKeyPath ?? '-',
    renetPath: config.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
    machines: machineCount,
    storages: storageCount,
    repositories: repoCount,
    defaultMachine: config.machine ?? '-',
  };
}

/** Encrypt master password if provided. Returns config updates. */
async function handleMasterPasswordSetup(options: {
  masterPassword?: string;
}): Promise<Partial<RdcConfig>> {
  if (!options.masterPassword) return {};
  const { nodeCryptoProvider } = await import('../adapters/crypto.js');
  const encrypted = await nodeCryptoProvider.encrypt(
    options.masterPassword,
    options.masterPassword
  );
  return { masterPassword: encrypted, encrypted: true };
}

/** Normalize API URL if provided. Returns config updates. */
async function handleApiUrlSetup(options: { apiUrl?: string }): Promise<Partial<RdcConfig>> {
  if (!options.apiUrl) return {};
  const { apiClient } = await import('../services/api.js');
  return { apiUrl: apiClient.normalizeApiUrl(options.apiUrl) };
}

/** Upload SSH key to S3 state if --ssh-key was provided. */
async function uploadSshKeyToS3(
  testClient: InstanceType<typeof import('../services/s3-client.js').S3ClientService>,
  sshKeyOption: string,
  masterPassword: string | null
): Promise<void> {
  const fs = await import('node:fs/promises');
  const sshKeyPath = sshKeyOption.startsWith('~')
    ? (await import('node:path')).join((await import('node:os')).homedir(), sshKeyOption.slice(1))
    : sshKeyOption;
  const { S3StateService } = await import('../services/s3-state.js');
  const stateService = await S3StateService.load(testClient, masterPassword);
  const sshPrivateKey = await fs.readFile(sshKeyPath, 'utf-8');
  let sshPublicKey = '';
  try {
    sshPublicKey = await fs.readFile(`${sshKeyPath}.pub`, 'utf-8');
  } catch {
    /* optional */
  }
  await stateService.setSSH({
    privateKey: sshPrivateKey.trim(),
    publicKey: sshPublicKey.trim() || undefined,
  });
}

/** Resolve the S3 secret access key, prompting if needed. */
async function resolveS3SecretKey(existing?: string): Promise<string> {
  if (existing) return existing;
  const { askPassword } = await import('../utils/prompt.js');
  const key = await askPassword(t('commands.config.init.promptS3SecretAccessKey'));
  if (!key) throw new ValidationError(t('commands.config.init.s3SecretRequired'));
  return key;
}

/** Validate S3 options, verify access, upload SSH key to S3. Returns config updates. */
async function handleS3Setup(options: {
  s3Endpoint?: string;
  s3Bucket?: string;
  s3AccessKeyId?: string;
  s3SecretAccessKey?: string;
  s3Region?: string;
  s3Prefix?: string;
  masterPassword?: string;
  sshKey?: string;
}): Promise<Partial<RdcConfig>> {
  if (!options.s3Endpoint && !options.s3Bucket && !options.s3AccessKeyId) return {};

  if (!options.s3Endpoint || !options.s3Bucket || !options.s3AccessKeyId) {
    throw new ValidationError(t('commands.config.init.s3Required'));
  }

  const endpoint = options.s3Endpoint;
  const bucket = options.s3Bucket;
  const accessKeyId = options.s3AccessKeyId;
  const region = options.s3Region ?? DEFAULTS.STORE.S3_REGION;
  const prefix = options.s3Prefix;

  const secretAccessKey = await resolveS3SecretKey(options.s3SecretAccessKey);

  let storedSecretAccessKey: string;
  if (options.masterPassword) {
    const { nodeCryptoProvider } = await import('../adapters/crypto.js');
    storedSecretAccessKey = await nodeCryptoProvider.encrypt(
      secretAccessKey,
      options.masterPassword
    );
  } else {
    storedSecretAccessKey = secretAccessKey;
  }

  outputService.info(t('commands.config.init.verifyingS3'));
  const { S3ClientService } = await import('../services/s3-client.js');
  const testClient = new S3ClientService({
    endpoint,
    bucket,
    region,
    accessKeyId,
    secretAccessKey,
    prefix,
  });
  await testClient.verifyAccess();
  outputService.success(t('commands.config.init.s3Verified'));

  await testClient.putJson('_meta.json', {
    schemaVersion: 2,
    createdAt: new Date().toISOString(),
    createdBy: 'rdc',
  });

  if (options.sshKey) {
    await uploadSshKeyToS3(testClient, options.sshKey, options.masterPassword ?? null);
  }

  return {
    s3: { endpoint, bucket, region, accessKeyId, secretAccessKey: storedSecretAccessKey, prefix },
  };
}

export function registerConfigCommands(program: Command): void {
  const config = program.command('config').description(t('commands.config.description'));

  // config init [name] - Initialize a new config file
  config
    .command('init [name]')
    .description(t('commands.config.init.description'))
    .option('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .option('--master-password <password>', t('commands.config.init.optionMasterPassword'))
    .option('--s3-endpoint <url>', t('commands.config.init.optionS3Endpoint'))
    .option('--s3-bucket <name>', t('commands.config.init.optionS3Bucket'))
    .option('--s3-access-key-id <key>', t('commands.config.init.optionS3AccessKeyId'))
    .option('--s3-secret-access-key <key>', t('commands.config.init.optionS3SecretAccessKey'))
    .option('--s3-region <region>', t('commands.config.init.optionS3Region'), 'auto')
    .option('--s3-prefix <prefix>', t('commands.config.init.optionS3Prefix'))
    .option('-u, --api-url <url>', t('options.apiUrl'))
    .action(async (name, options) => {
      try {
        const configName = name ?? DEFAULTS.CONTEXT.CONFIG_NAME;

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const exists = await configFileStorage.exists(configName);

        // Named configs must not already exist
        if (exists && name) {
          throw new ValidationError(t('commands.config.init.alreadyExists', { name: configName }));
        }

        // Default config already exists — if no flags, just confirm
        if (exists && !name) {
          const hasFlags =
            options.sshKey ??
            options.renetPath ??
            options.masterPassword ??
            options.apiUrl ??
            options.s3Endpoint ??
            options.s3Bucket ??
            options.s3AccessKeyId;
          if (!hasFlags) {
            outputService.success(t('commands.config.init.success', { name: configName }));
            return;
          }
        }

        const newConfig = exists
          ? await configFileStorage.load(configName)
          : await configService.init(configName);

        const updates: Partial<RdcConfig> = {};

        if (options.sshKey) {
          updates.ssh = { privateKeyPath: options.sshKey };
        }

        if (options.renetPath) {
          updates.renetPath = options.renetPath;
        }

        Object.assign(updates, await handleMasterPasswordSetup(options));
        Object.assign(updates, await handleApiUrlSetup(options));
        Object.assign(updates, await handleS3Setup(options));

        await configFileStorage.save({ ...newConfig, ...updates }, configName);
        outputService.success(t('commands.config.init.success', { name: configName }));
      } catch (error) {
        handleError(error);
      }
    });

  // config list
  config
    .command('list')
    .alias('ls')
    .description(t('commands.config.list.description'))
    .action(async () => {
      try {
        const configs = await configService.list();
        const format = program.opts().output as OutputFormat;
        const currentName = configService.getCurrentName();

        if (configs.length === 0) {
          outputService.info(t('commands.config.list.noConfigs'));
          return;
        }

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const displayData = [];
        for (const name of configs) {
          const cfg = await configFileStorage.load(name);
          const isCloud = hasCloudCredentials(cfg);
          displayData.push({
            name,
            active: name === currentName ? '*' : '',
            adapter: isCloud ? 'cloud' : 'local',
            machines: isCloud ? '-' : Object.keys(cfg.machines ?? {}).length.toString(),
          });
        }

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config show
  config
    .command('show')
    .description(t('commands.config.show.description'))
    .action(async () => {
      try {
        const cfg = await configService.getCurrent();
        const format = program.opts().output as OutputFormat;
        const name = configService.getCurrentName();

        if (!cfg) {
          outputService.info(t('commands.config.show.noConfig', { name }));
          return;
        }

        const isCloud = hasCloudCredentials(cfg);
        const display: Record<string, unknown> = isCloud
          ? {
              name,
              id: cfg.id,
              version: cfg.version,
              adapter: 'cloud',
              apiUrl: cfg.apiUrl,
              userEmail: cfg.userEmail ?? '-',
              team: cfg.team ?? '-',
              region: cfg.region ?? '-',
              bridge: cfg.bridge ?? '-',
              machine: cfg.machine ?? '-',
              authenticated: cfg.token ? 'yes' : 'no',
            }
          : await buildSelfHostedDisplay(cfg, name);

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config delete
  config
    .command('delete <name>')
    .alias('rm')
    .description(t('commands.config.delete.description'))
    .action(async (name) => {
      try {
        await configService.delete(name);
        outputService.success(t('commands.config.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config set
  config
    .command('set <key> <value>')
    .description(t('commands.config.set.description'))
    .action(async (key, value) => {
      try {
        const validKeys = ['team', 'region', 'bridge', 'machine'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
        }
        await configService.set(key as 'team' | 'region' | 'bridge' | 'machine', value);
        outputService.success(t('commands.config.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // config clear
  config
    .command('clear [key]')
    .description(t('commands.config.clear.description'))
    .action(async (key) => {
      try {
        if (key) {
          const validKeys = ['team', 'region', 'bridge', 'machine'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
          }
          await configService.remove(key as 'team' | 'region' | 'bridge' | 'machine');
          outputService.success(t('commands.config.clear.keyCleared', { key }));
        } else {
          await configService.clearDefaults();
          outputService.success(t('commands.config.clear.allCleared'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config recover
  config
    .command('recover [name]')
    .description(t('commands.config.recover.description'))
    .option('-y, --yes', 'Skip confirmation prompt')
    .action(async (name, options) => {
      try {
        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const configName = name ?? configService.getCurrentName();

        const backupInfo = await configFileStorage.getBackupInfo(configName);
        if (!backupInfo) {
          outputService.info(t('commands.config.recover.noBackup', { name: configName }));
          return;
        }

        const format = program.opts().output as OutputFormat;
        outputService.print(
          {
            config: configName,
            backupVersion: backupInfo.version,
            backupId: backupInfo.id,
            backupDate: backupInfo.modifiedAt.toISOString(),
            backupPath: backupInfo.path,
          },
          format
        );

        if (!options.yes) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirmed = await askConfirm(
            t('commands.config.recover.confirm', { name: configName })
          );
          if (!confirmed) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        const recovered = await configFileStorage.recover(configName);
        if (!recovered) {
          outputService.error(t('commands.config.recover.failed', { name: configName }));
          return;
        }

        outputService.success(
          t('commands.config.recover.success', {
            name: configName,
            version: String(recovered.version),
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // Register sub-command groups
  registerSetupCommands(config, program);
  registerLocalDataCommands(config, program);
  registerInfraCommands(config, program);
}
