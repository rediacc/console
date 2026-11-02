import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  execute: vi.fn(),
  print: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  setExitCode: vi.fn(),
  getRepository: vi.fn(),
  sftpExec: vi.fn(),
  format: { value: 'json' },
}));

vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mocks.fetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mocks.info,
    success: vi.fn(),
    warn: mocks.warn,
    error: vi.fn(),
    print: mocks.print,
  },
}));
vi.mock('../../services/core/request-context.js', async () => ({
  ...(await vi.importActual<typeof import('../../services/core/request-context.js')>(
    '../../services/core/request-context.js'
  )),
  setExitCode: mocks.setExitCode,
}));
vi.mock('../../utils/errors.js', async () => ({
  ...(await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js')),
  getOutputFormat: () => mocks.format.value,
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: vi.fn(),
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'shop', machineName: 'm1' }),
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop' }),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mocks.getRepository },
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockResolvedValue({
      sftp: { exec: mocks.sftpExec },
      machine: { datastore: WK_DATASTORE_PATH },
      release: vi.fn(),
    }),
  },
}));

import { registerBackupCheck } from '../backup-check.js';

const SNAP = '20261101T030000Z-0011223344556677';
const OLDER = '20261031T030000Z-aaaaaaaaaaaaaaaa';

const listing = (entries: { path: string; type: string; size: number }[]) =>
  JSON.stringify({ source: 'chunk-store', entries, truncated: false, totalSize: 0 });
const restorePath = (bytesWritten: number) =>
  JSON.stringify({ snapshotId: SNAP, path: 'etc/hosts', to: '/x', files: 1, bytesWritten });

interface Call {
  functionName: string;
  params: Record<string, unknown>;
}
const calls = (): Call[] => mocks.execute.mock.calls.map((c) => c[0] as Call);

function script(answers: {
  browse?: { success: boolean; exitCode?: number; stdout?: string };
  restore?: { success: boolean; exitCode?: number; stdout?: string };
}) {
  mocks.execute.mockImplementation((req: Call) => {
    if (req.functionName === 'backup_browse_at')
      return Promise.resolve({
        exitCode: 0,
        ...(answers.browse ?? {
          success: true,
          stdout: listing([
            { path: 'big.bin', type: 'file', size: 5_000_000 },
            { path: 'etc', type: 'dir', size: 0 },
            { path: 'etc/hosts', type: 'file', size: 120 },
            { path: 'empty', type: 'file', size: 0 },
          ]),
        }),
      });
    if (req.functionName === 'backup_restore_path')
      return Promise.resolve({
        exitCode: 0,
        ...(answers.restore ?? { success: true, stdout: restorePath(120) }),
      });
    return Promise.reject(new Error(`unexpected ${req.functionName}`));
  });
}

async function run(args: string[]): Promise<void> {
  const program = new Command().exitOverride();
  const backup = program.command('backup');
  registerBackupCheck(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...args]);
}
const printed = (): Record<string, unknown> => mocks.print.mock.calls.at(-1)?.[0];
const verificationPosts = () =>
  mocks.fetch.mock.calls.filter((c) => String(c[0]).includes('/verification'));
const rmCommands = () =>
  mocks.sftpExec.mock.calls.map((c) => String(c[0])).filter((c) => c.includes('rm '));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format.value = 'json';
  mocks.getRepository.mockResolvedValue({
    repositoryGuid: 'g1',
    grandGuid: 'lineage-1',
    credential: 'secret-passphrase',
  });
  mocks.sftpExec.mockResolvedValue('');
  mocks.fetch.mockImplementation((url: string) =>
    url.includes('/verification')
      ? Promise.resolve({ snapshotId: SNAP, verificationState: 'proven' })
      : Promise.resolve({
          manifests: [
            {
              snapshotId: OLDER,
              lineageGuid: 'lineage-1',
              createdAt: '2026-10-31T03:00:00Z',
              hasIndex: true,
            },
            {
              snapshotId: SNAP,
              lineageGuid: 'lineage-1',
              createdAt: '2026-11-01T03:00:00Z',
              hasIndex: true,
            },
          ],
        })
  );
  script({});
});

