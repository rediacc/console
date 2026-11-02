import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockFetch = vi.hoisted(() => vi.fn());
const mockInfo = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
const mockAskInput = vi.hoisted(() => vi.fn());
const mockResolveRef = vi.hoisted(() => vi.fn());
const mockPolicy = vi.hoisted(() => vi.fn());
const repos = vi.hoisted(() => new Map<string, { repositoryGuid: string; grandGuid?: string }>());
// Every configService call other than the one read is recorded here: the purge must never write the repo record.
const configWrites = vi.hoisted(() => [] as string[]);

// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: mockSuccess,
    warn: mockWarn,
    error: vi.fn(),
    print: vi.fn(),
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: new Proxy(
    {},
    {
      get: (_target, prop: string | symbol) => {
        if (typeof prop !== 'string' || prop === 'then') return undefined;
        if (prop === 'getRepository') {
          return async (key: string) => repos.get(key);
        }
        return (...args: unknown[]) => {
          configWrites.push(`${prop}(${JSON.stringify(args)})`);
        };
      },
    }
  ),
}));
vi.mock('../../utils/errors.js', () => {
  class ValidationError extends Error {}
  return {
    ValidationError,
    getOutputFormat: () => 'table',
    handleError: (error: unknown) => {
      throw error;
    },
  };
});
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRefLocal: mockResolveRef }));
vi.mock('../../utils/command-policy.js', () => ({
  CMD: { BACKUP_PURGE: 'backup purge' },
  assertCommandPolicy: mockPolicy,
}));
vi.mock('../../utils/prompt.js', () => ({ askInput: mockAskInput }));

import { registerBackupPurge } from '../backup-purge.js';

const LINEAGE = 'grand-guid-1';

/** Answers the account calls the way the server does for a lineage with two snapshots. */
function serveAccount(): void {
  let purged = false;
  mockFetch.mockImplementation((path: string, init?: { method?: string }) => {
    if (init?.method === 'DELETE') {
      purged = true;
      return Promise.resolve({
        lineageGuid: LINEAGE,
        done: true,
        freedBytes: 4096,
        deletedSnapshots: 2,
        deletedChunks: 7,
        deletedBytes: 4096,
      });
    }
    if (path.startsWith('/account/api/v1/backups/manifests')) {
      return Promise.resolve({ manifests: [{ snapshotId: 's1' }, { snapshotId: 's2' }] });
    }
    if (path === '/account/api/v1/backups/usage') {
      return Promise.resolve({
        lineages: purged
          ? []
          : [{ lineageGuid: LINEAGE, storedBytes: 4096, chunkCount: 7, logicalBytes: 0 }],
      });
    }
    return Promise.reject(new Error(`unexpected account call ${path}`));
  });
}

/** One DELETE answer: the last round carries the ledger totals, earlier ones a remaining estimate. */
function purgeRound(done: boolean): Record<string, unknown> {
  return {
    lineageGuid: LINEAGE,
    done,
    freedBytes: done ? 4096 : 0,
    deletedSnapshots: done ? 2 : 0,
    deletedChunks: 5,
    deletedBytes: 100,
    remainingChunks: done ? undefined : 10,
  };
}

async function run(args: string[]): Promise<void> {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupPurge(backup);
  await backup.parseAsync(['purge', ...args], { from: 'user' });
}

function deleteCalls(): unknown[][] {
  return mockFetch.mock.calls.filter(
    (c) => (c[1] as { method?: string } | undefined)?.method === 'DELETE'
  );
}

