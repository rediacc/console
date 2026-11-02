/**
 * `repo sync upload` runs the remote-parents step inside the rsync attempt.
 *
 * ensureUploadParents is unit-tested on its own; this file pins the WIRING in
 * syncUpload, which no other test drives: with the call removed from the rsync
 * attempt every other sync test still passes.
 */
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  ensureUploadParents: vi.fn(() => Promise.resolve([] as string[])),
  executeRsync: vi.fn(() =>
    Promise.resolve({ success: true, filesTransferred: 1, bytesTransferred: 1, errors: [] })
  ),
  order: [] as string[],
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('ora', () => ({
  default: () => {
    const spinner = {
      text: '',
      start: () => spinner,
      succeed: vi.fn(),
      fail: vi.fn(),
      stop: vi.fn(),
    };
    return spinner;
  },
}));
vi.mock('../../remote/ssh/index.js', () => ({
  createTempSSHKeyFile: () => Promise.resolve('/tmp/key'),
  createTempKnownHostsFile: () => Promise.resolve('/tmp/kh'),
  removeTempSSHKeyFile: () => Promise.resolve(),
  removeTempKnownHostsFile: () => Promise.resolve(),
}));
vi.mock('../../remote/sync/index.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  executeRsync: (...args: unknown[]) => {
    m.order.push('transfer');
    return (m.executeRsync as (...a: unknown[]) => unknown)(...args);
  },
  warnSkippedEntries: vi.fn(),
}));
vi.mock('../repo-sync-parents.js', () => ({
  ensureUploadParents: (...args: unknown[]) => {
    m.order.push('parents');
    return (m.ensureUploadParents as (...a: unknown[]) => unknown)(...args);
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: () => Promise.resolve({ machines: {} }),
    getRepository: () => Promise.resolve(undefined),
  },
}));
vi.mock('../../services/core/audit.js', () => ({ auditService: { recordOperation: vi.fn() } }));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: vi.fn(),
  writeStderr: vi.fn(),
  writeStdout: vi.fn(),
}));
vi.mock('../../services/machine/machine-connection.js', () => ({ withPooledSftp: vi.fn() }));
vi.mock('../../services/machine/ssh-connection.js', () => ({
  getSSHConnectionDetails: () =>
    Promise.resolve({
      host: '10.0.0.1',
      port: 22,
      user: 'root',
      privateKey: 'KEY',
      known_hosts: 'kh',
      universalUser: 'rediacc',
      workingDirectory: '/mnt/repo',
      datastore: WK_DATASTORE_PATH,
    }),
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn(),
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: () => Promise.resolve(),
}));
vi.mock('../../services/repo/repo-mount-check.js', () => ({
  assertRepoMountedOnMachine: () => Promise.resolve(),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: () => Promise.resolve(),
  validateRemotePath: vi.fn(),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', kubeCluster: undefined }),
}));
vi.mock('../../utils/spinner.js', () => ({
  oraOptions: (text: string) => ({ text }),
  withSpinner: (_label: string, fn: () => unknown) => fn(),
}));

const { registerRepoSyncCommands } = await import('../repo-sync.js');

let dir = '';
let local = '';

beforeEach(() => {
  vi.clearAllMocks();
  m.order.length = 0;
  dir = mkdtempSync(path.join(tmpdir(), 'repo-sync-parents-'));
  local = path.join(dir, 'f.txt');
  writeFileSync(local, 'x');
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

async function upload(...flags: string[]): Promise<void> {
  const repo = new Command().exitOverride();
  registerRepoSyncCommands(repo);
  await repo.parseAsync(['node', 'rdc', 'sync', 'upload', 'app', ...flags]);
}

describe('repo sync upload remote-parents wiring', () => {
  it('creates the remote parents before the transfer rsync, for the --remote-file path', async () => {
    await upload('--local', local, '--remote-file', 'a/b/f.txt');
    expect(m.ensureUploadParents).toHaveBeenCalledTimes(1);
    expect((m.ensureUploadParents.mock.calls[0] as unknown[])[1]).toBe('a/b/f.txt');
    expect(m.order).toEqual(['parents', 'transfer']);
  });
});
