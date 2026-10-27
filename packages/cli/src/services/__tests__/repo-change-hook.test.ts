/**
 * G4: the hook a repository-set change calls, and the unit text it re-renders.
 *
 * pushBackupSchedule lives in the same module as the hook, so it is observed through its first
 * effect: it reads the local config again and fails on an unknown strategy, which the hook turns
 * into the warning asserted here.
 */
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetLocalConfig = vi.hoisted(() => vi.fn());
const mockGetBackupStrategy = vi.hoisted(() => vi.fn());
vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getBackupStrategy: mockGetBackupStrategy,
    getCurrent: vi.fn(),
  },
}));
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../core/output.js', () => ({
  outputService: { warn: mockWarn, info: vi.fn(), success: vi.fn(), print: vi.fn() },
}));

const { reconcileBackupSchedules } = await import('../backup/repo-change-hook.js');
const { machineUnitSpecs } = await import('../backup/backup-schedule-targets.js');
const { computeDesiredUnits, computeReconcilePlan } = await import(
  '../backup/backup-schedule-reconcile.js'
);
const { sha256Hex } = await import('../backup/backup-schedule-unit-generator.js');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('reconcileBackupSchedules (G4 hook)', () => {
  it('a machine with no strategies is left alone: one config read, no push, no warning', async () => {
    mockGetLocalConfig.mockResolvedValue({ machines: { m1: {} } });
    await reconcileBackupSchedules('m1');
    expect(mockGetLocalConfig).toHaveBeenCalledOnce();
    expect(mockGetBackupStrategy).not.toHaveBeenCalled();
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('a machine with strategies pushes its schedule (the push resolves the bound strategies)', async () => {
    mockGetLocalConfig.mockResolvedValue({ machines: { m1: { backupStrategies: ['s'] } } });
    mockGetBackupStrategy.mockResolvedValue({
      schedule: '0 3 * * *',
      destinations: [],
      enabled: false,
    });
    await reconcileBackupSchedules('m1');
    // Hook read + the push's own read; the push then reached strategy loading for 's'.
    expect(mockGetLocalConfig).toHaveBeenCalledTimes(2);
    expect(mockGetBackupStrategy).toHaveBeenCalledExactlyOnceWith('s');
  });

  it('a failing push warns with the re-run hint and never throws', async () => {
    mockGetLocalConfig.mockResolvedValue({ machines: { m1: { backupStrategies: ['s'] } } });
    mockGetBackupStrategy.mockResolvedValue(undefined);
    await expect(reconcileBackupSchedules('m1')).resolves.toBeUndefined();
    expect(mockWarn).toHaveBeenCalledOnce();
    const message = String(mockWarn.mock.calls[0][0]);
    expect(message).toContain('Backup strategy "s" not found');
    expect(message).toContain('rdc backup schedule -m m1');
  });
});

describe('a new fork changes the rendered unit (G4)', () => {
  const G = {
    foo: '10000000-0000-4000-8000-000000000001',
    t1: '10000000-0000-4000-8000-000000000002',
  };
  const grandOnly = {
    foo: {
      placement: { machine: 'm1' },
      grand: 'latest',
      tags: { latest: { repositoryGuid: G.foo } },
    },
  };
  const withFork = {
    foo: {
      ...grandOnly.foo,
      tags: { ...grandOnly.foo.tags, t1: { repositoryGuid: G.t1 } },
    },
  };
  const configOf = (repositories: unknown) =>
    ({
      resources: {
        machines: { m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
        repositories,
      },
      state: {},
    }) as never;
  const strategies = [
    {
      name: 's',
      config: {
        schedule: '0 3 * * *',
        destinations: [{ kind: 'hosted-service' as const, name: 'chunks' }],
        include: ['foo'],
      },
    },
  ];
  const render = (repositories: unknown) =>
    computeDesiredUnits(
      machineUnitSpecs(strategies, configOf(repositories), 'm1'),
      '/usr/bin/renet'
    );

  it('adds the fork GUID to ExecStart, changes the service hash and reports the service changed', () => {
    const before = render(grandOnly).get('s');
    const after = render(withFork).get('s');
    expect(before && after).toBeTruthy();
    expect(before?.serviceContent).not.toContain(G.t1);
    expect(after?.serviceContent).toContain(G.t1);
    expect(sha256Hex(after?.serviceContent ?? '')).not.toBe(
      sha256Hex(before?.serviceContent ?? '')
    );

    const missing = { exists: false, sha256: null, path: '' };
    const remoteState = (b: NonNullable<typeof before>) => ({
      serviceFile: { exists: true, sha256: sha256Hex(b.serviceContent), path: '' },
      timerFile: { exists: true, sha256: sha256Hex(b.timerContent), path: '' },
      envFile: b.envFileContent
        ? { exists: true, sha256: sha256Hex(b.envFileContent), path: '' }
        : missing,
      isActiveService: false,
      isActiveAdhoc: false,
      isEnabledTimer: true,
      isActiveTimer: true,
      isFailed: false,
    });
    const plan = computeReconcilePlan(
      render(withFork),
      new Map([['s', remoteState(before as NonNullable<typeof before>)]])
    );
    expect(plan.toUpdate.map((d) => [d.name, d.changedFiles])).toEqual([['s', ['service']]]);
  });
});
