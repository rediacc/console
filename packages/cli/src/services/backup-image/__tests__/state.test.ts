import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  acquireLocalLock,
  type BeginRunInput,
  beginRun,
  completeRun,
  failRun,
  HISTORY_LIMIT,
  ImageLockError,
  type ImageState,
  localImagePaths,
  readImageState,
  recordUpload,
  releaseLocalLock,
  writeFully,
  writeImageState,
} from '../state.js';

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'img-state-'));
});
afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

const input = (now = '2026-10-29T10:00:00Z'): BeginRunInput => ({
  config: 'eu-remote',
  machine: 'hostinger',
  image: 'mail.latest.img',
  repo: { name: 'mail', tag: 'latest', guid: 'g-1', grandGuid: null },
  snapshotTakenAt: now,
  snapshotName: '.snapshot-g-1-x',
  apparentBytes: 100,
  allocatedBytes: 40,
  checkpoint: false,
  now,
});

const done = (now: string) => ({
  sha256: 'ab'.repeat(32),
  verify: 'sha256+rsync' as const,
  literalBytes: 10,
  matchedBytes: 90,
  durationMs: 5,
  now,
});

describe('localImagePaths', () => {
  it('lays files out under <dir>/<machine> with dotted stems', () => {
    const p = localImagePaths('/d', 'hostinger', 'mail', 'latest');
    expect(p.machineDir).toBe('/d/hostinger');
    expect(p.image).toBe('/d/hostinger/mail.latest.img');
    expect(p.state).toBe('/d/hostinger/mail.latest.state.json');
    expect(p.lock).toBe('/d/hostinger/mail.latest.lock');
  });
});

describe('state file writes', () => {
  it('is 0600 and creates its directory 0700', () => {
    const p = localImagePaths(root, 'hostinger', 'mail', 'latest');
    writeImageState(p.state, beginRun(null, input()));
    expect(statSync(p.state).mode & 0o777).toBe(0o600);
    expect(statSync(p.machineDir).mode & 0o777).toBe(0o700);
    expect(readImageState(p.state)?.status).toBe('incomplete');
  });

  it('returns null for a missing file', () => {
    expect(readImageState(join(root, 'none.json'))).toBeNull();
  });

  it('a write interrupted before the rename leaves the previous state readable', () => {
    const p = localImagePaths(root, 'm', 'mail', 'latest');
    const first = beginRun(null, input());
    writeImageState(p.state, first);
    const second = completeRun(first, done('2026-10-29T11:00:00Z'));
    expect(() =>
      writeImageState(p.state, second, {
        beforeRename: () => {
          throw new Error('crash');
        },
      })
    ).toThrow('crash');
    expect(readImageState(p.state)?.status).toBe('incomplete');
    expect(readdirSync(p.machineDir).filter((f) => f.includes('.tmp-'))).toEqual([]);
  });

  it('writes the rest of a short write and refuses a write that makes no progress', () => {
    const chunks: string[] = [];
    // A disk that takes at most 3 bytes per call.
    writeFully(7, 'hello world', (_fd, buf, offset, length) => {
      const n = Math.min(3, length);
      chunks.push(buf.subarray(offset, offset + n).toString());
      return n;
    });
    expect(chunks.join('')).toBe('hello world');
    // A full disk: the first call writes 4 bytes, then nothing.
    let calls = 0;
    expect(() => writeFully(7, 'hello world', () => (calls++ === 0 ? 4 : 0))).toThrow(
      'short write: 4 of 11 bytes written'
    );
  });

  it('drops a planted credential field, never writing it', () => {
    const p = localImagePaths(root, 'm', 'mail', 'latest');
    const dirty = beginRun(null, input()) as ImageState & Record<string, unknown>;
    dirty.credential = 'SECRET-PASSPHRASE';
    (dirty.repo as unknown as Record<string, unknown>).credential = 'SECRET-PASSPHRASE';
    (dirty.run as unknown as Record<string, unknown>).token = 'SECRET-PASSPHRASE';
    writeImageState(p.state, dirty);
    expect(readFileSync(p.state, 'utf8')).not.toContain('SECRET-PASSPHRASE');
  });
});

