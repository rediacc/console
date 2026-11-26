/**
 * Command-level behaviour of the repo sync fixes: the SFTP fallback when rsync cannot start (W3), `status` reporting the
 * files only the local side holds (W4), and the mirror's deletion count (W5). The rsync layer is mocked.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  unusable: undefined as string | undefined,
  executeRsync: vi.fn(),
  preview: vi.fn(),
  out: [] as string[],
  err: [] as string[],
}));

vi.mock('../../remote/sync/index.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  rsyncUnusableReason: () => Promise.resolve(m.unusable),
  executeRsync: m.executeRsync,
  getRsyncPreview: m.preview,
}));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  writeStdout: (s: string) => m.out.push(s),
  writeStderr: (s: string) => m.err.push(s),
  setExitCode: () => undefined,
}));

import { executeSyncWithSftpFallback } from '../repo-sync.js';
import { handleDryRun } from '../repo-sync-helpers.js';

const sftpOk = () =>
  Promise.resolve({
    success: true,
    filesTransferred: 2,
    bytesTransferred: 10,
    duration: 1,
    errors: [],
  });

const rsyncResult = (over: Record<string, unknown> = {}) => ({
  success: true,
  filesTransferred: 1,
  bytesTransferred: 0,
  duration: 1,
  errors: [],
  skipped: [],
  deleted: 0,
  ...over,
});

const base = { sshOptions: '', source: '/a/', destination: 'h:/b/' };

beforeEach(() => {
  m.unusable = undefined;
  m.executeRsync.mockReset();
  m.preview.mockReset();
  m.out = [];
  m.err = [];
});

describe('SFTP fallback when rsync cannot start', () => {
  it('warns with the reason and transfers by SFTP without calling rsync', async () => {
    m.unusable = 'rsync --version: exit code 3221225781 (0xC0000135)';
    const sftp = vi.fn(sftpOk);
    const counts = await executeSyncWithSftpFallback(base, 'upload', sftp);
    expect(m.executeRsync).not.toHaveBeenCalled();
    expect(sftp).toHaveBeenCalledOnce();
    expect(counts.filesTransferred).toBe(2);
    expect(m.err.join('')).toContain('0xC0000135');
  });

  it('control: a working rsync is used and SFTP is untouched', async () => {
    m.executeRsync.mockResolvedValue(rsyncResult());
    const sftp = vi.fn(sftpOk);
    await executeSyncWithSftpFallback(base, 'upload', sftp);
    expect(m.executeRsync).toHaveBeenCalledOnce();
    expect(sftp).not.toHaveBeenCalled();
  });

  it('refuses a mirror on the SFTP path, which cannot delete', async () => {
    m.unusable = 'broken';
    const sftp = vi.fn(sftpOk);
    await expect(
      executeSyncWithSftpFallback({ ...base, mirror: true }, 'upload', sftp)
    ).rejects.toThrow(/mirror/i);
    expect(sftp).not.toHaveBeenCalled();
  });
});

describe('mirror deletion count', () => {
  it('reports the deleted files beside the transferred count', async () => {
    m.executeRsync.mockResolvedValue(rsyncResult({ filesTransferred: 0, deleted: 4 }));
    await executeSyncWithSftpFallback({ ...base, mirror: true }, 'upload', sftpOk);
    expect(m.out.join('')).toContain('4');
    expect(m.out.join('')).toMatch(/delet/i);
  });

  it('control: no deletions prints no deletion line', async () => {
    m.executeRsync.mockResolvedValue(rsyncResult());
    await executeSyncWithSftpFallback({ ...base, mirror: true }, 'upload', sftpOk);
    expect(m.out.join('')).not.toMatch(/delet/i);
  });
});

describe('status local-only files', () => {
  const empty = { newFiles: [], modifiedFiles: [], deletedFiles: [], newDirs: [], other: [] };
  const opts = { sshOptions: '', source: 'h:/b/', destination: '/a/' };

  it('lists a file only the local side holds instead of saying everything is in sync', async () => {
    m.preview.mockResolvedValue({ ...empty, deletedFiles: ['skip/x.log'] });
    await handleDryRun(opts, { localOnly: true });
    const text = m.out.join('');
    expect(text).toContain('skip/x.log');
    expect(text).not.toContain('everything is in sync');
  });

  it('control: nothing differs still says in sync', async () => {
    m.preview.mockResolvedValue(empty);
    await handleDryRun(opts, { localOnly: true });
    expect(m.out.join('')).toContain('everything is in sync');
  });

  it('keeps remote-side changes in the summary beside the local-only list', async () => {
    m.preview.mockResolvedValue({ ...empty, newFiles: ['n.txt'], deletedFiles: ['only-local'] });
    await handleDryRun(opts, { localOnly: true });
    const text = m.out.join('');
    expect(text).toContain('New files: 1');
    expect(text).toContain('only-local');
  });
});

describe('sshKeyDiagnostic', () => {
  it('prints a PEM armour header but never key material (8b24deb8.2)', async () => {
    const { sshKeyDiagnostic } = await import('../repo-sync-display.js');
    const secret = `b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW${'A'.repeat(200)}`;
    // A malformed key with no newline must not print its body.
    const flat = sshKeyDiagnostic(`-----BEGIN OPENSSH ${'PRIVATE KEY'}-----${secret}`);
    expect(flat).not.toContain(secret.slice(0, 40));
    expect(flat).toContain('header="<not a PEM header>"');
    // Control: a well-formed key shows its armour line only.
    const good = sshKeyDiagnostic(
      `-----BEGIN OPENSSH ${'PRIVATE KEY'}-----\n${secret}\n-----END OPENSSH PRIVATE KEY-----\n`
    );
    expect(good).toContain(`header="-----BEGIN OPENSSH ${'PRIVATE KEY'}-----"`);
    expect(good).not.toContain(secret.slice(0, 40));
  });
});
