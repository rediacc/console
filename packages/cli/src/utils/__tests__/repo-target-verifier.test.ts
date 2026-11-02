/**
 * repo-target default step-5 verifier injection (design: derived-routing repair
 * family, R6). resolveRepoRef is the single funnel that turns "mutating repo
 * verb" into "GUID-presence check on the derived machine": a mutating call gets
 * the default verifier, a read-only call does not, and an explicitly-passed
 * verifier wins.
 *
 * Since agent/plans/PLAN-detached-jobs.md section 14 the check is the vault
 * precondition `expect: repo_present` of the verb's first job (recorded through
 * expectRepoState), not a repository_list probe before the work. Only a
 * converge-to-absent verb (absentOk) still probes, because it decides on the
 * answer; its probe failure fails OPEN.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  GUID: '11111111-1111-4111-8111-111111111111',
  /** What probeRepoPresent resolves to for the next call (undefined = probe failure). */
  present: undefined as boolean | undefined,
  probeRepoPresent: vi.fn(),
  expectRepoState: vi.fn(),
}));
const probeRepoPresent = h.probeRepoPresent;
const expectRepoState = h.expectRepoState;

vi.mock('../../services/executor/executor-factory.js', () => ({
  expectRepoState: h.expectRepoState,
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({
      state: { datastores: { ds1: { attachedTo: 'cp1' } } },
      resources: {
        repositories: {
          shop: {
            grand: 'main',
            tags: { main: { repositoryGuid: h.GUID } },
            placement: { machine: 'm1' },
          },
          kshop: {
            grand: 'main',
            tags: { main: { repositoryGuid: h.GUID } },
            placement: { datastore: 'ds1' },
          },
        },
        datastores: { ds1: { cluster: 'c1' } },
        machines: { m1: { ip: '10.0.0.1', user: 'root' }, cp1: { ip: '10.0.0.2', user: 'root' } },
      },
    }),
  },
}));

vi.mock('../../services/repo/repo-mount-check.js', () => ({
  probeRepoPresent: h.probeRepoPresent,
}));

import { CliExitError } from '../cli-exit-error.js';
import { resolveRepoRef } from '../repo-target.js';

beforeEach(() => {
  h.present = true;
  probeRepoPresent.mockImplementation(() => Promise.resolve(h.present));
});
afterEach(() => vi.clearAllMocks());

describe('resolveRepoRef — default step-5 verifier (R6)', () => {
  it('hands a mutating verb the repo_present precondition instead of probing', async () => {
    const resolved = await resolveRepoRef('shop');
    expect(resolved.machineName).toBe('m1');
    expect(probeRepoPresent).not.toHaveBeenCalled();
    expect(expectRepoState).toHaveBeenCalledOnce();
    expect(expectRepoState).toHaveBeenCalledWith({
      machine: 'm1',
      aliases: ['shop', 'shop:main', h.GUID],
      repoGuid: h.GUID,
      repoName: 'shop',
      expect: 'repo_present',
    });
  });

  it('a tagged ref records the tag key', async () => {
    await resolveRepoRef('shop:main');
    expect(expectRepoState.mock.calls[0][0].aliases).toEqual(['shop:main', 'shop:main', h.GUID]);
  });

  it('skips the check for a read-only verb', async () => {
    const resolved = await resolveRepoRef('shop', { readOnly: true });
    expect(resolved.machineName).toBe('m1');
    expect(probeRepoPresent).not.toHaveBeenCalled();
    expect(expectRepoState).not.toHaveBeenCalled();
  });

  it('lets an explicitly-passed verifier win over the default', async () => {
    const verifyMount = vi.fn().mockResolvedValue(true);
    await resolveRepoRef('shop', { verifyMount });
    expect(verifyMount).toHaveBeenCalledOnce();
    expect(probeRepoPresent).not.toHaveBeenCalled();
    expect(expectRepoState).not.toHaveBeenCalled();
  });

  it('absentOk still probes and converges on a definite absence', async () => {
    h.present = false;
    const resolved = await resolveRepoRef('shop', { absentOk: true });
    expect(probeRepoPresent).toHaveBeenCalledWith(h.GUID, 'm1');
    expect(resolved.imageAbsent).toBe(true);
    expect(expectRepoState).not.toHaveBeenCalled();
  });

  it('absentOk fails OPEN when the probe infrastructure fails (undefined)', async () => {
    h.present = undefined;
    const resolved = await resolveRepoRef('shop', { absentOk: true });
    expect(resolved.imageAbsent).toBeUndefined();
  });

  it('an explicit refusing verifier still exits 12', async () => {
    await expect(
      resolveRepoRef('shop', { verifyMount: vi.fn().mockResolvedValue(false) })
    ).rejects.toBeInstanceOf(CliExitError);
  });
});

// #92 (found live by the B1 window, the datastore arm's first-ever execution): probeRepoPresent rides repository_list, which is docker-world-only, so probing the DATASTORE arm false-refused every mutating verb on a cluster repo with exit 12. The arm now passes verification through to dispatch. Mutation control: re-point the datastore arm at the probe and the first test goes red
// (h.present=false would refuse).
describe('resolveRepoRef — datastore arm skips the docker probe (#92)', () => {
  it('never consults the probe nor records a precondition for a datastore-placed ref', async () => {
    h.present = false;
    const resolved = await resolveRepoRef('kshop', { absentOk: true });
    expect(resolved.machineName).toBe('cp1');
    expect(resolved.kubeCluster).toBe('c1');
    expect(probeRepoPresent).not.toHaveBeenCalled();
    expect(expectRepoState).not.toHaveBeenCalled();
  });

  it('records the precondition for a machine-placed ref', async () => {
    await resolveRepoRef('shop');
    expect(expectRepoState).toHaveBeenCalledOnce();
  });
});
