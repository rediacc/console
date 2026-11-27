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
  error: vi.fn(),
  setExitCode: vi.fn(),
  addRepository: vi.fn(),
  removeRepository: vi.fn(),
  getLocalConfig: vi.fn(),
  getRepository: vi.fn(),
  readAnchor: vi.fn(),
  sftpExec: vi.fn(),
  deployKey: vi.fn(),
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
    error: mocks.error,
    print: mocks.print,
  },
}));
vi.mock('../../services/core/request-context.js', async () => ({
  ...(await vi.importActual<typeof import('../../services/core/request-context.js')>(
    '../../services/core/request-context.js'
  )),
  setExitCode: mocks.setExitCode,
}));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: vi.fn() }));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => mocks.format.value,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: vi.fn(),
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'shop', machineName: 'm1' }),
}));
vi.mock('../../utils/repo-ref-local.js', () => ({
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop' }),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mocks.getRepository,
    getLocalConfig: mocks.getLocalConfig,
    allocateNetworkId: vi.fn().mockResolvedValue(77),
    addRepository: mocks.addRepository,
    removeRepository: mocks.removeRepository,
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  targetFloor: vi.fn().mockResolvedValue([]),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: mocks.deployKey,
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
vi.mock('../backup-restore-chunk.js', () => ({
  readSourceAnchor: mocks.readAnchor,
  resolveSnapshotAt: vi.fn(),
  runChunkRestore: vi.fn(),
  settleRestore: vi.fn(),
  streamScopeFor: vi.fn(),
}));
vi.mock('../backup-storage-browse.js', () => ({
  RENET_NO_LISTING_EXIT: 18,
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
  runBrowseAt: vi.fn(),
  lineageOf: (r: { grandGuid?: string; repositoryGuid: string }) => r.grandGuid ?? r.repositoryGuid,
}));

import { registerBackupStorageCommands } from '../backup-storage.js';

const SNAP = '20261101T030000Z-0011223344556677';
const SOURCE_GUID = '11111111-1111-4111-8111-111111111111';
const GB = 1024 ** 3;

const restoreRecord = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    guid: 'x',
    status: 'restored',
    snapshotId: SNAP,
    cellsTotal: 4,
    chunksFetched: 4,
    passphraseCheck: 'opened',
    ...over,
  });
const compareRecord = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    guid: 'x',
    against: SOURCE_GUID,
    status: 'identical',
    anchorSnapshotId: SNAP,
    ...over,
  });

interface ExecCall {
  functionName: string;
  params: Record<string, unknown>;
  machineName: string;
}
const calls = (): ExecCall[] => mocks.execute.mock.calls.map((c) => c[0] as ExecCall);
const deletes = () => calls().filter((c) => c.functionName === 'repository_delete');

/** Script the executor: restore, compare and delete answers. */
function script(answers: {
  restore?: { success: boolean; stdout?: string };
  compare?: { success: boolean; stdout?: string };
  del?: { success: boolean };
}) {
  mocks.execute.mockImplementation((req: ExecCall) => {
    if (req.functionName === 'backup_restore')
      return Promise.resolve({
        exitCode: 0,
        ...(answers.restore ?? { success: true, stdout: restoreRecord() }),
      });
    if (req.functionName === 'backup_compare')
      return Promise.resolve({
        exitCode: 0,
        ...(answers.compare ?? { success: true, stdout: compareRecord() }),
      });
    if (req.functionName === 'repository_delete')
      return Promise.resolve({ exitCode: 0, ...(answers.del ?? { success: true }) });
    return Promise.reject(new Error(`unexpected ${req.functionName}`));
  });
}

async function run(args: string[]): Promise<void> {
  const program = new Command().exitOverride();
  const backup = program.command('backup');
  registerBackupStorageCommands(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...args]);
}

