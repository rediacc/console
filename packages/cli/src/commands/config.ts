import { DEFAULTS } from '@rediacc/shared/config';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';
import { hasCloudCredentials } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { registerBackupStrategyCommands } from './config-backup-strategy.js';
import { registerRepositoryCommands, registerStorageCommands } from './config-data.js';
import { registerInfraCommands } from './config-infra.js';
import { registerMachineCommands, registerProviderCommands } from './config-setup.js';
import { registerRemoteCommands } from './config-remote.js';
import { registerSSHCommands } from './config-ssh.js';

/** Build display data for a self-hosted config. */
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

  const display: Record<string, unknown> = {
    name,
    id: config.id,
    version: config.version,
    adapter: 'local',
    encrypted: config.encrypted ? 'yes' : 'no',
    sshKey: config.ssh?.privateKeyPath ?? '-',
    renetPath: config.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
    machines: machineCount,
    storages: storageCount,
    repositories: repoCount,
  };
  if (config.remote) {
    display.remoteUrl = config.remote.apiUrl;
    display.dataRegion = config.remote.dataRegion ?? '-';
  }
  return display;
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

/** Check whether the user passed any config-init flags beyond --name. */
function hasInitFlags(options: {
  sshKey?: string;
  renetPath?: string;
  masterPassword?: string;
  apiUrl?: string;
  server?: string;
}): boolean {
  return !!(
    options.sshKey ??
    options.renetPath ??
    options.masterPassword ??
    options.apiUrl ??
    options.server
  );
}

export function registerConfigCommands(program: Command): void {
  const config = program
    .command('config')
    .summary(t('commands.config.descriptionShort'))
    .description(t('commands.config.description'));

  config.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc config init --name production --ssh-key ~/.ssh/id_ed25519   ${t('help.config.init')}
  $ rdc config machine add --name server-1 --ip 10.0.0.1 --user deploy  ${t('help.config.addMachine')}
  $ rdc config machine setup --name server-1                        ${t('help.config.setupMachine')}
`
  );

  // config init - Initialize a new config file
  config
    .command('init')
    .description(t('commands.config.init.description'))
    .option('--name <name>', t('options.name'))
    .option('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .option('--master-password <password>', t('commands.config.init.optionMasterPassword'))
    .option('-u, --api-url <url>', t('options.apiUrl'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        const name = options.name;
        const configName = name ?? DEFAULTS.CONTEXT.CONFIG_NAME;

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const exists = await configFileStorage.exists(configName);

        // Named configs must not already exist
        if (exists && name) {
          throw new ValidationError(t('commands.config.init.alreadyExists', { name: configName }));
        }

        // Default config already exists — if no flags, just confirm
        if (exists && !name && !hasInitFlags(options)) {
          outputService.success(t('commands.config.init.success', { name: configName }));
          return;
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

        if (options.server) {
          updates.accountServer = options.server.replace(/\/+$/, '');
        }

        Object.assign(updates, await handleMasterPasswordSetup(options));
        Object.assign(updates, await handleApiUrlSetup(options));
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
    .command('delete')
    .alias('rm')
    .description(t('commands.config.delete.description'))
    .requiredOption('--name <name>', t('options.name'))
    .action(async (options) => {
      try {
        const name = options.name;
        await configService.delete(name);
        outputService.success(t('commands.config.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config set
  config
    .command('set')
    .description(t('commands.config.set.description'))
    .requiredOption('--key <key>', t('options.configKey'))
    .requiredOption('--value <value>', t('options.configValue'))
    .action(async (options) => {
      try {
        const { key, value } = options;
        const validKeys = ['team', 'region', 'bridge'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
        }
        await configService.set(key as 'team' | 'region' | 'bridge', value);
        outputService.success(t('commands.config.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // config clear
  config
    .command('clear')
    .description(t('commands.config.clear.description'))
    .option('--key <key>', t('options.configKey'))
    .action(async (options) => {
      try {
        const key = options.key;
        if (key) {
          const validKeys = ['team', 'region', 'bridge'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
          }
          await configService.remove(key as 'team' | 'region' | 'bridge');
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
    .command('recover')
    .description(t('commands.config.recover.description'))
    .option('--name <name>', t('options.name'))
    .option('-y, --yes', t('options.yes'))
    .action(async (options) => {
      try {
        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const configName = options.name ?? configService.getCurrentName();

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

  registerBackupStrategyCommands(config);

  // Register nested sub-command groups
  registerMachineCommands(config, program);
  registerProviderCommands(config, program);
  registerRepositoryCommands(config, program);
  registerStorageCommands(config, program);
  registerInfraCommands(config, program);
  registerSSHCommands(config, program);
  registerRemoteCommands(config);
}
