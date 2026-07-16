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
      resources: {
        repositories: {
          shop: {
            grand: 'main',
            tags: { main: { repositoryGuid: h.GUID } },
            placement: { machine: 'm1' },
          },
        },
        machines: { m1: { ip: '10.0.0.1', user: 'root' } },
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
