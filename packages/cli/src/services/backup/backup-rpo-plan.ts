/**
 * `backup strategy set --rpo / --repo-rpo / --repo-cell-size`: turning the options into the stored
 * target, and the two seams the verb reaches outside the config through (the churn estimate and the
 * subscription plan).
 *
 * Pure over its inputs apart from the default dependencies, so a test drives the exact record an
 * operator's flags produce.
 */

import {
  formatDuration,
  parseCellSizeBytes,
  parseDurationSeconds,
  rpoProblem,
} from '@rediacc/shared/backup/duration';
import { PLAN_BACKUP_KEEP_WITHIN } from '@rediacc/shared/subscription/constants';
import { t } from '../../i18n/index.js';
import type { BackupStrategyConfig } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';

type RepoTargets = NonNullable<BackupStrategyConfig['repoTargets']>;

/** One target the estimate is asked about: the strategy's own (`ref` undefined) or a repository's. */
export interface RpoTargetAsk {
  ref: string | undefined;
  rpoSeconds: number;
}

/** What the estimate prints: the cost, the waiting total against the cap and the plan's quota, as finished lines. */
export interface RpoEstimateReport {
  lines: string[];
}

/**
 * The outside world of the verb. `estimate` answers undefined when a target has no churn measurement,
 * which the verb refuses unless `--no-estimate` is given. `planCode` answers undefined when the plan
 * cannot be read.
 */
export interface RpoDeps {
  estimate(targets: RpoTargetAsk[]): Promise<RpoEstimateReport | undefined>;
  planCode(): Promise<string | undefined>;
}

/**
 * The production dependencies. The estimate prices the measurement `rdc backup churn` stored for
 * each target (`estimateFromStore`); a target with none is refused without `--no-estimate`.
 */
export const defaultRpoDeps: RpoDeps = {
  estimate: async (asks) => {
    const { estimateFromStore } = await import('./backup-churn-store.js');
    return estimateFromStore(asks, defaultRpoDeps.planCode);
  },
  planCode: async () => {
    try {
      const { fetchSubscriptionLicenseReportOrThrow } = await import('../account/license.js');
      return (await fetchSubscriptionLicenseReportOrThrow())?.planCode;
    } catch {
      return undefined;
    }
  },
};

export interface RpoOptions {
  rpo?: string;
  repoRpo?: string[];
  repoCellSize?: string[];
}

export interface RpoChange {
  /** The fields of the strategy this call changes; `rpo: undefined` is present to clear. */
  update: Partial<BackupStrategyConfig>;
  /** The targets the estimate is asked about: only those this call sets. */
  asks: RpoTargetAsk[];
  /** Refs whose cell size this call changes. */
  reseeds: { ref: string; size: string }[];
  /** A human line per change, for a dry run. */
  summary: string[];
}

function rpoSecondsOf(raw: string, option: string): number {
  const seconds = parseDurationSeconds(raw);
  const problem =
    seconds === undefined ? 'expected a duration such as 15m or 1h' : rpoProblem(seconds);
  if (seconds === undefined || problem) {
    throw new ValidationError(
      t('commands.backup.strategy.set.rpoInvalid', {
        option,
        value: raw,
        reason: problem ?? 'expected a duration such as 15m or 1h',
      })
    );
  }
  return seconds;
}

/** `ref=value` split at the FIRST `=`; a ref holds no `=`. */
function splitPair(raw: string, option: string): [string, string] {
  const at = raw.indexOf('=');
  const ref = raw.slice(0, at).trim();
  const value = raw.slice(at + 1).trim();
  if (at < 1 || ref === '' || value === '') {
    throw new ValidationError(
      t('commands.backup.strategy.set.repoOptionInvalid', { option, value: raw })
    );
  }
  return [ref, value];
}

const isNone = (value: string): boolean => value.toLowerCase() === 'none';

/** The strategy's own `--rpo`: set, or `none` to clear. */
function planStrategyRpo(raw: string | undefined, change: RpoChange): void {
  if (raw === undefined) return;
  if (isNone(raw.trim())) {
    change.update.rpo = undefined;
    change.summary.push('rpo: cleared');
    return;
  }
  const seconds = rpoSecondsOf(raw, '--rpo');
  change.update.rpo = formatDuration(seconds);
  change.asks.push({ ref: undefined, rpoSeconds: seconds });
  change.summary.push(`rpo: ${change.update.rpo}`);
}

