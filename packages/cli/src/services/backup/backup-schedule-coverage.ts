/**
 * How often a schedule fires, and which repositories have fallen behind it.
 *
 * A backup job can succeed while covering less than it should (a licence lapses, a transfer window
 * closes before the largest images), and nothing about the unit says so. The age of each repo's last
 * successful upload, read from renet's backup_coverage, against the cadence the config asks for, is
 * what does. A repo is stale once its last success is older than twice its schedule interval: one
 * missed run is tolerated (a long seed, a reboot), two are not.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { BackupCoverage } from '@rediacc/shared/renet-contract/data/list-types.generated';
import {
  coverageByGuid,
  machineUnitSpecs,
  type ScheduledStrategy,
} from './backup-schedule-targets.js';
import { invalidCronReason } from './backup-strategy-validate.js';

const MINUTE_MS = 60_000;
const DAY_MS = 24 * 60 * MINUTE_MS;
/** Long enough to see a yearly gap's neighbours on both sides of a leap day. */
const SCAN_DAYS = 800;

/** `a`, `a-b` or `*` (with an optional `/step`) as an inclusive range. */
function fieldRange(range: string, hasStep: boolean, min: number, max: number): [number, number] {
  if (range === '*') return [min, max];
  const dash = range.indexOf('-');
  if (dash !== -1) return [Number(range.slice(0, dash)), Number(range.slice(dash + 1))];
  const lo = Number(range);
  // `5/15` is "from 5, every 15": a bare start with a step runs to the field maximum.
  return [lo, hasStep ? max : lo];
}

function parseField(field: string, min: number, max: number): Set<number> {
  const values = new Set<number>();
  for (const part of field.split(',')) {
    const [range, stepText] = part.split('/');
    const step = stepText === undefined ? 1 : Number(stepText);
    const [lo, hi] = fieldRange(range, stepText !== undefined, min, max);
    if (![lo, hi, step].every(Number.isInteger) || step < 1) {
      throw new Error(`Cannot read cron field "${field}"`);
    }
    for (let v = lo; v <= hi; v += step) values.add(v);
  }
  return values;
}

interface CronDays {
  doms: Set<number>;
  months: Set<number>;
  dows: Set<number>;
  domRestricted: boolean;
  dowRestricted: boolean;
}

/** Whether the cron fires on this UTC day. When both day fields are restricted, either one matching fires it. */
function firesOn(date: Date, days: CronDays): boolean {
  if (!days.months.has(date.getUTCMonth() + 1)) return false;
  const domHit = days.doms.has(date.getUTCDate());
  const dowHit = days.dows.has(date.getUTCDay());
  if (days.domRestricted && days.dowRestricted) return domHit || dowHit;
  return domHit && dowHit;
}

/**
 * The longest gap, in milliseconds, between two consecutive firings of a 5-field cron, scanned over
 * two years in UTC. Undefined when it fires fewer than twice in that window (a date that never comes).
 */
export function cronIntervalMs(cron: string): number | undefined {
  if (invalidCronReason(cron)) return undefined;
  const [minF, hourF, domF, monF, dowF] = cron.trim().split(/\s+/);
  const minutes = [...parseField(minF, 0, 59)].sort((a, b) => a - b);
  const hours = [...parseField(hourF, 0, 23)].sort((a, b) => a - b);
  const dows = parseField(dowF, 0, 7);
  if (dows.has(7)) dows.add(0);
  const days: CronDays = {
    doms: parseField(domF, 1, 31),
    months: parseField(monF, 1, 12),
    dows,
    domRestricted: domF !== '*',
    dowRestricted: dowF !== '*',
  };
  const offsets = hours.flatMap((h) => minutes.map((m) => (h * 60 + m) * MINUTE_MS));
  const start = Date.UTC(2026, 0, 1);
  const fires: number[] = [];
  for (let day = 0; day < SCAN_DAYS; day++) {
    const dayStart = start + day * DAY_MS;
    if (firesOn(new Date(dayStart), days)) fires.push(...offsets.map((o) => dayStart + o));
  }
  if (fires.length < 2) return undefined;
  let longest = 0;
  for (let i = 1; i < fires.length; i++) longest = Math.max(longest, fires[i] - fires[i - 1]);
  return longest;
}

/** One repo whose last successful backup is older than twice its schedule interval. */
export interface StaleBackupRepo {
  guid: string;
  name?: string;
  lastSuccessAt: string;
  ageDays: number;
  /** The shortest schedule interval covering the repo, in days. */
  intervalDays: number;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

/**
 * Repos the machine's bound strategies cover whose last success is older than 2x the shortest
 * interval covering them. A repo with no success on record is left to the never-backed-up check
 * (it may simply be new), and a repo no strategy covers is not this check's business.
 */
export function staleBackupRepos(
  coverage: BackupCoverage | undefined,
  cronsByGuid: Map<string, string[]>,
  nowMs: number = Date.now()
): StaleBackupRepo[] {
  const stale: StaleBackupRepo[] = [];
  for (const repo of coverage?.repos ?? []) {
    const interval = shortestInterval(cronsByGuid.get(repo.guid));
    const last = repo.last_success_at ? Date.parse(repo.last_success_at) : Number.NaN;
    if (interval === undefined || Number.isNaN(last) || !repo.last_success_at) continue;
    const age = nowMs - last;
    if (age <= 2 * interval) continue;
    stale.push({
      guid: repo.guid,
      ...(repo.name && { name: repo.name }),
      lastSuccessAt: repo.last_success_at,
      ageDays: round1(age / DAY_MS),
      intervalDays: round1(interval / DAY_MS),
    });
  }
  return stale;
}

/** The shortest interval among the crons covering a repo; undefined when none is readable. */
function shortestInterval(crons: string[] | undefined): number | undefined {
  const intervals = (crons ?? []).map(cronIntervalMs).filter((n): n is number => n !== undefined);
  return intervals.length > 0 ? Math.min(...intervals) : undefined;
}

/**
 * The stale repos on a machine, resolved through the config: the strategies bound to it, enabled,
 * rendered to unit specs exactly as `backup schedule` renders them. A config the scheduler would
 * refuse (an unknown repo name) yields no verdict rather than a crash of the status read.
 */
export function machineStaleBackups(
  config: RdcConfig,
  machineName: string,
  coverage: BackupCoverage | undefined,
  nowMs: number = Date.now()
): StaleBackupRepo[] {
  const machine = config.resources?.machines?.[machineName];
  const all = config.resources?.backupStrategies ?? {};
  const strategies: { name: string; config: ScheduledStrategy }[] = [];
  for (const name of machine?.backupStrategies ?? []) {
    if (!(name in all)) continue;
    const strategy = all[name];
    if (strategy.enabled === false) continue;
    strategies.push({ name, config: strategy });
  }
  if (strategies.length === 0) return [];
  try {
    const specs = machineUnitSpecs(strategies, config, machineName);
    return staleBackupRepos(coverage, coverageByGuid(specs, config, machineName), nowMs);
  } catch {
    return [];
  }
}
