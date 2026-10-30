/**
 * The executor seam's vault directives (agent/plans/PLAN-detached-jobs.md
 * section 14, J3b): what `resolveRepoRef` (`expect`) and
 * `ensureRepositoryNetworkId` (`network_id: "auto"`) record is stamped onto the
 * first call naming that repository on that machine, spent by it, and an ID the
 * start allocated is recorded in the config by the invoking process.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions, ExecuteResult } from '../types.js';

const h = vi.hoisted(() => ({
  probeRepoPresent: vi.fn(),
  recordNetworkId: vi.fn(),
}));

vi.mock('../../repo/repo-mount-check.js', () => ({ probeRepoPresent: h.probeRepoPresent }));
vi.mock('../../config/network-id-discovery.js', () => ({ recordNetworkId: h.recordNetworkId }));

const { attachDecorator, expectRepoState, requestNetworkIdAuto, resetVaultDirectives } =
  await import('../executor-factory.js');

const GUID = '33333333-3333-4333-8333-333333333333';
const seen: ExecuteOptions[] = [];
let answer: Partial<ExecuteResult> = {};
const executor = attachDecorator({
  execute(options) {
    seen.push(options);
    return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, ...answer });
  },
});

const call = (extra: Partial<ExecuteOptions> = {}) =>
  executor.execute({
    functionName: 'repository_up',
    machineName: 'm1',
    params: { repository: 'shop' },
    requestId: 'r',
    ...extra,
  });

const presence = (machine = 'm1') =>
  expectRepoState({
    machine,
    aliases: ['shop', 'shop:main', GUID],
    repoGuid: GUID,
    repoName: 'shop',
    expect: 'repo_present',
  });

beforeEach(() => {
  seen.length = 0;
  answer = {};
  resetVaultDirectives();
  h.probeRepoPresent.mockReset();
  h.recordNetworkId.mockReset();
});

afterEach(() => resetVaultDirectives());

describe('expect directive', () => {
  it('is stamped on the first call naming the repo on its machine, and spent by it', async () => {
    presence();
    await call();
    await call();
    expect(seen[0].expect).toBe('repo_present');
    expect(seen[1].expect).toBeUndefined();
    expect(h.probeRepoPresent).not.toHaveBeenCalled();
  });

  it('matches the GUID or tag key spelling of the same repo', async () => {
    presence();
    await call({ params: { repository: GUID } });
    expect(seen[0].expect).toBe('repo_present');
  });

  it('control: a call on another machine or repo, or with no repo, takes nothing', async () => {
    presence();
    await call({ machineName: 'm2' });
    await call({ params: { repository: 'other' } });
    await call({ functionName: 'repository_list', params: {} });
    expect(seen.map((o) => o.expect)).toEqual([undefined, undefined, undefined]);
    await call();
    expect(seen[3].expect).toBe('repo_present');
  });

  it('a caller explicit expect wins', async () => {
    presence();
    await call({ expect: 'repo_unmounted' });
    expect(seen[0].expect).toBe('repo_unmounted');
  });

  it('a renet execute exemption is checked by the client-side probe instead', async () => {
    presence();
    h.probeRepoPresent.mockResolvedValue(true);
    await call({ functionName: 'repository_exec', params: { repository: 'shop', tty: true } });
    expect(h.probeRepoPresent).toHaveBeenCalledWith(GUID, 'm1');
    expect(seen[0].expect).toBeUndefined();
  });

  it('the exemption refuses with exit 12 on a definite absence and runs nothing', async () => {
    presence();
    h.probeRepoPresent.mockResolvedValue(false);
    const error = await call({
      functionName: 'repository_exec',
      params: { repository: 'shop', tty: true },
    }).catch((e: unknown) => e);
    expect(error).toMatchObject({ exitCode: 12, code: 'STATE_MISMATCH' });
    expect(seen).toHaveLength(0);
  });

  it('the exemption fails open when the probe itself fails', async () => {
    presence();
    h.probeRepoPresent.mockResolvedValue(undefined);
    await call({ functionName: 'repository_exec', params: { repository: 'shop', tty: true } });
    expect(seen).toHaveLength(1);
  });
});

describe('network_id auto directive', () => {
  const auto = () =>
    requestNetworkIdAuto({
      machine: 'm1',
      aliases: ['shop:main', 'shop', GUID],
      repoGuid: GUID,
      repoName: 'shop',
      recordAs: 'shop:main',
    });

  it('is stamped, and the allocated ID is recorded under the config key', async () => {
    auto();
    answer = { networkId: 2944 };
    const result = await call();
    expect(seen[0].networkIdAuto).toBe(true);
    expect(result.networkId).toBe(2944);
    expect(h.recordNetworkId).toHaveBeenCalledWith('shop:main', 2944);
  });

  it('merges with the expect of the same repo into one directive', async () => {
    presence();
    auto();
    await call();
    expect(seen[0]).toMatchObject({ expect: 'repo_present', networkIdAuto: true });
    await call();
    expect(seen[1].networkIdAuto).toBeUndefined();
  });

  it('a caller params auto is recorded under the repository it named', async () => {
    answer = { networkId: 3008 };
    await call({ params: { repository: 'new', network_id: 'auto' } });
    expect(h.recordNetworkId).toHaveBeenCalledWith('new', 3008);
  });

  it('control: no ID on the result records nothing', async () => {
    auto();
    await call();
    expect(h.recordNetworkId).not.toHaveBeenCalled();
  });
});
