/**
 * Coverage and health of a declared protection target (D-rpo): staleness in seconds, measured against
 * T + grace with grace = max(T, 5 minutes), missed targets as named issues, and a nightly strategy
 * that reads as it always did.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyStaleness } = await import('../health.js');
const { missedTargetRows, staleBackupRows } = await import('../status.js');
const { machineBackupTargetStatus, missedTargetRepos, staleBackupRepos } = await import(
  '../../../services/backup/backup-schedule-coverage.js'
);

const NOW = Date.parse('2026-11-02T12:00:00Z');
const minutesAgo = (m: number): string => new Date(NOW - m * 60_000).toISOString();
const MAIL = 'a0000000-0000-4000-8000-000000000001';
const NIGHTLY = 'b0000000-0000-4000-8000-000000000001';

const crons = new Map<string, string[]>([
  [MAIL, ['*/5 * * * *']],
  [NIGHTLY, ['0 3 * * *']],
]);
const targets = new Map<string, number>([[MAIL, 300]]);

const stale = (repo: Record<string, unknown>, now = NOW) =>
  staleBackupRepos({ repos: [{ guid: MAIL, age_days: 0, ...repo }] }, crons, now, targets);

const healthy = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [],
  findings: [],
};

describe('a 5-minute target goes stale at T + grace, in seconds', () => {
  it('11 minutes behind is stale, and says minutes rather than 0 days', () => {
    const [repo] = stale({ last_success_at: minutesAgo(11), last_capture_at: minutesAgo(11) });
    expect(repo).toMatchObject({
      guid: MAIL,
      ageSeconds: 660,
      intervalSeconds: 300,
      targetSeconds: 300,
    });
    expect(staleBackupRows([repo], () => 'mail')).toEqual([
      expect.objectContaining({
        repository: 'mail',
        age: '11m',
        scheduleEvery: '5m',
        target: '5m',
      }),
    ]);
  });

  it('4 minutes behind is not stale (control)', () => {
    expect(stale({ last_success_at: minutesAgo(4), last_capture_at: minutesAgo(4) })).toEqual([]);
  });

  it('exactly T + grace (10 minutes) is still within it, one second more is not', () => {
    expect(stale({ last_capture_at: minutesAgo(10), last_success_at: minutesAgo(10) })).toEqual([]);
    expect(
      stale({ last_capture_at: minutesAgo(10.02), last_success_at: minutesAgo(10.02) })
    ).toHaveLength(1);
  });

  it('grace is max(T, 5m): a 1-hour target tolerates 2 hours, not 2h and a minute', () => {
    const hourly = new Map([[MAIL, 3600]]);
    const run = (m: number) =>
      staleBackupRepos(
        {
          repos: [
            {
              guid: MAIL,
              age_days: 0,
              last_capture_at: minutesAgo(m),
              last_success_at: minutesAgo(m),
            },
          ],
        },
        crons,
        NOW,
        hourly
      );
    expect(run(120)).toEqual([]);
    expect(run(121)).toHaveLength(1);
  });

  it('an unchanged run is fresh: capture moved though nothing was uploaded', () => {
    expect(stale({ last_success_at: minutesAgo(180), last_capture_at: minutesAgo(3) })).toEqual([]);
  });

  it('a hung run shows as missed: no capture for hours leaves the repo stale and named', () => {
    const [repo] = stale({ last_success_at: minutesAgo(180), last_capture_at: minutesAgo(180) });
    expect(repo.ageSeconds).toBe(10_800);
    const h = applyStaleness(healthy, { staleBinary: [], staleBackups: [repo] });
    expect(h.exitCode).toBe(1);
    expect(h.issues[0]).toMatch(/missed their backup target/);
    expect(h.issues[0]).toMatch(new RegExp(MAIL));
  });

  it('falls back to the last success when an older renet reports no capture time', () => {
    expect(stale({ last_success_at: minutesAgo(11) })).toHaveLength(1);
    expect(stale({ last_success_at: minutesAgo(4) })).toEqual([]);
  });
});

