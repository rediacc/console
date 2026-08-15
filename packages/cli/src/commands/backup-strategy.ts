import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import {
  unschedulableDestinationReason,
} from '../services/backup/backup-schedule-unit-generator.js';
import { configService } from '../services/config/config-resources.js';
import {
  bindBackupStrategy,
  unbindBackupStrategy,
} from '../services/config/config-strategy-binding.js';
import { outputService } from '../services/core/output.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';
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

type DestinationKind = 'storage' | 'hosted-service';

/**
 * Which kind of destination `--destination <name>` is talking about.
 *
 * THE SURFACE DECISION, and why it is a default rather than a flag. Until
 * 2026-08-15 this command could only make `storage` (rclone) destinations: it
 * hard-required `--storage`. Then the rclone emission was deleted from the unit
 * generator, and the two facts together left NO supported route from
 * `backup strategy set` to a deployable schedule — every path either threw at
 * set time for want of `--storage`, or threw at deploy time because a `storage`
 * destination can no longer be rendered. Only a hand-edited config JSON could
 * produce a working strategy.
 *
 * Three ways to close that were on the table: a `--hosted-service` boolean, a
 * `--kind <storage|hosted-service>` option, or making hosted-service what you
 * get when you do not say. This takes the third:
 *
 *  - The chunk store is the ONLY kind `rdc backup schedule` can deploy. A
 *    default that produces the undeployable kind is a trap, and a REQUIRED flag
 *    whose one useful value is always the same is a toll booth.
 *  - It adds no option, so the CLI contract and command tree do not move, and
 *    the working path is the shortest one to type.
 *  - `--storage <name>` keeps working unchanged and is now also the explicit
 *    opt-IN to the legacy kind, which is exactly the flag an operator who wants
 *    that kind was always going to pass.
 *
 * Precedence, and the reason for the middle rule: an EXISTING destination keeps
 * its kind when `--storage` is absent, so `set s --destination d --disable`
 * against the operator's live rclone destination edits it in place instead of
 * silently converting it to a chunk-store destination and orphaning the backups
 * behind it.
 */
function resolveDestinationKind(
  storageFlag: string | undefined,
  existing: { kind?: string } | undefined
): DestinationKind {
  if (storageFlag) return 'storage';
  // `kind` is declared OPTIONAL on this parameter on purpose. A destination
  // read through the config loader has been schema-parsed and always carries
  // one, but a hand-edited entry (and the operator's live config) has none, and
  // that case must still resolve to what the entry actually is.
  if (existing) {
    return (existing.kind ?? BACKUP_DEFAULTS.DESTINATION_KIND) === 'storage'
      ? 'storage'
      : 'hosted-service';
  }
  return BACKUP_DEFAULTS.NEW_DESTINATION_KIND;
}

/**
 * Drop keys whose value is undefined.
 *
 * Load-bearing, not tidiness. `configService.addBackupDestination` merges an
 * update over the stored destination with `{...existing, ...dest}`, and zod
 * KEEPS an optional key that was passed as an explicit `undefined` (verified on
 * zod 3.25.76: `parse({enabled: undefined})` yields an own `enabled` property).
 * A spread over that own property overwrites the stored value with undefined,
 * so before this, `backup strategy set s --destination d --bwlimit 6M` silently
 * re-ENABLED a destination the operator had disabled, and any set call without
 * `--bwlimit` silently dropped a per-destination bandwidth cap.
 */
function definedOnly(o: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined));
}

/**
 * Build the destination record to store, from the flags plus whatever is
 * already there. Pure: no config reads, no writes, so a test can drive the
 * exact object the operator's flags produce and hand it straight to the unit
 * generator. That crossing is deliberate — the defects in this stack all came
 * from each side being tested against its own fake.
 */
export function buildDestination(
  o: Omit<UpsertDestOpts, 'strategyName'>,
  existingDest: BackupStrategyDestination | undefined
): BackupStrategyDestination {
  const kind = resolveDestinationKind(o.storage, existingDest);
  if (kind === 'hosted-service') {
    // `--folder` is a subfolder inside an rclone bucket. The chunk store names
    // its own keys server-side (the client never composes an object key), so
    // there is nothing for a folder to mean here. Refused rather than dropped:
    // dropping it would put backups somewhere other than where the operator
    // said, which is the failure mode this whole surface keeps producing.
    if (o.folder !== undefined) {
      throw new ValidationError(t('commands.backup.strategy.set.storageRequired'));
    }
    return parseConfig(
      BackupDestinationSchema,
      definedOnly({
        kind,
        name: o.destinationName,
        enabled: o.enabled,
        bandwidthLimit: o.bwlimit,
      }),
      'backup destination'
    );
  }

  const existingStorageDest =
    existingDest && resolveDestinationKind(undefined, existingDest) === 'storage'
      ? (existingDest as { storage?: string; folder?: string })
      : undefined;
  const storageName = o.storage ?? existingStorageDest?.storage;
  if (!storageName) {
    throw new ValidationError(t('commands.backup.strategy.set.storageRequired'));
  }
  return parseConfig(
    BackupDestinationSchema,
    definedOnly({
      kind,
      name: o.destinationName,
      storage: storageName,
      enabled: o.enabled,
      bandwidthLimit: o.bwlimit,
      folder: o.folder ?? existingStorageDest?.folder,
    }),
    'backup destination'
  );
}

