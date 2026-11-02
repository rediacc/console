/**
 * Convergence proof (Design 3): the download argv, run by the REAL local rsync, makes the
 * destination byte-identical to the source whatever the destination held before.
 *
 * Red until C1 creates remote/sync/image-rsync.ts. The module is loaded with a runtime path
 * so tsc does not need it to exist; C1 may turn this into a static import.
 * A missing rsync binary FAILS the suite; nothing here skips.
 */

import { execFileSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import {
  closeSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  truncateSync,
  writeSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

interface ImageRsyncModule {
  buildImageRsyncArgs(opts: {
    direction: 'download' | 'upload';
    freshDest: boolean;
    sshCommand: string;
    bwlimitKiBps?: number;
  }): string[];
  parseRsyncStats(text: string): { literalBytes: number; matchedBytes: number };
}

const loadImageRsync = (): Promise<ImageRsyncModule> =>
  import(
    /* @vite-ignore */ fileURLToPath(
      new URL('../../../remote/sync/image-rsync.ts', import.meta.url)
    )
  );

const MiB = 1024 * 1024;
const SIZE = 64 * MiB;
let dir: string;
let v1: string;
let v2: string;

function writeAt(path: string, offset: number, data: Buffer): void {
  const fd = openSync(path, 'r+');
  writeSync(fd, data, 0, data.length, offset);
  closeSync(fd);
}

/** A 64 MiB sparse file: random runs at a spread of offsets, holes between. */
function makeFixture(path: string): void {
  const fd = openSync(path, 'w');
  closeSync(fd);
  truncateSync(path, SIZE);
  for (let off = 0; off < SIZE; off += 4 * MiB) {
    if ((off / (4 * MiB)) % 3 === 2) continue; // leave a hole
    writeAt(path, off, randomBytes(2 * MiB));
  }
}

const sha = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'converge-'));
  v1 = join(dir, 'v1.img');
  v2 = join(dir, 'v2.img');
  makeFixture(v1);
  // v2 = v1 plus scattered changes: 40 x 64 KiB = 2.5 MiB (about 4 percent).
  execFileSync('cp', ['--sparse=never', v1, v2]);
  for (let i = 0; i < 40; i++) {
    writeAt(v2, Math.floor((SIZE / 40) * i) + 4096, randomBytes(64 * 1024));
  }
});

afterAll(() => {
  rmSync(dir, { recursive: true, force: true });
});

function run(
  mod: ImageRsyncModule,
  src: string,
  dest: string,
  freshDest = false
): { literalBytes: number; matchedBytes: number } {
  const args = mod.buildImageRsyncArgs({ direction: 'download', freshDest, sshCommand: 'ssh' });
  expect(args).toContain('--no-whole-file');
  const out = execFileSync('rsync', [...args, src, dest], { encoding: 'utf8' });
  return mod.parseRsyncStats(out);
}

describe('real rsync with the image argv', () => {
  it('has an rsync binary', () => {
    expect(() => execFileSync('rsync', ['--version'])).not.toThrow();
  });

  it('converges from a 40 percent prefix of an older version', async () => {
    const mod = await loadImageRsync();
    const dest = join(dir, 'prefix.img');
    execFileSync('cp', ['--sparse=never', v1, dest]);
    truncateSync(dest, Math.floor(SIZE * 0.4));
    run(mod, v2, dest);
    expect(sha(dest)).toBe(sha(v2));
  });

  it('converges from a complete older version, sending only the scattered changes', async () => {
    const mod = await loadImageRsync();
    const dest = join(dir, 'older.img');
    execFileSync('cp', ['--sparse=never', v1, dest]);
    const stats = run(mod, v2, dest);
    expect(sha(dest)).toBe(sha(v2));
    expect(stats.literalBytes).toBeGreaterThan(0);
    expect(stats.literalBytes).toBeLessThan(SIZE * 0.1);
  });

  it('converges when the source shrank', async () => {
    const mod = await loadImageRsync();
    const src = join(dir, 'shrunk.img');
    execFileSync('cp', ['--sparse=never', v2, src]);
    truncateSync(src, 50 * MiB);
    const dest = join(dir, 'shrunk-dest.img');
    execFileSync('cp', ['--sparse=never', v1, dest]);
    run(mod, src, dest);
    expect(sha(dest)).toBe(sha(src));
  });

  it('converges when the source grew', async () => {
    const mod = await loadImageRsync();
    const src = join(dir, 'grown.img');
    execFileSync('cp', ['--sparse=never', v2, src]);
    truncateSync(src, SIZE + 10 * MiB);
    writeAt(src, SIZE, randomBytes(10 * MiB));
    const dest = join(dir, 'grown-dest.img');
    execFileSync('cp', ['--sparse=never', v1, dest]);
    run(mod, src, dest);
    expect(sha(dest)).toBe(sha(src));
  });

  it('converges onto garbage', async () => {
    const mod = await loadImageRsync();
    const dest = join(dir, 'garbage.img');
    const fd = openSync(dest, 'w');
    writeSync(fd, randomBytes(20 * MiB));
    closeSync(fd);
    run(mod, v2, dest);
    expect(sha(dest)).toBe(sha(v2));
  });

  it('writes a fresh destination with --sparse and still matches', async () => {
    const mod = await loadImageRsync();
    const dest = join(dir, 'fresh.img');
    run(mod, v2, dest, true);
    expect(sha(dest)).toBe(sha(v2));
  });
});