describe('a nightly strategy reads as before, now in seconds', () => {
  const nightly = (ageMinutes: number) =>
    staleBackupRepos(
      { repos: [{ guid: NIGHTLY, age_days: 0, last_success_at: minutesAgo(ageMinutes) }] },
      crons,
      NOW,
      targets
    );

  it('is stale past twice its interval and fresh inside it', () => {
    const [repo] = nightly(3 * 24 * 60);
    expect(repo).toMatchObject({ ageSeconds: 259_200, intervalSeconds: 86_400 });
    expect(repo.targetSeconds).toBeUndefined();
    expect(nightly(30 * 60)).toEqual([]);
  });

  it('keeps the old health wording for a cron repo', () => {
    const h = applyStaleness(healthy, { staleBinary: [], staleBackups: nightly(3 * 24 * 60) });
    expect(h.exitCode).toBe(1);
    expect(h.issues[0]).toMatch(/more than twice their schedule interval/);
    expect(h.issues[0]).not.toMatch(/target/);
  });

  it('renders days for a long age', () => {
    expect(staleBackupRows(nightly(3 * 24 * 60), () => 'n')[0]).toMatchObject({
      age: '3d',
      scheduleEvery: '1d',
      target: '-',
    });
  });
});

describe('missed targets are named issues', () => {
  const coverage = {
    repos: [
      {
        guid: MAIL,
        age_days: 0,
        name: 'mail',
        last_capture_at: minutesAgo(2),
        last_success_at: minutesAgo(2),
        target_seconds: 300,
        achieved_rpo_ms: 480_000,
        ticks_missed: 1,
        target_met: false,
        hook_failures: 3,
      },
      { guid: NIGHTLY, age_days: 0, target_met: false },
    ],
  };

  it('lists a repo whose latest run missed its declared target, and only that', () => {
    expect(missedTargetRepos(coverage, targets)).toEqual([
      {
        guid: MAIL,
        name: 'mail',
        targetSeconds: 300,
        achievedRpoMs: 480_000,
        ticksMissed: 1,
        hookFailures: 3,
      },
    ]);
  });

  it('a met target is not listed (control)', () => {
    expect(
      missedTargetRepos({ repos: [{ guid: MAIL, age_days: 0, target_met: true }] }, targets)
    ).toEqual([]);
  });

  it('raises health to exit 1 and names the repo, its target and the achieved window', () => {
    const missed = missedTargetRepos(coverage, targets);
    const h = applyStaleness(healthy, { staleBinary: [], staleBackups: [], missedTargets: missed });
    expect(h.exitCode).toBe(1);
    expect(h.issues[0]).toMatch(/mail \(target 5m, achieved 8m\)/);
    expect(missedTargetRows(missed, () => 'mail')).toEqual([
      expect.objectContaining({ repository: 'mail', target: '5m', achieved: '8m', ticksMissed: 1 }),
    ]);
  });

  it('a repo both stale and missed is reported once, as stale', () => {
    const [late] = stale({
      last_capture_at: minutesAgo(30),
      last_success_at: minutesAgo(30),
      target_met: false,
      target_seconds: 300,
    });
    const missed = missedTargetRepos(
      { repos: [{ guid: MAIL, age_days: 0, target_met: false, target_seconds: 300 }] },
      targets
    );
    const h = applyStaleness(healthy, {
      staleBinary: [],
      staleBackups: [late],
      missedTargets: missed,
    });
    expect(h.issues).toHaveLength(1);
  });
});

describe('machineBackupTargetStatus resolves targets through the config', () => {
  const config = {
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'u', backupStrategies: ['s'] } },
      repositories: {
        mail: {
          placement: { machine: 'm1' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: MAIL } },
        },
        files: {
          placement: { machine: 'm1' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: NIGHTLY } },
        },
      },
      backupStrategies: {
        s: {
          schedule: '0 3 * * *',
          destinations: [{ kind: 'hosted-service', name: 'c' }],
          repoTargets: { mail: { rpo: '5m' } },
        },
      },
    },
  } as never;

  it('judges the target repo by T + grace and the other by its cron', () => {
    const status = machineBackupTargetStatus(
      config,
      'm1',
      {
        repos: [
          {
            guid: MAIL,
            age_days: 0,
            last_capture_at: minutesAgo(11),
            last_success_at: minutesAgo(11),
          },
          { guid: NIGHTLY, age_days: 0, last_success_at: minutesAgo(11) },
        ],
      },
      NOW
    );
    expect(status.stale.map((s) => s.guid)).toEqual([MAIL]);
    expect(status.stale[0].targetSeconds).toBe(300);
  });
});
