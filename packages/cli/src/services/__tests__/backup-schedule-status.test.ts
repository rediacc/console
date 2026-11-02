/**
 * `backup status` per unit (G6) and the stale-backup verdict machine status and health share (G7).
 */

import { describe, expect, it } from 'vitest';
import {
  cronIntervalMs,
  machineStaleBackups,
  staleBackupRepos,
} from '../backup/backup-schedule-coverage.js';
import {
  buildScheduleStatusRows,
  parseSystemdTimestamp,
  readScheduleStatus,
  scheduleStatusExitCode,
} from '../backup/backup-schedule-status.js';

const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const NOW = Date.parse('2026-10-25T12:00:00Z');

function show(id: string, props: Record<string, string>): string {
  return [`Id=${id}`, ...Object.entries(props).map(([k, v]) => `${k}=${v}`)].join('\n');
}

function records(...blocks: string[]): Map<string, Record<string, string>> {
  const map = new Map<string, Record<string, string>>();
  for (const block of blocks) {
    const props: Record<string, string> = {};
    for (const line of block.split('\n')) {
      const eq = line.indexOf('=');
      props[line.slice(0, eq)] = line.slice(eq + 1);
    }
    map.set(props.Id, props);
  }
  return map;
}

const daily = { unitName: 'daily', strategyName: 'daily', schedule: '0 3 * * *' };
const timerOk = (last: string, next = 'Mon 2026-10-26 03:00:00 UTC') =>
  show('rediacc-backup-daily.timer', {
    LoadState: 'loaded',
    ActiveState: 'active',
    LastTriggerUSec: last,
    NextElapseUSecRealtime: next,
  });
const service = (result: string, active = 'inactive') =>
  show('rediacc-backup-daily.service', {
    LoadState: 'loaded',
    ActiveState: active,
    Result: result,
    ExecMainExitTimestamp: 'Sun 2026-10-25 04:10:00 UTC',
  });

describe('cronIntervalMs', () => {
  it('reads hourly, daily, weekly and monthly cadences', () => {
    expect(cronIntervalMs('0 * * * *')).toBe(HOUR);
    expect(cronIntervalMs('*/15 * * * *')).toBe(15 * 60_000);
    expect(cronIntervalMs('0 3 * * *')).toBe(DAY);
    expect(cronIntervalMs('0 3 * * 1')).toBe(7 * DAY);
    expect(cronIntervalMs('0 3 1 * *')).toBe(31 * DAY);
    // A list's longest gap is what counts: Mon and Thu leave a 4-day gap Thu -> Mon.
    expect(cronIntervalMs('0 3 * * 1,4')).toBe(4 * DAY);
  });

  it('is undefined for an invalid cron or one that never fires twice', () => {
    expect(cronIntervalMs('daily')).toBeUndefined();
    expect(cronIntervalMs('0 0 30 2 *')).toBeUndefined();
  });
});

describe('buildScheduleStatusRows (G6)', () => {
  it('says not scheduled when the timer is absent, and counts it as missed', () => {
    const rows = buildScheduleStatusRows(
      [daily],
      records(show('rediacc-backup-daily.timer', { LoadState: 'not-found' })),
      NOW
    );
    expect(rows[0]).toMatchObject({ scheduled: false, missed: true });
    expect(rows[0].reason).toMatch(/not scheduled/);
    expect(scheduleStatusExitCode(rows)).toBe(1);
  });

  it('shows last run, result and next run for a healthy timer, exit 0 (control)', () => {
    const rows = buildScheduleStatusRows(
      [daily],
      records(timerOk('Sun 2026-10-25 03:00:00 UTC'), service('success')),
      NOW
    );
    expect(rows[0]).toEqual({
      strategy: 'daily',
      unit: 'daily',
      scheduled: true,
      lastRun: '2026-10-25T03:00:00Z',
      result: 'success',
      nextRun: '2026-10-26T03:00:00Z',
      missed: false,
    });
    expect(scheduleStatusExitCode(rows)).toBe(0);
  });

  it('a failed last run is a missed run', () => {
    const rows = buildScheduleStatusRows(
      [daily],
      records(timerOk('Sun 2026-10-25 03:00:00 UTC'), service('exit-code')),
      NOW
    );
    expect(rows[0]).toMatchObject({ missed: true, result: 'exit-code' });
    expect(scheduleStatusExitCode(rows)).toBe(1);
  });

  it('a last trigger older than twice the interval is a missed run', () => {
    const rows = buildScheduleStatusRows(
      [daily],
      records(timerOk('Thu 2026-10-22 03:00:00 UTC'), service('success')),
      NOW
    );
    expect(rows[0].missed).toBe(true);
    expect(rows[0].reason).toMatch(/twice the schedule interval/);
  });

  it('a timer that never fired yet is not missed, and a running backup is not failed', () => {
    const fresh = buildScheduleStatusRows(
      [daily],
      records(timerOk('n/a'), service('success')),
      NOW
    );
    expect(fresh[0]).toMatchObject({ missed: false, lastRun: '2026-10-25T04:10:00Z', result: '-' });
    const running = buildScheduleStatusRows(
      [daily],
      records(timerOk('Sun 2026-10-25 03:00:00 UTC'), service('success', 'active')),
      NOW
    );
    expect(running[0]).toMatchObject({ missed: false, result: 'running' });
  });
});

