import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import type { OutputFormat } from '../types/index.js';
import type { StoreType } from '../types/store.js';
import type { Command } from 'commander';

const VALID_STORE_TYPES = [
  's3',
  'local-file',
  'bitwarden',
  'git',
  'vault',
] as const satisfies readonly StoreType[];

async function validateS3Options(options: Record<string, unknown>): Promise<void> {
  if (!options.s3Endpoint || !options.s3Bucket || !options.s3AccessKeyId) {
    throw new ValidationError(t('commands.store.add.s3Required'));
  }
  if (!options.s3SecretAccessKey) {
    const { askPassword } = await import('../utils/prompt.js');
    options.s3SecretAccessKey = await askPassword(t('commands.store.add.promptS3SecretAccessKey'));
    if (!options.s3SecretAccessKey) {
      throw new ValidationError(t('commands.store.add.s3SecretRequired'));
    }
  }
}

async function validateVaultOptions(options: Record<string, unknown>): Promise<void> {
  if (!options.vaultAddr) {
    throw new ValidationError(t('commands.store.add.vaultAddrRequired'));
  }
  if (!options.vaultToken) {
    options.vaultToken = process.env.VAULT_TOKEN;
    if (!options.vaultToken) {
      const { askPassword } = await import('../utils/prompt.js');
      options.vaultToken = await askPassword(t('commands.store.add.promptVaultToken'));
      if (!options.vaultToken) {
        throw new ValidationError(t('commands.store.add.vaultTokenRequired'));
      }
    }
  }
}

/**
 * Validate required options for a given store type.
 * Throws ValidationError if required options are missing; may prompt for secrets.
 */
async function validateStoreOptions(
  storeType: StoreType,
  options: Record<string, unknown>
): Promise<void> {
  if (storeType === 's3') {
    return validateS3Options(options);
  }
  if (storeType === 'local-file') {
    if (!options.localPath) {
      throw new ValidationError(t('commands.store.add.localPathRequired'));
    }
    return;
  }
  if (storeType === 'bitwarden') {
    // No required options — just needs bw CLI installed and logged in
    return;
  }
  if (storeType === 'git') {
    if (!options.gitUrl) {
      throw new ValidationError(t('commands.store.add.gitUrlRequired'));
    }
    return;
  }
  // vault (the only remaining valid type)
  return validateVaultOptions(options);
}

/**
 * Resolve which stores to operate on based on --store and --all flags.
 */
async function resolveStores(options: {
  all?: boolean;
  store?: string;
}): Promise<import('../types/store.js').StoreEntry[]> {
  const { storeRegistry } = await import('../stores/registry.js');
  if (options.all) {
    return storeRegistry.list();
  }
  if (options.store) {
    return [await storeRegistry.get(options.store)].filter(
      (s): s is import('../types/store.js').StoreEntry => s != null
    );
  }
  return storeRegistry.list();
}

/**
 * Sync a single store entry: pull (if newer) then push.
 */
async function syncSingleStore(
  entry: import('../types/store.js').StoreEntry,
  configName: string
): Promise<void> {
  const { createStoreAdapter } = await import('../stores/index.js');
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const adapter = await createStoreAdapter(entry);

  // Pull first
  const pullResult = await adapter.pull(configName);
  if (pullResult.success && pullResult.config) {
    const localConfig = await configFileStorage.load(configName);
    if (pullResult.config.version > localConfig.version) {
      await configFileStorage.save(pullResult.config, configName);
      outputService.info(t('commands.store.sync.pulled', { store: entry.name }));
    }
  }

  // Then push
  const config = await configFileStorage.load(configName);
  const pushResult = await adapter.push(config, configName);
  if (pushResult.success) {
    outputService.success(t('commands.store.sync.pushed', { store: entry.name }));
  }
}