/** The `--repo-rpo` entries, applied to `targets`: each sets one repository's target and keeps the rest of its entry, or `none` removes it. */
function planRepoRpo(raws: string[], targets: RepoTargets, change: RpoChange): void {
  for (const raw of raws) {
    const [ref, value] = splitPair(raw, '--repo-rpo');
    if (isNone(value)) {
      delete targets[ref];
      change.summary.push(`${ref}: target removed`);
      continue;
    }
    const seconds = rpoSecondsOf(value, '--repo-rpo');
    targets[ref] = { ...targets[ref], rpo: formatDuration(seconds) };
    change.asks.push({ ref, rpoSeconds: seconds });
    change.summary.push(`${ref}: rpo ${targets[ref].rpo}`);
  }
}

/** The `--repo-cell-size` entries, applied to `targets`. The cell size rides on a repository's own unit, so each needs a target. */
function planRepoCellSize(raws: string[], targets: RepoTargets, change: RpoChange): void {
  for (const raw of raws) {
    const [ref, value] = splitPair(raw, '--repo-cell-size');
    if (!(ref in targets)) {
      throw new ValidationError(t('commands.backup.strategy.set.repoCellSizeNeedsTarget', { ref }));
    }
    if (isNone(value)) {
      const { cellSize: _dropped, ...rest } = targets[ref];
      targets[ref] = rest;
      change.summary.push(`${ref}: cell size cleared`);
      continue;
    }
    if (parseCellSizeBytes(value) === undefined) {
      throw new ValidationError(t('commands.backup.strategy.set.cellSizeInvalid', { value }));
    }
    if (targets[ref].cellSize !== value) change.reseeds.push({ ref, size: value });
    targets[ref] = { ...targets[ref], cellSize: value };
    change.summary.push(`${ref}: cell size ${value}`);
  }
}

/**
 * The stored change for the target options, against the strategy as stored.
 *
 * - `--rpo <d>` sets the strategy's target, `none` clears it.
 * - `--repo-rpo <ref>=<d>` sets one repository's target and keeps the rest of its entry; `none`
 *   removes the entry (the repository returns to the main unit).
 * - `--repo-cell-size <ref>=<size>` needs a target for that ref (stored or in this call), because
 *   the cell size rides on the repository's own unit.
 */
export function planRpoChange(
  existing: Pick<BackupStrategyConfig, 'rpo' | 'repoTargets'> | undefined,
  options: RpoOptions
): RpoChange {
  const change: RpoChange = { update: {}, asks: [], reseeds: [], summary: [] };
  planStrategyRpo(options.rpo, change);
  const targets: RepoTargets = { ...existing?.repoTargets };
  const repoRpo = options.repoRpo ?? [];
  const repoCellSize = options.repoCellSize ?? [];
  planRepoRpo(repoRpo, targets, change);
  planRepoCellSize(repoCellSize, targets, change);
  if (repoRpo.length + repoCellSize.length > 0) {
    change.update.repoTargets = Object.keys(targets).length > 0 ? targets : undefined;
  }
  return change;
}

/** What the plan puts under a declared target when no retention is declared. */
export type DefaultWindow =
  | { kind: 'window'; seconds: number; plan: string }
  | { kind: 'no-storage'; plan: string }
  | { kind: 'unknown-plan' };

/** The default keep-within window of a plan (O3), or why there is none. */
export function defaultKeepWithin(planCode: string | undefined): DefaultWindow {
  if (!planCode || !(planCode in PLAN_BACKUP_KEEP_WITHIN)) return { kind: 'unknown-plan' };
  const seconds =
    PLAN_BACKUP_KEEP_WITHIN[planCode as keyof typeof PLAN_BACKUP_KEEP_WITHIN].defaultSeconds;
  return seconds === null
    ? { kind: 'no-storage', plan: planCode }
    : { kind: 'window', seconds, plan: planCode };
}
