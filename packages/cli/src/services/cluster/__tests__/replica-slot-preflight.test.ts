/**
 * The pre-flight is only worth having if the placement path actually reaches it,
 * so this file tests the WIRING rather than the check: it replaces the pre-flight
 * with one that refuses everything, and asserts that a replica-set placement stops
 * before recording anything or starting a job.
 *
 * The unit behaviour of the check itself lives in
 * services/__tests__/license-preflight.test.ts.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAssertSlots, mockRun, mockRecord } = vi.hoisted(() => ({
  mockAssertSlots: vi.fn(),
  mockRun: vi.fn(),
  mockRecord: vi.fn(),
}));

vi.mock('../../account/license-preflight.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../account/license-preflight.js')>()),
  assertMachineSlotsAvailable: mockAssertSlots,
}));
vi.mock('../cluster-job.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../cluster-job.js')>()),
  runClusterPhase: mockRun,
}));
vi.mock('../cluster-target.js', () => ({
  resolveExecutionTarget: vi.fn(() => Promise.resolve({ machineName: 'cp1', cluster: 'prod' })),
}));
vi.mock('../../config/config-cluster-ops.js', () => ({
  getCluster: vi.fn(() =>
    Promise.resolve({ pools: [{ name: 'w', role: 'hyperconverged', count: 2 }] })
  ),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn(() => Promise.resolve({ state: {} })),
    setStateBucket: mockRecord,
    getLocalMachine: vi.fn((name: string) => Promise.resolve({ ip: `10.0.0.${name.slice(-1)}` })),
    getRepository: vi.fn(() => Promise.resolve({ repositoryGuid: 'guid-sqldb' })),
  },
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const { replicateRepo } = await import('../repo-replicate-ops.js');

const base = {
  repo: 'sqldb',
  cluster: 'prod',
  datastore: 'ds-data',
  image: 'postgres:16',
  port: 5432,
};

describe('replica placement asks for machine slots first', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAssertSlots.mockResolvedValue(undefined);
    mockRecord.mockResolvedValue(undefined);
    mockRun.mockResolvedValue({ result: { success: true }, pending: true, unfinished: [] });
  });

  it('counts the DISTINCT nodes the round-robin reaches, not the replica count', async () => {
    // Three replicas over two nodes touch two machines, so two slots. Charging three would refuse a placement that fits.
    await replicateRepo({ ...base, replicas: 3 });

    expect(mockAssertSlots).toHaveBeenCalledWith({ machineCount: 2 });
  });

  it('refuses before anything is recorded or started, so a refused placement changes nothing', async () => {
    mockAssertSlots.mockRejectedValue(new Error('Maximum machines (5) reached'));

    await expect(replicateRepo({ ...base, replicas: 3 })).rejects.toThrow(/Maximum machines/);

    expect(mockRecord).not.toHaveBeenCalled();
    expect(mockRun).not.toHaveBeenCalled();
  });

  it('reports the partial state when the first job fails', async () => {
    mockRun.mockRejectedValue(new Error('Replica step "replica_fork" failed on cp1: no space'));

    const error = await replicateRepo({ ...base, replicas: 2 }).then(
      () => {
        throw new Error('expected replicateRepo to reject, but it resolved');
      },
      (e: unknown) => e as Error
    );

    expect(error.message).toContain('no space');
    expect(error.message).toContain('Nothing was rolled back');
    expect(error.message).toContain('rdc repo replicate sqldb --replicas 2');
  });
});
