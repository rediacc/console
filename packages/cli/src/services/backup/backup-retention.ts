/**
 * Strategy-level snapshot retention: the `--retention "last=7,daily=7"` spec, the cron-fit check and
 * the push of a strategy's policy to the lineages it covers.
 *
 * The CLI declares, the account server enforces (retentionPolicySweep). A strategy's policy is a
 * DEFAULT for the repositories it covers: a per-repo `backup retention set` is the more specific
 * statement and wins, so the automatic pushes (`backup schedule`, `backup run`) only fill lineages
 * that have no lineage-level policy. `backup strategy set --retention` is the explicit act that
 * overwrites, because the operator just changed the number on purpose.
 */

import type { RdcConfig, RepoFamily } from '@rediacc/shared/config-schema';
import type { BackupStrategyConfig } from '../../types/index.js';
import { accountServerFetch } from '../account/account-client.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { configService } from '../config/config-resources.js';

export interface RetentionSpec {
  keepLast?: number;
  keepHourly?: number;
  keepDaily?: number;
  keepWeekly?: number;
  keepMonthly?: number;
  keepYearly?: number;
}

type RetentionKnob = keyof RetentionSpec;

/** Spec names, as typed in `--retention`, mapped to the wire knob. */
const SPEC_NAMES: Record<string, RetentionKnob> = {
  last: 'keepLast',
  hourly: 'keepHourly',
  daily: 'keepDaily',
  weekly: 'keepWeekly',
  monthly: 'keepMonthly',
  yearly: 'keepYearly',
};

/** Thrown for a `--retention` value that does not parse; the command turns it into a ValidationError. */
export class RetentionSpecError extends Error {}

/**
 * Parse `last=7,daily=7,weekly=4,monthly=6`. An empty value or `none` returns undefined, which
 * clears the strategy's policy. Any unknown name, repeated name or non-integer count is refused:
 * a policy decides what gets deleted, so a guess is never acceptable.
 */
export function parseRetentionSpec(raw: string): RetentionSpec | undefined {
  const trimmed = raw.trim();
  if (trimmed === '' || trimmed.toLowerCase() === 'none') return undefined;
  const spec: RetentionSpec = {};
  for (const part of trimmed.split(',')) {
    const [name, count, ...rest] = part.split('=').map((s) => s.trim());
    const knob = SPEC_NAMES[name.toLowerCase()];
    if (knob === undefined || count === undefined || rest.length > 0 || !/^\d+$/.test(count)) {
      throw new RetentionSpecError(raw);
    }
    if (knob in spec) throw new RetentionSpecError(raw);
    spec[knob] = Number(count);
  }
  return spec;
}

export type CronCadence = 'subdaily' | 'daily' | 'weekly' | 'monthly';

const isPlainNumber = (field: string): boolean => /^\d+$/.test(field);

/**
 * How often a 5-field cron produces a snapshot, coarsely: a specific day of month is monthly, one
 * specific weekday is weekly, a wildcard, list, range or step in the hour field is sub-daily, and
 * the rest is daily.
 */
export function cronCadence(cron: string): CronCadence {
  const [, hour, dom, , dow] = cron.trim().split(/\s+/);
  if (dom !== undefined && isPlainNumber(dom)) return 'monthly';
  if (dow !== undefined && isPlainNumber(dow)) return 'weekly';
  if (hour !== undefined && !isPlainNumber(hour)) return 'subdaily';
  return 'daily';
}

/** The knobs a cadence can never fill: one snapshot per bucket needs a snapshot per bucket. */
const USELESS_KNOBS: Record<CronCadence, { knob: RetentionKnob; flag: string }[]> = {
  subdaily: [],
  daily: [{ knob: 'keepHourly', flag: 'hourly' }],
  weekly: [
    { knob: 'keepHourly', flag: 'hourly' },
    { knob: 'keepDaily', flag: 'daily' },
  ],
  monthly: [
    { knob: 'keepHourly', flag: 'hourly' },
    { knob: 'keepDaily', flag: 'daily' },
    { knob: 'keepWeekly', flag: 'weekly' },
  ],
};

