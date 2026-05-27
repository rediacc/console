import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { BackupStrategyConfig } from '../types/index.js';
import {
  assertStorageExists,
  BackupDestinationSchema,
  parseConfig,
} from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';

function resolveEnabledFlag(enable?: boolean, disable?: boolean): boolean | undefined {
  if (enable) return true;
  if (disable) return false;
  return undefined;
}

interface UpsertDestOpts {
  strategyName: string;
  destinationName: string;
  storage?: string;
  enabled?: boolean;
  bwlimit?: string;
  folder?: string;
}

async function upsertBackupDestination(o: UpsertDestOpts): Promise<void> {
  const existing = await configService.getBackupStrategy(o.strategyName);
  const existingDest = existing?.destinations.find((d) => d.name === o.destinationName);
  const storageName = o.storage ?? existingDest?.storage;
  if (!storageName) {
    throw new ValidationError(t('commands.config.backupStrategy.set.storageRequired'));
  }
  await assertStorageExists(storageName);
  const dest = parseConfig(
    BackupDestinationSchema,
    {
      name: o.destinationName,
      storage: storageName,
      enabled: o.enabled,
      bandwidthLimit: o.bwlimit,
      folder: o.folder ?? existingDest?.folder,
    },
    'backup destination'
  );
  await configService.addBackupDestination(o.strategyName, dest);
}

// parseRepoFilter turns a comma-separated --include/--exclude value into a repo
// list, or returns undefined to CLEAR the filter. An empty string or the literal
// "none" (and a value that is only separators/whitespace) clears it — that's how
// you drop a strategy's include/exclude entirely (e.g. make a cold backup cover
// all repos again). setBackupStrategy merges with `{...existing, ...update}`, and
// an undefined value is dropped on JSON write, so the key is removed.
export function parseRepoFilter(raw: string): string[] | undefined {
  const trimmed = raw.trim();
  if (trimmed === '' || trimmed.toLowerCase() === 'none') return undefined;
  const list = trimmed
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return list.length > 0 ? list : undefined;
}

export function buildStrategyUpdate(
  opts: { cron?: string; mode?: string; bwlimit?: string; include?: string; exclude?: string },
  enabled: boolean | undefined
): Partial<BackupStrategyConfig> {
  const u: Partial<BackupStrategyConfig> = {};
  if (opts.cron !== undefined) u.schedule = opts.cron;
  if (opts.mode !== undefined) u.mode = opts.mode as 'hot' | 'cold';
  if (enabled !== undefined) u.enabled = enabled;
  if (opts.bwlimit !== undefined) u.bandwidthLimit = opts.bwlimit;
  // include/exclude are mutually exclusive; setting one clears the other.
  // An empty/"none" value clears the filter entirely.
  if (opts.include !== undefined) {
    u.include = parseRepoFilter(opts.include);
    u.exclude = undefined;
  }
  if (opts.exclude !== undefined) {
    u.exclude = parseRepoFilter(opts.exclude);
    u.include = undefined;
  }
  return u;
}

async function applyBackupStrategyOptions(options: {
  name: string;
  destination?: string;
  storage?: string;
  cron?: string;
  mode?: string;
  bwlimit?: string;
  include?: string;
  exclude?: string;
  folder?: string;
  enable?: boolean;
  disable?: boolean;
}): Promise<void> {
  const enabled = resolveEnabledFlag(options.enable, options.disable);
  if (options.destination) {
    await upsertBackupDestination({
      strategyName: options.name,
      destinationName: options.destination,
      storage: options.storage,
      enabled,
      bwlimit: options.bwlimit,
      folder: options.folder,
    });
  } else {
    await configService.setBackupStrategy(options.name, buildStrategyUpdate(options, enabled));
  }
}

