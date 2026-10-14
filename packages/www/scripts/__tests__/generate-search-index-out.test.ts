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
  // Every directory reports inode 0. `resolve` maps a path to the spelling the volume would find for stat and realpath (identity on a case-sensitive one); `resolveReal` overrides realpath alone, for a volume whose realpath keeps the spelling it was given.
  const withInodeZero = (
    body: () => boolean,
    resolve: (p: string) => string = (p) => p,
    resolveReal: (p: string) => string = (p) => realReal(resolve(p))
  ) => {
    const statDesc = Object.getOwnPropertyDescriptor(fs, 'statSync');
    const pathDesc = Object.getOwnPropertyDescriptor(fs, 'realpathSync');
    (fs as { statSync: unknown }).statSync = ((p: fs.PathLike) => {
      const s = realStat(resolve(String(p))) as fs.Stats;
      return Object.assign(Object.create(Object.getPrototypeOf(s)), s, { ino: 0 });
    }) as typeof fs.statSync;
    (fs as { realpathSync: unknown }).realpathSync = Object.assign(
      (p: fs.PathLike) => resolveReal(String(p)),
      { native: realReal.native }
    );
    try {
      return body();
    } finally {
      if (statDesc) Object.defineProperty(fs, 'statSync', statDesc);
      if (pathDesc) Object.defineProperty(fs, 'realpathSync', pathDesc);
    }
  };
  const realStat = fs.statSync;
  const realReal = fs.realpathSync;

  // A case-insensitive volume: each segment finds the entry whose name matches ignoring case, and the stored spelling is returned.
  const insensitive = (p: string): string => {
    let cur = path.parse(p).root;
    for (const part of path.relative(cur, p).split(path.sep).filter(Boolean)) {
      const hit = fs.readdirSync(cur).find((n) => n.toLowerCase() === part.toLowerCase());
      cur = path.join(cur, hit ?? part);
    }
    return cur;
  };
  // Whether a lookup finds the entry at all, without canonicalizing its spelling.
  const keepsSpelling = (p: string): string => {
    realReal(insensitive(p));
    return p;
  };

  // Names differing only by case coexist only on a case-sensitive volume; a case-insensitive host (macOS, Windows) skips the tests that need both.
  const caseSensitive = (() => {
    const probe = path.join(scratch, 'CaseProbe');
    fs.mkdirSync(probe);
    return !fs.existsSync(path.join(scratch, 'caseprobe'));
  })();
  const makePair = (upperName: string, lowerName: string): [string, string] => {
    const upper = path.join(scratch, upperName);
    const lower = path.join(scratch, lowerName);
    fs.mkdirSync(upper);
    fs.mkdirSync(lower);
    return [upper, lower];
  };

  it.skipIf(!caseSensitive)(
    'keeps two directories that differ only by case apart on a case-sensitive volume',
    () => {
      const [upper, lower] = makePair('Pub', 'pub');
      expect(withInodeZero(() => sameDirectory(upper, lower, 'darwin'))).toBe(false);
      expect(withInodeZero(() => sameDirectory(upper, lower, 'win32'))).toBe(false);
    }
  );

  it.skipIf(!caseSensitive)(
    'keeps them apart when the fully case-swapped spelling also exists as a sibling',
    () => {
      const [upper, lower] = makePair('PUB2', 'pub2');
      const mixed = path.join(scratch, 'Pub2');
      fs.mkdirSync(mixed);
      expect(withInodeZero(() => sameDirectory(upper, lower, 'darwin'))).toBe(false);
      expect(withInodeZero(() => sameDirectory(lower, upper, 'win32'))).toBe(false);
    }
  );

  it('CONTROL: folds two spellings of one directory when the volume ignores case and its realpath keeps the spelling given', () => {
    const dir = path.join(scratch, 'Only');
    fs.mkdirSync(dir);
    const other = path.join(scratch, 'only');
    // The two realpaths differ here, so the equality short-circuit cannot answer and the fold decides.
    expect(keepsSpelling(other)).not.toBe(keepsSpelling(dir));
    expect(
      withInodeZero(() => sameDirectory(dir, other, 'darwin'), insensitive, keepsSpelling)
    ).toBe(true);
    // A platform that does not default to case-insensitive volumes never folds.
    expect(
      withInodeZero(() => sameDirectory(dir, other, 'linux'), insensitive, keepsSpelling)
    ).toBe(false);
  });

  it('folds when the last segment has no letters, probing the nearest segment that has', () => {
    const site = path.join(scratch, 'Site');
    fs.mkdirSync(path.join(site, '2024'), { recursive: true });
    const a = path.join(site, '2024');
    const b = path.join(scratch, 'site', '2024');
    expect(withInodeZero(() => sameDirectory(a, b, 'darwin'), insensitive, keepsSpelling)).toBe(
      true
    );
  });
});
