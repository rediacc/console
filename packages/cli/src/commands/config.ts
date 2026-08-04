import { DEFAULTS } from '@rediacc/shared/config';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getSubscriptionServerUrl } from '../services/account/subscription-auth.js';
import type { ReconcileDeps } from '../services/config/config-reconcile.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat, RdcConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { registerAuditCommands } from './config/audit.js';
import { registerEditCommands } from './config/edit.js';
import { registerFieldCommands } from './config/field.js';
import { registerPruneCommand as registerConfigPruneCommand } from './config-prune-cmd.js';
import { registerRemoteCommands, rotateCek } from './config-remote.js';
import { registerSSHCommands } from './config-ssh.js';
import { registerCurrentCommand } from './config/current.js';

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
  const { readSSHKey, readOptionalSSHKey } = await import('../services/renet/renet-execution.js');
  const privateKey = (await readSSHKey(keyPath)).trim();
  const publicKey = (await readOptionalSSHKey(`${keyPath}.pub`)).trim() || undefined;
  return { privateKey, publicKey };
}

/**
 * One row of `config list`.
 *
 * An unparseable file must not abort the whole listing, so it degrades to a
 * status:"invalid" row and the walk continues (same tolerant-read stance as
 * configFileStorage.getBackupInfo).
 */
async function buildConfigListRow(
  name: string,
  currentName: string
): Promise<{ name: string; active: string; machines: string; status: string }> {
  const active = name === currentName ? '*' : '';
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  try {
    const cfg = await configFileStorage.load(name);
    return {
      name,
      active,
      machines: Object.keys(cfg.resources?.machines ?? {}).length.toString(),
      status: 'ok',
    };
  } catch {
    return { name, active, machines: '-', status: 'invalid' };
  }
}

/**
 * Build the `account` patch for `config init --server <url>`.
 *
 * Writing only `accountServer` leaves the config with no `e2ePublicKey`, so the
 * FIRST tunnelled request falls through to the baked-in production key
 * (getServerKeyMaterial tier 3) and dies with a bare "Decryption failed". Only
 * a LATER command self-heals, via discoverServerKey(). Seeding the key here is
 * what makes the first real command work.
 *
 * An unreachable server is not fatal: discovery still heals the config on a
 * later run, so this warns and writes the server URL alone.
 */