describe('run lifecycle', () => {
  it('begin keeps the previous complete block and counts attempts', () => {
    const s1 = completeRun(beginRun(null, input()), done('2026-10-29T10:30:00Z'));
    expect(s1.status).toBe('complete');
    const s2 = beginRun(s1, input('2026-11-05T10:00:00Z'));
    expect(s2.status).toBe('incomplete');
    expect(s2.complete?.sha256).toBe('ab'.repeat(32));
    expect(s2.run.attempts).toBe(1);
    const s3 = beginRun(failRun(s2, { error: 'x', now: 'n' }), input('2026-11-06T10:00:00Z'));
    expect(s3.run.attempts).toBe(2);
  });

  it('fail keeps incomplete and records the error and outcome', () => {
    const s = failRun(beginRun(null, input()), {
      error: 'sha256 mismatch',
      outcome: 'interrupted',
      now: '2026-10-29T10:10:00Z',
    });
    expect(s.status).toBe('incomplete');
    expect(s.run.lastError).toBe('sha256 mismatch');
    expect(s.history.at(-1)?.outcome).toBe('interrupted');
  });

  it('records and clears the upload block', () => {
    const s = recordUpload(beginRun(null, input()), {
      machine: 'm2',
      name: 'mail',
      guid: 'g-2',
      datastore: '/mnt/rediacc',
      startedAt: 'n',
      status: 'staging',
    });
    expect(s.upload?.guid).toBe('g-2');
    expect(recordUpload(s, null).upload).toBeNull();
  });

  it('history caps at 12', () => {
    let s = beginRun(null, input());
    for (let i = 0; i < 20; i++) {
      s = failRun(beginRun(s, input()), { error: 'e', literalBytes: i, now: `t${i}` });
    }
    expect(s.history).toHaveLength(HISTORY_LIMIT);
    expect(s.history.at(-1)?.literalBytes).toBe(19);
    expect(s.history[0]?.literalBytes).toBe(8);
    const p = localImagePaths(root, 'm', 'mail', 'latest');
    writeImageState(p.state, s);
    expect(readImageState(p.state)?.history).toHaveLength(HISTORY_LIMIT);
  });
});

describe('local lock', () => {
  const lock = () => join(root, 'mail.latest.lock');

  it('refuses a live holder', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'h', isPidAlive: () => true });
    expect(() => acquireLocalLock(lock(), { pid: 222, host: 'h', isPidAlive: () => true })).toThrow(
      ImageLockError
    );
  });

  it('takes over a dead pid on the same host', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'h', isPidAlive: () => true });
    const info = acquireLocalLock(lock(), { pid: 222, host: 'h', isPidAlive: () => false });
    expect(info.pid).toBe(222);
    expect(JSON.parse(readFileSync(lock(), 'utf8')).pid).toBe(222);
  });

  it('never takes over a lock from another host', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'other', isPidAlive: () => false });
    expect(() =>
      acquireLocalLock(lock(), { pid: 222, host: 'h', isPidAlive: () => false })
    ).toThrow(ImageLockError);
  });

  it('a crash between writing the lock body and publishing it leaves no lock, so the next run is not refused', () => {
    expect(() =>
      acquireLocalLock(lock(), {
        pid: 111,
        host: 'h',
        beforePublish: () => {
          throw new Error('crash');
        },
      })
    ).toThrow('crash');
    expect(existsSync(lock())).toBe(false);
    expect(readdirSync(root)).toEqual([]);
    expect(acquireLocalLock(lock(), { pid: 222, host: 'h' }).pid).toBe(222);
  });

  it('a takeover never deletes the fresh lock a faster run created over the same dead holder', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'h', isPidAlive: () => true });
    const alive = (pid: number) => pid === 333;
    expect(() =>
      acquireLocalLock(lock(), {
        pid: 222,
        host: 'h',
        isPidAlive: alive,
        // The faster run (pid 333) removes the dead lock and creates its own while this one is between its read and its takeover.
        beforeTakeover: () => {
          rmSync(lock());
          acquireLocalLock(lock(), { pid: 333, host: 'h', isPidAlive: alive });
        },
      })
    ).toThrow(ImageLockError);
    expect(JSON.parse(readFileSync(lock(), 'utf8')).pid).toBe(333);
    expect(readdirSync(root)).toEqual(['mail.latest.lock']);
  });

  it('takes the lock when the dead holder is removed before the takeover', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'h', isPidAlive: () => true });
    const info = acquireLocalLock(lock(), {
      pid: 222,
      host: 'h',
      isPidAlive: () => false,
      beforeTakeover: () => rmSync(lock()),
    });
    expect(info.pid).toBe(222);
    expect(JSON.parse(readFileSync(lock(), 'utf8')).pid).toBe(222);
  });

  it('releases only its own lock', () => {
    acquireLocalLock(lock(), { pid: 111, host: 'h' });
    releaseLocalLock(lock(), { pid: 222, host: 'h' });
    expect(existsSync(lock())).toBe(true);
    releaseLocalLock(lock(), { pid: 111, host: 'h' });
    expect(existsSync(lock())).toBe(false);
    writeFileSync(lock(), 'not json');
    releaseLocalLock(lock());
    expect(existsSync(lock())).toBe(true);
  });
});
