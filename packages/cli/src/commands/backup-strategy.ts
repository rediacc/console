import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import {
  type CronCadence,
  hasAccountToken,
  parseRetentionSpec,
  pushStrategyRetention,
  RetentionSpecError,
  retentionCronMismatches,
} from '../services/backup/backup-retention.js';
import {
  bandwidthToBytesPerSecond,
  parseCpuLimitPercent,
  readCapBytesPerSecond,
  strategyUnschedulableReason,
} from '../services/backup/backup-strategy-validate.js';
import { configService } from '../services/config/config-resources.js';
import {
  bindBackupStrategy,
  removeStrategyChecked,
  unbindBackupStrategy,
} from '../services/config/config-strategy-binding.js';
import { outputService } from '../services/core/output.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';
import { BackupDestinationSchema, parseConfig } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';

function resolveEnabledFlag(enable?: boolean, disable?: boolean): boolean | undefined {
  if (enable) return true;
  if (disable) return false;
  return undefined;
}

interface UpsertDestOpts {
  strategyName: string;
  destinationName: string;
  enabled?: boolean;
  bwlimit?: string;
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
 * Build the destination record to store, from the flags. Pure: no config reads,
 * no writes, so a test can drive the exact object the operator's flags produce
 * and hand it straight to the unit generator. Every destination is the chunk
 * store (`hosted-service`); the stored `endpoint` and `vaultContent` of an
 * existing destination are kept by the merge in `addBackupDestination`.
 */
export function buildDestination(
  o: Omit<UpsertDestOpts, 'strategyName'>
): BackupStrategyDestination {
  return parseConfig(
    BackupDestinationSchema,
    definedOnly({
      kind: BACKUP_DEFAULTS.NEW_DESTINATION_KIND,
      name: o.destinationName,
      enabled: o.enabled,
      bandwidthLimit: o.bwlimit,
    }),
    'backup destination'
  );
}

async function upsertBackupDestination(o: UpsertDestOpts): Promise<void> {
  await configService.addBackupDestination(o.strategyName, buildDestination(o));
}

// parseRepoFilter turns a comma-separated --include/--exclude value into a repo list, or returns undefined to CLEAR the filter. An empty string or the literal "none" (and a value that is only separators/whitespace) clears it, that's how you drop a strategy's include/exclude entirely (e.g. make a cold backup cover
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

/** `--retention` to the stored policy; `none` or an empty value clears it. */
export function parseRetentionOption(raw: string): BackupStrategyConfig['retention'] {
  try {
    return parseRetentionSpec(raw);
  } catch (error) {
    if (error instanceof RetentionSpecError) {
      throw new ValidationError(t('commands.backup.strategy.set.retentionInvalid', { value: raw }));
    }
    throw error;
  }
}

export function buildStrategyUpdate(
  opts: {
    cron?: string;
    mode?: string;
    bwlimit?: string;
    readBwlimit?: string;
    cpuLimit?: string;
    include?: string;
    exclude?: string;
    retention?: string;
  },
  enabled: boolean | undefined
): Partial<BackupStrategyConfig> {
  const u: Partial<BackupStrategyConfig> = {};
  if (opts.retention !== undefined) u.retention = parseRetentionOption(opts.retention);
  if (opts.cron !== undefined) u.schedule = opts.cron;
  if (opts.mode !== undefined) {
    // `--mode cold` used to be refused here, because the scheduled verb could only take a hot snapshot and accepting the flag would have promised a quiesce that never happened. `backup snapshot --cold` exists now, so both modes schedule and there is nothing left to refuse: the schema's
    // enum is exactly hot|cold, so any other value fails at config load.
    u.mode = opts.mode as 'hot' | 'cold';
  }
  if (enabled !== undefined) u.enabled = enabled;
  // Both caps are validated here, at set time: an unparseable value stored now would only surface later as an unschedulable strategy.
  if (opts.bwlimit !== undefined) {
    if (opts.bwlimit.trim() === '') {
      throw new ValidationError(
        t('commands.backup.snapshot.bwlimitInvalid', { value: opts.bwlimit })
      );
    }
    bandwidthToBytesPerSecond(opts.bwlimit);
    u.bandwidthLimit = opts.bwlimit;
  }
  // `none` clears the read cap, so the verb default applies again.
  if (opts.readBwlimit !== undefined) {
    const raw = opts.readBwlimit.trim();
    if (raw.toLowerCase() === 'none') {
      u.readBandwidthLimit = undefined;
    } else {
      if (raw === '') {
        throw new ValidationError(
          t('commands.backup.snapshot.readBwlimitInvalid', { value: opts.readBwlimit })
        );
      }
      readCapBytesPerSecond(raw);
      u.readBandwidthLimit = opts.readBwlimit;
    }
  }
  // `none` clears the ceiling, so the verb default (50 percent of all cores) applies again.
  if (opts.cpuLimit !== undefined) {
    u.cpuLimit =
      opts.cpuLimit.trim().toLowerCase() === 'none'
        ? undefined
        : parseCpuLimitPercent(opts.cpuLimit);
  }
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

/**
 * Refuse repo names the active config does not know. A typo in --include would otherwise schedule a backup of nothing (or, for exclude, of everything), and surface only as a missing snapshot. Every unknown name is reported at once, and the check runs before anything is written.
 */
async function assertKnownRepoNames(names: string[] | undefined): Promise<void> {
  const unknown: string[] = [];
  for (const name of names ?? []) {
    if (!(await configService.getRepository(name))) unknown.push(name);
  }
  if (unknown.length > 0) {
    throw new ValidationError(
      `Unknown repository ${unknown.length === 1 ? 'name' : 'names'}: ${unknown.map((n) => `"${n}"`).join(', ')}. Names must match repositories in the active config (rdc repo list).`
    );
  }
}

/**
 * Refuse to bind a strategy `backup schedule` could not turn into a unit, through the same rules schedule applies (strategyUnschedulableReason). Disabled destinations are skipped, as the scheduler skips them.
 */
export async function assertStrategyBindable(strategyName: string): Promise<void> {
  const strategy = await configService.getBackupStrategy(strategyName);
  if (!strategy) return;
  const reason = strategyUnschedulableReason(
    strategy,
    strategy.destinations.filter((d) => d.enabled !== false)
  );
  if (reason) {
    throw new ValidationError(
      `Strategy "${strategyName}" cannot be scheduled, not bound. ${reason}`
    );
  }
}

export async function applyBackupStrategyOptions(
  name: string,
  options: {
    destination?: string;
    cron?: string;
    mode?: string;
    bwlimit?: string;
    readBwlimit?: string;
    cpuLimit?: string;
    include?: string;
    exclude?: string;
    retention?: string;
    enable?: boolean;
    disable?: boolean;
  }
): Promise<void> {
  const enabled = resolveEnabledFlag(options.enable, options.disable);
  const targetsDestination = Boolean(options.destination);
  if (targetsDestination && options.readBwlimit !== undefined) {
    throw new ValidationError(t('commands.backup.strategy.set.readBwlimitStrategyOnly'));
  }

  if (targetsDestination && options.cpuLimit !== undefined) {
    throw new ValidationError(t('commands.backup.strategy.set.cpuLimitStrategyOnly'));
  }

  // Strategy fields and destination fields are applied in the SAME call. This used to be an either/or, so creating a strategy with a destination took two invocations, and the first one, `set <new> --destination …`, silently produced a strategy with an empty schedule.
  //
  // `--bwlimit` and `--enable/--disable` stay scoped to the destination when one is named, which is what they have always meant there: `set s --destination d --disable` disables that destination, not the whole strategy.
  const update = buildStrategyUpdate(
    { ...options, bwlimit: targetsDestination ? undefined : options.bwlimit },
    targetsDestination ? undefined : enabled
  );

  await assertKnownRepoNames(update.include);
  await assertKnownRepoNames(update.exclude);

  // Order matters: upsertBackupDestination reads the stored strategy to merge destination defaults, so the strategy has to exist before the destination is attached. These cannot run in parallel.
  if (!targetsDestination || Object.keys(update).length > 0) {
    await configService.setBackupStrategy(name, update);
  }

  if (options.destination) {
    await upsertBackupDestination({
      strategyName: name,
      destinationName: options.destination,
      enabled,
      bwlimit: options.bwlimit,
    });
  }

  // Warn after the write, from the stored result: `--cron` alone can invalidate a retention set earlier.
  if (options.retention !== undefined || options.cron !== undefined) {
    await warnRetentionCronMismatch(name);
  }
}

function cadenceLabel(cadence: CronCadence): string {
  switch (cadence) {
    case 'weekly':
      return t('commands.backup.strategy.set.cadence.weekly');
    case 'monthly':
      return t('commands.backup.strategy.set.cadence.monthly');
    default:
      return t('commands.backup.strategy.set.cadence.daily');
  }
}

/** F7: a retention knob the strategy's cron can never fill is saved but called out. */
async function warnRetentionCronMismatch(name: string): Promise<void> {
  const strategy = await configService.getBackupStrategy(name);
  if (!strategy?.schedule) return;
  for (const { knob, cadence } of retentionCronMismatches(strategy.retention, strategy.schedule)) {
    outputService.warn(
      t('commands.backup.strategy.set.retentionCronMismatch', {
        strategy: name,
        knob,
        cron: strategy.schedule,
        cadence: cadenceLabel(cadence),
      })
    );
  }
}

/**
 * Apply a just-saved strategy retention to the lineages the strategy covers. The config write has
 * already happened, so a server that cannot be reached is a warning, not a failed command.
 */
async function applyRetentionNow(name: string): Promise<void> {
  const strategy = await configService.getBackupStrategy(name);
  if (!strategy?.retention) return;
  if (!hasAccountToken()) {
    outputService.warn(t('commands.backup.strategy.set.retentionNotPushed', { strategy: name }));
    return;
  }
  try {
    const { pushed } = await pushStrategyRetention(strategy, { overwrite: true });
    outputService.info(t('commands.backup.strategy.set.retentionPushed', { count: pushed }));
  } catch (error) {
    // A 4xx is the server's verdict on this retention (plan limits, bad values): retrying cannot help, so it fails the command with the server's message. Only an unreachable server or a 5xx is a warning.
    const status = (error as { status?: unknown } | null)?.status;
    if (typeof status === 'number' && status >= 400 && status < 500) throw error;
    outputService.warn(
      t('commands.backup.strategy.set.retentionPushFailed', {
        strategy: name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
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
  if (strategy.readBandwidthLimit) {
    outputService.info(`  Read bandwidth limit: ${strategy.readBandwidthLimit}`);
  }
  if (strategy.cpuLimit !== undefined) {
    outputService.info(`  CPU limit: ${strategy.cpuLimit}% of all cores`);
  }
  if (strategy.include) outputService.info(`  Include: ${strategy.include.join(', ')}`);
  if (strategy.exclude) outputService.info(`  Exclude: ${strategy.exclude.join(', ')}`);
  if (strategy.retention) {
    outputService.info(`  Retention: ${formatRetention(strategy.retention)}`);
  }
  displayStrategyDestinations(strategy);
}

function formatRetention(retention: NonNullable<BackupStrategyConfig['retention']>): string {
  const parts: [string, number | undefined][] = [
    ['last', retention.keepLast],
    ['hourly', retention.keepHourly],
    ['daily', retention.keepDaily],
    ['weekly', retention.keepWeekly],
    ['monthly', retention.keepMonthly],
    ['yearly', retention.keepYearly],
  ];
  return parts
    .filter(([, n]) => n !== undefined)
    .map(([name, n]) => `${name}=${n}`)
    .join(',');
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
  const target = `hosted-service${dest.endpoint ? `  endpoint=${dest.endpoint}` : ''}`;
  return `    ${dest.name}  ${target}  bwlimit=${bwlimit}  enabled=${enabled}`;
}

/** Register the `backup strategy` subgroup (named backup strategy records). */
export function registerBackupStrategyCommands(backup: Command): void {
  const group = backup.command('strategy').description(t('commands.backup.strategy.description'));

  group
    .command('set')
    .argument('<strategy>', t('options.strategyName'))
    .description(t('commands.backup.strategy.set.description'))
    .option('--destination <name>', t('commands.backup.strategy.set.optionDestination'))
    .option('--cron <expression>', t('commands.backup.strategy.set.optionCron'))
    .addOption(
      new Option('--mode <mode>', t('commands.backup.strategy.set.optionMode')).choices([
        'hot',
        'cold',
      ])
    )
    .option('--bwlimit <limit>', t('commands.backup.strategy.set.optionBwlimit'))
    .option('--read-bwlimit <limit>', t('commands.backup.strategy.set.optionReadBwlimit'))
    .option('--cpu-limit <percent>', t('commands.backup.strategy.set.optionCpuLimit'))
    .option('--include <repos>', t('commands.backup.strategy.set.optionInclude'))
    .option('--exclude <repos>', t('commands.backup.strategy.set.optionExclude'))
    .option('--retention <spec>', t('commands.backup.strategy.set.optionRetention'))
    .option('--enable', t('commands.backup.strategy.set.optionEnable'))
    .option('--disable', t('commands.backup.strategy.set.optionDisable'))
    .action(async (strategy: string, options) => {
      try {
        await applyBackupStrategyOptions(strategy, options);
        outputService.success(t('commands.backup.strategy.set.saved'));
        if (options.retention !== undefined) await applyRetentionNow(strategy);
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
        await assertStrategyBindable(strategy);
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
    // --unbind applies to removing the whole strategy; with --destination it would be silently ignored.
    .addOption(
      new Option('--unbind', t('commands.backup.strategy.remove.optionUnbind')).conflicts(
        'destination'
      )
    )
    .action(async (strategy: string, options) => {
      try {
        if (options.destination) {
          await configService.removeBackupDestination(strategy, options.destination);
        } else {
          const unbound = await removeStrategyChecked(strategy, options.unbind === true);
          if (unbound.length > 0) {
            outputService.warn(
              t('commands.backup.strategy.remove.unboundWarn', {
                strategy,
                machines: unbound.join(', '),
              })
            );
          }
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
        // A strategy is only ever deployed to machines that bind it, so a listing without bindings cannot answer "why did this not run?".
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
