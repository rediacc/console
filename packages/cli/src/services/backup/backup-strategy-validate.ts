/**
 * The ONE rule set for "can this strategy be scheduled".
 *
 * `backup schedule` enforces it when a unit is generated (buildBackupCommands,
 * cronToOnCalendar's caller) and `backup strategy bind` enforces it up front, so
 * a strategy that can never run is refused where the operator decides, not at
 * deploy time. Both paths call strategyUnschedulableReason; a rule added here
 * reaches both.
 */

import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import type { BackupStrategyDestination } from '../../types/index.js';
import type { ScheduledStrategy } from './backup-schedule-targets.js';

/**
 * Why a destination cannot be scheduled, or undefined when it can.
 *
 * `kind` is OPTIONAL on the parameter on purpose: a destination that came from the config loader has been through the schema and always carries one, but a hand-edited entry (and the operator's live config) has no `kind` field at all, and this must name it correctly rather than print "undefined".
 */
function unschedulableDestinationReason(dest: { name: string; kind?: string }): string | undefined {
  // A destination with no kind predates the field, when the only kind was the removed `storage` one.
  const kind = dest.kind ?? BACKUP_DEFAULTS.LEGACY_DESTINATION_KIND;
  if (kind === BACKUP_DEFAULTS.NEW_DESTINATION_KIND) return undefined;
  return (
    `Backup destination "${dest.name}" has kind "${kind}". Only ` +
    '`hosted-service` destinations can be scheduled; change it to one so the ' +
    'schedule uses the chunk store.'
  );
}

/**
 * `bandwidthLimit` is a SUFFIXED SIZE STRING ('6M'), the form the schema declares. `renet backup snapshot --bwlimit` is an Int64 in BYTES PER SECOND (cmd/renet/backup_snapshot.go:132), so passing the string through unchanged emits `--bwlimit 6M`, which dies at cobra's flag parse, at RUN time, inside a systemd timer.
 *
 * Suffixes are binary (6M = 6 MiB/s). A value that cannot be parsed is REFUSED rather than dropped or passed through: dropping it silently lifts a cap the operator set deliberately.
 */
export function bandwidthToBytesPerSecond(limit: string | undefined): number | undefined {
  if (!limit) return undefined;
  const m = /^(\d+(?:\.\d+)?)\s*([KMGTkmgt])?i?[Bb]?$/.exec(limit.trim());
  if (!m) {
    throw new Error(
      `Backup strategy bandwidthLimit "${limit}" is not a size this can convert. ` +
        'Use a plain number of bytes/second, or a suffixed value such as "6M". ' +
        'Refusing rather than dropping it, because dropping would silently remove ' +
        'a cap you set.'
    );
  }
  const scale: Record<string, number> = { k: 1024, m: 1024 ** 2, g: 1024 ** 3, t: 1024 ** 4 };
  // .at(2) rather than m[2]: the group is OPTIONAL, and this repo does not set noUncheckedIndexedAccess, so m[2] is typed as always-present and lint calls the guard redundant. .at() returns string | undefined, which is the truth.
  const unit = m.at(2)?.toLowerCase() ?? '';
  return Math.round(Number(m[1]) * (unit ? scale[unit] : 1));
}

/** Why a cron expression cannot become an OnCalendar line, or undefined when it can. */
export function invalidCronReason(cron: string): string | undefined {
  return cron.trim().split(/\s+/).length === 5
    ? undefined
    : `Invalid cron expression: "${cron}" (expected 5 fields)`;
}

/** The first per-repo cadence override whose cron is not 5 fields. */
function repoScheduleReason(strategy: ScheduledStrategy): string | undefined {
  for (const [ref, repoCron] of Object.entries(strategy.repoSchedules ?? {})) {
    const reason = invalidCronReason(repoCron);
    if (reason) return `Per-repo schedule for "${ref}": ${reason}`;
  }
  return undefined;
}

/** An unusable destination kind, or destinations on more than one endpoint. */
function destinationsReason(destinations: BackupStrategyDestination[]): string | undefined {
  for (const dest of destinations) {
    const reason = unschedulableDestinationReason(dest);
    if (reason) return `${reason} Refusing to generate a unit that would back up nothing.`;
  }
  const endpoints = new Set(destinations.map((d) => d.endpoint ?? ''));
  if (endpoints.size <= 1) return undefined;
  return (
    `This backup strategy has destinations on ${endpoints.size} different endpoints. ` +
    'One run takes one snapshot to one endpoint; split the destinations into one strategy per endpoint.'
  );
}

/**
 * Why a strategy cannot be turned into a unit, or undefined when it can.
 *
 * `destinations` defaults to every destination; the scheduler passes the enabled ones. One strategy run is ONE snapshot, whatever the number of destinations (renet uploads to the account server its licences name), so enabled destinations naming two different endpoints cannot both be honoured and are refused rather than half-served.
 *
 * `exclude` is accepted: the unit generator resolves it to GUIDs and emits `--exclude-repo <guid>`.
 */
export function strategyUnschedulableReason(
  strategy: ScheduledStrategy,
  destinations: BackupStrategyDestination[] = strategy.destinations
): string | undefined {
  const reason =
    invalidCronReason(strategy.schedule) ??
    repoScheduleReason(strategy) ??
    destinationsReason(destinations);
  if (reason) return reason;
  try {
    bandwidthToBytesPerSecond(strategy.bandwidthLimit);
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
  return undefined;
}

/** Throwing form for the schedule path. */
export function assertStrategySchedulable(
  strategy: ScheduledStrategy,
  destinations: BackupStrategyDestination[] = strategy.destinations
): void {
  const reason = strategyUnschedulableReason(strategy, destinations);
  if (reason) throw new Error(reason);
}
