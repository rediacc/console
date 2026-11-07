/**
 * `backup strategy set` flags to the stored shape: destinations, repo filters, retention and the
 * strategy update. Parsing and validation only; applying the result is in backup-strategy.ts.
 */
import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { parseRetentionSpec, RetentionSpecError } from '../services/backup/backup-retention.js';
import {
  bandwidthToBytesPerSecond,
  parseCpuLimitPercent,
  readCapBytesPerSecond,
} from '../services/backup/backup-strategy-validate.js';
import { configService } from '../services/config/config-resources.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';
import { BackupDestinationSchema, parseConfig } from '../utils/config-schema.js';
import { ValidationError } from '../utils/errors.js';

export function resolveEnabledFlag(enable?: boolean, disable?: boolean): boolean | undefined {
  if (enable) return true;
  if (disable) return false;
  return undefined;
}

interface UpsertDestOpts {
  strategyName: string;
  destinationName: string;
  enabled?: boolean;
  bwlimit?: string;
  /** A registered store id the destination writes to; absent keeps the stored one (or `home`). */
  target?: string;
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
 * store (`hosted-service`); `target` names the registered store it writes to, and an
 * existing destination's stored target is kept by the merge in `addBackupDestination`
 * when the flag is absent.
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
      target: o.target,
    }),
    'backup destination'
  );
}

export async function upsertBackupDestination(o: UpsertDestOpts): Promise<void> {
  await configService.addBackupDestination(o.strategyName, buildDestination(o));
}

// parseRepoFilter turns a comma-separated --include/--exclude value into a repo list, or returns undefined to CLEAR the filter. An empty string or the literal "none" (and a value that is only separators/whitespace) clears it, which is what drops a strategy's include/exclude entirely (e.g. a cold backup covering
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

type StrategyUpdate = Partial<BackupStrategyConfig>;

/** The upload, read and CPU caps. All validated here, at set time: an unparseable value stored now would only surface later as an unschedulable strategy. */
function applyCapOptions(
  u: StrategyUpdate,
  opts: { bwlimit?: string; readBwlimit?: string; cpuLimit?: string }
): void {
  if (opts.bwlimit !== undefined) {
    if (opts.bwlimit.trim() === '') {
      throw new ValidationError(
        t('commands.backup.snapshot.bwlimitInvalid', { value: opts.bwlimit })
      );
    }
    bandwidthToBytesPerSecond(opts.bwlimit);
    u.bandwidthLimit = opts.bwlimit;
  }
  if (opts.readBwlimit !== undefined) applyReadCap(u, opts.readBwlimit);
  // `none` clears the ceiling, so the verb default (50 percent of all cores) applies again.
  if (opts.cpuLimit !== undefined) {
    u.cpuLimit =
      opts.cpuLimit.trim().toLowerCase() === 'none'
        ? undefined
        : parseCpuLimitPercent(opts.cpuLimit);
  }
}

/** `none` clears the read cap, so the verb default applies again. */
function applyReadCap(u: StrategyUpdate, value: string): void {
  const raw = value.trim();
  if (raw.toLowerCase() === 'none') {
    u.readBandwidthLimit = undefined;
    return;
  }
  if (raw === '') {
    throw new ValidationError(t('commands.backup.snapshot.readBwlimitInvalid', { value }));
  }
  readCapBytesPerSecond(raw);
  u.readBandwidthLimit = value;
}

/** include and exclude are mutually exclusive, so setting one clears the other. An empty or "none" value clears the filter entirely. */
function applyRepoFilters(u: StrategyUpdate, opts: { include?: string; exclude?: string }): void {
  if (opts.include !== undefined) {
    u.include = parseRepoFilter(opts.include);
    u.exclude = undefined;
  }
  if (opts.exclude !== undefined) {
    u.exclude = parseRepoFilter(opts.exclude);
    u.include = undefined;
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
): StrategyUpdate {
  const u: StrategyUpdate = {};
  if (opts.retention !== undefined) u.retention = parseRetentionOption(opts.retention);
  if (opts.cron !== undefined) u.schedule = opts.cron;
  if (opts.mode !== undefined) {
    // `--mode cold` used to be refused here, because the scheduled verb could only take a hot snapshot and accepting the flag would have promised a quiesce that never happened. `backup snapshot --cold` exists now, so both modes schedule and there is nothing left to refuse: the schema's
    // enum is exactly hot|cold, so any other value fails at config load.
    u.mode = opts.mode as 'hot' | 'cold';
  }
  if (enabled !== undefined) u.enabled = enabled;
  applyCapOptions(u, opts);
  applyRepoFilters(u, opts);
  return u;
}
