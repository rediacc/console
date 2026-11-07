import { formatDuration } from '@rediacc/shared/backup/duration';
import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import {
  type ReplicationSyncResult,
  registerStrategyReplication,
  removeReplicationRulesFor,
  replicateDestinations,
} from '../services/backup/backup-replication.js';
import {
  type CronCadence,
  hasAccountToken,
  pushStrategyRetention,
  retentionCronMismatches,
} from '../services/backup/backup-retention.js';
import {
  defaultKeepWithin,
  defaultRpoDeps,
  planRpoChange,
  type RpoDeps,
} from '../services/backup/backup-rpo-plan.js';
import {
  cronFloorReason,
  strategyUnschedulableReason,
  uncheckedTargets,
} from '../services/backup/backup-strategy-validate.js';
import { configService } from '../services/config/config-resources.js';
import {
  bindBackupStrategy,
  machinesBoundToStrategy,
  removeStrategyChecked,
  unbindBackupStrategy,
} from '../services/config/config-strategy-binding.js';
import { outputService } from '../services/core/output.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import {
  buildStrategyUpdate,
  resolveEnabledFlag,
  upsertBackupDestination,
} from './backup-strategy-options.js';

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
export async function assertStrategyBindable(strategyName: string): Promise<string[]> {
  const strategy = await configService.getBackupStrategy(strategyName);
  if (!strategy) return [];
  const enabled = strategy.destinations.filter((d) => d.enabled !== false);
  const reason = strategyUnschedulableReason(strategy, enabled);
  if (reason) {
    throw new ValidationError(
      `Strategy "${strategyName}" cannot be scheduled, not bound. ${reason}`
    );
  }
  // No store list client exists in the CLI, so registration is not checked offline; the caller says so.
  return uncheckedTargets(enabled, undefined);
}

export async function applyBackupStrategyOptions(
  name: string,
  options: {
    destination?: string;
    target?: string;
    replicateFrom?: string;
    cron?: string;
    mode?: string;
    bwlimit?: string;
    readBwlimit?: string;
    cpuLimit?: string;
    include?: string;
    exclude?: string;
    retention?: string;
    rpo?: string;
    repoRpo?: string[];
    repoCellSize?: string[];
    /** `--no-estimate` makes this false; undefined and true both estimate. */
    estimate?: boolean;
    dryRun?: boolean;
    enable?: boolean;
    disable?: boolean;
  },
  deps: RpoDeps = defaultRpoDeps
): Promise<RetentionFill | undefined> {
  const enabled = resolveEnabledFlag(options.enable, options.disable);
  const targetsDestination = Boolean(options.destination);
  if (!targetsDestination && options.target !== undefined) {
    throw new ValidationError(t('commands.backup.strategy.set.targetNeedsDestination'));
  }
  if (!targetsDestination && options.replicateFrom !== undefined) {
    throw new ValidationError(t('commands.backup.strategy.set.replicateFromNeedsDestination'));
  }
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

  // A cron under the 5-minute floor is refused where it is typed, not when the unit is rendered.
  if (options.cron !== undefined) {
    const floor = cronFloorReason(options.cron, 'Schedule');
    if (floor) throw new ValidationError(floor);
  }
  const fill = await applyTargetOptions(name, options, update, deps);
  if (options.dryRun) return undefined;

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
      target: options.target,
      replicateFrom: options.replicateFrom,
    });
    if (enabled !== undefined || options.replicateFrom !== undefined) {
      await syncReplicationRules(name);
    }
  }

  // Warn after the write, from the stored result: `--cron` alone can invalidate a retention set earlier.
  if (options.retention !== undefined || options.cron !== undefined) {
    await warnRetentionCronMismatch(name);
  }
  return fill;
}

/** A retention filled in because a target was declared with none, so the caller pushes it like an explicit one. */
interface RetentionFill {
  seconds: number;
}

/**
 * The target options of one `strategy set`: fold them into `update`, gate them on the churn estimate,
 * fill the default window, and report. Throws before anything is written. A dry run goes through all
 * of it, estimate included, and the caller stops short of the write.
 */
async function applyTargetOptions(
  name: string,
  options: {
    rpo?: string;
    repoRpo?: string[];
    repoCellSize?: string[];
    estimate?: boolean;
    dryRun?: boolean;
    retention?: string;
  },
  update: Partial<BackupStrategyConfig>,
  deps: RpoDeps
): Promise<RetentionFill | undefined> {
  const stored = await configService.getBackupStrategy(name);
  const change = planRpoChange(stored, options);
  if (change.asks.length === 0 && change.summary.length === 0) return undefined;
  Object.assign(update, change.update);

  if (change.asks.length > 0 && options.estimate !== false) {
    const report = await deps.estimate(change.asks);
    if (!report) {
      const refs = change.asks.map((a) => a.ref ?? name).join(', ');
      throw new ValidationError(t('commands.backup.strategy.set.noMeasurement', { refs }));
    }
    for (const line of report.lines) outputService.info(line);
  }
  for (const { ref, size } of change.reseeds) {
    outputService.warn(t('commands.backup.strategy.set.reseedWarning', { ref, size }));
  }

  let fill: RetentionFill | undefined;
  if (change.asks.length > 0 && !stored?.retention && options.retention === undefined) {
    fill = await fillDefaultWindow(name, update, deps);
  }
  if (options.dryRun) {
    outputService.info(
      t('commands.backup.strategy.set.dryRun', {
        strategy: name,
        changes: change.summary.join('; '),
      })
    );
  }
  return fill;
}

