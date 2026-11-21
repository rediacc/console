import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
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
    // The settle step reads the fork's record; the backup entry does not exist yet.
    getRepository: (key: string) =>
      Promise.resolve(
        key === 'mautic:test'
          ? { repositoryGuid: 'fork-guid', parentGuid: 'grand-guid' }
          : undefined
      ),
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

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach } from 'vitest';
import { RemoteWriteFailedClosedError } from '../../adapters/remote-config-errors.js';
import { setCommandJobDeps } from '../../services/jobs/command-job.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';
import { registerRepoPromoteCommand } from '../repo-promote.js';

// The promote is one job: the config swap is its success step, so a failed swap is the step's warning, not a throw.
const warnings: string[] = [];
let ticketDir: string;
function installJob(): void {
  ticketDir = mkdtempSync(join(tmpdir(), 'repo-promote-converge-'));
  const store = new TicketStore('test', ticketDir);
  setCommandJobDeps({
    executor: () => ({ execute: cfg.exec }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: (text: string) => void warnings.push(text),
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
}
afterEach(() => {
  setCommandJobDeps();
  rmSync(ticketDir, { recursive: true, force: true });
  process.exitCode = 0;
});

const run = async () => {
  const repo = new Command().exitOverride();
  registerRepoPromoteCommand(repo);
  await repo.parseAsync(['node', 'x', 'promote', 'mautic:test', '-y']);
};

describe('repo promote after a config save failure', () => {
  beforeEach(() => {
    failures.handled.length = 0;
    warnings.length = 0;
    installJob();
    cfg.add.mockReset().mockResolvedValue(undefined);
    cfg.remove.mockReset().mockResolvedValue(undefined);
    cfg.reconcile.mockReset().mockResolvedValue(undefined);
    cfg.exec.mockReset().mockResolvedValue({ success: true, stdout: '', stderr: '', exitCode: 0 });
  });

  it('names the manual config fix and forbids a re-run when the save fails (red on old code)', async () => {
    cfg.remove.mockRejectedValue(
      new RemoteWriteFailedClosedError('rediacc', WK_ACCOUNT_DEFAULT_ORIGIN, new Error('down'))
    );
    await run();
    expect(cfg.exec).toHaveBeenCalledTimes(1);
    const text = warnings[0];
    expect(text).toContain('commands.repo.promote.configSaveFailed');
    expect(text).toContain('"fork":"mautic:test"');
    expect(text).toMatch(/"backup":"mautic:pre-promote-\d{8}"/);
    expect(process.exitCode).toBe(1);
    expect(cfg.reconcile).not.toHaveBeenCalled();
  });

  it('a non-network save failure exits with the general error code (red on old code)', async () => {
    cfg.add.mockRejectedValue(new Error('disk full'));
    await run();
    expect(cfg.remove).not.toHaveBeenCalled();
    const text = warnings[0];
    expect(text).toContain('commands.repo.promote.configSaveFailed');
    expect(text).toContain('"fork":"mautic:test"');
    expect(text).toMatch(/"backup":"mautic:pre-promote-\d{8}"/);
    expect(text).toContain('disk full');
    expect(process.exitCode).toBe(1);
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