describe('backup check', () => {
  it('browses the newest snapshot with the passphrase, restores one file, and posts proven', async () => {
    await run(['check', 'shop']);
    const [browse, restore] = calls();
    expect(browse.functionName).toBe('backup_browse_at');
    expect(browse.params).toMatchObject({ lineage: 'lineage-1', at: SNAP });
    expect(restore.functionName).toBe('backup_restore_path');
    expect(restore.params).toMatchObject({ lineage: 'lineage-1', at: SNAP });
    // No --path: a small real file is chosen, never a directory or an empty file.
    expect(restore.params.path).toBe('etc/hosts');
    expect(verificationPosts()).toHaveLength(1);
    expect(verificationPosts()[0][0]).toContain(`/snapshots/${SNAP}/verification`);
    expect(verificationPosts()[0][1]).toEqual({
      method: 'POST',
      body: { level: 'test-open', status: 'proven' },
    });
    expect(printed()).toMatchObject({ status: 'proven', path: 'etc/hosts', size: 120 });
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('--path names the file, and the browse is scoped to it', async () => {
    script({
      browse: {
        success: true,
        stdout: listing([{ path: 'big.bin', type: 'file', size: 5_000_000 }]),
      },
      restore: { success: true, stdout: restorePath(5_000_000) },
    });
    await run(['check', 'shop', '--path', '/big.bin']);
    expect(calls()[0].params.path).toBe('big.bin');
    expect(calls()[1].params.path).toBe('big.bin');
    expect(printed()).toMatchObject({ status: 'proven', path: 'big.bin' });
  });

  it('a restored size that differs from the listed one is failed and posted as failed', async () => {
    script({ restore: { success: true, stdout: restorePath(7) } });
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(verificationPosts()[0][1].body).toEqual({ level: 'test-open', status: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('prints failed, not proven, when the server answers that the snapshot is still failed', async () => {
    mocks.fetch.mockImplementation((url: string) =>
      url.includes('/verification')
        ? Promise.resolve({ snapshotId: SNAP, verificationState: 'failed' })
        : Promise.resolve({
            manifests: [
              {
                snapshotId: SNAP,
                lineageGuid: 'lineage-1',
                createdAt: '2026-11-01T03:00:00Z',
                hasIndex: true,
              },
            ],
          })
    );
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'failed', verificationState: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('a snapshot with no index is reported plainly, is not proven, and posts nothing', async () => {
    mocks.fetch.mockResolvedValue({
      manifests: [
        {
          snapshotId: SNAP,
          lineageGuid: 'lineage-1',
          createdAt: '2026-11-01T03:00:00Z',
          hasIndex: false,
        },
      ],
    });
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'no-index', snapshotId: SNAP });
    expect(mocks.warn.mock.calls.map((c) => String(c[0])).join('\n')).toContain(
      'commands.backup.check.noIndex'
    );
    expect(mocks.execute).not.toHaveBeenCalled();
    expect(verificationPosts()).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('a listing the machine cannot serve (exit 18) is no-index as well, not a failure of the snapshot', async () => {
    script({ browse: { success: false, exitCode: 18, stdout: '' } });
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'no-index' });
    expect(verificationPosts()).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('a restore that errors is failed locally and not recorded against the snapshot', async () => {
    script({ restore: { success: false, exitCode: 1, stdout: '' } });
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(verificationPosts()).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  describe('the scratch directory', () => {
    const scratchOf = () => String(calls()[1].params.to);

    it('is unique, under the datastore restores, and deleted by exactly that path', async () => {
      await run(['check', 'shop']);
      expect(scratchOf()).toMatch(new RegExp(`^${WK_DATASTORE_PATH}/restores/check-[0-9a-f]{8}$`));
      const rm = rmCommands();
      expect(rm).toHaveLength(1);
      expect(rm[0]).toContain(scratchOf());
      expect(rm[0]).not.toMatch(/restores['" ]*$/);
    });

    it('is deleted after a failed restore too', async () => {
      script({ restore: { success: false, exitCode: 1, stdout: '' } });
      await run(['check', 'shop']);
      expect(rmCommands()).toHaveLength(1);
      expect(rmCommands()[0]).toContain(scratchOf());
    });

    it('is deleted when the executor throws', async () => {
      mocks.execute.mockImplementation((req: Call) =>
        req.functionName === 'backup_browse_at'
          ? Promise.resolve({
              success: true,
              exitCode: 0,
              stdout: listing([{ path: 'a.txt', type: 'file', size: 3 }]),
            })
          : Promise.reject(new Error('ssh dropped'))
      );
      await expect(run(['check', 'shop'])).rejects.toThrow('ssh dropped');
      expect(rmCommands()).toHaveLength(1);
    });

    it('is not created when nothing was restored (no index)', async () => {
      script({ browse: { success: false, exitCode: 18, stdout: '' } });
      await run(['check', 'shop']);
      expect(rmCommands()).toHaveLength(0);
    });
  });

  it('needs the credential, and never puts it on the wire params', async () => {
    await run(['check', 'shop']);
    expect(JSON.stringify(mocks.execute.mock.calls)).not.toContain('secret-passphrase');
    mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g1', grandGuid: 'lineage-1' });
    await expect(run(['check', 'shop'])).rejects.toThrow('commands.backup.check.needsCredential');
  });

  it('a lineage with no snapshot says so', async () => {
    mocks.fetch.mockResolvedValue({ manifests: [] });
    await expect(run(['check', 'shop'])).rejects.toThrow('commands.backup.check.noSnapshot');
  });

  it('a listing with no non-empty file cannot be checked and is not proven', async () => {
    script({ browse: { success: true, stdout: listing([{ path: 'etc', type: 'dir', size: 0 }]) } });
    await run(['check', 'shop']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(calls().some((c) => c.functionName === 'backup_restore_path')).toBe(false);
    expect(verificationPosts()).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });
});
