import { beforeEach, describe, expect, it, vi } from 'vitest';

// `repo delete --purge-backups` frees the chunk-store backups, so the "backups outlive the repository" notice would contradict the line printed just before it. Without the flag the notice stays.

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { applyDefaults: () => Promise.resolve({ team: 't' }) },
}));
vi.mock('../../remote/vscode/index.js', () => ({
  generateConnectionName: () => 'c',
  removePersistedKeys: vi.fn(),
  removeSSHConfigEntry: vi.fn(),
}));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: vi.fn(() => Promise.resolve()),
}));
vi.mock('../repo-delete-settle.js', () => ({
  isFork: () => false,
  settleCloudBackups: vi.fn(() => Promise.resolve()),
  settleConfigEntry: vi.fn(() => Promise.resolve()),
  settleRepoLicense: vi.fn(() => Promise.resolve()),
}));

const infos = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    success: vi.fn(),
    warn: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));

import { handleDeleteSuccess } from '../repo-create-delete.js';

const ok = { success: true, allSteps: [] } as never;

describe('repo delete cloud-backup notice', () => {
  beforeEach(() => {
    infos.length = 0;
  });

  it('is printed when the backups were left in place', async () => {
    await handleDeleteSuccess('lva', 'vm1', { repositoryGuid: 'g1' }, false, ok, 'lva', false);
    expect(infos.join('\n')).toContain('commands.repo.delete.cloudBackupHint');
  });

  it('is suppressed when --purge-backups freed them', async () => {
    await handleDeleteSuccess('lva', 'vm1', { repositoryGuid: 'g1' }, false, ok, 'lva', true);
    expect(infos.join('\n')).not.toContain('commands.repo.delete.cloudBackupHint');
  });
});
