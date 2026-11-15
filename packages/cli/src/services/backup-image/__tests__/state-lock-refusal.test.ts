import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { acquireLocalLock, ImageLockError, sleepSync } from '../state.js';

let root: string;
let lockPath: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'img-lock-refusal-'));
  lockPath = join(root, 'repo.lock');
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('unreadable lock refusal text', () => {
  it('names the path and tells the operator to remove it by hand when no run is writing it', () => {
    writeFileSync(lockPath, '');
    let error: unknown;
    try {
      acquireLocalLock(lockPath, {
        pid: 8,
        host: 'h1',
        isPidAlive: () => true,
        sleep: () => undefined,
      });
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(ImageLockError);
    expect((error as Error).message).toBe(
      `${lockPath} exists and is unreadable; if no run is writing it, remove it by hand`
    );
  });

  it('control: a readable live holder is refused with the holder text, not the by-hand advice', () => {
    writeFileSync(
      lockPath,
      JSON.stringify({ pid: 77, host: 'h1', startedAt: '2026-01-01T00:00:00.000Z' })
    );
    expect(() =>
      acquireLocalLock(lockPath, { pid: 8, host: 'h1', isPidAlive: () => true })
    ).toThrow(/another run holds .* \(pid 77 on h1\)/);
  });
});

describe('default sleepSync', () => {
  it('blocks for at least the requested time', () => {
    const start = process.hrtime.bigint();
    sleepSync(60);
    const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
    expect(elapsedMs).toBeGreaterThanOrEqual(55);
  });

  it('control: a zero wait returns at once', () => {
    const start = process.hrtime.bigint();
    sleepSync(0);
    expect(Number(process.hrtime.bigint() - start) / 1e6).toBeLessThan(50);
  });
});
