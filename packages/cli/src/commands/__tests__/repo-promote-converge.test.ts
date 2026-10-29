import { beforeEach, describe, expect, it, vi } from 'vitest';

// `repo promote` is machine-first and cannot converge on retry (both images survive the swap, so a re-run would swap the data back). When the config save fails after the machine promote, the error must say so, forbid the re-run and name the manual config fix.

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const cfg = vi.hoisted(() => ({
  add: vi.fn(),
  remove: vi.fn(),
  exec: vi.fn(),
  reconcile: vi.fn(),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ machineName: 'hostinger', repoKey: 'mautic:test', kubeCluster: undefined }),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    resolveDestructiveTarget: (key: string) =>
      Promise.resolve({
        key,
        config: { repositoryGuid: 'fork-guid', parentGuid: 'grand-guid' },
      }),
    listRepositories: () =>
      Promise.resolve([{ name: 'mautic', config: { repositoryGuid: 'grand-guid' } }]),
    addRepository: cfg.add,
    removeRepository: cfg.remove,
  },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: cfg.exec }),
}));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: cfg.reconcile,
}));
vi.mock('../../utils/repo-executor.js', () => ({ recordedDatastoreMount: () => undefined }));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn(),
  CMD: { REPO_PROMOTE: 'repo.promote' },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const failures = vi.hoisted(() => ({ handled: [] as unknown[] }));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    failures.handled.push(e);
    throw e;
  },
}));

import { Command } from 'commander';
import { RemoteWriteFailedClosedError } from '../../adapters/remote-config-errors.js';
import { registerRepoPromoteCommand } from '../repo-promote.js';

const run = async () => {
  const repo = new Command().exitOverride();
  registerRepoPromoteCommand(repo);
  await repo.parseAsync(['node', 'x', 'promote', 'mautic:test', '-y']);
};

describe('repo promote after a config save failure', () => {
  beforeEach(() => {
    failures.handled.length = 0;
    cfg.add.mockReset().mockResolvedValue(undefined);
    cfg.remove.mockReset().mockResolvedValue(undefined);
    cfg.reconcile.mockReset().mockResolvedValue(undefined);
    cfg.exec.mockReset().mockResolvedValue({ success: true, stdout: '', stderr: '', exitCode: 0 });
  });

  it('names the manual config fix and forbids a re-run when the save fails (red on old code)', async () => {
    cfg.remove.mockRejectedValue(
      new RemoteWriteFailedClosedError('rediacc', 'https://eu.rediacc.com', new Error('down'))
    );
    await expect(run()).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      exitCode: 6,
      retryable: false,
    });
    expect(cfg.exec).toHaveBeenCalledTimes(1);
    const err = failures.handled[0] as Error;
    expect(err.message).toContain('commands.repo.promote.configSaveFailed');
    expect(err.message).toContain('"fork":"mautic:test"');
    expect(err.message).toMatch(/"backup":"mautic:pre-promote-\d{8}"/);
    expect(cfg.reconcile).not.toHaveBeenCalled();
  });

  it('a non-network save failure exits with the general error code (red on old code)', async () => {
    cfg.add.mockRejectedValue(new Error('disk full'));
    await expect(run()).rejects.toMatchObject({ code: 'GENERAL_ERROR', retryable: false });
    expect(cfg.remove).not.toHaveBeenCalled();
    const err = failures.handled[0] as Error;
    expect(err.message).toContain('commands.repo.promote.configSaveFailed');
    expect(err.message).toContain('"fork":"mautic:test"');
    expect(err.message).toMatch(/"backup":"mautic:pre-promote-\d{8}"/);
    expect(err.message).toContain('disk full');
  });

  it('the normal path promotes, settles the config and reconciles, rc 0', async () => {
    await run();
    expect(cfg.exec).toHaveBeenCalledTimes(1);
    expect(cfg.add).toHaveBeenCalledWith(
      expect.stringMatching(/^mautic:pre-promote-\d{8}$/),
      expect.anything()
    );
    expect(cfg.remove).toHaveBeenCalledWith('mautic:test');
    expect(cfg.reconcile).toHaveBeenCalledWith('hostinger');
    expect(failures.handled).toHaveLength(0);
  });
});
