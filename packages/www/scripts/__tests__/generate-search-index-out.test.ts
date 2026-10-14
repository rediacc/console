import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';
import { sameDirectory } from '../lib/same-directory.js';

const wwwRoot = fileURLToPath(new URL('../..', import.meta.url));
const script = path.join(wwwRoot, 'scripts', 'generate-search-index.js');
const publicDir = path.join(wwwRoot, 'public');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'search-index-out-'));
afterAll(() => fs.rmSync(scratch, { recursive: true, force: true }));

const run = (out: string) =>
  spawnSync(process.execPath, [script, '--out', out], { cwd: wwwRoot, encoding: 'utf8' });

describe('search-index --out guard', () => {
  it('refuses a symlink that aliases the tracked public/ directory, with rc 2', () => {
    const alias = path.join(scratch, 'alias');
    fs.symlinkSync(publicDir, alias);
    const res = run(alias);
    expect(res.status).toBe(2);
    expect(res.stderr).toContain('must not name the tracked public/ directory');
  });

  it('CONTROL: refuses public/ spelled directly, so the symlink case is not passing for another reason', () => {
    const res = run(publicDir);
    expect(res.status).toBe(2);
    expect(res.stderr).toContain('must not name the tracked public/ directory');
  });

  it('does not refuse an unrelated existing directory', () => {
    const other = path.join(scratch, 'other');
    fs.mkdirSync(other);
    const res = run(other);
    expect(res.stderr).not.toContain('must not name the tracked public/ directory');
    expect(res.status).not.toBe(2);
  }, 120_000);
});

describe('sameDirectory', () => {
  const a = fs.mkdtempSync(path.join(scratch, 'a-'));
  const b = fs.mkdtempSync(path.join(scratch, 'b-'));
  const link = path.join(scratch, 'link-a');
  fs.symlinkSync(a, link);

  it('identifies a directory through a symlink and tells two directories apart', () => {
    expect(sameDirectory(a, link)).toBe(true);
    expect(sameDirectory(a, b)).toBe(false);
  });

  it('with inode 0 on either side falls back to real paths: equal for an alias, different for another directory', () => {
    const real = fs.statSync;
    const zero = ((p: fs.PathLike) => {
      const s = real(p) as fs.Stats;
      return Object.assign(Object.create(Object.getPrototypeOf(s)), s, { ino: 0 });
    }) as typeof fs.statSync;
    const spy = Object.getOwnPropertyDescriptor(fs, 'statSync');
    try {
      (fs as { statSync: unknown }).statSync = zero;
      expect(sameDirectory(a, link)).toBe(true);
      expect(sameDirectory(a, b)).toBe(false);
    } finally {
      if (spy) Object.defineProperty(fs, 'statSync', spy);
    }
  });
});

describe('inode 0 on a case-folding platform', () => {
  // Every directory reports inode 0; `resolve` maps a path to the spelling the volume would find (identity on a case-sensitive one).
  const withInodeZero = (body: () => boolean, resolve: (p: string) => string = (p) => p) => {
    const realStat = fs.statSync;
    const realReal = fs.realpathSync;
    const statDesc = Object.getOwnPropertyDescriptor(fs, 'statSync');
    const pathDesc = Object.getOwnPropertyDescriptor(fs, 'realpathSync');
    (fs as { statSync: unknown }).statSync = ((p: fs.PathLike) => {
      const s = realStat(resolve(String(p))) as fs.Stats;
      return Object.assign(Object.create(Object.getPrototypeOf(s)), s, { ino: 0 });
    }) as typeof fs.statSync;
    (fs as { realpathSync: unknown }).realpathSync = Object.assign(
      (p: fs.PathLike) => realReal(resolve(String(p))),
      { native: realReal.native }
    );
    try {
      return body();
    } finally {
      if (statDesc) Object.defineProperty(fs, 'statSync', statDesc);
      if (pathDesc) Object.defineProperty(fs, 'realpathSync', pathDesc);
    }
  };
  const upper = path.join(scratch, 'Pub');
  const lower = path.join(scratch, 'pub');
  fs.mkdirSync(upper);
  fs.mkdirSync(lower);

  it('keeps two directories that differ only by case apart on a case-sensitive volume', () => {
    expect(withInodeZero(() => sameDirectory(upper, lower, 'darwin'))).toBe(false);
    expect(withInodeZero(() => sameDirectory(upper, lower, 'win32'))).toBe(false);
  });

  it('CONTROL: calls two spellings of one directory equal when the volume ignores case', () => {
    const dir = path.join(scratch, 'Only');
    fs.mkdirSync(dir);
    // A case-insensitive volume: a spelling that differs by case finds the one entry.
    const insensitive = (p: string): string => {
      const hit = fs
        .readdirSync(path.dirname(p))
        .find((n) => n.toLowerCase() === path.basename(p).toLowerCase());
      return hit ? path.join(path.dirname(p), hit) : p;
    };
    const same = withInodeZero(
      () => sameDirectory(dir, path.join(scratch, 'only'), 'darwin'),
      insensitive
    );
    expect(same).toBe(true);
  });
});
