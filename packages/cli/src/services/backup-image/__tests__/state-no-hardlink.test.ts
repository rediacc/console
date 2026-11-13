import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A filesystem without hard links (exFAT, FAT32) answers link() with EPERM; a WSL-mounted
// exFAT drive refused every `rdc backup download` lock on 2026-11-13 this way.
const linkCode = { value: 'EPERM' as string | null };
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    linkSync: (src: string, dest: string) => {
      if (linkCode.value) {
        const error = new Error(`${linkCode.value}: link`) as NodeJS.ErrnoException;
        error.code = linkCode.value;
        throw error;
      }
      return actual.linkSync(src, dest);
    },
  };
});

const { acquireLocalLock, ImageLockError, releaseLocalLock } = await import('../state.js');

describe('local lock on a filesystem without hard links', () => {
  let dir: string;
  let lockPath: string;
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'bdl-nolink-'));
    lockPath = join(dir, 'app.latest.lock');
    linkCode.value = 'EPERM';
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it('takes the lock through an exclusive create and leaves no temp file', () => {
    const info = acquireLocalLock(lockPath, { pid: 4242, host: 'h1', isPidAlive: () => true });
    expect(JSON.parse(readFileSync(lockPath, 'utf8'))).toEqual(info);
    expect(existsSync(lockPath)).toBe(true);
    releaseLocalLock(lockPath, { pid: 4242, host: 'h1' });
    expect(existsSync(lockPath)).toBe(false);
  });

  it('still refuses a live holder', () => {
    acquireLocalLock(lockPath, { pid: 1, host: 'h1', isPidAlive: () => true });
    expect(() =>
      acquireLocalLock(lockPath, { pid: 2, host: 'h1', isPidAlive: () => true })
    ).toThrow(ImageLockError);
  });

  it('still takes over a dead holder on the same host', () => {
    acquireLocalLock(lockPath, { pid: 1, host: 'h1', isPidAlive: () => true });
    const info = acquireLocalLock(lockPath, { pid: 2, host: 'h1', isPidAlive: () => false });
    expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(info.pid);
  });

  it('control: a link error that is not a missing-hard-link code still fails the run', () => {
    linkCode.value = 'EIO';
    expect(() =>
      acquireLocalLock(lockPath, { pid: 3, host: 'h1', isPidAlive: () => true })
    ).toThrow(/EIO/);
  });
});