export function registerStoreCommands(program: Command): void {
  const store = program.command('store').description(t('commands.store.description'));

  store.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc store add my-backup --type s3 --s3-bucket my-backups  ${t('help.store.add')}
  $ rdc store push                                            ${t('help.store.push')}
  $ rdc store pull                                            ${t('help.store.pull')}
`
  );

  // store add <name>
  store
    .command('add <name>')
    .description(t('commands.store.add.description'))
    .requiredOption('--type <type>', t('commands.store.add.optionType'))
    .option('--encryption-key <key>', t('commands.store.add.optionEncryptionKey'))
    // S3 options
    .option('--s3-endpoint <url>', t('commands.store.add.optionS3Endpoint'))
    .option('--s3-bucket <name>', t('commands.store.add.optionS3Bucket'))
    .option('--s3-region <region>', t('commands.store.add.optionS3Region'), 'auto')
    .option('--s3-access-key-id <key>', t('commands.store.add.optionS3AccessKeyId'))
    .option('--s3-secret-access-key <key>', t('commands.store.add.optionS3SecretAccessKey'))
    .option('--s3-prefix <prefix>', t('commands.store.add.optionS3Prefix'))
    // Local file options
    .option('--local-path <path>', t('commands.store.add.optionLocalPath'))
    // Bitwarden options
    .option('--bw-folder-id <id>', t('commands.store.add.optionBwFolderId'))
    // Git options
    .option('--git-url <url>', t('commands.store.add.optionGitUrl'))
    .option('--git-branch <branch>', t('commands.store.add.optionGitBranch'))
    .option('--git-path <path>', t('commands.store.add.optionGitPath'))
    // Vault options
    .option('--vault-addr <url>', t('commands.store.add.optionVaultAddr'))
    .option('--vault-token <token>', t('commands.store.add.optionVaultToken'))
    .option('--vault-mount <path>', t('commands.store.add.optionVaultMount'))
    .option('--vault-prefix <path>', t('commands.store.add.optionVaultPrefix'))
    .option('--vault-namespace <ns>', t('commands.store.add.optionVaultNamespace'))
    .action(async (name, options) => {
      try {
        const storeType = options.type as StoreType;
        if (!VALID_STORE_TYPES.includes(storeType)) {
          throw new ValidationError(
            t('commands.store.add.invalidType', {
              type: storeType,
              valid: VALID_STORE_TYPES.join(', '),
            })
          );
        }

        await validateStoreOptions(storeType, options);

        const { storeRegistry } = await import('../stores/registry.js');
        const existing = await storeRegistry.get(name);
        if (existing) {
          throw new ValidationError(t('commands.store.add.alreadyExists', { name }));
        }

        await storeRegistry.add({
          name,
          type: storeType,
          encryptionKey: options.encryptionKey,
          s3Endpoint: options.s3Endpoint,
          s3Bucket: options.s3Bucket,
          s3Region: options.s3Region,
          s3AccessKeyId: options.s3AccessKeyId,
          s3SecretAccessKey: options.s3SecretAccessKey,
          s3Prefix: options.s3Prefix,
          localPath: options.localPath,
          bwFolderId: options.bwFolderId,
          gitUrl: options.gitUrl,
          gitBranch: options.gitBranch,
          gitPath: options.gitPath,
          vaultAddr: options.vaultAddr,
          vaultToken: options.vaultToken,
          vaultMount: options.vaultMount,
          vaultPrefix: options.vaultPrefix,
          vaultNamespace: options.vaultNamespace,
        });

        // Verify connection
        const { createStoreAdapter } = await import('../stores/index.js');
        const entry = await storeRegistry.get(name);
        if (!entry) throw new Error(`Store "${name}" was added but could not be retrieved`);
        const adapter = await createStoreAdapter(entry);
        const ok = await adapter.verify();
        if (ok) {
          outputService.success(t('commands.store.add.success', { name, type: storeType }));
        } else {
          outputService.warn(t('commands.store.add.addedButUnverified', { name }));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // store list
  store
    .command('list')
    .alias('ls')
    .description(t('commands.store.list.description'))
    .action(async () => {
      try {
        const { storeRegistry } = await import('../stores/registry.js');
        const stores = await storeRegistry.list();
        const format = program.opts().output as OutputFormat;

        if (stores.length === 0) {
          outputService.info(t('commands.store.list.noStores'));
          return;
        }

        const displayData = stores.map((s) => ({
          name: s.name,
          type: s.type,
          encrypted: s.encryptionKey ? 'yes' : 'no',
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // store remove <name>
  store
    .command('remove <name>')
    .alias('rm')
    .description(t('commands.store.remove.description'))
    .action(async (name) => {
      try {
        const { storeRegistry } = await import('../stores/registry.js');
        await storeRegistry.remove(name);
        outputService.success(t('commands.store.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // store push [--store <name>] [--all]
  store
    .command('push')
    .description(t('commands.store.push.description'))
    .option('--store <name>', t('commands.store.push.optionStore'))
    .option('--all', t('commands.store.push.optionAll'))
    .action(async (options) => {
      try {
        const { createStoreAdapter } = await import('../stores/index.js');
        const { configFileStorage } = await import('../adapters/config-file-storage.js');

        const configName = configService.getCurrentName();
        const config = await configFileStorage.load(configName);

        const stores = await resolveStores(options);

        if (stores.length === 0) {
          outputService.info(t('commands.store.push.noStores'));
          return;
        }

        for (const entry of stores) {
          try {
            const adapter = await createStoreAdapter(entry);
            const result = await adapter.push(config, configName);
            if (result.success) {
              outputService.success(
                t('commands.store.push.success', { store: entry.name, config: configName })
              );
            } else {
              outputService.error(
                t('commands.store.push.failed', {
                  store: entry.name,
                  error: result.error ?? DEFAULTS.TELEMETRY.UNKNOWN,
                })
              );
            }
          } catch (error) {
            outputService.error(
              t('commands.store.push.failed', { store: entry.name, error: String(error) })
            );
          }
        }
      } catch (error) {
        handleError(error);
      }
    });

  // store pull --store <name>
  store
    .command('pull')
    .description(t('commands.store.pull.description'))
    .requiredOption('--store <name>', t('commands.store.pull.optionStore'))
    .option('--config <name>', t('commands.store.pull.optionConfig'))
    .action(async (options) => {
      try {
        const { storeRegistry } = await import('../stores/registry.js');
        const { createStoreAdapter } = await import('../stores/index.js');
        const { configFileStorage } = await import('../adapters/config-file-storage.js');

        const entry = await storeRegistry.get(options.store);
        if (!entry) {
          throw new ValidationError(t('commands.store.pull.notFound', { name: options.store }));
        }

        const configName = options.config ?? configService.getCurrentName();
        const adapter = await createStoreAdapter(entry);
        const result = await adapter.pull(configName);

        if (result.success && result.config) {
          await configFileStorage.save(result.config, configName);
          outputService.success(
            t('commands.store.pull.success', { store: entry.name, config: configName })
          );
        } else {
          outputService.error(
            t('commands.store.pull.failed', {
              store: entry.name,
              error: result.error ?? DEFAULTS.TELEMETRY.UNKNOWN,
            })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // store sync [--store <name>] [--all]
  store
    .command('sync')
    .description(t('commands.store.sync.description'))
    .option('--store <name>', t('commands.store.sync.optionStore'))
    .option('--all', t('commands.store.sync.optionAll'))
    .action(async (options) => {
      try {
        const configName = configService.getCurrentName();

        const stores = await resolveStores(options);

        if (stores.length === 0) {
          outputService.info(t('commands.store.sync.noStores'));
          return;
        }

        for (const entry of stores) {
          try {
            await syncSingleStore(entry, configName);
          } catch (error) {
            outputService.error(
              t('commands.store.sync.failed', { store: entry.name, error: String(error) })
            );
          }
        }
      } catch (error) {
        handleError(error);
      }
    });
}
