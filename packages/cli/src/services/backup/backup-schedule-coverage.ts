/**
 * How often a schedule fires, and which repositories have fallen behind it or their declared target.
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
  targetsByGuid,
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

/**
 * What renet's backup_coverage reports per repository once a target is declared. Declared here beside
 * the generated type, which carries the fields only after the contract is regenerated from renet.
 */
type CoverageRepo = BackupCoverage['repos'][number] & {
  last_capture_at?: string;
  target_seconds?: number;
  achieved_rpo_ms?: number;
  ticks_missed?: number;
  target_met?: boolean;
  hook_failures?: number;
};

/** How far past its target a repository may fall before it counts as late: max(T, 5 minutes). The same figure renet's nextExpected uses. */
function targetGraceSeconds(targetSeconds: number): number {
  return Math.max(targetSeconds, 300);
}

/**
 * One repo that has fallen behind: a cron repo whose last success is older than twice its schedule
 * interval, or a target repo whose last capture is older than T + grace. Seconds, because at a
 * sub-hour cadence a figure in days rounds to 0 and says nothing.
 */
export interface StaleBackupRepo {
  guid: string;
  name?: string;
  lastSuccessAt: string;
  ageSeconds: number;
  /** The shortest schedule interval covering the repo (its target length for a target repo), in seconds. */
  intervalSeconds: number;
  /** Set for a repo with a declared target; the verdict then measures against T + grace. */
  targetSeconds?: number;
}

/** One repo whose latest run missed its declared target, with how the run went. */
export interface MissedTargetRepo {
  guid: string;
  name?: string;
  targetSeconds: number;
  achievedRpoMs?: number;
  ticksMissed?: number;
  hookFailures?: number;
}

/**
 * The instant a target repo's content was last proven: the later of its last capture (a commit or an
 * unchanged check) and its last success. An older renet reports no capture time, and the success
 * time then stands alone.
 */
function lastProvenMs(repo: CoverageRepo): number {
  const times = [repo.last_capture_at, repo.last_success_at]
    .map((v) => (v ? Date.parse(v) : Number.NaN))
    .filter((n) => !Number.isNaN(n));
  return times.length > 0 ? Math.max(...times) : Number.NaN;
}

/**
 * Repos the machine's bound strategies cover that have fallen behind. A cron repo is stale past 2x
 * the shortest interval covering it; a repo with a declared target is stale past T + grace measured
 * from its last capture, so an idle repo whose `unchanged` runs advance the capture stays fresh and a
 * hung run, which writes nothing, ages out. A repo with no success on record is left to the
 * never-backed-up check (it may simply be new), and a repo no strategy covers is not this check's
 * business.
 */
export function staleBackupRepos(
  coverage: BackupCoverage | undefined,
  cronsByGuid: Map<string, string[]>,
  nowMs: number = Date.now(),
  targetsByGuid: Map<string, number> = new Map()
): StaleBackupRepo[] {
  const stale: StaleBackupRepo[] = [];
  for (const repo of (coverage?.repos ?? []) as CoverageRepo[]) {
    const verdict = staleVerdict(
      repo,
      cronsByGuid.get(repo.guid),
      targetsByGuid.get(repo.guid),
      nowMs
    );
    if (verdict) stale.push(verdict);
  }
  return stale;
}

/** One repo's verdict: how far behind it is and against what, or undefined when it is within its limit or has nothing to judge. */
function staleVerdict(
  repo: CoverageRepo,
  crons: string[] | undefined,
  target: number | undefined,
  nowMs: number
): StaleBackupRepo | undefined {
  if (!repo.last_success_at) return undefined;
  const intervalMs = target === undefined ? shortestInterval(crons) : target * 1000;
  const lastMs = target === undefined ? Date.parse(repo.last_success_at) : lastProvenMs(repo);
  if (intervalMs === undefined || Number.isNaN(lastMs)) return undefined;
  const age = nowMs - lastMs;
  const limit =
    target === undefined ? 2 * intervalMs : (target + targetGraceSeconds(target)) * 1000;
  if (age <= limit) return undefined;
  return {
    guid: repo.guid,
    ...(repo.name && { name: repo.name }),
    lastSuccessAt: repo.last_success_at,
    ageSeconds: Math.round(age / 1000),
    intervalSeconds: Math.round(intervalMs / 1000),
    ...(target !== undefined && { targetSeconds: target }),
  };
}

/**
 * Repos with a declared target whose latest run reported `target_met: false` (a skipped, throttled,
 * hook-failed or late run). A repo with no declared target is not judged: the flag is a statement
 * about a target, and a removed target's leftovers must not read as a miss.
 */
