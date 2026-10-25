/**
 * What `backup status` reports per scheduled unit: whether a timer exists at all, the last run and
 * its result, the next run, and whether a run was missed.
 *
 * The old report read only `systemctl is-active` on the service, so a machine with NO timer printed
 * "idle", exactly like a healthy one between runs (hostinger, 2026-10-15: no backup since 2026-08-14,
 * status "idle"). The timer is the thing that makes a backup happen, so its absence is the first
 * thing said.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { cronIntervalMs } from './backup-schedule-coverage.js';
import { parseSystemctlShow } from './backup-schedule-reconcile.js';

/** A unit the config expects on the machine. */
export interface ExpectedScheduleUnit {
  unitName: string;
  strategyName: string;
  schedule: string;
}

export interface ScheduleStatusRow {
  strategy: string;
  unit: string;
  /** False when the timer is not loaded on the machine. */
  scheduled: boolean;
  lastRun: string;
  result: string;
  nextRun: string;
  /** True when the last run failed, or the last trigger is older than twice the interval. */
  missed: boolean;
  reason?: string;
}

const PROPERTIES = [
  'Id',
  'LoadState',
  'ActiveState',
  'SubState',
  'Result',
  'NextElapseUSecRealtime',
  'LastTriggerUSec',
  'ExecMainExitTimestamp',
].join(',');

/** systemd timestamps under TZ=UTC: `Sun 2026-10-25 03:00:00 UTC`. Undefined when empty or n/a. */
export function parseSystemdTimestamp(value: string | undefined): number | undefined {
  const m = /(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})/.exec(value ?? '');
  if (!m) return undefined;
  const ms = Date.parse(`${m[1]}T${m[2]}Z`);
  return Number.isNaN(ms) ? undefined : ms;
}

function iso(ms: number | undefined): string {
  return ms === undefined ? '-' : new Date(ms).toISOString().replace('.000Z', 'Z');
}

/**
 * Build status rows from `systemctl show` records. Pure, so the missed-run rules are testable with
 * fixtures: a failed last run is missed; a last trigger older than 2x the cron interval is missed; a
 * timer that never fired is not (it may have been deployed an hour ago).
 */
export function buildScheduleStatusRows(
  expected: ExpectedScheduleUnit[],
  records: Map<string, Record<string, string>>,
  nowMs: number = Date.now()
): ScheduleStatusRow[] {
  return expected.map((unit) => {
    const timer: SystemdProps = records.get(`rediacc-backup-${unit.unitName}.timer`) ?? {};
    const service: SystemdProps = records.get(`rediacc-backup-${unit.unitName}.service`) ?? {};
    const base = { strategy: unit.strategyName, unit: unit.unitName };
    if (timer.LoadState !== 'loaded') {
      return {
        ...base,
        scheduled: false,
        lastRun: '-',
        result: '-',
        nextRun: '-',
        missed: true,
        reason: 'not scheduled: no timer on the machine (run: rdc backup schedule)',
      };
    }
    const lastTrigger = parseSystemdTimestamp(timer.LastTriggerUSec);
    const result = runResult(service, lastTrigger);
    const scheduled = timer.ActiveState === 'active';
    const reason = missedReason(unit, timer, result, lastTrigger, nowMs);
    return {
      ...base,
      scheduled,
      lastRun: iso(lastTrigger ?? parseSystemdTimestamp(service.ExecMainExitTimestamp)),
      result,
      nextRun: iso(parseSystemdTimestamp(timer.NextElapseUSecRealtime)),
      missed: reason !== undefined,
      ...(reason !== undefined && { reason }),
    };
  });
}

type SystemdProps = Partial<Record<string, string>>;

/** `running` while the service is up, `-` before the first trigger, else systemd's Result. */
function runResult(service: SystemdProps, lastTrigger: number | undefined): string {
  if (service.ActiveState === 'active' || service.ActiveState === 'activating') return 'running';
  if (lastTrigger === undefined) return '-';
  return service.Result ?? '-';
}

/** Why a loaded timer counts as a missed run, or undefined when it does not. */
function missedReason(
  unit: ExpectedScheduleUnit,
  timer: SystemdProps,
  result: string,
  lastTrigger: number | undefined,
  nowMs: number
): string | undefined {
  if (timer.ActiveState !== 'active') {
    return `timer is ${timer.ActiveState ?? 'unknown'}, so no run is queued`;
  }
  if (result !== 'success' && result !== '-' && result !== 'running') {
    return `last run ended with ${result}`;
  }
  const interval = cronIntervalMs(unit.schedule);
  if (interval === undefined || lastTrigger === undefined) return undefined;
  if (nowMs - lastTrigger <= 2 * interval) return undefined;
  return `no run since ${iso(lastTrigger)}, more than twice the schedule interval`;
}

/** Read the expected units' timer and service state from the machine and build the rows. */
export async function readScheduleStatus(
  sftp: SFTPClient,
  expected: ExpectedScheduleUnit[],
  nowMs: number = Date.now()
): Promise<ScheduleStatusRow[]> {
  if (expected.length === 0) return [];
  const units = expected.flatMap((u) => [
    `rediacc-backup-${u.unitName}.timer`,
    `rediacc-backup-${u.unitName}.service`,
  ]);
  let stdout = '';
  // TZ=UTC makes systemctl print every timestamp in UTC, so parsing needs no zone table.
  await sftp.execStreaming(`TZ=UTC systemctl show --property=${PROPERTIES} ${units.join(' ')}`, {
    onStdout: (data) => {
      stdout += data.toString();
    },
    onStderr: () => {},
  });
  return buildScheduleStatusRows(expected, parseSystemctlShow(stdout), nowMs);
}

/** `backup status` exit code: 1 when any unit is unscheduled or missed a run, else 0. */
export function scheduleStatusExitCode(rows: ScheduleStatusRow[]): number {
  return rows.some((r) => r.missed) ? 1 : 0;
}
