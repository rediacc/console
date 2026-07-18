import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import {
  bindBackupStrategy,
  unbindBackupStrategy,
} from '../services/config/config-strategy-binding.js';
import { outputService } from '../services/core/output.js';
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
    throw new ValidationError(t('commands.backup.strategy.set.storageRequired'));
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

async function applyBackupStrategyOptions(
  name: string,
  options: {
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
  }
): Promise<void> {
  const enabled = resolveEnabledFlag(options.enable, options.disable);
  const targetsDestination = Boolean(options.destination);

  // Strategy fields and destination fields are applied in the SAME call. This
  // used to be an either/or, so creating a strategy with a destination took two
  // invocations — and the first one, `set <new> --destination …`, silently
  // produced a strategy with an empty schedule.
  //
  // `--bwlimit` and `--enable/--disable` stay scoped to the destination when one
  // is named, which is what they have always meant there: `set s --destination d
  // --disable` disables that destination, not the whole strategy.
  const update = buildStrategyUpdate(
    { ...options, bwlimit: targetsDestination ? undefined : options.bwlimit },
    targetsDestination ? undefined : enabled
  );

  // Order matters: upsertBackupDestination reads the stored strategy to merge
  // destination defaults, so the strategy has to exist before the destination
  // is attached. These cannot run in parallel.
  if (!targetsDestination || Object.keys(update).length > 0) {
    await configService.setBackupStrategy(name, update);
  }

  if (options.destination) {
    await upsertBackupDestination({
      strategyName: name,
      destinationName: options.destination,
      storage: options.storage,
      enabled,
      bwlimit: options.bwlimit,
      folder: options.folder,
    });
  }
}

/** strategy name -> machines binding it, for reporting deployment reach. */
async function strategyBindings(): Promise<Map<string, string[]>> {
  const machines = await configService.listMachines();
  const bindings = new Map<string, string[]>();
  for (const { name, config } of machines) {
    for (const strategy of config.backupStrategies ?? []) {
      const list = bindings.get(strategy);
      if (list) list.push(name);
      else bindings.set(strategy, [name]);
    }
  }
  return bindings;
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
    outputService.info(t('commands.backup.strategy.show.noDestinations'));
    return;
  }
  outputService.info(t('commands.backup.strategy.show.destinationsHeader'));
  for (const dest of strategy.destinations) {
    const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit ?? '-';
    const enabled = dest.enabled !== false;
    const folder = dest.folder ? `  folder=${dest.folder}` : '';
    outputService.info(
      `    ${dest.name}  storage=${dest.storage}  bwlimit=${bwlimit}  enabled=${enabled}${folder}`
    );
  }
}

/** Register the `backup strategy` subgroup (named backup strategy records). */
export function registerBackupStrategyCommands(backup: Command): void {
  const group = backup.command('strategy').description(t('commands.backup.strategy.description'));

  group
    .command('set')
    .argument('<strategy>', t('options.strategyName'))
    .description(t('commands.backup.strategy.set.description'))
    .option('--destination <name>', t('commands.backup.strategy.set.optionDestination'))
    .option('--storage <name>', t('commands.backup.strategy.set.optionStorage'))
    .option('--cron <expression>', t('commands.backup.strategy.set.optionCron'))
    .addOption(
      new Option('--mode <mode>', t('commands.backup.strategy.set.optionMode')).choices([
        'hot',
        'cold',
      ])
    )
    .option('--bwlimit <limit>', t('commands.backup.strategy.set.optionBwlimit'))
    .option('--include <repos>', t('commands.backup.strategy.set.optionInclude'))
    .option('--exclude <repos>', t('commands.backup.strategy.set.optionExclude'))
    .option('--folder <path>', t('commands.backup.strategy.set.optionFolder'))
    .option('--enable', t('commands.backup.strategy.set.optionEnable'))
    .option('--disable', t('commands.backup.strategy.set.optionDisable'))
    .action(async (strategy: string, options) => {
      try {
        await applyBackupStrategyOptions(strategy, options);
        outputService.success(t('commands.backup.strategy.set.saved'));
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('bind')
    .argument('<strategy>', t('options.strategyName'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .description(t('commands.backup.strategy.bind.description'))
    .action(async (strategy: string, options: { machine: string }) => {
      try {
        const bound = await bindBackupStrategy(options.machine, strategy);
        outputService.success(
          bound
            ? t('commands.backup.strategy.bind.bound', {
                strategy,
                machine: options.machine,
              })
            : t('commands.backup.strategy.bind.alreadyBound', {
                strategy,
                machine: options.machine,
              })
        );
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('unbind')
    .argument('<strategy>', t('options.strategyName'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .description(t('commands.backup.strategy.unbind.description'))
    .action(async (strategy: string, options: { machine: string }) => {
      try {
        const removed = await unbindBackupStrategy(options.machine, strategy);
        outputService.success(
          removed
            ? t('commands.backup.strategy.unbind.unbound', {
                strategy,
                machine: options.machine,
              })
            : t('commands.backup.strategy.unbind.notBound', {
                strategy,
                machine: options.machine,
              })
        );
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('remove')
    .argument('<strategy>', t('options.strategyName'))
    .description(t('commands.backup.strategy.remove.description'))
    .option('--destination <name>', t('commands.backup.strategy.remove.optionDestination'))
    .action(async (strategy: string, options) => {
      try {
        if (options.destination) {
          await configService.removeBackupDestination(strategy, options.destination);
        } else {
          await configService.removeBackupStrategy(strategy);
        }
        outputService.success(t('commands.backup.strategy.remove.removed'));
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('list')
    .description(t('commands.backup.strategy.list.description'))
    .action(async () => {
      try {
        const strategies = await configService.listBackupStrategies();
        const names = Object.keys(strategies);
        if (names.length === 0) {
          outputService.info(t('commands.backup.strategy.show.notConfigured'));
          return;
        }
        // A strategy is only ever deployed to machines that bind it, so a
        // listing without bindings cannot answer "why did this not run?".
        const boundTo = await strategyBindings();
        for (const name of names) {
          const s = strategies[name];
          const mode = s.mode ?? BACKUP_DEFAULTS.MODE;
          const destCount = s.destinations.length;
          const enabled = s.enabled !== false;
          const machines = boundTo.get(name);
          const bound = machines?.length ? machines.join(',') : '-';
          outputService.info(
            `  ${name}  schedule=${s.schedule}  mode=${mode}  destinations=${destCount}  enabled=${enabled}  machines=${bound}`
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('show')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.strategy.show.description'))
    .action(async (strategy: string | undefined) => {
      try {
        if (strategy) {
          const found = await configService.getBackupStrategy(strategy);
          if (!found) {
            outputService.info(t('commands.backup.strategy.show.notFound', { name: strategy }));
            return;
          }
          displayStrategy(strategy, found);
          return;
        }
        const strategies = await configService.listBackupStrategies();
        const names = Object.keys(strategies);
        if (names.length === 0) {
          outputService.info(t('commands.backup.strategy.show.notConfigured'));
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
