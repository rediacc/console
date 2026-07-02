import { DEFAULTS } from '@rediacc/shared/config';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { registerBackupStrategyCommands } from './config-backup-strategy.js';
import { registerPruneCommand as registerConfigPruneCommand } from './config-prune-cmd.js';
import { registerAuditCommands } from './config/audit.js';
import { registerEditCommands } from './config/edit.js';
import { registerFieldCommands } from './config/field.js';
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
    machineCount = Object.keys(config.resources?.machines ?? {}).length;
    storageCount = Object.keys(config.resources?.storages ?? {}).length;
    repoCount = Object.keys(config.resources?.repositories ?? {}).length;
  }

  const display: Record<string, unknown> = {
    name,
    id: config.id,
    version: config.version,
    adapter: 'local',
    encrypted: config.encryption?.mode === 'master-password' ? 'yes' : 'no',
    sshKey: config.credentials?.ssh?.privateKey ? '(inline)' : '-',
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
  return {
    credentials: { masterPasswordVerifier: encrypted },
    encryption: { mode: 'master-password' },
  };
}

/**
 * Read an SSH key file + optional .pub sibling for `config init --ssh-key <path>`.
 * Returns the `credentials.ssh` sub-shape that gets merged into the config.
 *
 * Exported so the regression test can exercise the read without driving
 * Commander / configFileStorage.
 */
export async function readSshKeyForInit(
  keyPath: string
): Promise<{ privateKey: string; publicKey?: string }> {
  const { readSSHKey, readOptionalSSHKey } = await import('../services/renet-execution.js');
  const privateKey = (await readSSHKey(keyPath)).trim();
  const publicKey = (await readOptionalSSHKey(`${keyPath}.pub`)).trim() || undefined;
  return { privateKey, publicKey };
}

/**
 * Merge the pieces an `init` action collects into a single RdcConfig ready
 * for `configFileStorage.save`. Pure — no I/O — so unit tests can drive it
 * and assert the resulting shape, which is where the v1→v2 regression hid.
 */
export function mergeInitUpdates(
  newConfig: RdcConfig,
  parts: {
    renetPath?: string;
    accountUpdate?: Partial<NonNullable<RdcConfig['account']>>;
    sshContent?: { privateKey: string; publicKey?: string; knownHosts?: string };
    mpUpdate: Partial<RdcConfig>;
  }
): RdcConfig {
  return {
    ...newConfig,
    ...(parts.renetPath ? { renetPath: parts.renetPath } : {}),
    ...parts.mpUpdate,
    account: {
      ...(newConfig.account ?? {}),
      ...(parts.accountUpdate ?? {}),
    },
    credentials:
      parts.mpUpdate.credentials || parts.sshContent
        ? {
            ...(newConfig.credentials ?? {}),
            ...(parts.mpUpdate.credentials ?? {}),
            ...(parts.sshContent ? { ssh: parts.sshContent } : {}),
          }
        : newConfig.credentials,
    encryption: parts.mpUpdate.encryption ?? newConfig.encryption,
  };
}

/** Check whether the user passed any config-init flags beyond --name. */
function hasInitFlags(options: {
  sshKey?: string;
  renetPath?: string;
  masterPassword?: string;
  server?: string;
}): boolean {
  return !!(options.sshKey ?? options.renetPath ?? options.masterPassword ?? options.server);
}

/** Gate --reveal: refuse agents and non-TTY; emit audit log. */
async function applyRevealGate(cfg: RdcConfig): Promise<void> {
  const { isAgentEnvironment } = await import('../utils/agent-guard.js');
  const { auditLog } = await import('../services/audit-log.js');
  const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
  const auditDir = `${xdg}/rediacc`;

  if (isAgentEnvironment()) {
    try {
      auditLog(auditDir, {
        command: 'config show --reveal',
        paths: [],
        outcome: 'refused',
        configId: cfg.id,
        configVersion: cfg.version,
        reason: 'agent environment',
      });
    } catch {
      /* best-effort */
    }
    throw new ValidationError(t('errors.agent.showReveal'));
  }

  const { isatty } = await import('node:tty');
  if (!isatty(process.stdout.fd)) {
    throw new ValidationError(t('errors.agent.showRevealRequiresTty'));
  }

  try {
    auditLog(auditDir, {
      command: 'config show --reveal',
      paths: [],
      outcome: 'reveal_granted',
      configId: cfg.id,
      configVersion: cfg.version,
    });
  } catch {
    /* best-effort */
  }
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

        const sshContent = options.sshKey ? await readSshKeyForInit(options.sshKey) : undefined;

        const accountUpdate = options.server
          ? { accountServer: options.server.replace(/\/+$/, '') }
          : undefined;

        const mpUpdate = await handleMasterPasswordSetup(options);
        const merged: RdcConfig = mergeInitUpdates(newConfig, {
          renetPath: options.renetPath,
          accountUpdate,
          sshContent,
          mpUpdate,
        });
        await configFileStorage.save(merged, configName);
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
          // One unparseable file must not abort the whole listing — show it
          // as invalid and keep going (same tolerant-read stance as
          // configFileStorage.getBackupInfo).
          try {
            const cfg = await configFileStorage.load(name);
            displayData.push({
              name,
              active: name === currentName ? '*' : '',
              machines: Object.keys(cfg.resources?.machines ?? {}).length.toString(),
              status: 'ok',
            });
          } catch {
            displayData.push({
              name,
              active: name === currentName ? '*' : '',
              machines: '-',
              status: 'invalid',
            });
          }
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
    .option('--reveal', t('commands.config.show.optionReveal'))
    .action(async (options: { reveal?: boolean }) => {
      try {
        const cfg = await configService.getCurrent();
        const format = program.opts().output as OutputFormat;
        const name = configService.getCurrentName();

        if (!cfg) {
          outputService.info(t('commands.config.show.noConfig', { name }));
          return;
        }

        // Default: redact sensitive values. --reveal opts in (humans only).
        // The redactor is schema-driven (packages/cli/src/schema/walker.ts).
        if (options.reveal) {
          await applyRevealGate(cfg);
        } else {
          const { redactClone } = await import('../schema/walker.js');
          const redacted = redactClone(cfg);
          Object.assign(cfg as Record<string, unknown>, redacted);
        }

        const display: Record<string, unknown> = await buildSelfHostedDisplay(cfg, name);

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
  registerConfigPruneCommand(config);

  // Register nested sub-command groups
  registerMachineCommands(config, program);
  registerProviderCommands(config, program);
  registerRepositoryCommands(config, program);
  registerStorageCommands(config, program);
  registerInfraCommands(config, program);
  registerSSHCommands(config, program);
  registerRemoteCommands(config);
  registerFieldCommands(config, program);
  registerEditCommands(config, program);
  registerAuditCommands(config, program);
}