export async function buildInitAccountUpdate(
  server: string | undefined
): Promise<Partial<NonNullable<RdcConfig['account']>> | undefined> {
  if (!server) return undefined;
  const accountServer = server.replace(/\/+$/, '');
  try {
    const { fetchServerInfo } = await import('../services/account/account-client.js');
    const info = await fetchServerInfo(accountServer);
    const e2ePublicKey = info.e2e.keys[0]?.publicKeySpki;
    if (e2ePublicKey) return { accountServer, e2ePublicKey };
    outputService.warn(t('commands.config.init.serverKeyMissing', { server: accountServer }));
  } catch (error) {
    outputService.warn(
      t('commands.config.init.serverKeyUnreachable', {
        server: accountServer,
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
  return { accountServer };
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

/**
 * The v3 `defaults` keys `config set`/`clear` accept (spec/03 §5.1). `team`,
 * `region` and `machine` are DELETED keys (R2-F9 residue sweep): they get a
 * teaching error naming the valid keys, never a silent write.
 */
const DEFAULT_KEYS: Record<string, 'language' | 'datastoreSize' | 'pruneGraceDays'> = {
  language: 'language',
  'datastore-size': 'datastoreSize',
  'prune-grace-days': 'pruneGraceDays',
};
const RETIRED_KEYS = new Set(['team', 'region', 'machine']);

function resolveDefaultKey(key: string): 'language' | 'datastoreSize' | 'pruneGraceDays' {
  // hasOwn, not a truthiness check on the lookup: index access is typed as always
  // present (no noUncheckedIndexedAccess), so `if (!DEFAULT_KEYS[key])` reads as dead
  // code to the type system even though an unknown key is exactly what it catches.
  if (!Object.hasOwn(DEFAULT_KEYS, key)) {
    const valid = Object.keys(DEFAULT_KEYS).join(', ');
    if (RETIRED_KEYS.has(key)) {
      throw new ValidationError(t('errors.config.retiredKey', { key, keys: valid }));
    }
    throw new ValidationError(t('errors.invalidKey', { keys: valid }));
  }
  return DEFAULT_KEYS[key];
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
  const { auditLog } = await import('../services/core/audit-log.js');
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

  // Use process.stdout.isTTY, not isatty(fd): the fd can be undefined in
  // worker threads or stream wrappers, where isatty() would throw a TypeError.
  if (!process.stdout.isTTY) {
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

interface ReconcileCliOptions {
  machine?: string[];
  dryRun?: boolean;
  acceptObserved?: boolean;
}

/**
 * `config reconcile` body (extracted so the action stays thin). Rebuilds the
 * state half from machine truth; under --accept-observed it also rewrites an
 * unambiguous machine-arm placement drift (spec/04 §4.3) through the
 * version-bumping resources writer, distinct from the state writer.
 */
async function runReconcile(program: Command, options: ReconcileCliOptions): Promise<void> {
  try {
    await runReconcileInner(program, options);
  } catch (error) {
    handleError(error);
  }
}

/** Build the reconcile DI deps: a config loader filtered to `--machine`, and the
 * two writers (state-half and version-bumping resources), both no-ops under --dry-run. */
async function buildReconcileDeps(
  cfgName: string,
  filter: string[] | undefined,
  dryRun: boolean | undefined
): Promise<ReconcileDeps> {
  const { fetchMachineStatus } = await import('../services/machine/machine-status.js');
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const noop = async () => {};
  return {
    loadConfig: async () => {
      const cfg = await configService.getCurrent();
      if (!cfg || !filter?.length) return cfg;
      const machines = Object.fromEntries(
        Object.entries(cfg.resources?.machines ?? {}).filter(([n]) => filter.includes(n))
      );
      return { ...cfg, resources: { ...(cfg.resources ?? {}), machines } };
    },
    fetchStatus: (m) => fetchMachineStatus(m),
    writeState: dryRun
      ? noop
      : async (updater) => {
          await configFileStorage.updateState(cfgName, updater);
        },
    writeResources: dryRun
      ? noop
      : async (updater) => {
          await configFileStorage.update(cfgName, updater);
        },
  };
}

async function runReconcileInner(program: Command, options: ReconcileCliOptions): Promise<void> {
  const { reconcileState } = await import('../services/config/config-reconcile.js');
  const cfgName = configService.getEffectiveConfigName();
  const filter = options.machine;

  // --accept-observed rewrites a declaration from "observed on exactly one
  // machine", which is meaningless when --machine scanned only a subset:
  // rewriting from partial evidence is a guess. Refuse the combination
  // (spec/04 §4.3); run it unfiltered instead.
  if (options.acceptObserved && filter?.length) {
    throw new ValidationError(t('commands.config.reconcile.acceptObservedUnfiltered'));
  }

  const deps = await buildReconcileDeps(cfgName, filter, options.dryRun);
  const report = await reconcileState(deps, { acceptObserved: options.acceptObserved });

  const format = program.opts().output as OutputFormat;
  outputService.print(
    {
      dryRun: !!options.dryRun,
      reconciledAt: report.reconciledAt,
      machinesSeen: report.machinesSeen,
      unreachable: report.machinesUnreachable,
      placementsFilled: report.placementsFilled,
      placementsAccepted: report.placementsAccepted,
      conflicts: report.conflicts,
    },
    format
  );
  // Exit 6 (NETWORK) when nothing was reachable but machines were tried.
  if (report.machinesSeen.length === 0 && report.machinesUnreachable.length > 0) {
    process.exitCode = 6;
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
  $ rdc config init production --ssh-key ~/.ssh/id_ed25519          ${t('help.config.init')}
  $ rdc machine add server-1 --ip 10.0.0.1 --user deploy            ${t('help.config.addMachine')}
  $ rdc machine setup server-1                                      ${t('help.config.setupMachine')}
`
  );

  // config init [name] - Create a named config file
  config
    .command('init')
    .argument('[name]', t('options.name'))
    .description(t('commands.config.init.description'))
    .option('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .option('--master-password <password>', t('commands.config.init.optionMasterPassword'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (name: string | undefined, options) => {
      try {
        const configName = name ?? DEFAULTS.CONTEXT.CONFIG_NAME;

        // The default config auto-creates on first use; `config init` is for
        // named configs. A bare, flagless invocation teaches that and exits 2.
        if (!name && !hasInitFlags(options)) {
          throw new ValidationError(t('commands.config.init.bareForm'));
        }

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const exists = await configFileStorage.exists(configName);

        // Named configs must not already exist
        if (exists && name) {
          throw new ValidationError(t('commands.config.init.alreadyExists', { name: configName }));
        }

        const newConfig = exists
          ? await configFileStorage.load(configName)
          : await configService.init(configName);

        const sshContent = options.sshKey ? await readSshKeyForInit(options.sshKey) : undefined;

        const accountUpdate = await buildInitAccountUpdate(options.server);

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

        if (configs.length === 0 && format === 'table') {
          outputService.info(t('commands.config.list.noConfigs'));
          return;
        }

        const displayData = [];
        for (const name of configs) {
          displayData.push(await buildConfigListRow(name, currentName));
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
          // Same contract as the list commands: a machine-readable format gets an
          // explicit null payload, never an empty stdout.
          if (format === 'table') outputService.info(t('commands.config.show.noConfig', { name }));
          else outputService.print(null, format);
          return;
        }

        // Default: redact sensitive values. --reveal opts in (humans only).
        // The redactor is schema-driven (packages/shared/src/config-schema/walker.ts).
        if (options.reveal) {
          await applyRevealGate(cfg);
        } else {
          const { redactClone } = await import('../schema/fingerprint.js');
          const redacted = redactClone(cfg);
          Object.assign(cfg as Record<string, unknown>, redacted);
        }

        const display: Record<string, unknown> = await buildSelfHostedDisplay(cfg, name);

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config current
  registerCurrentCommand(config, program);

  // config delete <name>
  config
    .command('delete')
    .alias('rm')
    .argument('<name>', t('options.name'))
    .description(t('commands.config.delete.description'))
    .action(async (name: string) => {
      try {
        await configService.delete(name);
        outputService.success(t('commands.config.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config set <key> <value>
  config
    .command('set')
    .argument('<key>', t('options.configKey'))
    .argument('<value>', t('options.configValue'))
    .description(t('commands.config.set.description'))
    .action(async (key: string, value: string) => {
      try {
        const field = resolveDefaultKey(key);
        await configService.setDefault(field, value);
        outputService.success(t('commands.config.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // config clear [key]
  config
    .command('clear')
    .argument('[key]', t('options.configKey'))
    .description(t('commands.config.clear.description'))
    .action(async (key: string | undefined) => {
      try {
        if (key) {
          const field = resolveDefaultKey(key);
          await configService.clearDefault(field);
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
    .argument('[name]', t('options.name'))
    .option('-y, --yes', t('options.yes'))
    .action(async (name: string | undefined, options) => {
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

  registerConfigPruneCommand(config);

  // config reconcile — rebuild the state bucket from machine truth (R2-F2).
  config
    .command('reconcile')
    .description(t('commands.config.reconcile.description'))
    .option('--machine <m...>', t('commands.config.reconcile.optionMachine'))
    .option('--dry-run', t('options.dryRun'))
    .option('--accept-observed', t('commands.config.reconcile.optionAcceptObserved'))
    .action((options: ReconcileCliOptions) => runReconcile(program, options));

  // config rotate-cek — destructive, org-wide (Q3): registered here, not under
  // `config remote`, because it rotates the ORGANIZATION's key, not this device's
  // link. The impl still lives in config-remote.ts alongside the store internals.
  config
    .command('rotate-cek')
    .description(t('commands.config.rotateCek.description'))
    .option('--api-url <url>', t('commands.config.rotateCek.optionApiUrl'))
    .action(async (options: { apiUrl?: string }) => {
      try {
        const configName = configService.getEffectiveConfigName();
        const apiUrl = options.apiUrl ?? getSubscriptionServerUrl();
        await rotateCek(configName, apiUrl);
      } catch (error) {
        handleError(error);
      }
    });

  // Register nested sub-command groups
  registerSSHCommands(config, program);
  registerRemoteCommands(config);
  registerFieldCommands(config, program);
  registerEditCommands(config, program);
  registerAuditCommands(config, program);
}