function displayStrategy(name: string, strategy: BackupStrategyConfig): void {
  const mode = strategy.mode ?? BACKUP_DEFAULTS.MODE;
  outputService.info(`Strategy: ${name}`);
  outputService.info(`  Schedule: ${strategy.schedule}`);
  outputService.info(`  Mode: ${mode}`);
  outputService.info(`  Enabled: ${strategy.enabled !== false}`);
  if (strategy.bandwidthLimit) outputService.info(`  Bandwidth limit: ${strategy.bandwidthLimit}`);
  if (strategy.include) outputService.info(`  Include: ${strategy.include.join(', ')}`);
  if (strategy.exclude) outputService.info(`  Exclude: ${strategy.exclude.join(', ')}`);
  if (strategy.destinations.length === 0) {
    outputService.info(t('commands.config.backupStrategy.show.noDestinations'));
    return;
  }
  outputService.info(t('commands.config.backupStrategy.show.destinationsHeader'));
  for (const dest of strategy.destinations) {
    const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit ?? '-';
    const enabled = dest.enabled !== false;
    const folder = dest.folder ? `  folder=${dest.folder}` : '';
    outputService.info(
      `    ${dest.name}  storage=${dest.storage}  bwlimit=${bwlimit}  enabled=${enabled}${folder}`
    );
  }
}

export function registerBackupStrategyCommands(config: Command): void {
  const group = config
    .command('backup-strategy')
    .description(t('commands.config.backupStrategy.description'));

  group
    .command('set')
    .description(t('commands.config.backupStrategy.set.description'))
    .requiredOption('--name <name>', t('commands.config.backupStrategy.set.optionName'))
    .option('--destination <name>', t('commands.config.backupStrategy.set.optionDestination'))
    .option('--storage <name>', t('commands.config.backupStrategy.set.optionStorage'))
    .option('--cron <expression>', t('commands.config.backupStrategy.set.optionCron'))
    .option('--mode <mode>', t('commands.config.backupStrategy.set.optionMode'))
    .option('--bwlimit <limit>', t('commands.config.backupStrategy.set.optionBwlimit'))
    .option('--include <repos>', t('commands.config.backupStrategy.set.optionInclude'))
    .option('--exclude <repos>', t('commands.config.backupStrategy.set.optionExclude'))
    .option('--folder <path>', t('commands.config.backupStrategy.set.optionFolder'))
    .option('--enable', t('commands.config.backupStrategy.set.optionEnable'))
    .option('--disable', t('commands.config.backupStrategy.set.optionDisable'))
    .action(async (options) => {
      try {
        await applyBackupStrategyOptions(options);
        outputService.success(t('commands.config.backupStrategy.set.saved'));
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('remove')
    .description(t('commands.config.backupStrategy.remove.description'))
    .requiredOption('--name <name>', t('commands.config.backupStrategy.remove.optionName'))
    .option('--destination <name>', t('commands.config.backupStrategy.remove.optionDestination'))
    .action(async (options) => {
      try {
        if (options.destination) {
          await configService.removeBackupDestination(options.name, options.destination);
        } else {
          await configService.removeBackupStrategy(options.name);
        }
        outputService.success(t('commands.config.backupStrategy.remove.removed'));
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('list')
    .description(t('commands.config.backupStrategy.list.description'))
    .action(async () => {
      try {
        const strategies = await configService.listBackupStrategies();
        const names = Object.keys(strategies);
        if (names.length === 0) {
          outputService.info(t('commands.config.backupStrategy.show.notConfigured'));
          return;
        }
        for (const name of names) {
          const s = strategies[name];
          const mode = s.mode ?? BACKUP_DEFAULTS.MODE;
          const destCount = s.destinations.length;
          const enabled = s.enabled !== false;
          outputService.info(
            `  ${name}  schedule=${s.schedule}  mode=${mode}  destinations=${destCount}  enabled=${enabled}`
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('show')
    .description(t('commands.config.backupStrategy.show.description'))
    .option('--name <name>', t('commands.config.backupStrategy.show.optionName'))
    .action(async (options) => {
      try {
        if (options.name) {
          const strategy = await configService.getBackupStrategy(options.name);
          if (!strategy) {
            outputService.info(
              t('commands.config.backupStrategy.show.notFound', { name: options.name })
            );
            return;
          }
          displayStrategy(options.name, strategy);
          return;
        }
        const strategies = await configService.listBackupStrategies();
        const names = Object.keys(strategies);
        if (names.length === 0) {
          outputService.info(t('commands.config.backupStrategy.show.notConfigured'));
          return;
        }
        for (const name of names) {
          displayStrategy(name, strategies[name]);
          outputService.info('');
        }
      } catch (error) {
        handleError(error);
      }
    });
}
