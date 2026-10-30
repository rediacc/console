/**
 * PLAN-free-license R13: a Free License has no hosted backup plane. The backup
 * verbs that need it print the upgrade message (with the signup link) instead
 * of a token error or a raw session refusal.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  fetch: vi.fn(),
  execute: vi.fn(),
  tokenState: vi.fn(),
  warn: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: m.warn, error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: vi.fn() }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: vi.fn() }));
vi.mock('../../utils/errors.js', () => ({
  ValidationError: class ValidationError extends Error {},
  getOutputFormat: () => 'json',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../utils/repo-executor.js', () => ({ executeRepoFunction: m.execute }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'shop', machineName: 'm1' }),
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop' }),
}));
vi.mock('../backup-storage-browse.js', () => ({
  RENET_NO_LISTING_EXIT: 18,
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
  runBrowseAt: vi.fn(),
}));

import { registerBackupStorageCommands, runStoreVerify } from '../backup-storage.js';

async function run(args: string[]) {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupStorageCommands(backup);
  await backup.parseAsync(args, { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  m.tokenState.mockReturnValue({ kind: 'missing' });
});

describe('hosted backup reads with no login', () => {
  it.each([['usage'], ['manifests']])(
    '`backup %s` prints the upgrade message and never calls the account',
    async (verb) => {
      await expect(run([verb])).rejects.toThrow(/errors\.freeLicense\.noHostedBackup/);
      await expect(run([verb])).rejects.toThrow(/acct\.example\/account\/login/);
      expect(m.fetch).not.toHaveBeenCalled();
    }
  );

  it('`backup verify --store` refuses the same way', async () => {
    await expect(runStoreVerify('lineage-1')).rejects.toThrow(
      /errors\.freeLicense\.noHostedBackup/
    );
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('a login reaches the account as before', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockResolvedValue({ manifests: [] });
    await run(['manifests']);
    expect(m.fetch).toHaveBeenCalledTimes(1);
  });
});

describe('backup snapshot on a Free License', () => {
  it("names the upgrade when the server refused the FREE blob's backup session", async () => {
    m.execute.mockResolvedValue({
      success: false,
      exitCode: 1,
      stdout: '',
      error:
        'backup server refused (HTTP 403, FREE_LICENSE_NO_BACKUP): A Free License has no hosted backup storage.',
    });
    await run(['snapshot', 'shop']);
    expect(m.warn).toHaveBeenCalledWith(
      expect.stringContaining('errors.freeLicense.noHostedBackup')
    );
  });

  it('leaves any other failure alone', async () => {
    m.execute.mockResolvedValue({ success: false, exitCode: 1, stdout: '', error: 'disk full' });
    await run(['snapshot', 'shop']);
    expect(m.warn).not.toHaveBeenCalled();
  });
});