/** No retention is declared and a target is: keep every snapshot within the plan's default window, and say so. */
async function fillDefaultWindow(
  name: string,
  update: Partial<BackupStrategyConfig>,
  deps: RpoDeps
): Promise<RetentionFill | undefined> {
  const window = defaultKeepWithin(await deps.planCode());
  if (window.kind === 'window') {
    update.retention = { keepWithinSeconds: window.seconds };
    outputService.info(
      t('commands.backup.strategy.set.retentionDefaulted', {
        strategy: name,
        window: formatDuration(window.seconds),
        plan: window.plan,
      })
    );
    return { seconds: window.seconds };
  }
  outputService.warn(
    window.kind === 'no-storage'
      ? t('commands.backup.strategy.set.retentionDefaultNoStorage', { plan: window.plan })
      : t('commands.backup.strategy.set.retentionDefaultNoPlan')
  );
  return undefined;
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
    // A 4xx is the server's verdict on this retention (plan limits, bad values): retrying cannot help, so it fails the command with the server's message. A 408 or 429 is not a verdict, a later run succeeds, so it warns like every other failure (an unreachable server, a 5xx, or a local error with no HTTP status).
    const status = (error as { status?: unknown } | null)?.status;
    const transient = status === 408 || status === 429;
    if (typeof status === 'number' && status >= 400 && status < 500 && !transient) throw error;
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

function formatRetention(retention: NonNullable<BackupStrategyConfig['retention']>): string {
  const parts: [string, number | undefined][] = [
    ['last', retention.keepLast],
    ['within', retention.keepWithinSeconds],
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

/** One destination as a cell: its name, with a marker when it is switched off. */
function destinationCell(dest: BackupStrategyDestination): string {
  return dest.enabled === false ? `${dest.name} (disabled)` : dest.name;
}

/** One strategy as a row of `show`: the same fields in every format, so a script and a person read one document. */
function strategyRow(name: string, strategy: BackupStrategyConfig): Record<string, unknown> {
  return {
    name,
    schedule: strategy.schedule,
    mode: strategy.mode ?? BACKUP_DEFAULTS.MODE,
    enabled: strategy.enabled !== false,
    bandwidthLimit: strategy.bandwidthLimit ?? '-',
    readBandwidthLimit: strategy.readBandwidthLimit ?? '-',
    cpuLimit: strategy.cpuLimit ?? '-',
    include: strategy.include?.join(',') ?? '-',
    exclude: strategy.exclude?.join(',') ?? '-',
    retention: strategy.retention ? formatRetention(strategy.retention) : '-',
    destinations: strategy.destinations.map(destinationCell).join(', ') || '-',
  };
}

/** Commander accumulator for a repeatable option. */
function collectRepeated(value: string, previous: string[]): string[] {
  return [...previous, value];
}

/** Say what a replication-rule sync did. Never throws: the config change it follows has already been written. */
function reportReplication(result: ReplicationSyncResult, verb: 'registered' | 'removed'): void {
  if (result.unsupported) {
    outputService.warn(t('commands.backup.strategy.replication.unsupported'));
    return;
  }
  if (result.done > 0) {
    outputService.info(t(`commands.backup.strategy.replication.${verb}`, { count: result.done }));
  }
  for (const failure of result.failures) {
    outputService.warn(
      t('commands.backup.strategy.replication.failed', {
        lineage: failure.lineageGuid,
        target: failure.target,
        reason: failure.reason,
      })
    );
  }
}

/** Run a rule sync when the strategy has replicate destinations and an account token exists to authenticate it. */
async function withReplication(
  strategy: Pick<BackupStrategyConfig, 'include' | 'exclude' | 'destinations'> | undefined,
  run: (
    strategy: Pick<BackupStrategyConfig, 'include' | 'exclude' | 'destinations'>
  ) => Promise<void>
): Promise<void> {
  if (!strategy || replicateDestinations(strategy, false).length === 0) return;
  if (!hasAccountToken()) {
    outputService.warn(t('commands.backup.strategy.replication.notPushed'));
    return;
  }
  try {
    await run(strategy);
  } catch (error) {
    outputService.warn(
      t('commands.backup.strategy.replication.syncFailed', {
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * Bring the server's rules in line with one strategy's replicate destinations after a destination changed: a disabled
 * one loses its rules, an enabled one is registered for every machine the strategy is bound to.
 */
async function syncReplicationRules(name: string): Promise<void> {
  const strategy = await configService.getBackupStrategy(name);
  await withReplication(strategy, async (found) => {
    const disabled = replicateDestinations(found, false).filter((d) => d.enabled === false);
    reportReplication(await removeReplicationRulesFor(found, disabled), 'removed');
    for (const machine of await machinesBoundToStrategy(name)) {
      reportReplication(await registerStrategyReplication(found, machine), 'registered');
    }
  });
}

/** Drop every replicate destination's rules for the lineages a strategy covers on one machine (an unbind). */
async function dropReplicationForMachine(
  strategy: BackupStrategyConfig | undefined,
  machine: string
): Promise<void> {
  await withReplication(strategy, async (found) => {
    const all = replicateDestinations(found, false);
    reportReplication(await removeReplicationRulesFor(found, all, machine), 'removed');
  });
}

/** Register the `backup strategy` subgroup (named backup strategy records). */
export function registerBackupStrategyCommands(backup: Command): void {
  const group = backup.command('strategy').description(t('commands.backup.strategy.description'));

  group
    .command('set')
    .argument('<strategy>', t('options.strategyName'))
    .description(t('commands.backup.strategy.set.description'))
    .option('--destination <name>', t('commands.backup.strategy.set.optionDestination'))
    .option('--target <storeId>', t('commands.backup.strategy.set.optionTarget'))
    .option('--replicate-from <storeId>', t('commands.backup.strategy.set.optionReplicateFrom'))
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
    .option('--rpo <duration>', t('commands.backup.strategy.set.optionRpo'))
    .option(
      '--repo-rpo <ref=duration>',
      t('commands.backup.strategy.set.optionRepoRpo'),
      collectRepeated,
      []
    )
    .option(
      '--repo-cell-size <ref=size>',
      t('commands.backup.strategy.set.optionRepoCellSize'),
      collectRepeated,
      []
    )
    .option('--no-estimate', t('commands.backup.strategy.set.optionNoEstimate'))
    .option('--dry-run', t('commands.backup.strategy.set.optionDryRun'))
    .option('--enable', t('commands.backup.strategy.set.optionEnable'))
    .option('--disable', t('commands.backup.strategy.set.optionDisable'))
    .action(async (strategy: string, options) => {
      try {
        const fill = await applyBackupStrategyOptions(strategy, options);
        if (options.dryRun) return;
        outputService.success(t('commands.backup.strategy.set.saved'));
        if (options.retention !== undefined || fill) await applyRetentionNow(strategy);
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
        const unchecked = await assertStrategyBindable(strategy);
        if (unchecked.length > 0) {
          outputService.info(
            t('commands.backup.strategy.bind.uncheckedTargets', { targets: unchecked.join(', ') })
          );
        }
        const bound = await bindBackupStrategy(options.machine, strategy);
        // The bind is written; a rule that cannot be registered is a warning, and a later `bind` or `set` retries it.
        await withReplication(await configService.getBackupStrategy(strategy), async (found) => {
          reportReplication(
            await registerStrategyReplication(found, options.machine),
            'registered'
          );
        });
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
        const stored = await configService.getBackupStrategy(strategy);
        const removed = await unbindBackupStrategy(options.machine, strategy);
        if (removed) await dropReplicationForMachine(stored, options.machine);
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
          const stored = await configService.getBackupStrategy(strategy);
          const gone = stored?.destinations.filter((d) => d.name === options.destination);
          await configService.removeBackupDestination(strategy, options.destination);
          if (stored && gone && gone.length > 0) {
            await withReplication({ ...stored, destinations: gone }, async (found) => {
              reportReplication(
                await removeReplicationRulesFor(found, replicateDestinations(found, false)),
                'removed'
              );
            });
          }
        } else {
          const stored = await configService.getBackupStrategy(strategy);
          const unbound = await removeStrategyChecked(strategy, options.unbind === true);
          for (const machine of unbound) await dropReplicationForMachine(stored, machine);
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
        // A strategy is only ever deployed to machines that bind it, so a listing without bindings cannot answer "why did this not run?".
        const boundTo = await strategyBindings();
        const rows = names.map((name) => {
          const s = strategies[name];
          const machines = boundTo.get(name);
          return {
            name,
            schedule: s.schedule,
            mode: s.mode ?? BACKUP_DEFAULTS.MODE,
            destinations: s.destinations.length,
            enabled: s.enabled !== false,
            machines: machines?.length ? machines.join(',') : '-',
          };
        });
        // Rows go to stdout in every format (an empty list is `[]` under -o json); the notice is prose on stderr.
        outputService.print(rows, getOutputFormat());
        if (rows.length === 0) outputService.info(t('commands.backup.strategy.show.notConfigured'));
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
            throw new ValidationError(
              t('commands.backup.strategy.show.notFound', { name: strategy })
            );
          }
          outputService.print([strategyRow(strategy, found)], getOutputFormat());
          return;
        }
        const strategies = await configService.listBackupStrategies();
        const rows = Object.entries(strategies).map(([name, s]) => strategyRow(name, s));
        outputService.print(rows, getOutputFormat());
        if (rows.length === 0) outputService.info(t('commands.backup.strategy.show.notConfigured'));
      } catch (error) {
        handleError(error);
      }
    });
}
