import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import {
  buildSyncRemotePaths,
  resolveUploadLocalPaths,
  validateDownloadOptions,
  validateUploadOptions,
} from '../repo-sync-helpers.js';

describe('resolveUploadLocalPaths', () => {
  let root: string;
  let fileA: string;
  let fileB: string;
  let dirC: string;

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), 'rdc-sync-test-'));
    fileA = join(root, 'a.txt');
    fileB = join(root, 'b.md');
    dirC = join(root, 'dir');
    writeFileSync(fileA, 'A');
    writeFileSync(fileB, 'B');
    mkdirSync(dirC, { recursive: true });
    writeFileSync(join(dirC, 'nested.txt'), 'nested');
  });

  afterAll(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('defaults to cwd as a directory source', () => {
    const result = resolveUploadLocalPaths(undefined);
    expect(result).toHaveLength(1);
    expect(result[0].isFile).toBe(false);
    expect(result[0].path.endsWith('/')).toBe(true);
  });

  it('treats a single file path as a file source without trailing slash', () => {
    const [src] = resolveUploadLocalPaths([fileA]);
    expect(src.isFile).toBe(true);
    expect(src.path).toBe(fileA);
    expect(src.path.endsWith('/')).toBe(false);
    expect(src.rawPath).toBe(fileA);
  });

  it('appends trailing slash to directory sources', () => {
    const [src] = resolveUploadLocalPaths([dirC]);
    expect(src.isFile).toBe(false);
    expect(src.path.endsWith('/')).toBe(true);
    expect(src.rawPath).toBe(dirC);
  });

  it('handles mixed file + directory inputs', () => {
    const result = resolveUploadLocalPaths([fileA, dirC, fileB]);
    expect(result).toHaveLength(3);
    expect(result[0]).toMatchObject({ isFile: true, rawPath: fileA });
    expect(result[1]).toMatchObject({ isFile: false, rawPath: dirC });
    expect(result[1].path.endsWith('/')).toBe(true);
    expect(result[2]).toMatchObject({ isFile: true, rawPath: fileB });
  });

  it('throws when a path does not exist', () => {
    const missing = join(root, 'does-not-exist.bin');
    expect(() => resolveUploadLocalPaths([missing])).toThrow(/does not exist/i);
  });

  it('does not double-append a trailing slash when caller already added one', () => {
    const [src] = resolveUploadLocalPaths([`${dirC}/`]);
    expect(src.path.endsWith('//')).toBe(false);
    expect(src.path.endsWith('/')).toBe(true);
  });
});

describe('validateDownloadOptions', () => {
  let dir: string;
  let file: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'rdc-download-test-'));
    file = join(dir, 'f.txt');
    writeFileSync(file, '');
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('rejects --remote and --remote-file together', () => {
    expect(() => validateDownloadOptions({ remote: 'a', remoteFile: 'b', local: dir })).toThrow(
      /together/i
    );
  });

  it('rejects --mirror with --remote-file', () => {
    expect(() =>
      validateDownloadOptions({ remoteFile: 'f.txt', mirror: true, local: dir })
    ).toThrow(/mirror/i);
  });

  it('rejects --remote-file when --local is a file', () => {
    expect(() => validateDownloadOptions({ remoteFile: 'f.txt', local: file })).toThrow(
      /must be an existing directory/i
    );
  });

  it('accepts --remote-file with a directory --local', () => {
    const result = validateDownloadOptions({ remoteFile: 'f.txt', local: dir });
    expect(result.isFileMode).toBe(true);
    expect(result.localPath).toBe(dir);
  });

  it('falls back to directory mode when neither file flag is set', () => {
    const result = validateDownloadOptions({ remote: 'sub', local: dir });
    expect(result.isFileMode).toBe(false);
  });
});

