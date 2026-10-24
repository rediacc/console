import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { acquireSegLock } from '../seg-lock.ts';

describe('acquireSegLock', () => {
  it('excludes a second holder until the first releases, and releases on demand', async () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'seglock-'));
    const file = path.join(dir, 'x.lock');
    try {
      const a = await acquireSegLock('x', file);
      let bHeld = false;
      const b = acquireSegLock('x', file).then((l) => {
        bHeld = true;
        return l;
      });
      await new Promise((r) => setTimeout(r, 600));
      // CONTROL: while A holds, B must still be waiting. A lock that never excludes would pass the second half of this test alone.
      expect(bHeld).toBe(false);
      a.release();
      (await b).release();
      expect(bHeld).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('lets two different tutorials hold their locks at once', async () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'seglock-'));
    try {
      const a = await acquireSegLock('a', path.join(dir, 'a.lock'));
      const b = await acquireSegLock('b', path.join(dir, 'b.lock'));
      a.release();
      b.release();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
