import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PLAN-config-networkid-discovery T3: a synced ID beats discovery, a discovered ID beats allocation, a definite absence allocates above the target machine's used set, an unreachable machine fails closed, and a mismatch adopts the persisted ID.

const GUID = '11111111-1111-1111-1111-111111111111';

const h = vi.hoisted(() => ({
  /** Per-function canned results; a missing entry means the call fails. */
  responses: {} as Record<string, { success: boolean; stdout?: string }>,
  calls: [] as { functionName: string; machineName: string; datastore?: string }[],
}));

vi.mock('../../executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: vi.fn((opts: { functionName: string; machineName: string; datastore?: string }) => {
      h.calls.push({
        functionName: opts.functionName,
        machineName: opts.machineName,
        datastore: opts.datastore,
      });
      const r = h.responses[opts.functionName] ?? { success: false };
      return Promise.resolve({ exitCode: r.success ? 0 : 1, durationMs: 1, ...r });
    }),
  }),
}));

function listing(entries: { name: string; network_id?: number }[]): string {
  return JSON.stringify(entries);
}

function used(ids: number[]): string {
  return JSON.stringify(ids.map((network_id) => ({ kind: 'repo', name: 'x', network_id })));
}

beforeEach(() => {
  h.responses = {};
  h.calls = [];
});

describe('resolveMissingNetworkId', () => {
  it('returns the machine persisted ID without allocating (N1b)', async () => {
    h.responses.repository_list = {
      success: true,
      stdout: listing([
        { name: 'other', network_id: 2816 },
        { name: GUID, network_id: 2880 },
      ]),
    };
    const allocate = vi.fn();
    const { resolveMissingNetworkId } = await import('../network-id-discovery.js');
    const id = await resolveMissingNetworkId({
      repository: 'y',
      repoGuid: GUID,
      target: { machine: 'm' },
      allocate,
    });
    expect(id).toBe(2880);
    expect(allocate).not.toHaveBeenCalled();
    expect(h.calls.map((c) => c.functionName)).toEqual(['repository_list']);
  });

  it('allocates above the target machine used set on a definite absence', async () => {
    h.responses.repository_list = {
      success: true,
      stdout: listing([{ name: 'other', network_id: 2816 }]),
    };
    h.responses.network_used = { success: true, stdout: used([2816, 2880, 4032]) };
    const allocate = vi.fn((floor: number[]) => Promise.resolve(Math.max(...floor) + 64));
    const { resolveMissingNetworkId } = await import('../network-id-discovery.js');
    const id = await resolveMissingNetworkId({
      repository: 'z',
      repoGuid: GUID,
      target: { machine: 'm' },
      allocate,
    });
    expect(allocate).toHaveBeenCalledWith([2816, 2880, 4032]);
    expect(id).toBe(4096);
    expect(h.calls.every((c) => c.machineName === 'm')).toBe(true);
  });

  it('falls back to the listed IDs when the machine has no network_used (rollout skew)', async () => {
    h.responses.repository_list = {
      success: true,
      stdout: listing([{ name: 'other', network_id: 3008 }]),
    };
    const allocate = vi.fn(() => Promise.resolve(3072));
    const { resolveMissingNetworkId } = await import('../network-id-discovery.js');
    await resolveMissingNetworkId({
      repository: 'z',
      repoGuid: GUID,
      target: { machine: 'm' },
      allocate,
    });
    expect(allocate).toHaveBeenCalledWith([3008]);
  });

  it('fails closed on an unreachable machine and never allocates (N6, D6(a))', async () => {
    const allocate = vi.fn();
    const { resolveMissingNetworkId, NetworkIdUndiscoverableError } = await import(
      '../network-id-discovery.js'
    );
    await expect(
      resolveMissingNetworkId({
        repository: 'y',
        repoGuid: GUID,
        target: { machine: 'm' },
        allocate,
      })
    ).rejects.toBeInstanceOf(NetworkIdUndiscoverableError);
    expect(allocate).not.toHaveBeenCalled();
  });

  it('fails closed when the repo is present but its mirror records no ID', async () => {
    h.responses.repository_list = { success: true, stdout: listing([{ name: GUID }]) };
    const allocate = vi.fn();
    const { resolveMissingNetworkId, NetworkIdUndiscoverableError } = await import(
      '../network-id-discovery.js'
    );
    await expect(
      resolveMissingNetworkId({
        repository: 'y',
        repoGuid: GUID,
        target: { machine: 'm' },
        allocate,
      })
    ).rejects.toBeInstanceOf(NetworkIdUndiscoverableError);
    expect(allocate).not.toHaveBeenCalled();
  });

  it('probes the named datastore the repo lives on', async () => {
    h.responses.repository_list = {
      success: true,
      stdout: listing([{ name: GUID, network_id: 2944 }]),
    };
    const { resolveMissingNetworkId } = await import('../network-id-discovery.js');
    await resolveMissingNetworkId({
      repository: 'y',
      repoGuid: GUID,
      target: { machine: 'm', datastore: `${WK_DATASTORE_PATH}/datastores/fast` },
      allocate: vi.fn(),
    });
    expect(h.calls[0].datastore).toBe(`${WK_DATASTORE_PATH}/datastores/fast`);
  });
});

