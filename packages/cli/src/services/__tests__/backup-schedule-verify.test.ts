/**
 * Verification units of a scheduled backup (F9, F12): verify after the snapshot, an OnFailure report, a staggered
 * full-verify timer, the strategy `verify` block, and the cadence handed to renet's dead-man check.
 *
 * The rendered text is the contract. The flags are cross-checked against renet's own cobra declarations in
 * backup-schedule-renet-contract.test.ts, so a unit that names a flag renet lacks fails there.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { RdcConfigSchema } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import { cronMaxGapSeconds } from '../backup/backup-schedule-interval.js';
import {
  computeDesiredUnits,
  computeReconcilePlan,
  type RemoteUnitState,
} from '../backup/backup-schedule-reconcile.js';
import { machineUnitSpecs, type ScheduledStrategy } from '../backup/backup-schedule-targets.js';

const RENET = '/usr/lib/rediacc/renet/current/renet';
const G = {
  mail: '10000000-0000-4000-8000-000000000001',
  gitlab: '20000000-0000-4000-8000-000000000001',
};

const config = {
  resources: {
    machines: { m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
    repositories: {
      mail: {
        placement: { machine: 'm1' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.mail, credential: 'TOPSECRET-credential-value' } },
      },
      gitlab: {
        placement: { machine: 'm1' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.gitlab } },
      },
    },
  },
} as never;

const hosted = { kind: 'hosted-service' as const, name: 'chunks' };
const strat = (over: Partial<ScheduledStrategy> = {}): ScheduledStrategy => ({
  schedule: '0 3 * * *',
  destinations: [hosted],
  ...over,
});

const render = (over: Partial<ScheduledStrategy> = {}, name = 'nightly') =>
  computeDesiredUnits(machineUnitSpecs([{ name, config: strat(over) }], config, 'm1'), RENET, 4);

const execLines = (service: string) =>
  service
    .split('\n')
    .filter((l) => l.startsWith('ExecStart='))
    .map((l) => l.slice('ExecStart='.length));

describe('the snapshot service', () => {
  it('runs verify after the snapshot with the same scope flags, so a failed snapshot stops it', () => {
    const units = render({ exclude: ['gitlab'] });
    const lines = execLines(units.get('nightly')?.serviceContent ?? '');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain(' backup snapshot ');
    expect(lines[1]).toBe(
      `${RENET} backup verify --datastore ${WK_DATASTORE_PATH} --exclude-repo ${G.gitlab} --level spot`
    );
    expect(lines[0]).toContain(`--exclude-repo ${G.gitlab}`);
  });

  it('names the failure report as OnFailure', () => {
    const svc = render().get('nightly')?.serviceContent ?? '';
    expect(svc).toMatch(/^\[Unit\]\n(?:.*\n)*?OnFailure=rediacc-backup-nightly\.alert\.service$/m);
  });

  it('hands renet the cadence, so the dead-man check has a nextExpectedAt', () => {
    const svc = render().get('nightly')?.serviceContent ?? '';
    expect(execLines(svc)[0]).toContain('--expected-interval 86400s');
    const hourly = render({ schedule: '0 * * * *' }).get('nightly')?.serviceContent ?? '';
    expect(execLines(hourly)[0]).toContain('--expected-interval 3600s');
  });

  it('a per-repo target unit states its target and leaves the next-run estimate to renet', () => {
    const units = render({ repoTargets: { gitlab: { rpo: '30m' } } });
    const override = [...units.entries()].find(([k]) => k.includes('.repo.gitlab'));
    const line = execLines(override?.[1].serviceContent ?? '')[0];
    expect(line).toContain('--target 30m --deadline 1h30m');
    expect(line).not.toContain('--expected-interval');
  });
});

describe('the verify timer unit', () => {
  it('runs a full, rotating verify at one core and low priority', () => {
    const verify = render().get('nightly.verify');
    expect(verify).toBeDefined();
    const svc = verify?.serviceContent ?? '';
    expect(execLines(svc)).toEqual([
      `${RENET} backup verify --datastore ${WK_DATASTORE_PATH} --level full --next-due 7d`,
    ]);
    expect(svc).toContain('CPUQuota=100%');
    expect(svc).toContain('Nice=10');
    expect(svc).toContain('OnFailure=rediacc-backup-nightly.verify.alert.service');
  });

  it('is scoped like the unit it belongs to, and paces its read when the strategy caps reads', () => {
    const units = render({ include: ['mail'], readBandwidthLimit: '20M' });
    const lines = execLines(units.get('nightly.verify')?.serviceContent ?? '');
    expect(lines[0]).toBe(
      `${RENET} backup verify --datastore ${WK_DATASTORE_PATH} --repo ${G.mail} --level full --next-due 7d --read-bwlimit 20000000`
    );
  });

  it('fires daily at a staggered, deterministic time that differs between units', () => {
    const a = render({}, 'alpha').get('alpha.verify')?.timerContent ?? '';
    const again = render({}, 'alpha').get('alpha.verify')?.timerContent ?? '';
    expect(a).toBe(again);
    expect(a).toMatch(/OnCalendar=\*-\*-\* 0[1-5]:\d\d:00/);
    expect(a).toContain('Persistent=true');
    const times = new Set(
      ['alpha', 'beta', 'gamma', 'delta', 'eps', 'zeta'].map(
        (n) => /OnCalendar=(.*)/.exec(render({}, n).get(`${n}.verify`)?.timerContent ?? '')?.[1]
      )
    );
    expect(times.size).toBeGreaterThan(1);
  });

  it('deepSchedule replaces the default time', () => {
    const t = render({ verify: { deepSchedule: '30 4 * * 6' } }).get(
      'nightly.verify'
    )?.timerContent;
    expect(t).toContain('OnCalendar=Sat *-*-* 04:30:00');
  });
});

describe('the failure report units', () => {
  it('runs renet backup report for the same scope, with a fixed reason and no secret', () => {
    const units = render({ include: ['mail'] });
    const alert = units.get('nightly.alert');
    expect(alert).toBeDefined();
    expect(execLines(alert?.serviceContent ?? '')).toEqual([
      `${RENET} backup report --datastore ${WK_DATASTORE_PATH} --repo ${G.mail} --kind snapshot --status failed --reason 'systemd unit rediacc-backup-nightly.service failed'`,
    ]);
    expect(alert?.timerContent).toBe('');
    expect(alert?.envFileContent).toBe('');
    expect(alert?.serviceContent).not.toMatch(/EnvironmentFile|setenv|TOPSECRET/);
  });

  it('the verify failure report names kind verify and level full', () => {
    const alert = render().get('nightly.verify.alert');
    expect(execLines(alert?.serviceContent ?? '')[0]).toContain(
      '--kind verify --level full --status failed --reason'
    );
  });

  it('a timerless unit is staged as a service only', () => {
    const desired = render();
    const plan = computeReconcilePlan(desired, new Map());
    const alert = plan.toCreate.find((d) => d.name === 'nightly.alert');
    expect(alert?.changedFiles).toEqual(['service']);
    const verify = plan.toCreate.find((d) => d.name === 'nightly.verify');
    expect(verify?.changedFiles).toEqual(['service', 'timer']);
  });
});

describe('the strategy verify block', () => {
  it('off renders neither the spot after the run nor any verify unit', () => {
    const units = render({ verify: { off: true } });
    expect(execLines(units.get('nightly')?.serviceContent ?? '')).toHaveLength(1);
    expect([...units.keys()].sort((a, b) => a.localeCompare(b))).toEqual([
      'nightly',
      'nightly.alert',
    ]);
  });

  it('spotAfterRun false drops only the spot, keeping the timer', () => {
    const units = render({ verify: { spotAfterRun: false } });
    expect(execLines(units.get('nightly')?.serviceContent ?? '')).toHaveLength(1);
    expect(units.has('nightly.verify')).toBe(true);
  });

  const parse = (verify: unknown) =>
    RdcConfigSchema.safeParse({
      schemaVersion: 3,
      id: '11111111-2222-4333-8444-555555555555',
      version: 1,
      resources: {
        backupStrategies: { nightly: { destinations: [hosted], schedule: '0 3 * * *', verify } },
      },
    });

  it('is accepted by the schema', () => {
    const ok = parse({ spotAfterRun: false, off: false, deepSchedule: '0 4 * * *' });
    expect(ok.success).toBe(true);
    expect(
      (ok.data?.resources?.backupStrategies as Record<string, { verify?: unknown }>).nightly.verify
    ).toEqual({ spotAfterRun: false, off: false, deepSchedule: '0 4 * * *' });
  });

  it('refuses a misspelled key and a bad cron instead of stripping them', () => {
    expect(parse({ offf: true }).success).toBe(false);
    expect(parse({ deepSchedule: 'nope' }).success).toBe(false);
  });
});

describe('removal and identity', () => {
  it('removing the strategy removes every unit it rendered', () => {
    const desired = render();
    const remote = new Map<string, RemoteUnitState>();
    for (const [name, unit] of desired) {
      const file = (suffix: string, has: boolean) => ({
        path: `/etc/systemd/system/rediacc-backup-${name}.${suffix}`,
        exists: has,
        sha256: null,
      });
      remote.set(name, {
        serviceFile: file('service', true),
        timerFile: file('timer', unit.timerContent !== ''),
        envFile: { path: '', exists: false, sha256: null },
        isActiveService: false,
        isActiveAdhoc: false,
        isEnabledTimer: false,
        isActiveTimer: false,
        isFailed: false,
      });
    }
    const plan = computeReconcilePlan(new Map(), remote);
    expect(plan.toRemove.map((d) => d.name).sort((a, b) => a.localeCompare(b))).toEqual(
      ['nightly', 'nightly.alert', 'nightly.verify', 'nightly.verify.alert'].sort((a, b) =>
        a.localeCompare(b)
      )
    );
  });

  it('no rendered unit ever carries --accept-identity-change', () => {
    for (const over of [{}, { mode: 'cold' as const }, { verify: { off: true } }]) {
      for (const unit of render(over).values()) {
        expect(unit.serviceContent).not.toContain('accept-identity-change');
      }
    }
  });

  it('two units that render to one name are refused, not overwritten', () => {
    const specs = machineUnitSpecs([{ name: 'a', config: strat() }], config, 'm1');
    expect(() => computeDesiredUnits([...specs, ...specs], RENET, 4)).toThrow(/more than one unit/);
  });
});

describe('cronMaxGapSeconds', () => {
  it.each([
    ['*/5 * * * *', 300],
    ['0 * * * *', 3600],
    ['0 3 * * *', 86400],
    ['0 2,14 * * *', 43200],
    ['0 3 * * 1', 604800],
    ['0 3 * * 1-5', 259200],
    ['0 3 1 * *', 31 * 86400],
    // Jan 1 to Jul 1 is 182 days in 2024, but Jul 1 to the next Jan 1 is 184.
    ['0 3 1 1,7 *', 184 * 86400],
  ])('%s has a longest gap of %i seconds', (cron, seconds) => {
    expect(cronMaxGapSeconds(cron)).toBe(seconds);
  });

  it('a day-of-month that starts with a star is unrestricted, so the day-of-week still narrows it', () => {
    // Treated as restricted, `*/2` OR Monday would fire at least every second day.
    expect(cronMaxGapSeconds('0 3 */2 * 1')).toBeGreaterThanOrEqual(7 * 86400);
  });

  it('is independent of the clock, since the unit text is hashed', () => {
    expect(cronMaxGapSeconds('0 3 * * *')).toBe(cronMaxGapSeconds('0 3 * * *'));
  });
});
