/**
 * repo-target default step-5 verifier injection (design: derived-routing repair
 * family, R6). resolveRepoRef is the single funnel that turns "mutating repo
 * verb" into "GUID-presence probe on the derived machine": a mutating call gets
 * the default verifier, a read-only call does not, and an explicitly-passed
 * verifier wins. Probe-infrastructure failure fails OPEN.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  GUID: '11111111-1111-4111-8111-111111111111',
  /** What probeRepoPresent resolves to for the next call (undefined = probe failure). */
  present: undefined as boolean | undefined,
  probeRepoPresent: vi.fn(),
}));
const probeRepoPresent = h.probeRepoPresent;

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
  it('injects the presence probe for a mutating verb', async () => {
    const resolved = await resolveRepoRef('shop');
    expect(resolved.machineName).toBe('m1');
    expect(probeRepoPresent).toHaveBeenCalledWith(h.GUID, 'm1');
  });

  it('skips the probe for a read-only verb', async () => {
    const resolved = await resolveRepoRef('shop', { readOnly: true });
    expect(resolved.machineName).toBe('m1');
    expect(probeRepoPresent).not.toHaveBeenCalled();
  });

  it('lets an explicitly-passed verifier win over the default', async () => {
    const verifyMount = vi.fn().mockResolvedValue(true);
    await resolveRepoRef('shop', { verifyMount });
    expect(verifyMount).toHaveBeenCalledOnce();
    expect(probeRepoPresent).not.toHaveBeenCalled();
  });

  it('exits 12 when the probe reports definite absence', async () => {
    h.present = false;
    await expect(resolveRepoRef('shop')).rejects.toBeInstanceOf(CliExitError);
  });

  it('fails OPEN when the probe infrastructure fails (undefined)', async () => {
    h.present = undefined;
    const resolved = await resolveRepoRef('shop');
    expect(resolved.machineName).toBe('m1');
  });
});

// #92 (found live by the B1 window — the datastore arm's first-ever execution):
// probeRepoPresent rides repository_list, which is docker-world-only, so probing
// the DATASTORE arm false-refused every mutating verb on a cluster repo with
// exit 12. The arm now passes verification through to dispatch. Mutation
// control: re-point the datastore arm at the probe and the first test goes red
// (h.present=false would refuse).
describe('resolveRepoRef — datastore arm skips the docker probe (#92)', () => {
  it('never consults the probe for a datastore-placed ref, even when it would refuse', async () => {
    h.present = false;
    const resolved = await resolveRepoRef('kshop');
    expect(resolved.machineName).toBe('cp1');
    expect(resolved.kubeCluster).toBe('c1');
    expect(probeRepoPresent).not.toHaveBeenCalled();
  });

  it('still consults the probe for a machine-placed ref', async () => {
    await resolveRepoRef('shop');
    expect(probeRepoPresent).toHaveBeenCalledWith(h.GUID, 'm1');
  });
});