const printed = (): Record<string, unknown> => mocks.print.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.removeRepository.mockResolvedValue(undefined);
  mocks.format.value = 'json';
  mocks.getRepository.mockResolvedValue({
    repositoryGuid: SOURCE_GUID,
    grandGuid: 'lineage-1',
    credential: 'secret-passphrase',
  });
  mocks.getLocalConfig.mockResolvedValue({ machines: { m1: {}, l1vm: {} } });
  mocks.readAnchor.mockResolvedValue(SNAP);
  // The index row for the anchored snapshot (10 GiB) and a datastore with room to spare.
  mocks.fetch.mockImplementation((url: string) => {
    if (url.includes('/verification'))
      return Promise.resolve({ snapshotId: SNAP, verificationState: 'proven' });
    return Promise.resolve({ snapshotId: SNAP, lineageGuid: 'lineage-1', totalBytes: 10 * GB });
  });
  mocks.sftpExec.mockResolvedValue(`${40 * GB}\n`);
  script({});
});

describe('backup verify --restore-test', () => {
  it('restores the anchor snapshot under a new name with no seed, compares, and records proven', async () => {
    await run(['verify', 'shop', '--restore-test']);

    const restore = calls().find((c) => c.functionName === 'backup_restore');
    expect(restore?.params).toMatchObject({ at: SNAP, lineage: 'lineage-1', no_seed: true });
    expect(restore?.params.repository).not.toBe('shop');
    const compare = calls().find((c) => c.functionName === 'backup_compare');
    expect(compare?.params.against_anchor).toBe(SOURCE_GUID);
    expect(compare?.params.repository).toBe(restore?.params.repository);

    const post = mocks.fetch.mock.calls.find((c) => String(c[0]).includes('/verification'));
    expect(post?.[0]).toContain(`/snapshots/${SNAP}/verification`);
    expect(post?.[1]).toEqual({
      method: 'POST',
      body: { level: 'restore-test', status: 'proven' },
    });
    expect(printed()).toMatchObject({ status: 'proven', verificationState: 'proven' });
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('refuses when the datastore has less than 1.2x the image free, before registering a copy', async () => {
    mocks.sftpExec.mockResolvedValue(`${11 * GB}\n`);
    await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow(
      'commands.backup.verify.restoreTestNoSpace'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('fails closed when the free space cannot be read', async () => {
    mocks.sftpExec.mockResolvedValue('not a number');
    await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow(
      'commands.backup.verify.restoreTestFreeUnknown'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
  });

  it('names the unknown size, not a shortage, when the index has no row for the anchor', async () => {
    mocks.fetch.mockImplementation((url: string) =>
      url.includes('/verification')
        ? Promise.resolve({ snapshotId: SNAP, verificationState: 'proven' })
        : Promise.reject(Object.assign(new Error('not found'), { status: 404 }))
    );
    await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow(
      'commands.backup.verify.restoreTestSizeUnknown'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
  });

  it('a differing copy exits 1, records failed, and says failed', async () => {
    script({ compare: { success: false, stdout: compareRecord({ status: 'different' }) } });
    await run(['verify', 'shop', '--restore-test']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
    const post = mocks.fetch.mock.calls.find((c) => String(c[0]).includes('/verification'));
    expect(post?.[1].body).toEqual({ level: 'restore-test', status: 'failed' });
  });

  it('an anchor that moved since the restore is not a verdict on the snapshot: failed locally, nothing recorded', async () => {
    script({
      compare: {
        success: true,
        stdout: compareRecord({ anchorSnapshotId: '20261102T030000Z-aaaaaaaaaaaaaaaa' }),
      },
    });
    await run(['verify', 'shop', '--restore-test']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(printed().reason).toContain('the anchor moved');
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
    expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(false);
  });

  describe('a live repository whose backup loop moved the anchor during the restore (hostinger mail, 2026-11-27)', () => {
    const MOVED = '20261127T055548Z-638b4ab3e7d6db20';
    const heldToSnapshot = (over: Record<string, unknown> = {}) =>
      compareRecord({
        anchorSnapshotId: MOVED,
        heldTo: 'snapshot',
        snapshotId: SNAP,
        cellsRoot: 'r1',
        snapshotCellsRoot: 'r1',
        ...over,
      });

    it('proves the copy held to the restored snapshot, and records proven', async () => {
      script({
        restore: { success: true, stdout: restoreRecord({ cellsRoot: 'verified' }) },
        compare: { success: true, stdout: heldToSnapshot() },
      });
      await run(['verify', 'shop', '--restore-test']);
      expect(printed()).toMatchObject({ status: 'proven', snapshotId: SNAP });
      expect(mocks.setExitCode).not.toHaveBeenCalled();
      const post = mocks.fetch.mock.calls.find((c) => String(c[0]).includes('/verification'));
      expect(post?.[0]).toContain(`/snapshots/${SNAP}/verification`);
      expect(post?.[1].body).toEqual({ level: 'restore-test', status: 'proven' });
    });

    it('refuses when the restore did not verify the inventory root, and records nothing', async () => {
      script({
        restore: { success: true, stdout: restoreRecord({ cellsRoot: 'absent' }) },
        compare: { success: true, stdout: heldToSnapshot() },
      });
      await run(['verify', 'shop', '--restore-test']);
      expect(printed()).toMatchObject({ status: 'failed' });
      expect(printed().reason).toContain('manifest root');
      expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(
        false
      );
    });

    it('refuses a copy held to some other snapshot', async () => {
      script({
        restore: { success: true, stdout: restoreRecord({ cellsRoot: 'verified' }) },
        compare: { success: true, stdout: heldToSnapshot({ snapshotId: MOVED }) },
      });
      await run(['verify', 'shop', '--restore-test']);
      expect(printed()).toMatchObject({ status: 'failed' });
      expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(
        false
      );
    });

    it('a copy that differs from its snapshot records failed', async () => {
      script({
        restore: { success: true, stdout: restoreRecord({ cellsRoot: 'verified' }) },
        compare: {
          success: false,
          stdout: heldToSnapshot({ status: 'different', reason: '1 cells of the copy differ' }),
        },
      });
      await run(['verify', 'shop', '--restore-test']);
      expect(printed()).toMatchObject({ status: 'failed', reason: '1 cells of the copy differ' });
      const post = mocks.fetch.mock.calls.find((c) => String(c[0]).includes('/verification'));
      expect(post?.[1].body).toEqual({ level: 'restore-test', status: 'failed' });
    });
  });

  it('prints failed, not proven, when the server answers that the snapshot is still failed', async () => {
    mocks.fetch.mockImplementation((url: string) =>
      url.includes('/verification')
        ? Promise.resolve({ snapshotId: SNAP, verificationState: 'failed' })
        : Promise.resolve({ snapshotId: SNAP, lineageGuid: 'lineage-1', totalBytes: 10 * GB })
    );
    await run(['verify', 'shop', '--restore-test']);
    expect(printed()).toMatchObject({ status: 'failed', verificationState: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('a restore the passphrase refused is failed and not recorded against the snapshot', async () => {
    script({
      restore: {
        success: false,
        stdout: restoreRecord({ status: 'failed', passphraseCheck: 'refused', reason: 'kept /x' }),
      },
    });
    await run(['verify', 'shop', '--restore-test']);
    expect(printed()).toMatchObject({ status: 'failed', passphraseCheck: 'refused' });
    expect(calls().some((c) => c.functionName === 'backup_compare')).toBe(false);
    expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(false);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  describe('the delete names only the copy, on every path', () => {
    const copyName = () => {
      const restore = calls().find((c) => c.functionName === 'backup_restore');
      return restore?.params.repository as string;
    };
    const expectOnlyCopyDeleted = () => {
      expect(deletes()).toHaveLength(1);
      expect(deletes()[0].params).toEqual({ repository: copyName() });
      expect(deletes()[0].params.repository).not.toBe('shop');
      const removed = mocks.removeRepository.mock.calls.map((c) => String(c[0]));
      expect(removed).toHaveLength(1);
      expect(removed[0]).toContain(copyName());
      // The registered copy carries a fresh GUID, never the source's.
      const added = mocks.addRepository.mock.calls[0][1] as { repositoryGuid: string };
      expect(added.repositoryGuid).not.toBe(SOURCE_GUID);
    };

    it('after a proven run', async () => {
      await run(['verify', 'shop', '--restore-test']);
      expectOnlyCopyDeleted();
    });
    it('after a restore failure', async () => {
      script({ restore: { success: false, stdout: restoreRecord({ status: 'failed' }) } });
      await run(['verify', 'shop', '--restore-test']);
      expectOnlyCopyDeleted();
    });
    it('after a differing compare', async () => {
      script({ compare: { success: false, stdout: compareRecord({ status: 'different' }) } });
      await run(['verify', 'shop', '--restore-test']);
      expectOnlyCopyDeleted();
    });
    it('after an executor that throws', async () => {
      mocks.execute.mockImplementation((req: ExecCall) =>
        req.functionName === 'repository_delete'
          ? Promise.resolve({ success: true, exitCode: 0 })
          : Promise.reject(new Error('ssh dropped'))
      );
      await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow('ssh dropped');
      expectOnlyCopyDeleted();
    });
    it('a failed delete is loud and exits 1, naming the copy', async () => {
      script({ del: { success: false } });
      await run(['verify', 'shop', '--restore-test']);
      expect(mocks.setExitCode).toHaveBeenCalledWith(1);
      expect(mocks.warn.mock.calls.join('\n')).toContain(copyName());
    });

    const retires = () =>
      mocks.fetch.mock.calls.map((c) => String(c[0])).filter((url) => url.endsWith('/retire'));

    it("retires the deleted copy's licence, and never the source's", async () => {
      await run(['verify', 'shop', '--restore-test']);
      const copyGuid = (mocks.addRepository.mock.calls[0][1] as { repositoryGuid: string })
        .repositoryGuid;
      expect(retires()).toEqual([`/account/api/v1/licenses/repos/${copyGuid}/retire`]);
      expect(retires().join()).not.toContain(SOURCE_GUID);
    });

    it('retires nothing when the copy could not be deleted (control)', async () => {
      script({ del: { success: false } });
      await run(['verify', 'shop', '--restore-test']);
      expect(retires()).toEqual([]);
    });
  });

  it('refuses --restore-test combined with --store or --deep, and a repo with no credential', async () => {
    await expect(run(['verify', 'shop', '--restore-test', '--store'])).rejects.toThrow(
      'commands.backup.verify.restoreTestExclusive'
    );
    mocks.getRepository.mockResolvedValue({ repositoryGuid: SOURCE_GUID, grandGuid: 'lineage-1' });
    await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow(
      'commands.backup.verify.restoreTestNeedsCredential'
    );
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('refuses when the source has no anchor to restore', async () => {
    mocks.readAnchor.mockResolvedValue(undefined);
    await expect(run(['verify', 'shop', '--restore-test'])).rejects.toThrow(
      'commands.backup.verify.restoreTestNoAnchor'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
  });

  it('never puts the credential on the wire params', async () => {
    await run(['verify', 'shop', '--restore-test']);
    expect(JSON.stringify(mocks.execute.mock.calls)).not.toContain('secret-passphrase');
  });
});

describe('backup verify --restore-test --restore-to', () => {
  it('routes the restore and the delete to the named machine, never the source machine', async () => {
    script({ restore: { success: true, stdout: restoreRecord({ cellsRoot: 'verified' }) } });
    await run(['verify', 'shop', '--restore-test', '--restore-to', 'l1vm']);
    const restore = calls().find((c) => c.functionName === 'backup_restore');
    expect(restore?.machineName).toBe('l1vm');
    expect(restore?.params).toMatchObject({ at: SNAP, no_seed: true });
    expect(deletes()).toHaveLength(1);
    expect(deletes()[0].machineName).toBe('l1vm');
    expect(deletes()[0].params.repository).toBe(restore?.params.repository);
    expect(deletes()[0].params.repository).not.toBe('shop');
    expect(calls().every((c) => c.machineName === 'l1vm')).toBe(true);
    // The anchor file is on the source machine, so no anchor compare is issued.
    expect(calls().some((c) => c.functionName === 'backup_compare')).toBe(false);
    const added = mocks.addRepository.mock.calls[0][1] as {
      repositoryGuid: string;
      placement: { machine: string };
    };
    expect(added.placement.machine).toBe('l1vm');
    expect(added.repositoryGuid).not.toBe(SOURCE_GUID);
    expect(printed()).toMatchObject({
      status: 'proven',
      restoredOn: 'l1vm',
      verificationState: 'proven',
    });
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('is not proven when the restore did not verify the manifest root, and records nothing', async () => {
    script({ restore: { success: true, stdout: restoreRecord({ cellsRoot: 'absent' }) } });
    await run(['verify', 'shop', '--restore-test', '--restore-to', 'l1vm']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
    expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(false);
    expect(deletes()).toHaveLength(1);
  });

  it('checks the space on the target machine and refuses before registering a copy', async () => {
    mocks.sftpExec.mockResolvedValue(`${11 * GB}\n`);
    await expect(run(['verify', 'shop', '--restore-test', '--restore-to', 'l1vm'])).rejects.toThrow(
      'commands.backup.verify.restoreTestNoSpace'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('refuses an unknown or empty machine, before any copy exists', async () => {
    await expect(run(['verify', 'shop', '--restore-test', '--restore-to', 'nope'])).rejects.toThrow(
      'commands.backup.verify.restoreToUnknown'
    );
    await expect(run(['verify', 'shop', '--restore-test', '--restore-to', ''])).rejects.toThrow(
      'commands.backup.verify.restoreToUnknown'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('refuses an inherited object name such as constructor as an unknown machine', async () => {
    await expect(
      run(['verify', 'shop', '--restore-test', '--restore-to', 'constructor'])
    ).rejects.toThrow('commands.backup.verify.restoreToUnknown');
    expect(mocks.addRepository).not.toHaveBeenCalled();
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it.each(['refused', 'not-available'])(
    'is not proven when the root verified but the passphrase check is %s, and records nothing',
    async (passphraseCheck) => {
      script({
        restore: {
          success: true,
          stdout: restoreRecord({ cellsRoot: 'verified', passphraseCheck }),
        },
      });
      await run(['verify', 'shop', '--restore-test', '--restore-to', 'l1vm']);
      expect(printed()).toMatchObject({ status: 'failed' });
      expect(mocks.setExitCode).toHaveBeenCalledWith(1);
      expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/verification'))).toBe(
        false
      );
    }
  );

  it("refuses the source's own machine", async () => {
    await expect(run(['verify', 'shop', '--restore-test', '--restore-to', 'm1'])).rejects.toThrow(
      'commands.backup.verify.restoreToSameMachine'
    );
    expect(mocks.addRepository).not.toHaveBeenCalled();
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('refuses --restore-to without --restore-test', async () => {
    await expect(run(['verify', 'shop', '--restore-to', 'l1vm'])).rejects.toThrow(
      'commands.backup.verify.restoreToNeedsRestoreTest'
    );
    expect(mocks.execute).not.toHaveBeenCalled();
  });

  it('control: without the option the compare against the anchor still runs on the source machine', async () => {
    await run(['verify', 'shop', '--restore-test']);
    expect(calls().some((c) => c.functionName === 'backup_compare')).toBe(true);
    expect(calls().every((c) => c.machineName === 'm1')).toBe(true);
    expect(printed()).not.toHaveProperty('restoredOn');
  });
});
