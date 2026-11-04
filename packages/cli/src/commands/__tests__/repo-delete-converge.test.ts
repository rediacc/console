import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// `repo delete` is machine-first. When the config save fails after the machine delete, the error must say so and name the retry; the retry (image now absent) must skip the machine dispatch and finish the config side.

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const settle = vi.hoisted(() => ({
  entry: vi.fn(),
  backups: vi.fn(),
  license: vi.fn(),
}));
vi.mock('../repo-delete-settle.js', () => ({
  isFork: () => false,
  settleConfigEntry: settle.entry,
  settleCloudBackups: settle.backups,
  settleRepoLicense: settle.license,
}));

const resolve = vi.hoisted(() => ({ ref: vi.fn(), exec: vi.fn() }));
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRef: resolve.ref }));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: resolve.exec }),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    applyDefaults: () => Promise.resolve({ team: 't' }),
    resolveDestructiveTarget: (key: string) =>
      Promise.resolve({ key, config: { repositoryGuid: 'g1' } }),
    getRepository: () => Promise.resolve({ repositoryGuid: 'g1' }),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  ensureRepositoryNetworkId: vi.fn(),
}));
vi.mock('../../utils/repo-executor.js', () => ({ recordedDatastoreMount: () => undefined }));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn(),
  CMD: { REPO_DELETE: 'repo.delete' },
}));
vi.mock('../../remote/vscode/index.js', () => ({
  generateConnectionName: () => 'c',
  removePersistedKeys: vi.fn(),
  removeSSHConfigEntry: vi.fn(),
}));
const reconcile = vi.hoisted(() => ({ fn: vi.fn() }));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: reconcile.fn,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
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
import { registerRepoCreateDeleteCommands } from '../repo-create-delete.js';

// The delete is one job: the settlement is its success step, so a failed settlement is the step's warning, not a throw.
const warnings: string[] = [];
let ticketDir: string;
function installJob(): void {
  ticketDir = mkdtempSync(join(tmpdir(), 'repo-delete-converge-'));
  const store = new TicketStore('test', ticketDir);
  setCommandJobDeps({
    executor: () => ({ execute: resolve.exec }),
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

const run = async (...args: string[]) => {
  const repo = new Command().exitOverride();
  registerRepoCreateDeleteCommands(repo);
  await repo.parseAsync(['node', 'x', 'delete', ...args]);
};

const base = { name: 'mautic', repoKey: 'mautic:readcap', machineName: 'hostinger' };

describe('repo delete converges after a partial failure', () => {
  beforeEach(() => {
    failures.handled.length = 0;
    warnings.length = 0;
    installJob();
    settle.entry.mockReset().mockResolvedValue(undefined);
    settle.backups.mockReset().mockResolvedValue(undefined);
    settle.license.mockReset().mockResolvedValue(undefined);
    reconcile.fn.mockReset().mockResolvedValue(undefined);
    resolve.exec
      .mockReset()
      .mockResolvedValue({ success: true, stdout: '', stderr: '', exitCode: 0 });
    resolve.ref.mockReset().mockResolvedValue(base);
  });

  it('names the retry when the config save fails after the machine delete', async () => {
    settle.entry.mockRejectedValue(
      new RemoteWriteFailedClosedError('rediacc', WK_ACCOUNT_DEFAULT_ORIGIN, new Error('down'))
    );
    await run('mautic:readcap', '-y');
    expect(resolve.exec).toHaveBeenCalledTimes(1);
    expect(warnings[0]).toContain('commands.repo.delete.configSaveFailed');
    expect(warnings[0]).toContain('rdc repo delete mautic:readcap -y');
    // The step failed, so the command does not exit 0.
    expect(process.exitCode).toBe(1);
    // The steps after the config save are deferred to the retry (see handleDeleteSuccess).
    expect(reconcile.fn).not.toHaveBeenCalled();
    expect(settle.backups).not.toHaveBeenCalled();
    expect(settle.license).not.toHaveBeenCalled();
  });

  it('a retry whose image is already gone skips the machine and still settles the config, rc 0', async () => {
    resolve.ref.mockResolvedValue({ ...base, imageAbsent: true });
    await run('mautic:readcap', '-y');
    expect(resolve.exec).not.toHaveBeenCalled();
    expect(settle.entry).toHaveBeenCalledWith(
      'mautic:readcap',
      'hostinger',
      expect.anything(),
      false
    );
    // The retry runs the steps the failed save skipped.
    expect(reconcile.fn).toHaveBeenCalledWith('hostinger');
    expect(settle.backups).toHaveBeenCalledTimes(1);
    expect(settle.license).toHaveBeenCalledTimes(1);
    expect(failures.handled).toHaveLength(0);
  });

  it('the normal path deletes on the machine, then settles the config', async () => {
    await run('mautic:readcap', '-y');
    expect(resolve.exec).toHaveBeenCalledTimes(1);
    expect(settle.entry).toHaveBeenCalledTimes(1);
    expect(failures.handled).toHaveLength(0);
  });
});
