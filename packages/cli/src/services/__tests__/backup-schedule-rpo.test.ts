/**
 * Rendering of a declared protection target (D-rpo): the timer text, the finite timeouts, the flags on
 * the verb, exact-ref resolution and what happens to the main unit when a target comes and goes.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { computeDesiredUnits, computeReconcilePlan } from '../backup/backup-schedule-reconcile.js';
import {
  machineUnitSpecs,
  type ScheduledStrategy,
  strategyUnitSpecs,
} from '../backup/backup-schedule-targets.js';

const RENET = '/usr/lib/rediacc/renet/current/renet';
const G = {
  mail: '10000000-0000-4000-8000-000000000001',
  mailFork: '10000000-0000-4000-8000-000000000002',
  gitlab: '20000000-0000-4000-8000-000000000001',
};
const config = {
  resources: {
    machines: { m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
    repositories: {
      mail: {
        placement: { machine: 'm1' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.mail }, trial: { repositoryGuid: G.mailFork } },
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
const implicit = { key: undefined, path: WK_DATASTORE_PATH };

function strategy(over: Partial<ScheduledStrategy> = {}): ScheduledStrategy {
  return { schedule: '0 3 * * *', destinations: [hosted], ...over };
}

function render(over: Partial<ScheduledStrategy> = {}) {
  return computeDesiredUnits(
    machineUnitSpecs([{ name: 's', config: strategy(over) }], config, 'm1'),
    RENET
  );
}

const execLines = (svc: string): string[] =>
  svc
    .split('\n')
    .filter((l) => l.startsWith('ExecStart='))
    .map((l) => l.slice('ExecStart='.length));

describe('exact-ref resolution of a per-repo target (F1)', () => {
  const guids = (over: Partial<ScheduledStrategy>): string[] =>
    strategyUnitSpecs('s', strategy(over), config, 'm1', implicit)
      .filter((spec) => spec.repoRef !== undefined)
      .flatMap((spec) => spec.scope.include ?? []);

  it('a bare name renders exactly the grand, not its forks', () => {
    expect(guids({ repoTargets: { mail: { rpo: '15m' } } })).toEqual([G.mail]);
  });

  it('name:tag renders exactly that tag', () => {
    expect(guids({ repoTargets: { 'mail:trial': { rpo: '15m' } } })).toEqual([G.mailFork]);
  });

  it('name:* asks for the whole family, one unit per repository', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ repoTargets: { 'mail:*': { rpo: '15m' } } }),
      config,
      'm1',
      implicit
    );
    expect(specs.map((s) => s.unitName)).toEqual(['s', 's.repo.mail.latest', 's.repo.mail.trial']);
  });

  it('an exact entry beats a family entry for the same repository', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ repoTargets: { 'mail:*': { rpo: '30m' }, 'mail:trial': { rpo: '5m' } } }),
      config,
      'm1',
      implicit
    );
    expect(specs.find((s) => s.unitName === 's.repo.mail.trial')?.schedule).toBe('*/5 * * * *');
    expect(specs.find((s) => s.unitName === 's.repo.mail.latest')?.schedule).toBe('*/30 * * * *');
  });

  it('refuses an unknown tag and an unknown name', () => {
    expect(() => guids({ repoTargets: { 'mail:nope': { rpo: '15m' } } })).toThrow(/no tag "nope"/);
    expect(() => guids({ repoTargets: { ghost: { rpo: '15m' } } })).toThrow(/not in the config/);
  });
});

describe.each([
  ['5m', '*-*-* *:00/5:00', 2400, '15m'],
  ['15m', '*-*-* *:00/15:00', 6000, '45m'],
  ['30m', '*-*-* *:00/30:00', 11_400, '1h30m'],
])('the units of a %s target', (rpo, onCalendar, timeoutStart, deadline) => {
  const units = render({ repoTargets: { gitlab: { rpo: rpo as '5m' } } });
  const unit = units.get('s.repo.gitlab.latest');

  it('renders a timer with a stable per-timer offset, accurate to a second', () => {
    expect(unit?.timerContent).toContain(`OnCalendar=${onCalendar}`);
    expect(unit?.timerContent).toContain('RandomizedDelaySec=60s');
    expect(unit?.timerContent).toContain('FixedRandomDelay=true');
    expect(unit?.timerContent).toContain('AccuracySec=1s');
    expect(unit?.timerContent).toContain('Persistent=true');
  });

  it('renders a finite start timeout of 2 x deadline + 10 minutes', () => {
    expect(unit?.serviceContent).toContain(`TimeoutStartSec=${timeoutStart}`);
    expect(unit?.serviceContent).not.toContain('TimeoutStartSec=infinity');
  });

  it('passes the target and the deadline to the verb', () => {
    expect(execLines(unit?.serviceContent ?? '')[0]).toContain(
      `--target ${rpo} --deadline ${deadline}`
    );
  });
});