describe('ensureRepositoryNetworkId', () => {
  it('a synced local ID wins and makes no machine call (N1a)', async () => {
    const { configService } = await import('../config-resources.js');
    const keySpy = vi.spyOn(configService, 'getRepositoryKey').mockResolvedValue('y');
    const stateSpy = vi.spyOn(configService, 'getResourceState').mockResolvedValue({
      getRepositories: () => ({ y: { repositoryGuid: GUID, networkId: 2880 } }),
    } as never);
    const { ensureRepositoryNetworkId } = await import('../network-id-discovery.js');
    expect(await ensureRepositoryNetworkId('y', { machine: 'm' })).toBe(2880);
    expect(h.calls).toEqual([]);
    keySpy.mockRestore();
    stateSpy.mockRestore();
  });
});

describe('network-ID conflicts', () => {
  const inUse = JSON.stringify({
    holder: { kind: 'repo', name: 'x-guid', datastore: WK_DATASTORE_PATH },
    code: 'network_id_in_use',
    message: 'held',
    network_id: 2880,
  });

  it('parses the renet refusal from stderr, prefixed or not', async () => {
    const { parseNetworkIdConflict } = await import('../network-id-discovery.js');
    expect(parseNetworkIdConflict({ stderr: `noise\n${inUse}\n` })).toEqual({
      code: 'network_id_in_use',
      networkId: 2880,
      holder: { kind: 'repo', name: 'x-guid', datastore: WK_DATASTORE_PATH },
    });
    expect(parseNetworkIdConflict({ stderr: `[relay] ${inUse}` })?.code).toBe('network_id_in_use');
    expect(parseNetworkIdConflict({ stderr: 'renet exited with code 1' })).toBeUndefined();
  });

  it('a mismatch adopts the persisted ID without allocating', async () => {
    const { nextNetworkIdAfterConflict } = await import('../network-id-discovery.js');
    const allocate = vi.fn();
    const id = await nextNetworkIdAfterConflict(
      { code: 'network_id_mismatch', networkId: 2816, persistedNetworkId: 2880 },
      { machine: 'm' },
      allocate
    );
    expect(id).toBe(2880);
    expect(allocate).not.toHaveBeenCalled();
  });

  it('an ID in use allocates past the holder and the machine used set', async () => {
    h.responses.network_used = { success: true, stdout: used([2816]) };
    const { nextNetworkIdAfterConflict } = await import('../network-id-discovery.js');
    const allocate = vi.fn(() => Promise.resolve(2944));
    await nextNetworkIdAfterConflict(
      { code: 'network_id_in_use', networkId: 2880 },
      { machine: 'm' },
      allocate
    );
    expect(allocate).toHaveBeenCalledWith([2816, 2880]);
  });

  function refusal(networkId: number): string {
    return JSON.stringify({ code: 'network_id_in_use', message: 'held', network_id: networkId });
  }

  async function withRepoState(
    body: (setRepositories: ReturnType<typeof vi.fn>) => Promise<void>
  ): Promise<void> {
    const { configService } = await import('../config-resources.js');
    const keySpy = vi.spyOn(configService, 'getRepositoryKey').mockResolvedValue('z');
    const setRepositories = vi.fn();
    const stateSpy = vi.spyOn(configService, 'getResourceState').mockResolvedValue({
      getRepositories: () => ({ z: { repositoryGuid: GUID, networkId: 2880 } }),
      setRepositories,
    } as never);
    try {
      await body(setRepositories);
    } finally {
      keySpy.mockRestore();
      stateSpy.mockRestore();
    }
  }

  // The allocator hands out the first multiple of 64 above everything in the floor.
  const allocateAbove = (floor: number[]): Promise<number> =>
    Promise.resolve(Math.max(0, ...floor) + 64);

  it('runWithNetworkIdRetry moves past every refused ID and succeeds on the third', async () => {
    const { runWithNetworkIdRetry } = await import('../network-id-discovery.js');
    await withRepoState(async (setRepositories) => {
      const refuse = (id: number) => ({
        success: false,
        exitCode: 17,
        durationMs: 1,
        stderr: refusal(id),
      });
      const run = vi
        .fn()
        .mockResolvedValueOnce(refuse(2816))
        .mockResolvedValueOnce(refuse(2880))
        .mockResolvedValueOnce({ success: true, exitCode: 0, durationMs: 1 });
      const result = await runWithNetworkIdRetry({
        repoKey: 'z',
        target: { machine: 'm' },
        networkId: 2816,
        run,
        allocate: allocateAbove,
      });
      expect(run.mock.calls.map((c) => c[0])).toEqual([2816, 2880, 2944]);
      expect(setRepositories).toHaveBeenLastCalledWith({
        z: { repositoryGuid: GUID, networkId: 2944 },
      });
      expect(result.success).toBe(true);
    });
  });

  it('runWithNetworkIdRetry stops at the attempt cap and returns the last refusal', async () => {
    const { runWithNetworkIdRetry, MAX_NETWORK_ID_ATTEMPTS } = await import(
      '../network-id-discovery.js'
    );
    await withRepoState(async () => {
      let next = 2816;
      const run = vi.fn().mockImplementation(() => {
        const id = next;
        next += 64;
        return Promise.resolve({
          success: false,
          exitCode: 17,
          durationMs: 1,
          stderr: refusal(id),
        });
      });
      const result = await runWithNetworkIdRetry({
        repoKey: 'z',
        target: { machine: 'm' },
        networkId: 2816,
        run,
        allocate: allocateAbove,
      });
      expect(run).toHaveBeenCalledTimes(MAX_NETWORK_ID_ATTEMPTS);
      expect(result.success).toBe(false);
    });
  });

  it('runWithNetworkIdRetry stops when a mismatch names a persisted ID already refused', async () => {
    const { runWithNetworkIdRetry } = await import('../network-id-discovery.js');
    await withRepoState(async () => {
      const mismatch = JSON.stringify({
        code: 'network_id_mismatch',
        message: 'persisted',
        network_id: 2944,
        persisted_network_id: 2880,
      });
      const fail = (stderr: string) => ({ success: false, exitCode: 17, durationMs: 1, stderr });
      // 2816 mismatches (persisted 2880); 2880 is in use; the fresh 2944 mismatches back to 2880.
      const run = vi
        .fn()
        .mockResolvedValueOnce(
          fail(
            JSON.stringify({
              code: 'network_id_mismatch',
              message: 'persisted',
              network_id: 2816,
              persisted_network_id: 2880,
            })
          )
        )
        .mockResolvedValueOnce(fail(refusal(2880)))
        .mockResolvedValue(fail(mismatch));
      const result = await runWithNetworkIdRetry({
        repoKey: 'z',
        target: { machine: 'm' },
        networkId: 2816,
        run,
        allocate: allocateAbove,
      });
      expect(run.mock.calls.map((c) => c[0])).toEqual([2816, 2880, 2944]);
      expect(result.success).toBe(false);
      expect(result.stderr).toBe(mismatch);
    });
  });

  it('runWithNetworkIdRetry does not retry an unrelated failure', async () => {
    const { runWithNetworkIdRetry } = await import('../network-id-discovery.js');
    const run = vi
      .fn()
      .mockResolvedValue({ success: false, exitCode: 1, durationMs: 1, stderr: 'disk full' });
    await runWithNetworkIdRetry({ repoKey: 'z', target: { machine: 'm' }, networkId: 2880, run });
    expect(run).toHaveBeenCalledTimes(1);
  });
});

describe('parseNetworkUsed', () => {
  it('reads the claims line and tolerates log noise', async () => {
    const { parseNetworkUsed } = await import('../network-id-discovery.js');
    expect(parseNetworkUsed(`info line\n${used([2816, 2880])}\n`)).toEqual([2816, 2880]);
    expect(parseNetworkUsed('[]')).toEqual([]);
    expect(parseNetworkUsed('no json')).toBeUndefined();
  });
});
