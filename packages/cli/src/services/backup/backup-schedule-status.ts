/**
 * What `backup status` reports per scheduled unit: whether a timer exists at all, the last run and
 * its result, the next run, and whether a run was missed.
 *
 * The old report read only `systemctl is-active` on the service, so a machine with NO timer printed
 * "idle", exactly like a healthy one between runs (hostinger, 2026-10-15: no backup since 2026-08-14,
 * status "idle"). The timer is the thing that makes a backup happen, so its absence is the first
 * thing said.
 */

import { TELEMETRY_DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { cronIntervalMs } from './backup-schedule-coverage.js';

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
  /** True when the machine's answer for this unit was missing or unreadable: nothing is known about the timer. */
  unread?: boolean;
  reason?: string;
}

/**
 * Parse `systemctl show` records into a map keyed by `Id`. A record ends at a blank line OR where a key
 * repeats, because a job folds output lines into events and an empty line carries no `msg`, so the blank
 * separators between records do not survive the fold (hostinger, 2026-11-05: every record merged into one,
 * the last `Id` won, and a healthy timer read as "no timer"). Every record carries `Id`, so the repeat is a
 * reliable boundary whether or not the blank lines arrive.
 */
export function parseFoldedSystemctlShow(output: string): Map<string, Record<string, string>> {
  const result = new Map<string, Record<string, string>>();
  let props: Record<string, string> = {};
  const flush = () => {
    if (props.Id) result.set(props.Id, props);
    props = {};
  };
  for (const line of output.split('\n')) {
    if (line.trim() === '') {
      flush();
      continue;
    }
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq);
    if (key in props) flush();
    props[key] = line.slice(eq + 1).replace(/\r$/, '');
  }
  flush();
  return result;
}

/** The scheduled timer's name for a unit, the key its record carries. */
const timerId = (unitName: string): string => `rediacc-backup-${unitName}.timer`;

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
  nowMs: number = Date.now(),
  unreadCause?: string
): ScheduleStatusRow[] {
  return expected.map((unit) => {
    const found: SystemdProps | undefined = records.get(timerId(unit.unitName));
    const timer: SystemdProps = found ?? {};
    const service: SystemdProps = records.get(`rediacc-backup-${unit.unitName}.service`) ?? {};
    const base = { strategy: unit.strategyName, unit: unit.unitName };
    // "No timer" is only what the machine said (LoadState other than loaded). No record, or a record without
    // LoadState, says nothing about the timer, so it is unknown and never reported as absent.
    if (found?.LoadState === undefined) {
      return {
        ...base,
        scheduled: false,
        lastRun: '-',
        result: '-',
        nextRun: '-',
        missed: true,
        unread: true,
        reason: `status could not be read: ${unreadCause ?? `the machine returned no record for ${timerId(unit.unitName)}`}`,
      };
    }
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
    return `timer is ${timer.ActiveState ?? TELEMETRY_DEFAULTS.UNKNOWN}, so no run is queued`;
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
  return buildScheduleStatusRows(expected, parseFoldedSystemctlShow(stdout), nowMs);
}

/** `backup status` exit code: 2 when any unit could not be read, 1 when any is unscheduled or missed a run, else 0. */
export function scheduleStatusExitCode(rows: ScheduleStatusRow[]): number {
  if (rows.some((r) => r.unread)) return 2;
  return rows.some((r) => r.missed) ? 1 : 0;
}
