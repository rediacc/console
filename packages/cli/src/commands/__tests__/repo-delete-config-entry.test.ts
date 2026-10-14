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

const infos = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
  },
}));

import { settleConfigEntry } from '../repo-create-delete.js';

const fork = { repositoryGuid: 'f1', grandGuid: 'g1' };
const grand = { repositoryGuid: 'g1', grandGuid: 'g1' };
const joined = () => infos.join('\n');

describe('repo delete settles the config entry', () => {
  beforeEach(() => {
    infos.length = 0;
    mockRemove.mockClear();
    mockArchive.mockClear();
  });

  it('drops a fork with no other holder, so the tag can be forked again', async () => {
    await settleConfigEntry('lva:m1', 'vm1', fork, false);
    expect(mockRemove).toHaveBeenCalledWith('lva:m1');
    expect(joined()).toContain('configDropped');
    expect(joined()).not.toContain('configRetained');
  });

  it('ignores a push record for the machine just deleted from', async () => {
    await settleConfigEntry('lva:m1', 'vm1', { ...fork, pushState: { vm1: {} } }, false);
    expect(mockRemove).toHaveBeenCalledWith('lva:m1');
  });

  it('retains a fork pushed elsewhere and names the other machines', async () => {
    await settleConfigEntry('lva:m1', 'vm1', { ...fork, pushState: { vm2: {}, vm3: {} } }, false);
    expect(mockRemove).not.toHaveBeenCalled();
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
