import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A filesystem without hard links (exFAT, FAT32) answers link() with EPERM; a WSL-mounted
// exFAT drive refused every `rdc backup download` lock on 2026-11-13 this way.
const linkCode = { value: 'EPERM' as string | null };
const probeDenied: { value: boolean } = { value: false };
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    openSync: (path: string, ...rest: unknown[]) => {
      if (probeDenied.value && String(path).includes('.clock-')) {
        const error = new Error('EACCES: open') as NodeJS.ErrnoException;
        error.code = 'EACCES';
        throw error;
      }
      return (actual.openSync as (...args: unknown[]) => number)(path, ...rest);
    },
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

const { acquireLocalLock, ImageLockError, releaseLocalLock, UNREADABLE_LOCK_RETRY_MS } =
  await import('../state.js');
const noSleep = (): void => undefined;

describe('local lock on a filesystem without hard links', () => {
  let dir: string;
  let lockPath: string;
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'bdl-nolink-'));
    lockPath = join(dir, 'app.latest.lock');
    linkCode.value = 'EPERM';
    probeDenied.value = false;
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it('takes the lock through an exclusive create and leaves no temp file', () => {
    const info = acquireLocalLock(lockPath, {
      pid: 4242,
      host: 'h1',
      isPidAlive: () => true,
    });
    expect(JSON.parse(readFileSync(lockPath, 'utf8'))).toEqual(info);
    expect(existsSync(lockPath)).toBe(true);
    expect(readdirSync(dir)).toEqual(['app.latest.lock']);
    releaseLocalLock(lockPath, { pid: 4242, host: 'h1' });
    expect(existsSync(lockPath)).toBe(false);
  });

  it.each(['EPERM', 'ENOTSUP', 'EOPNOTSUPP', 'ENOSYS'])(
    'takes the exclusive-create fallback when link() answers %s',
    (code) => {
      linkCode.value = code;
      const info = acquireLocalLock(lockPath, {
        pid: 7,
        host: 'h1',
        isPidAlive: () => true,
      });
      expect(JSON.parse(readFileSync(lockPath, 'utf8'))).toEqual(info);
      expect(readdirSync(dir)).toEqual(['app.latest.lock']);
    }
  );

  it('takes over an empty lock a crash left behind once it is past the grace period', () => {
    writeFileSync(lockPath, '');
    const info = acquireLocalLock(lockPath, {
      pid: 8,
      host: 'h1',
      isPidAlive: () => true,
      unreadableGraceMs: -1,
    });
    expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(info.pid);
    expect(readdirSync(dir)).toEqual(['app.latest.lock']);
  });

  it('control: still refuses a fresh unreadable lock, which a live run may be writing', () => {
    writeFileSync(lockPath, '');
    expect(() =>
      acquireLocalLock(lockPath, {
        pid: 8,
        host: 'h1',
        isPidAlive: () => true,
        sleep: noSleep,
      })
    ).toThrow(/unreadable/);
    expect(readFileSync(lockPath, 'utf8')).toBe('');
  });

  it('control: judges a lock by the filesystem clock, so a skewed host clock cannot make a fresh one look old', () => {
    writeFileSync(lockPath, '');
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(Date.now() + 3_600_000);
    try {
      expect(() =>
        acquireLocalLock(lockPath, {
          pid: 8,
          host: 'h1',
          isPidAlive: () => true,
          sleep: noSleep,
        })
      ).toThrow(/unreadable/);
    } finally {
      vi.useRealTimers();
    }
    expect(readdirSync(dir)).toEqual(['app.latest.lock']);
  });

  it('refuses an old unreadable lock when no probe file can be made, since the mount clock is unknown', () => {
    // Review ee0ca8b1.1: a mount whose clock runs behind would stamp a live run's fresh lock in the past,
    // so with no probe the host clock cannot tell an abandoned lock from a live one.
    writeFileSync(lockPath, '');
    const old = new Date(Date.now() - 3_600_000);
    utimesSync(lockPath, old, old);
    probeDenied.value = true;
    expect(() =>
      acquireLocalLock(lockPath, {
        pid: 9,
        host: 'h1',
        isPidAlive: () => true,
        sleep: noSleep,
      })
    ).toThrow(/unreadable/);
    expect(readFileSync(lockPath, 'utf8')).toBe('');
  });

  it('control: with no probe file, a fresh unreadable lock is still refused', () => {
    writeFileSync(lockPath, '');
    probeDenied.value = true;
    expect(() =>
      acquireLocalLock(lockPath, {
        pid: 9,
        host: 'h1',
        isPidAlive: () => true,
        sleep: noSleep,
      })
    ).toThrow(/unreadable/);
  });

  it('still refuses a live holder', () => {
    acquireLocalLock(lockPath, { pid: 1, host: 'h1', isPidAlive: () => true });
    expect(() =>
      acquireLocalLock(lockPath, {
        pid: 2,
        host: 'h1',
        isPidAlive: () => true,
      })
    ).toThrow(ImageLockError);
  });

  it('still takes over a dead holder on the same host', () => {
    acquireLocalLock(lockPath, { pid: 1, host: 'h1', isPidAlive: () => true });
    const info = acquireLocalLock(lockPath, {
      pid: 2,
      host: 'h1',
      isPidAlive: () => false,
    });
    expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(info.pid);
  });

  it('control: a link error that is not a missing-hard-link code still fails the run', () => {
    linkCode.value = 'EIO';
    expect(() =>
      acquireLocalLock(lockPath, {
        pid: 3,
        host: 'h1',
        isPidAlive: () => true,
      })
    ).toThrow(/EIO/);
  });

  describe('retrying an unreadable lock', () => {
    it('re-reads the lock after 10 s, and a lock that became readable follows the live-holder rule', () => {
      writeFileSync(lockPath, '');
      const sleeps: number[] = [];
      const live = {
        pid: 77,
        host: 'h1',
        startedAt: '2026-01-01T00:00:00.000Z',
      };
      expect(() =>
        acquireLocalLock(lockPath, {
          pid: 8,
          host: 'h1',
          isPidAlive: () => true,
          sleep: (ms) => {
            sleeps.push(ms);
            writeFileSync(lockPath, JSON.stringify(live));
          },
        })
      ).toThrow(ImageLockError);
      expect(sleeps).toEqual([UNREADABLE_LOCK_RETRY_MS]);
      expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(77);
    });

    it('takes over a dead holder once the lock became readable', () => {
      writeFileSync(lockPath, '');
      const info = acquireLocalLock(lockPath, {
        pid: 8,
        host: 'h1',
        isPidAlive: () => false,
        sleep: () =>
          writeFileSync(
            lockPath,
            JSON.stringify({
              pid: 77,
              host: 'h1',
              startedAt: '2026-01-01T00:00:00.000Z',
            })
          ),
      });
      expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(info.pid);
    });

    it('takes over when the probe starts working on the third attempt', () => {
      writeFileSync(lockPath, '');
      const old = new Date(Date.now() - 3_600_000);
      utimesSync(lockPath, old, old);
      probeDenied.value = true;
      let sleeps = 0;
      const info = acquireLocalLock(lockPath, {
        pid: 9,
        host: 'h1',
        isPidAlive: () => true,
        sleep: () => {
          sleeps += 1;
          if (sleeps === 2) probeDenied.value = false;
        },
      });
      expect(sleeps).toBe(2);
      expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(info.pid);
    });

    it('refuses after three attempts, naming the path and the remedy', () => {
      writeFileSync(lockPath, '');
      const old = new Date(Date.now() - 3_600_000);
      utimesSync(lockPath, old, old);
      probeDenied.value = true;
      const sleeps: number[] = [];
      let message = '';
      try {
        acquireLocalLock(lockPath, {
          pid: 9,
          host: 'h1',
          isPidAlive: () => true,
          sleep: (ms) => sleeps.push(ms),
        });
      } catch (error) {
        message = (error as Error).message;
      }
      expect(sleeps).toEqual([UNREADABLE_LOCK_RETRY_MS, UNREADABLE_LOCK_RETRY_MS]);
      expect(message).toContain(lockPath);
      expect(message).toMatch(/remove it by hand/);
    });

    it('control: a fresh readable live lock is never taken over and never waited on', () => {
      acquireLocalLock(lockPath, {
        pid: 1,
        host: 'h1',
        isPidAlive: () => true,
      });
      const sleeps: number[] = [];
      expect(() =>
        acquireLocalLock(lockPath, {
          pid: 2,
          host: 'h1',
          isPidAlive: () => true,
          sleep: (ms) => sleeps.push(ms),
        })
      ).toThrow(ImageLockError);
      expect(sleeps).toEqual([]);
      expect(JSON.parse(readFileSync(lockPath, 'utf8')).pid).toBe(1);
    });
  });
});
