/**
 * The pre-flight is only worth having if the placement paths actually reach it,
 * so this file tests the WIRING rather than the check: it replaces the
 * pre-flight with one that refuses everything, and asserts that a replica-set
 * placement stops before dispatching anything to a machine.
 *
 * The unit behaviour of the check itself lives in
 * services/__tests__/license-preflight.test.ts.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAssertSlots, mockExecute } = vi.hoisted(() => ({
  mockAssertSlots: vi.fn(),
  mockExecute: vi.fn(),
}));

vi.mock('../../account/license-preflight.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../account/license-preflight.js')>()),
  assertMachineSlotsAvailable: mockAssertSlots,
}));

vi.mock('../../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

const { provisionReplicaDatastores } = await import('../repo-replicate.js');

const base = {
  repo: 'sqldb',
  repoGuid: 'guid-sqldb',
  setName: 'set1',
  datastore: 'ds-data',
  snapshot: 'replicate-set1',
  controlMachine: 'cp1',
  controlMount: '/mnt/rediacc-ds/ds-control-prod',
};

const nodes = [
  { machine: 'n1', ip: '10.0.0.1' },
  { machine: 'n2', ip: '10.0.0.2' },
];

describe('replica placement asks for machine slots first', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAssertSlots.mockResolvedValue(undefined);
    mockExecute.mockResolvedValue({ success: true, stdout: '{}' });
  });

  it('counts the DISTINCT nodes the round-robin reaches, not the replica count', async () => {
    // Three replicas over two nodes touch two machines, so two slots. Charging
    // three would refuse a placement that fits.
    await provisionReplicaDatastores({ ...base, replicas: 3, nodes });

    expect(mockAssertSlots).toHaveBeenCalledWith({ machineCount: 2 });
  });

  it('refuses before the snapshot, so a refused placement changes nothing', async () => {
    mockAssertSlots.mockRejectedValue(new Error('Maximum machines (5) reached'));

    await expect(provisionReplicaDatastores({ ...base, replicas: 3, nodes })).rejects.toThrow(
      /Maximum machines/
    );

    // Not even the datastore snapshot ran: this is the whole point of checking
    // early rather than discovering the wall on the third fork-attach.
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('reports the partial state when a placement dies part-way through', async () => {
    // First replica lands, second fails: a real, working, incomplete deployment.
    // Keyed on the replica's own tag rather than a call count, so the test does
    // not silently start asserting the wrong replica when the dispatch sequence
    // for one replica changes.
    mockExecute.mockImplementation((options: unknown) => {
      if (JSON.stringify(options).includes('set1-r2')) {
        throw new Error('Maximum machines (5) reached');
      }
      return Promise.resolve({ success: true, stdout: '{}' });
    });

    const error = await provisionReplicaDatastores({ ...base, replicas: 2, nodes }).then(
      () => {
        throw new Error('expected provisionReplicaDatastores to reject, but it resolved');
      },
      (e: unknown) => e as Error
    );

    expect(error.message).toContain('Maximum machines (5) reached');
    expect(error.message).toContain('1 machine(s) completed (n1)');
    expect(error.message).toContain('Nothing was rolled back');
    expect(error.message).toContain('rdc repo replicate sqldb --replicas 2');
  });
});