describe('buildSyncRemotePaths', () => {
  const base = '/mnt/rediacc/mounts/repo-guid';

  it('directory mode without subpath: trailing slash and "."', () => {
    const r = buildSyncRemotePaths(base, undefined, false);
    expect(r.remotePath).toBe(`${base}/`);
    expect(r.sftpRemotePath).toBe('.');
  });

  it('directory mode with subpath: trailing slash on both', () => {
    const r = buildSyncRemotePaths(base, 'sub', false);
    expect(r.remotePath).toBe(`${base}/sub/`);
    expect(r.sftpRemotePath).toBe('sub/');
  });

  it('file mode with nested subpath: no trailing slash', () => {
    const r = buildSyncRemotePaths(base, 'a/b.txt', true);
    expect(r.remotePath).toBe(`${base}/a/b.txt`);
    expect(r.sftpRemotePath).toBe('a/b.txt');
    expect(r.remotePath.endsWith('/')).toBe(false);
  });

  it('file mode with deep nested subpath', () => {
    const r = buildSyncRemotePaths(base, 'etc/config/app.toml', true);
    expect(r.remotePath).toBe(`${base}/etc/config/app.toml`);
    expect(r.sftpRemotePath).toBe('etc/config/app.toml');
  });

  it('file mode with undefined subpath returns base path with no trailing slash', () => {
    // Single-file mode against a missing subpath returns the base directly
    // (no trailing slash) so rsync sees a file-target rather than dir-target.
    const r = buildSyncRemotePaths(base, undefined, true);
    expect(r.remotePath).toBe(base);
    expect(r.sftpRemotePath).toBe('');
  });

  it('directory mode strips caller-provided trailing slash to avoid `path//`', () => {
    // Bug fix: previously the helper concatenated `sub/` + `/` producing
    // `sub//`, which broke rsync semantics on some hosts. Now it
    // normalizes the caller's input by stripping leading + trailing slashes.
    const r = buildSyncRemotePaths(base, 'sub/', false);
    expect(r.remotePath).toBe(`${base}/sub/`);
    expect(r.sftpRemotePath).toBe('sub/');
  });

  it('directory mode strips both leading and trailing slashes', () => {
    const r = buildSyncRemotePaths(base, '/sub/nested/', false);
    expect(r.remotePath).toBe(`${base}/sub/nested/`);
    expect(r.sftpRemotePath).toBe('sub/nested/');
  });

  it('file mode strips slashes around the subpath', () => {
    const r = buildSyncRemotePaths(base, '/etc/file.txt/', true);
    expect(r.remotePath).toBe(`${base}/etc/file.txt`);
    expect(r.sftpRemotePath).toBe('etc/file.txt');
  });
});

describe('validateUploadOptions', () => {
  let root: string;
  let file: string;
  let dir: string;

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), 'rdc-upload-validate-'));
    file = join(root, 'a.txt');
    dir = join(root, 'sub');
    writeFileSync(file, 'a');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'inner.txt'), 'i');
  });

  afterAll(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('rejects --remote and --remote-file together', () => {
    expect(() => validateUploadOptions({ local: [file], remote: 'a', remoteFile: 'b' })).toThrow(
      /together/i
    );
  });

  it('rejects --mirror with --remote-file', () => {
    expect(() => validateUploadOptions({ local: [file], remoteFile: 'b', mirror: true })).toThrow(
      /mirror/i
    );
  });

  it('rejects --mirror when any source is a file', () => {
    expect(() => validateUploadOptions({ local: [file], mirror: true })).toThrow(/mirror/i);
  });

  it('rejects --remote-file with a directory --local', () => {
    expect(() => validateUploadOptions({ local: [dir], remoteFile: 'a.txt' })).toThrow(
      /exactly one/i
    );
  });

  it('rejects --remote-file with multiple --local paths', () => {
    expect(() => validateUploadOptions({ local: [file, dir], remoteFile: 'a.txt' })).toThrow(
      /exactly one/i
    );
  });

  it('accepts --remote-file with a single file --local', () => {
    const r = validateUploadOptions({ local: [file], remoteFile: 'a.txt' });
    expect(r.isFileMode).toBe(true);
    expect(r.sources).toHaveLength(1);
    expect(r.sources[0].isFile).toBe(true);
  });

  it('accepts --remote without --remote-file for directory uploads', () => {
    const r = validateUploadOptions({ local: [dir], remote: 'sub' });
    expect(r.isFileMode).toBe(false);
    expect(r.sources[0].isFile).toBe(false);
  });

  it('accepts no flags (defaults to cwd directory upload)', () => {
    const r = validateUploadOptions({ local: [dir] });
    expect(r.isFileMode).toBe(false);
  });
});
