import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockRemove = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockArchive = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { removeRepository: mockRemove, archiveRepository: mockArchive },
}));

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
const mockTokenState = vi.hoisted(() => ({ kind: 'ready' as 'ready' | 'missing' }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => mockTokenState,
}));

const infos = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
  },
}));

import { settleCloudBackups, settleConfigEntry } from '../repo-delete-settle.js';

const fork = { repositoryGuid: 'f1', grandGuid: 'g1' };
const grand = { repositoryGuid: 'g1', grandGuid: 'g1' };
const joined = () => infos.join('\n');

describe('repo delete settles the config entry', () => {
  beforeEach(() => {
    infos.length = 0;
    mockRemove.mockClear();
    mockArchive.mockClear();
  });

  it('archives a fork with no other holder, so the tag can be forked again and the GUID stays restorable', async () => {
    await settleConfigEntry('lva:m1', 'vm1', fork, false);
    expect(mockArchive).toHaveBeenCalledWith('lva:m1');
    expect(mockRemove).not.toHaveBeenCalled();
    expect(joined()).toContain('archived');
    expect(joined()).toContain('restoreHint');
    expect(joined()).not.toContain('configRetained');
  });

  it('ignores a push record for the machine just deleted from', async () => {
    await settleConfigEntry('lva:m1', 'vm1', { ...fork, pushState: { vm1: {} } }, false);
    expect(mockArchive).toHaveBeenCalledWith('lva:m1');
  });

  it('retains a fork pushed elsewhere and names the other machines', async () => {
    await settleConfigEntry('lva:m1', 'vm1', { ...fork, pushState: { vm2: {}, vm3: {} } }, false);
    expect(mockRemove).not.toHaveBeenCalled();
    expect(mockArchive).not.toHaveBeenCalled();
    expect(joined()).toContain('configRetainedElsewhere');
    expect(joined()).toContain('vm2, vm3');
  });

  it('retains a grand repo with the plain retained message', async () => {
    await settleConfigEntry('lva', 'vm1', grand, false);
    expect(mockRemove).not.toHaveBeenCalled();
    expect(joined()).toContain('configRetained:');
    expect(joined()).not.toContain('configRetainedElsewhere');
  });

  it('archives with --archive-config and prints no retained message', async () => {
    for (const cfg of [fork, grand, { ...fork, pushState: { vm2: {} } }]) {
      infos.length = 0;
      await settleConfigEntry('lva:m1', 'vm1', cfg, true);
      expect(mockArchive).toHaveBeenCalledWith('lva:m1');
      expect(joined()).toContain('archived');
      expect(joined()).not.toContain('Retained');
      expect(joined()).not.toContain('configRetained');
      expect(joined()).not.toContain('archiveHint');
    }
    expect(mockRemove).not.toHaveBeenCalled();
  });
});

describe('repo delete settles the cloud backups (F8)', () => {
  beforeEach(() => {
    infos.length = 0;
    mockFetch.mockReset();
    mockTokenState.kind = 'ready';
  });

  it('marks the lineage of a grand repo orphaned', async () => {
    mockFetch.mockResolvedValue({ orphanExpiresAt: '2027-01-23T00:00:00.000Z' });
    await settleCloudBackups('lva', grand, false);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0] as [string, { method: string }];
    expect(url).toBe('/account/api/v1/backups/lineages/g1/orphan');
    expect(init.method).toBe('POST');
    expect(joined()).toContain('2027-01-23');
  });

  it('--purge-backups deletes the lineage now and says how much was freed', async () => {
    mockFetch.mockResolvedValue({ deletedSnapshots: 4, freedBytes: 2048 });
    await settleCloudBackups('lva', grand, true);
    const [url, init] = mockFetch.mock.calls[0] as [string, { method: string }];
    expect(url).toBe('/account/api/v1/backups/lineages/g1');
    expect(init.method).toBe('DELETE');
    expect(joined()).toContain('"count":4');
  });

  it("leaves a fork alone: its lineage is its parent's", async () => {
    await settleCloudBackups('lva:m1', fork, false);
    await settleCloudBackups('lva:m1', fork, true);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('says nothing and calls nothing when no account token exists', async () => {
    mockTokenState.kind = 'missing';
    await settleCloudBackups('lva', grand, false);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(infos).toEqual([]);
  });

  it('an orphan call that fails is a warning, never a failed delete', async () => {
    mockFetch.mockRejectedValue(new Error('server down'));
    await expect(settleCloudBackups('lva', grand, false)).resolves.toBeUndefined();
  });

  it('a purge that fails is raised, so the operator knows the backups remain', async () => {
    mockFetch.mockRejectedValue(new Error('server down'));
    await expect(settleCloudBackups('lva', grand, true)).rejects.toThrow('server down');
  });
});
