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
import { t } from '../../i18n/index.js';
import type { BackupStrategyDestination } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
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
 * `bandwidthLimit` is a rate string, and `renet backup snapshot --bwlimit` is emitted in BYTES PER SECOND, so the unit and the function never depend on renet re-parsing a suffix.
 *
 * The grammar is renet's `pkg/bwrate` table, with the same test vectors on both sides:
 * - a bare number (optionally `B` or `B/s`) is bytes/second;
 * - `K`, `M`, `G`, `T` (optionally `B`, `B/s`) are DECIMAL bytes: 12.5M = 12,500,000 B/s;
 * - `Ki`, `Mi`, `Gi`, `Ti` (optionally `B`, `B/s`) are binary bytes: 6Mi = 6 MiB/s;
 * - `bit`, `bps`, `bit/s` after a decimal prefix are BITS: 100Mbps = 12,500,000 B/s.
 *
 * `100Mb` is refused: megabits by convention, megabytes by habit, and either guess is an 8x error. A value that cannot be parsed is REFUSED rather than dropped or passed through: dropping it silently lifts a cap the operator set deliberately. `0` means unlimited and returns undefined.
 */
export function bandwidthToBytesPerSecond(limit: string | undefined): number | undefined {
  if (!limit?.trim()) return undefined;
  const parsed = parseRate(limit.trim());
  if (typeof parsed === 'string') {
    // Refused rather than dropped: dropping would silently remove a cap the operator set.
    throw new ValidationError(
      t('commands.backup.strategy.bandwidthUnconvertible', { value: limit, reason: parsed })
    );
  }
  return parsed === 0 ? undefined : parsed;
}

/**
 * The read cap of a strategy, in bytes/second, or undefined when the strategy sets none. Unlike the upload cap, a literal zero is KEPT (returned as 0): it means "unlimited read" and must reach the unit as `--read-bwlimit 0`, because dropping it would reapply the verb's gentle default and silently undo what the operator asked for. An unparseable value throws.
 */
export function readCapBytesPerSecond(limit: string | undefined): number | undefined {
  if (!limit?.trim()) return undefined;
  const parsed = parseRate(limit.trim());
  if (typeof parsed === 'string') {
    throw new ValidationError(
      t('commands.backup.strategy.readBandwidthUnconvertible', { value: limit, reason: parsed })
    );
  }
  return parsed;
}

const DECIMAL_SCALE: Record<string, number> = { '': 1, k: 1e3, m: 1e6, g: 1e9, t: 1e12 };
const BINARY_SCALE: Record<string, number> = { k: 2 ** 10, m: 2 ** 20, g: 2 ** 30, t: 2 ** 40 };

/** Why a binary (`i`) unit is unusable, or undefined when it is fine. */
function binaryUnitProblem(prefix: string, bits: boolean): string | undefined {
  if (!prefix) return 'a binary unit needs a prefix';
  if (bits) return 'bit rates are decimal';
  return undefined;
}

/** Bytes/second for a trimmed rate string, or the reason it is refused. */
function parseRate(limit: string): number | string {
  const m = /^(\d+(?:\.\d+)?)\s*([KMGTkmgt]?)(i?)(B|B\/s|bit|bits|bit\/s|bps)?$/.exec(limit);
  if (!m) return 'unknown unit';
  const value = Number(m[1]);
  const prefix = m[2].toLowerCase();
  const binary = m[3] === 'i';
  // .at(4) rather than m[4]: the group is OPTIONAL, and this repo does not set noUncheckedIndexedAccess, so m[4] is typed as always-present. .at() returns string | undefined, which is the truth.
  const unit = m.at(4) ?? '';
  const bits = unit.startsWith('bit') || unit === 'bps';
  const unitProblem = binary ? binaryUnitProblem(prefix, bits) : undefined;
  if (unitProblem) return unitProblem;
  const scale = binary ? BINARY_SCALE[prefix] : DECIMAL_SCALE[prefix];
  const rounded = Math.round((value * scale) / (bits ? 8 : 1));
  if (rounded === 0 && value > 0) return 'it rounds to zero bytes/second';
  return rounded;
}

/**
 * Concurrent chunk uploads a scheduled or strategy run uses: modest, so a capped upload is a steady trickle rather than a fan of connections each waiting its turn (operator order 2026-10-29). renet's own default is 4.
 */
export const STRATEGY_UPLOAD_PARALLELISM = 2;

/** The ceiling a snapshot runs under when nothing says otherwise: half of all cores (operator order 2026-10-29). Mirrors renet's defaultCPULimitPercent. */
export const DEFAULT_CPU_LIMIT_PERCENT = 50;

/**
 * Parse a CPU ceiling: an integer percent of ALL cores, 1 to 100 (100 = no ceiling). Anything else throws ValidationError, so a typo is refused where it is typed (before SSH, at `strategy set`, at unit generation) and never reaches renet or a unit as a different number.
 */
export function parseCpuLimitPercent(raw: string | number): number {
  const text = String(raw).trim();
  const n = Number(text);
  if (text === '' || !Number.isInteger(n) || n < 1 || n > 100) {
    throw new ValidationError(
      t('commands.backup.snapshot.cpuLimitInvalid', { value: String(raw) })
    );
  }
  return n;
}

/** The systemd `CPUQuota=` value for a ceiling on a machine with `cpuCount` cores (one core is 100%), or undefined for 100, which asks for no ceiling. */
export function cpuQuotaValue(limitPercent: number, cpuCount: number): string | undefined {
  if (limitPercent >= 100) return undefined;
  return `${limitPercent * cpuCount}%`;
}

/**
 * The cap one strategy run uploads at, in bytes/second, or undefined for none.
 *
 * Every cap that is set binds, the strategy's and each destination's, and one run is ONE upload whatever the number of destinations, so the tightest cap of them all wins: a looser destination cap never lifts the strategy's. Before this the run read only the strategy-level field, so `backup strategy set s --destination d --bwlimit 6M` stored a cap no unit ever applied.
 */
export function effectiveBandwidthLimit(
  strategy: { bandwidthLimit?: string },
  destinations: { bandwidthLimit?: string }[]
): number | undefined {
  // Every cap that is set binds: the strategy's and each destination's. A looser destination cap
  // never lifts the strategy's, and the run takes the tightest of them all.
  const caps = [strategy.bandwidthLimit, ...destinations.map((d) => d.bandwidthLimit)]
    .map((v) => bandwidthToBytesPerSecond(v))
    .filter((v): v is number => v !== undefined);
  return caps.length > 0 ? Math.min(...caps) : undefined;
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
    effectiveBandwidthLimit(strategy, destinations);
    // A typo in the read cap must refuse the unit, never reach it as an unlimited read.
    readCapBytesPerSecond(strategy.readBandwidthLimit);
    // An out-of-range ceiling (a hand-edited config) refuses the unit rather than becoming a different quota.
    if (strategy.cpuLimit !== undefined) parseCpuLimitPercent(strategy.cpuLimit);
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
