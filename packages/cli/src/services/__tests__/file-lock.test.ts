/**
 * The cross-process provisioning lock.
 *
 * This module had no tests at all, while owning three behaviors that decide
 * whether a concurrent `rdc` run waits politely, steals a dead process's lock,
 * or hangs for two minutes and then says something useless: stale reclamation,
 * the wait notification, and the timeout error's shape.
 */

import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  acquireLocalLock,
  type LockHolder,
  LockTimeoutError,
  readLockHolder,
  releaseLocalLock,
} from '../core/file-lock.js';

let dir: string;
let lockPath: string;

beforeEach(async () => {
  dir = await fs.mkdtemp(path.join(os.tmpdir(), 'rdc-lock-test-'));
  lockPath = path.join(dir, 'provision.lock');
});

afterEach(async () => {
  await fs.rm(dir, { recursive: true, force: true });
});

/** Pretend another live process holds the lock (this process is certainly alive). */
async function holdWithLivePid(pid = process.pid): Promise<void> {
  await fs.mkdir(lockPath);
  await fs.writeFile(path.join(lockPath, 'pid'), String(pid));
}

/** A pid that is almost certainly not running. */
const DEAD_PID = 2_147_483_640;

describe('acquire and release', () => {
  it('creates the lock with this process pid, and releases it', async () => {
    await acquireLocalLock(lockPath, { deadline: Date.now() + 1000, pollMs: 5 });
    expect(await fs.readFile(path.join(lockPath, 'pid'), 'utf-8')).toBe(String(process.pid));

    await releaseLocalLock(lockPath);
    await expect(fs.stat(lockPath)).rejects.toThrow();
  });

  it('can be re-acquired after release', async () => {
    await acquireLocalLock(lockPath, { deadline: Date.now() + 1000, pollMs: 5 });
    await releaseLocalLock(lockPath);
    await expect(
      acquireLocalLock(lockPath, { deadline: Date.now() + 1000, pollMs: 5 })
    ).resolves.toBeUndefined();
  });
});

describe('stale reclamation', () => {
  it('reclaims a lock whose holder is gone', async () => {
    await holdWithLivePid(DEAD_PID);
    const onWait = vi.fn();

    // Deadline already passed: reclamation must not depend on waiting.
    await acquireLocalLock(lockPath, { deadline: Date.now() - 1, pollMs: 5, onWait });

    expect(await fs.readFile(path.join(lockPath, 'pid'), 'utf-8')).toBe(String(process.pid));
    expect(onWait).not.toHaveBeenCalled();
  });

  it('treats a malformed pid file as stale', async () => {
    await fs.mkdir(lockPath);
    await fs.writeFile(path.join(lockPath, 'pid'), 'not-a-pid');

    await acquireLocalLock(lockPath, { deadline: Date.now() - 1, pollMs: 5 });
    expect(await fs.readFile(path.join(lockPath, 'pid'), 'utf-8')).toBe(String(process.pid));
  });

  it('treats a missing pid file as stale', async () => {
    await fs.mkdir(lockPath);

    await acquireLocalLock(lockPath, { deadline: Date.now() - 1, pollMs: 5 });
    expect(await fs.readFile(path.join(lockPath, 'pid'), 'utf-8')).toBe(String(process.pid));
  });
});

describe('contention', () => {
  it('waits for a live holder and notifies exactly once', async () => {
    await holdWithLivePid();
    const seen: LockHolder[] = [];

    const acquiring = acquireLocalLock(lockPath, {
      deadline: Date.now() + 5_000,
      pollMs: 5,
      onWait: (holder) => seen.push(holder),
    });

    // Let several polls elapse, so a per-poll notification would be visible.
    await new Promise((resolve) => setTimeout(resolve, 60));
    await releaseLocalLock(lockPath);
    await acquiring;

    expect(seen).toHaveLength(1);
    expect(seen[0].pid).toBe(process.pid);
    expect(seen[0].heldForMs).toBeGreaterThanOrEqual(0);
    // /proc is Linux-only, so only the type is guaranteed.
    expect(['string', 'object']).toContain(typeof seen[0].command);
  });

  it('still acquires when the wait callback throws', async () => {
    await holdWithLivePid();

    const acquiring = acquireLocalLock(lockPath, {
      deadline: Date.now() + 5_000,
      pollMs: 5,
      onWait: () => {
        throw new Error('a broken progress renderer');
      },
    });

    await new Promise((resolve) => setTimeout(resolve, 30));
    await releaseLocalLock(lockPath);
    await expect(acquiring).resolves.toBeUndefined();
  });
});

describe('timeout', () => {
  it('throws LockTimeoutError naming the live holder', async () => {
    await holdWithLivePid();

    const error = await acquireLocalLock(lockPath, {
      deadline: Date.now() + 20,
      pollMs: 5,
    }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(LockTimeoutError);
    expect(error).toBeInstanceOf(Error);
    const timeout = error as LockTimeoutError;
    expect(timeout.lockPath).toBe(lockPath);
    expect(timeout.holder.pid).toBe(process.pid);
    expect(timeout.holder.heldForMs).toBeGreaterThanOrEqual(0);
  });
});

describe('readLockHolder', () => {
  it('reports nulls for a lock that does not exist', async () => {
    const holder = await readLockHolder(lockPath);
    expect(holder).toEqual({ pid: null, heldForMs: null, command: null });
  });

  it('reads the pid of an existing lock', async () => {
    await holdWithLivePid();
    const holder = await readLockHolder(lockPath);
    expect(holder.pid).toBe(process.pid);
    expect(holder.heldForMs).toBeGreaterThanOrEqual(0);
  });
});
