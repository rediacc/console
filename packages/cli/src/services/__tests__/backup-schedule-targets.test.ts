/**
 * Which repositories each scheduled backup unit covers (G1, G5, G10).
 *
 * renet takes GUIDs only, so every name a strategy holds is resolved here against the config, and
 * only repositories placed on a unit's datastore reach that unit.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import {
  coverageByGuid,
  machineUnitSpecs,
  type ScheduledStrategy,
  scheduleDatastoresFor,
  strategyUnitSpecs,
} from '../backup/backup-schedule-targets.js';
import {
  buildBackupCommands,
  generateTimerUnit,
} from '../backup/backup-schedule-unit-generator.js';

const G = {
  mail: '10000000-0000-4000-8000-000000000001',
  mailFork: '10000000-0000-4000-8000-000000000002',
  gitlab: '20000000-0000-4000-8000-000000000001',
  elsewhere: '30000000-0000-4000-8000-000000000001',
  pool: '40000000-0000-4000-8000-000000000001',
  rbd: '50000000-0000-4000-8000-000000000001',
};

const config = {
  resources: {
    machines: {
      m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH },
      m2: { ip: '10.0.0.2', user: 'u' },
    },
    datastores: {
      pool: { backend: { kind: 'local', machine: 'm1', path: '/mnt/pool' } },
      other: { backend: { kind: 'local', machine: 'm2', path: '/mnt/other' } },
      shared: { backend: { kind: 'rbd', pool: 'p', image: 'i' } },
    },
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
      remote: {
        placement: { machine: 'm2' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.elsewhere } },
      },
      poolrepo: {
        placement: { datastore: 'pool' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.pool } },
      },
      rbdrepo: {
        placement: { datastore: 'shared' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.rbd } },
      },
    },
  },
  state: { datastores: { shared: { attachedTo: 'm1', mountPath: '/mnt/shared' } } },
} as never;

const hosted = { kind: 'hosted-service' as const, name: 'chunks' };
const strategy = (over: Partial<ScheduledStrategy> = {}): ScheduledStrategy => ({
  schedule: '0 3 * * *',
  destinations: [hosted],
  ...over,
});
const implicit = { key: undefined, path: WK_DATASTORE_PATH };

describe('scheduleDatastoresFor (G5)', () => {
  it('lists the implicit datastore, named local ones on the machine, and attached rbd ones', () => {
    expect(scheduleDatastoresFor(config, 'm1')).toEqual([
      implicit,
      { key: 'pool', path: '/mnt/pool' },
      { key: 'shared', path: '/mnt/shared' },
    ]);
    expect(scheduleDatastoresFor(config, 'm2')).toEqual([
      { key: undefined, path: WK_DATASTORE_PATH },
      { key: 'other', path: '/mnt/other' },
    ]);
  });
});

describe('strategyUnitSpecs (G1)', () => {
  it('a family name covers the grand and its forks, as GUIDs', () => {
    const [spec] = strategyUnitSpecs('s', strategy({ include: ['mail'] }), config, 'm1', implicit);
    expect(spec.scope).toEqual({ include: [G.mail, G.mailFork], exclude: [] });
  });

  it('name:tag covers exactly that tag', () => {
    const [spec] = strategyUnitSpecs(
      's',
      strategy({ include: ['mail:trial'] }),
      config,
      'm1',
      implicit
    );
    expect(spec.scope.include).toEqual([G.mailFork]);
  });

  it('keeps only repositories placed on the target datastore', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ include: ['gitlab', 'remote', 'poolrepo'] }),
      config,
      'm1',
      implicit
    );
    expect(specs).toHaveLength(1);
    expect(specs[0].scope.include).toEqual([G.gitlab]);
  });

  it('an include list with nothing on this datastore yields NO unit, never an all-repos one', () => {
    expect(
      strategyUnitSpecs('s', strategy({ include: ['remote'] }), config, 'm1', implicit)
    ).toEqual([]);
  });

  it('an exclude list becomes exclude GUIDs on an otherwise all-repos unit', () => {
    const [spec] = strategyUnitSpecs('s', strategy({ exclude: ['mail'] }), config, 'm1', implicit);
    expect(spec.scope).toEqual({ exclude: [G.mail, G.mailFork] });
  });

  it('refuses an unknown name and an unknown tag', () => {
    expect(() =>
      strategyUnitSpecs('s', strategy({ include: ['ghost'] }), config, 'm1', implicit)
    ).toThrow(/"ghost", which is not in the config/);
    expect(() =>
      strategyUnitSpecs('s', strategy({ exclude: ['mail:nope'] }), config, 'm1', implicit)
    ).toThrow(/has no tag "nope"/);
  });

  it('refuses a repository with no placement rather than guessing its datastore', () => {
    const unplaced = {
      resources: {
        machines: { m1: { ip: '10.0.0.1', user: 'u' } },
        repositories: { loose: { grand: 'latest', tags: { latest: { repositoryGuid: G.mail } } } },
      },
    } as never;
    expect(() =>
      strategyUnitSpecs('s', strategy({ include: ['loose'] }), unplaced, 'm1', implicit)
    ).toThrow(/has no placement/);
  });

  it('renders the resolved scope as GUID flags only', () => {
    const [spec] = strategyUnitSpecs('s', strategy({ include: ['mail'] }), config, 'm1', implicit);
    const { commands } = buildBackupCommands(
      spec.strategy,
      spec.strategy.destinations,
      spec.datastore.path,
      '/usr/bin/renet',
      spec.scope
    );
    expect(commands).toEqual([
      `/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH} --repo ${G.mail} --repo ${G.mailFork}`,
    ]);
  });
});

describe('machineUnitSpecs (G5)', () => {
  it('renders one unit per datastore, each scoped to its own repositories', () => {
    const specs = machineUnitSpecs(
      [{ name: 's', config: strategy({ include: ['gitlab', 'poolrepo', 'rbdrepo'] }) }],
      config,
      'm1'
    );
    expect(specs.map((s) => [s.unitName, s.datastore.path, s.scope.include])).toEqual([
      ['s', WK_DATASTORE_PATH, [G.gitlab]],
      ['s.ds.pool', '/mnt/pool', [G.pool]],
      ['s.ds.shared', '/mnt/shared', [G.rbd]],
    ]);
  });

  it('an all-repos strategy runs on every datastore of the machine', () => {
    const specs = machineUnitSpecs([{ name: 's', config: strategy() }], config, 'm1');
    expect(specs.map((s) => s.unitName)).toEqual(['s', 's.ds.pool', 's.ds.shared']);
  });
});

describe('per-repo cadence (G10)', () => {
  it('gives an overridden repo its own unit and timer, and takes it out of the main unit', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ repoSchedules: { gitlab: '0 * * * *' } }),
      config,
      'm1',
      implicit
    );
    expect(specs.map((s) => [s.unitName, s.schedule, s.scope])).toEqual([
      ['s', '0 3 * * *', { exclude: [G.gitlab] }],
      ['s.repo.gitlab.latest', '0 * * * *', { include: [G.gitlab], exclude: [] }],
    ]);
    expect(generateTimerUnit(specs[1].unitName, 'x')).toContain(
      'Rediacc Backup Timer (s.repo.gitlab.latest)'
    );
  });

  it('with an include list, the override leaves the main unit and no exclude flag is needed', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ include: ['mail', 'gitlab'], repoSchedules: { 'mail:trial': '*/15 * * * *' } }),
      config,
      'm1',
      implicit
    );
    expect(specs.map((s) => [s.unitName, s.scope.include])).toEqual([
      ['s', [G.mail, G.gitlab]],
      ['s.repo.mail.trial', [G.mailFork]],
    ]);
  });

  it('ignores an override for a repo the strategy excludes or does not include', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ include: ['gitlab'], repoSchedules: { mail: '0 * * * *' } }),
      config,
      'm1',
      implicit
    );
    expect(specs.map((s) => s.unitName)).toEqual(['s']);
  });

  it('refuses an override whose cron is not 5 fields', () => {
    const [spec] = strategyUnitSpecs(
      's',
      strategy({ repoSchedules: { gitlab: 'hourly' } }),
      config,
      'm1',
      implicit
    );
    expect(() =>
      buildBackupCommands(spec.strategy, spec.strategy.destinations, '/d', '/r', spec.scope)
    ).toThrow(/Per-repo schedule for "gitlab"/);
  });
});

describe('coverageByGuid', () => {
  it('maps each covered GUID to the crons of the units covering it', () => {
    const specs = strategyUnitSpecs(
      's',
      strategy({ exclude: ['mail:trial'], repoSchedules: { gitlab: '0 * * * *' } }),
      config,
      'm1',
      implicit
    );
    const cov = coverageByGuid(specs, config, 'm1');
    expect(cov.get(G.mail)).toEqual(['0 3 * * *']);
    expect(cov.get(G.gitlab)).toEqual(['0 * * * *']);
    expect(cov.has(G.mailFork)).toBe(false);
    expect(cov.has(G.elsewhere)).toBe(false);
    expect(cov.has(G.pool)).toBe(false);
  });
});