describe('what is never rendered', () => {
  it('RuntimeMaxSec appears in no unit of any target (a oneshot ignores it)', () => {
    const units = render({
      rpo: '15m',
      repoTargets: { gitlab: { rpo: '5m' }, 'mail:trial': { rpo: '1h' } },
    });
    expect(units.size).toBeGreaterThan(4);
    for (const unit of units.values()) {
      expect(unit.serviceContent + unit.timerContent).not.toContain('RuntimeMaxSec');
    }
  });

  it('jitter and timeouts are only for target units: a nightly unit keeps infinity and no jitter', () => {
    const nightly = render().get('s');
    expect(nightly?.serviceContent).toContain('TimeoutStartSec=infinity');
    expect(nightly?.timerContent).not.toContain('RandomizedDelaySec');
    expect(execLines(nightly?.serviceContent ?? '')[0]).not.toContain('--target');
  });

  it('--cell-bytes is omitted unless a cell size is chosen', () => {
    const lines = [...render({ rpo: '15m' }).values()].flatMap((u) => execLines(u.serviceContent));
    expect(lines.join('\n')).not.toContain('--cell-bytes');
  });
});

describe('a target changes the target repo and nothing else', () => {
  it('the nightly unit differs only by excluding the target repo', () => {
    const before = render().get('s');
    const after = render({ repoTargets: { gitlab: { rpo: '15m' } } }).get('s');
    expect(after?.timerContent).toBe(before?.timerContent);
    expect(after?.serviceContent.replaceAll(` --exclude-repo ${G.gitlab}`, '')).toBe(
      before?.serviceContent
    );
    expect(after?.serviceContent).toContain(`--exclude-repo ${G.gitlab}`);
  });

  it('removing the target returns the repo to the main scope and removes its units', () => {
    const withTarget = render({ repoTargets: { gitlab: { rpo: '15m' } } });
    const without = render();
    expect(without.get('s')?.serviceContent).not.toContain(G.gitlab);
    const remote = new Map(
      [...withTarget.keys()].map((name) => [
        name,
        {
          serviceFile: {
            path: `/etc/systemd/system/rediacc-backup-${name}.service`,
            exists: true,
            sha256: 'x',
          },
          timerFile: { path: '', exists: false, sha256: null },
          envFile: { path: '', exists: false, sha256: null },
          isActiveService: false,
          isActiveAdhoc: false,
          isEnabledTimer: false,
          isActiveTimer: false,
          isFailed: false,
        },
      ])
    );
    const plan = computeReconcilePlan(without, remote);
    const removed = plan.toRemove.map((d) => d.name);
    expect(removed).toContain('s.repo.gitlab.latest');
    expect(removed).toContain('s.repo.gitlab.latest.alert');
    expect(removed).not.toContain('s');
  });
});

describe('the strategy-level target', () => {
  it('renders the main unit from the target, over the whole scope', () => {
    const unit = render({
      rpo: '30m',
      hookFailure: 'abort',
      hookTimeout: '45s',
      indexEvery: '2h',
    }).get('s');
    expect(unit?.timerContent).toContain('OnCalendar=*-*-* *:00/30:00');
    const line = execLines(unit?.serviceContent ?? '')[0];
    expect(line).toContain('--target 30m --deadline 1h30m');
    expect(line).toContain('--hook-timeout 45s --hook-failure abort --index-every 2h');
  });

  it('a per-repo field overrides the strategy field of the same name', () => {
    const units = render({
      hookFailure: 'abort',
      repoTargets: { gitlab: { rpo: '15m', hookFailure: 'continue' } },
    });
    expect(execLines(units.get('s.repo.gitlab.latest')?.serviceContent ?? '')[0]).toContain(
      '--hook-failure continue'
    );
    expect(execLines(units.get('s')?.serviceContent ?? '')[0]).toContain('--hook-failure abort');
  });

  it('carries --cell-bytes as bytes for a chosen cell size, never the grid-change consent', () => {
    const line = execLines(
      render({ repoTargets: { gitlab: { rpo: '15m', cellSize: '1M' } } }).get(
        's.repo.gitlab.latest'
      )?.serviceContent ?? ''
    )[0];
    expect(line).toContain('--cell-bytes 1048576');
    expect(line).not.toContain('--accept-grid-change');
  });
});