describe('readScheduleStatus', () => {
  it('asks systemd in UTC for the timer and service of every expected unit', async () => {
    const calls: string[] = [];
    const sftp = {
      execStreaming: (cmd: string, opts: { onStdout: (b: Buffer) => void }) => {
        calls.push(cmd);
        opts.onStdout(
          Buffer.from(`${timerOk('Sun 2026-10-25 03:00:00 UTC')}\n\n${service('success')}\n`)
        );
        return Promise.resolve(0);
      },
    };
    const rows = await readScheduleStatus(sftp as never, [daily], NOW);
    expect(calls[0]).toMatch(/^TZ=UTC systemctl show --property=/);
    expect(calls[0]).toContain('rediacc-backup-daily.timer rediacc-backup-daily.service');
    expect(rows[0].result).toBe('success');
  });

  it('parses systemd timestamps and ignores n/a', () => {
    expect(parseSystemdTimestamp('Sun 2026-10-25 03:00:00 UTC')).toBe(
      Date.parse('2026-10-25T03:00:00Z')
    );
    expect(parseSystemdTimestamp('n/a')).toBeUndefined();
    expect(parseSystemdTimestamp(undefined)).toBeUndefined();
  });
});

const GUID_A = 'a0000000-0000-4000-8000-000000000001';
const GUID_B = 'b0000000-0000-4000-8000-000000000001';

describe('staleBackupRepos (G7)', () => {
  const crons = new Map([
    [GUID_A, ['0 3 * * *']],
    [GUID_B, ['0 3 * * 0', '0 * * * *']],
  ]);

  it('flags a repo whose last success is older than twice its interval', () => {
    const stale = staleBackupRepos(
      {
        repos: [
          { guid: GUID_A, age_days: 3, last_success_at: '2026-10-22T03:00:00Z', name: 'mail' },
        ],
      },
      crons,
      NOW
    );
    expect(stale).toEqual([
      {
        guid: GUID_A,
        name: 'mail',
        lastSuccessAt: '2026-10-22T03:00:00Z',
        ageDays: 3.4,
        intervalDays: 1,
      },
    ]);
  });

  it('uses the shortest interval covering the repo, and passes a fresh one (control)', () => {
    const fresh = staleBackupRepos(
      { repos: [{ guid: GUID_A, age_days: 0, last_success_at: '2026-10-25T03:00:00Z' }] },
      crons,
      NOW
    );
    expect(fresh).toEqual([]);
    // Weekly AND hourly cover B: three hours behind is stale against the hourly unit.
    const behind = staleBackupRepos(
      { repos: [{ guid: GUID_B, age_days: 0, last_success_at: '2026-10-25T09:00:00Z' }] },
      crons,
      NOW
    );
    expect(behind.map((s) => s.guid)).toEqual([GUID_B]);
  });

  it('ignores repos with no success on record and repos no strategy covers', () => {
    expect(
      staleBackupRepos(
        {
          repos: [
            { guid: GUID_A, age_days: -1 },
            {
              guid: 'c0000000-0000-4000-8000-000000000001',
              age_days: 90,
              last_success_at: '2026-07-01T00:00:00Z',
            },
          ],
        },
        crons,
        NOW
      )
    ).toEqual([]);
  });
});

describe('machineStaleBackups', () => {
  const config = {
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'u', backupStrategies: ['daily', 'off'] } },
      repositories: {
        mail: {
          placement: { machine: 'm1' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: GUID_A } },
        },
      },
      backupStrategies: {
        daily: { schedule: '0 3 * * *', destinations: [{ kind: 'hosted-service', name: 'c' }] },
        off: {
          schedule: '* * * * *',
          enabled: false,
          destinations: [{ kind: 'hosted-service', name: 'd' }],
        },
      },
    },
  } as never;

  it('resolves coverage through the bound, enabled strategies', () => {
    const stale = machineStaleBackups(
      config,
      'm1',
      { repos: [{ guid: GUID_A, age_days: 5, last_success_at: '2026-10-20T03:00:00Z' }] },
      NOW
    );
    expect(stale.map((s) => [s.guid, s.intervalDays])).toEqual([[GUID_A, 1]]);
  });

  it('a machine with no bound strategy has no verdict', () => {
    expect(
      machineStaleBackups(
        config,
        'nope',
        { repos: [{ guid: GUID_A, age_days: 5, last_success_at: '2026-10-20T03:00:00Z' }] },
        NOW
      )
    ).toEqual([]);
  });
});