async function upsertBackupDestination(o: UpsertDestOpts): Promise<void> {
  const existing = await configService.getBackupStrategy(o.strategyName);
  const existingDest = existing?.destinations.find((d) => d.name === o.destinationName);
  const dest = buildDestination(o, existingDest);

  if (dest.kind === 'storage') await assertStorageExists(dest.storage);

  // A kind CHANGE cannot go through the merge in addBackupDestination: it
  // spreads the new record over the old one, so flipping hosted-service ->
  // storage would leave `endpoint`/`vaultContent` behind in the file (the
  // schema strips them on the next read, so the junk would be invisible until
  // someone diffed the config). Drop the old record first and write a clean one.
  // Compared through resolveDestinationKind, not `existingDest.kind`, so a
  // legacy entry with no `kind` at all is not treated as a flip and rewritten
  // for nothing.
  if (existingDest && resolveDestinationKind(undefined, existingDest) !== dest.kind) {
    await configService.removeBackupDestination(o.strategyName, o.destinationName);
  }
  await configService.addBackupDestination(o.strategyName, dest);

  // Saved, then flagged. A `storage` destination is still legal to hold on disk
  // and still legal to create — but no unit can be generated for one, and an
  // operator who learns that at deploy time has already bound the strategy and
  // walked away. Say it here, where the decision is.
  const unschedulable = unschedulableDestinationReason(dest);
  if (unschedulable) {
    // Naming the two commands matters: omitting --storage PRESERVES an existing
    // kind (see resolveDestinationKind), so there is no single flag that turns a
    // storage destination into a chunk-store one. "Change it to a hosted-service
    // destination" without the how is the same dead end in a friendlier voice.
    outputService.warn(
      `${unschedulable} The destination was saved, but \`rdc backup schedule\` will refuse to deploy a unit for it. ` +
        `To convert it: rdc backup strategy remove ${o.strategyName} --destination ${o.destinationName} ` +
        `&& rdc backup strategy set ${o.strategyName} --destination ${o.destinationName}`
    );
  }
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
  if (opts.mode !== undefined) {
    // `--mode cold` used to be refused here, because the scheduled verb could
    // only take a hot snapshot and accepting the flag would have promised a
    // quiesce that never happened. `backup snapshot --cold` exists now, so
    // both modes schedule and there is nothing left to refuse: the schema's
    // enum is exactly hot|cold, so any other value fails at config load.
    u.mode = opts.mode as 'hot' | 'cold';
  }
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
  displayStrategyDestinations(strategy);
}

/**
 * Render a strategy's destination list. Split out of `displayStrategy` only to
 * keep both under the sonarjs cognitive-complexity ceiling; the output is
 * byte-identical to when this was inline.
 */
function displayStrategyDestinations(strategy: BackupStrategyConfig): void {
  if (strategy.destinations.length === 0) {
    outputService.info(t('commands.backup.strategy.show.noDestinations'));
    return;
  }
  outputService.info(t('commands.backup.strategy.show.destinationsHeader'));
  for (const dest of strategy.destinations) {
    outputService.info(destinationLine(strategy, dest));
  }
}

/** One rendered destination line, marker included. Split out for the same
 *  cognitive-complexity ceiling as above. */
function destinationLine(strategy: BackupStrategyConfig, dest: BackupStrategyDestination): string {
  const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit ?? '-';
  const enabled = dest.enabled !== false;
  const target =
    dest.kind === 'storage'
      ? `storage=${dest.storage}${dest.folder ? `  folder=${dest.folder}` : ''}`
      : `hosted-service${dest.endpoint ? `  endpoint=${dest.endpoint}` : ''}`;
  // Same reason the mode marker existed: the operator's live config still holds rclone
  // destinations, and `show` is where they will look first when a backup stops
  // happening. An unmarked line here reads as healthy.
  const note = unschedulableDestinationReason(dest)
    ? '  (NOT SCHEDULABLE: rclone path removed)'
    : '';
  return `    ${dest.name}  ${target}  bwlimit=${bwlimit}  enabled=${enabled}${note}`;
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
