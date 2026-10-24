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
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';

/**
 * Why a destination cannot be scheduled, or undefined when it can.
 *
 * `kind` is OPTIONAL on the parameter on purpose: a destination that came from the config loader has been through the schema and always carries one, but a hand-edited entry (and the operator's live config) has no `kind` field at all, and this must name it correctly rather than print "undefined".
 */
export function unschedulableDestinationReason(dest: {
  name: string;
  kind?: string;
}): string | undefined {
  const kind = dest.kind ?? BACKUP_DEFAULTS.DESTINATION_KIND;
  if (kind === BACKUP_DEFAULTS.NEW_DESTINATION_KIND) return undefined;
  return (
    `Backup destination "${dest.name}" has kind "${kind}". The ` +
    'rclone/OneDrive path was removed on 2026-08-15; change it to a ' +
    '`hosted-service` destination so the schedule uses the chunk store.'
  );
}

/**
 * `bandwidthLimit` is an RCLONE-STYLE STRING ('6M'), because that is what the old rclone path took and what the schema still declares. `renet backup snapshot --bwlimit` is an Int64 in BYTES PER SECOND (cmd/renet/backup_snapshot.go:132), so passing the string through unchanged emits `--bwlimit 6M`, which dies at cobra's flag parse, at RUN time, inside a systemd timer.
 *
 * Suffixes follow rclone's convention (binary: 6M = 6 MiB/s). A value that cannot be parsed is REFUSED rather than dropped or passed through: dropping it silently lifts a cap the operator set deliberately.
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

/**
 * Why a strategy cannot be turned into a unit, or undefined when it can.
 *
 * `destinations` defaults to every destination; the scheduler passes the enabled ones, which are the only ones that get a command.
 *
 * `exclude` is REFUSED rather than dropped. `backup snapshot` filters by repeated --repo and has no exclude flag, so honouring an exclude list would mean silently backing up repositories the operator asked to leave out.
 */
export function strategyUnschedulableReason(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[] = strategy.destinations
): string | undefined {
  const cron = invalidCronReason(strategy.schedule);
  if (cron) return cron;
  for (const dest of destinations) {
    const reason = unschedulableDestinationReason(dest);
    if (reason) return `${reason} Refusing to generate a unit that would back up nothing.`;
  }
  if (strategy.exclude?.length) {
    return (
      'This backup strategy sets exclude, which a hosted-service destination ' +
      'cannot express: `backup snapshot` selects ' +
      'repositories with --repo and has no exclude flag. List the repositories ' +
      'to back up with include instead, so the scheduled scope is explicit.'
    );
  }
  try {
    bandwidthToBytesPerSecond(strategy.bandwidthLimit);
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
  return undefined;
}

/** Throwing form for the schedule path. */
export function assertStrategySchedulable(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[] = strategy.destinations
): void {
  const reason = strategyUnschedulableReason(strategy, destinations);
  if (reason) throw new Error(reason);
}