describe('backup purge', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockInfo.mockReset();
    mockSuccess.mockReset();
    mockWarn.mockReset();
    mockAskInput.mockReset();
    mockPolicy.mockReset();
    mockResolveRef.mockReset();
    mockResolveRef.mockImplementation(async (ref: string) => ({ repoKey: ref, name: ref }));
    repos.clear();
    repos.set('shop', { repositoryGuid: LINEAGE });
    repos.set('shop:fork', { repositoryGuid: 'fork-guid', grandGuid: LINEAGE });
    configWrites.length = 0;
    serveAccount();
  });

  it('--dry-run reports the lineage, snapshot count and stored bytes, and sends no DELETE', async () => {
    await run(['shop', '--dry-run']);

    expect(deleteCalls()).toHaveLength(0);
    expect(mockAskInput).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledWith(`/account/api/v1/backups/manifests?lineage=${LINEAGE}`);
    expect(mockFetch).toHaveBeenCalledWith('/account/api/v1/backups/usage');
    expect(mockInfo).toHaveBeenCalledWith('commands.backup.purge.dryRun');
    expect(configWrites).toEqual([]);
  });

  it('-y sends exactly one DELETE, to the resolved lineage, without prompting', async () => {
    await run(['shop', '-y']);

    const deletes = deleteCalls();
    expect(deletes).toHaveLength(1);
    expect(deletes[0][0]).toBe(`/account/api/v1/backups/lineages/${LINEAGE}`);
    expect(mockAskInput).not.toHaveBeenCalled();
    expect(mockPolicy).toHaveBeenCalledWith('backup purge', 'shop');
    expect(mockSuccess).toHaveBeenCalledWith('commands.backup.purge.success');
    // The server reports no chunk count, so the usage before and after is printed.
    expect(mockInfo).toHaveBeenCalledWith('commands.backup.purge.usageDelta');
    expect(configWrites).toEqual([]);
  });

  it('loops DELETE until done, printing progress per round, then reads usage once more', async () => {
    const served = mockFetch.getMockImplementation() as (...a: unknown[]) => Promise<unknown>;
    let rounds = 0;
    mockFetch.mockImplementation((path: string, init?: { method?: string }) =>
      init?.method === 'DELETE' ? Promise.resolve(purgeRound(++rounds === 3)) : served(path, init)
    );
    await run(['shop', '-y']);

    expect(deleteCalls()).toHaveLength(3);
    const progress = mockInfo.mock.calls.filter((c) => c[0] === 'commands.backup.purge.progress');
    expect(progress).toHaveLength(2);
    expect(mockSuccess).toHaveBeenCalledWith('commands.backup.purge.success');
    expect(mockInfo).toHaveBeenCalledWith('commands.backup.purge.usageDelta');
    // The post-purge usage read happens after the last DELETE.
    const calls = mockFetch.mock.calls.map(
      (c) => (c[1] as { method?: string } | undefined)?.method ?? c[0]
    );
    expect(calls.at(-1)).toBe('/account/api/v1/backups/usage');
    expect(calls.lastIndexOf('DELETE')).toBe(calls.length - 2);
  });

  it('takes freedBytes and deletedSnapshots from the final round, summing chunks and bytes', async () => {
    const rounds = [purgeRound(false), purgeRound(false), purgeRound(true)];
    mockFetch.mockImplementation(() => Promise.resolve(rounds.shift()));
    const { purgeLineageRounds } = await import('../backup-purge.js');
    const total = await purgeLineageRounds('shop', LINEAGE, String);
    expect(total.freedBytes).toBe(4096);
    expect(total.deletedSnapshots).toBe(2);
    expect(total.deletedChunks).toBe(15);
    expect(total.deletedBytes).toBe(300);
  });

  it('treats a response with no done field as the final round (an older server)', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        lineageGuid: LINEAGE,
        freedBytes: 7,
        deletedSnapshots: 1,
        deletedChunks: 2,
        deletedBytes: 3,
      })
    );
    const { purgeLineageRounds } = await import('../backup-purge.js');
    const total = await purgeLineageRounds('shop', LINEAGE, String);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(total.freedBytes).toBe(7);
  });

  it('stops with an error when the account never reports done', async () => {
    const served = mockFetch.getMockImplementation() as (...a: unknown[]) => Promise<unknown>;
    mockFetch.mockImplementation((path: string, init?: { method?: string }) =>
      init?.method === 'DELETE'
        ? Promise.resolve({
            lineageGuid: LINEAGE,
            done: false,
            freedBytes: 0,
            deletedSnapshots: 0,
            deletedChunks: 1,
            deletedBytes: 1,
          })
        : served(path, init)
    );
    await expect(run(['shop', '-y'])).rejects.toThrow('commands.backup.purge.tooManyRounds');
    expect(deleteCalls()).toHaveLength(200);
    expect(mockSuccess).not.toHaveBeenCalled();
  });

  it('warns when the usage read after a successful purge fails', async () => {
    let usageReads = 0;
    const served = mockFetch.getMockImplementation() as (...a: unknown[]) => Promise<unknown>;
    mockFetch.mockImplementation((path: string, init?: unknown) => {
      if (path === '/account/api/v1/backups/usage' && ++usageReads === 2) {
        return Promise.reject(new Error('usage down'));
      }
      return served(path, init);
    });
    await run(['shop', '-y']);

    expect(deleteCalls()).toHaveLength(1);
    expect(mockSuccess).toHaveBeenCalledWith('commands.backup.purge.success');
    expect(mockWarn).toHaveBeenCalledWith('commands.backup.purge.usageUnavailable');
    expect(mockInfo).not.toHaveBeenCalledWith('commands.backup.purge.usageDelta');
  });

  it('a typed name that does not match cancels and sends nothing destructive', async () => {
    mockAskInput.mockResolvedValue('shopp');
    await run(['shop']);

    expect(mockAskInput).toHaveBeenCalledTimes(1);
    expect(deleteCalls()).toHaveLength(0);
    expect(mockInfo).toHaveBeenCalledWith('status.cancelled');
    expect(configWrites).toEqual([]);
  });

  it('typing the repository name confirms the purge', async () => {
    mockAskInput.mockResolvedValue('shop');
    await run(['shop']);

    expect(deleteCalls()).toHaveLength(1);
  });

  it('an unknown repo is refused before any account call', async () => {
    await expect(run(['ghost', '-y'])).rejects.toThrow('commands.backup.purge.notFound');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(configWrites).toEqual([]);
  });

  it('a ref the resolver rejects is refused before any account call', async () => {
    mockResolveRef.mockRejectedValue(new Error('repository "ghost" is not in this config.'));
    await expect(run(['ghost', '-y'])).rejects.toThrow('not in this config');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("a fork is refused before any account call: its lineage is the parent's", async () => {
    await expect(run(['shop:fork', '-y'])).rejects.toThrow('commands.backup.purge.forkRefused');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('the agent policy refusal stops the purge before any account call', async () => {
    mockPolicy.mockRejectedValue(new Error('errors.agent.grandGuard'));
    await expect(run(['shop', '-y'])).rejects.toThrow('errors.agent.grandGuard');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('a lineage with nothing stored sends no DELETE', async () => {
    mockFetch.mockImplementation(async (path: string) =>
      path === '/account/api/v1/backups/usage' ? { lineages: [] } : { manifests: [] }
    );
    await run(['shop', '-y']);

    expect(deleteCalls()).toHaveLength(0);
    expect(mockInfo).toHaveBeenCalledWith('commands.backup.purge.nothingStored');
  });
});
