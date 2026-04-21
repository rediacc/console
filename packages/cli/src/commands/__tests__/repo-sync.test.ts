import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { resolveUploadLocalPaths, validateDownloadOptions } from '../repo-sync-helpers.js';

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