export function missedTargetRepos(
  coverage: BackupCoverage | undefined,
  targetsByGuid: Map<string, number>
): MissedTargetRepo[] {
  const missed: MissedTargetRepo[] = [];
  for (const repo of (coverage?.repos ?? []) as CoverageRepo[]) {
    const target = targetsByGuid.get(repo.guid);
    if (target === undefined || repo.target_met !== false) continue;
    missed.push({
      guid: repo.guid,
      ...(repo.name && { name: repo.name }),
      targetSeconds: target,
      ...(repo.achieved_rpo_ms !== undefined && { achievedRpoMs: repo.achieved_rpo_ms }),
      ...(repo.ticks_missed !== undefined && { ticksMissed: repo.ticks_missed }),
      ...(repo.hook_failures !== undefined && { hookFailures: repo.hook_failures }),
    });
  }
  return missed;
}

/** The shortest interval among the crons covering a repo; undefined when none is readable. */
function shortestInterval(crons: string[] | undefined): number | undefined {
  const intervals = (crons ?? []).map(cronIntervalMs).filter((n): n is number => n !== undefined);
  return intervals.length > 0 ? Math.min(...intervals) : undefined;
}

/** A span in the unit a person reads it in: `45s`, `11m`, `3h20m`, `3d`. */
export function formatSpan(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 2 * 86_400 && seconds % 86_400 !== 0) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return m === 0 ? `${h}h` : `${h}h${m}m`;
  }
  const days = Math.round((seconds / 86_400) * 10) / 10;
  return `${days}d`;
}

/** The backup standing of a machine: repos behind their schedule or target, and repos whose latest run missed a target. */
export interface MachineTargetStatus {
  stale: StaleBackupRepo[];
  missed: MissedTargetRepo[];
}

/**
 * The standing of every repository on a machine, resolved through the config: the strategies bound
 * to it, enabled, rendered to unit specs exactly as `backup schedule` renders them. A config the
 * scheduler would refuse (an unknown repo name) yields no verdict rather than a crash of the status
 * read. A repo that is stale is not also listed as missed.
 */
export function machineBackupTargetStatus(
  config: RdcConfig,
  machineName: string,
  coverage: BackupCoverage | undefined,
  nowMs: number = Date.now()
): MachineTargetStatus {
  const machine = config.resources?.machines?.[machineName];
  const all = config.resources?.backupStrategies ?? {};
  const strategies: { name: string; config: ScheduledStrategy }[] = [];
  for (const name of machine?.backupStrategies ?? []) {
    if (!(name in all)) continue;
    const strategy = all[name];
    if (strategy.enabled === false) continue;
    strategies.push({ name, config: strategy });
  }
  if (strategies.length === 0) return { stale: [], missed: [] };
  try {
    const specs = machineUnitSpecs(strategies, config, machineName);
    const targets = targetsByGuid(specs, config, machineName);
    const stale = staleBackupRepos(
      coverage,
      coverageByGuid(specs, config, machineName),
      nowMs,
      targets
    );
    const late = new Set(stale.map((s) => s.guid));
    return {
      stale,
      missed: missedTargetRepos(coverage, targets).filter((m) => !late.has(m.guid)),
    };
  } catch {
    return { stale: [], missed: [] };
  }
}

/** The stale repos on a machine (see machineBackupTargetStatus). */
export function machineStaleBackups(
  config: RdcConfig,
  machineName: string,
  coverage: BackupCoverage | undefined,
  nowMs: number = Date.now()
): StaleBackupRepo[] {
  return machineBackupTargetStatus(config, machineName, coverage, nowMs).stale;
}

/** One repo whose most recent `backup verify` did not come back clean. */
export interface FailedVerifyRepo {
  guid: string;
  name?: string;
  /** renet's verdict for that run: `mismatch`, `failed`, or whatever it recorded. */
  status: string;
  verifiedAt?: string;
}

/**
 * Repos whose last recorded verify is anything but `verified`, from renet's backup_coverage. A repo
 * with no recorded verify is not listed: it has no verdict, and a repo with no backup records none.
 */
export function failedVerifyRepos(coverage: BackupCoverage | undefined): FailedVerifyRepo[] {
  const failed: FailedVerifyRepo[] = [];
  for (const repo of coverage?.repos ?? []) {
    const status = repo.last_verify_status;
    if (!status || status === 'verified') continue;
    failed.push({
      guid: repo.guid,
      ...(repo.name && { name: repo.name }),
      status,
      ...(repo.last_verify_at && { verifiedAt: repo.last_verify_at }),
    });
  }
  return failed;
}