export interface RetentionCronMismatch {
  /** The spec name (`hourly`, `daily`, `weekly`). */
  knob: string;
  cadence: CronCadence;
}

/** The retention knobs a strategy declares that its cron cannot produce snapshots for. */
export function retentionCronMismatches(
  retention: RetentionSpec | undefined,
  cron: string
): RetentionCronMismatch[] {
  if (!retention) return [];
  const cadence = cronCadence(cron);
  return USELESS_KNOBS[cadence]
    .filter(({ knob }) => (retention[knob] ?? 0) > 0)
    .map(({ flag }) => ({ knob: flag, cadence }));
}

/** Whether a repo ref list names `name` (every tag) or `name:tag` exactly. */
function namesRepo(list: string[] | undefined, name: string, tag: string): boolean {
  return (list ?? []).some((ref) => ref === name || ref === `${name}:${tag}`);
}

/** A family placed on another machine is out of scope; one with no machine placement is always in. */
function onMachine(family: RepoFamily, machineName: string | undefined): boolean {
  if (!machineName || !family.placement || !('machine' in family.placement)) return true;
  return family.placement.machine === machineName;
}

/** The lineage (grand) GUIDs a strategy covers, resolved from the config's include/exclude names. */
export function strategyLineages(
  strategy: Pick<BackupStrategyConfig, 'include' | 'exclude'>,
  config: RdcConfig,
  machineName?: string
): string[] {
  const families: Record<string, RepoFamily> = config.resources?.repositories ?? {};
  const covered = (name: string, tag: string): boolean =>
    (!strategy.include?.length || namesRepo(strategy.include, name, tag)) &&
    !namesRepo(strategy.exclude, name, tag);
  const lineages = new Set<string>();
  for (const [name, family] of Object.entries(families)) {
    if (!onMachine(family, machineName)) continue;
    for (const [tag, record] of Object.entries(family.tags)) {
      if (covered(name, tag)) lineages.add(record.grandGuid ?? record.repositoryGuid);
    }
  }
  return [...lineages].sort((x, y) => x.localeCompare(y));
}

interface ServerPolicyRow {
  lineageGuid: string;
  streamId?: string | null;
}

export interface RetentionPushResult {
  /** Lineages the policy was written to. */
  pushed: number;
  /** Lineages left alone because they already carry a lineage-level policy. */
  kept: number;
}

/** Lineages that already carry a lineage-level policy (a stream-level row is not one). */
async function declaredLineages(): Promise<Set<string>> {
  const existing = await accountServerFetch<{ policies: ServerPolicyRow[] }>(
    '/account/api/v1/backups/retention'
  );
  return new Set(existing.policies.filter((row) => !row.streamId).map((row) => row.lineageGuid));
}

/**
 * Write a strategy's retention to the lineages it covers.
 *
 * `overwrite: false` (the automatic pushes) fills only lineages with no lineage-level policy, so a
 * per-repo `retention set` is never undone by the next scheduled run. `overwrite: true` (the
 * explicit `strategy set --retention`) replaces every covered lineage's policy.
 */
export async function pushStrategyRetention(
  strategy: Pick<BackupStrategyConfig, 'include' | 'exclude' | 'retention'>,
  opts: { overwrite: boolean; machineName?: string }
): Promise<RetentionPushResult> {
  const result: RetentionPushResult = { pushed: 0, kept: 0 };
  const config = await configService.getCurrent();
  if (!strategy.retention || !config) return result;
  const lineages = strategyLineages(strategy, config, opts.machineName);
  if (lineages.length === 0) return result;

  const declared = opts.overwrite ? new Set<string>() : await declaredLineages();
  for (const lineageGuid of lineages) {
    if (declared.has(lineageGuid)) {
      result.kept++;
      continue;
    }
    await accountServerFetch('/account/api/v1/backups/retention', {
      method: 'PUT',
      body: { lineageGuid, ...strategy.retention },
    });
    result.pushed++;
  }
  return result;
}

/** Whether an account token is available, so a push has something to authenticate with. */
export function hasAccountToken(): boolean {
  return getSubscriptionTokenState().kind === 'ready';
}
