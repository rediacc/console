import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { assertThrowawayDir } from './throwaway-dir.js';

// A path that is never under the temp directory, whatever HOME is (a CI container may keep HOME in /tmp, review 1f969add.2).
const REAL_CONFIG_HOME = path.join(
  path.parse(os.tmpdir()).root,
  'var',
  'lib',
  'rdc-probe',
  '.config',
  'rediacc'
);

describe('assertThrowawayDir', () => {
  const made: string[] = [];
  afterEach(() => {
    for (const p of made.splice(0)) fs.rmSync(p, { recursive: true, force: true });
  });

  it('admits a directory under the temp directory', () => {
    expect(() =>
      assertThrowawayDir(path.join(os.tmpdir(), 'rdc-cli-test-home-x', 'config'))
    ).not.toThrow();
  });

  it('refuses a config home outside the temp directory, the 2026-10-14 deletion (#61fb7bc3)', () => {
    expect(() => assertThrowawayDir(REAL_CONFIG_HOME)).toThrow(/refusing to delete/);
  });

  it('refuses the temp directory itself and a sibling that only shares its prefix', () => {
    expect(() => assertThrowawayDir(os.tmpdir())).toThrow(/refusing to delete/);
    expect(() => assertThrowawayDir(`${path.resolve(os.tmpdir())}-other/x`)).toThrow(
      /refusing to delete/
    );
  });

  it('judges a symlink under the temp directory where it lands (review 1f969add.1)', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'rdc-throwaway-'));
    made.push(base);
    // The filesystem root is outside the temp directory on every machine, and linking to it writes nothing there (review f434e6dc.1, .6).
    fs.symlinkSync(path.parse(base).root, path.join(base, 'link'));
    expect(() => assertThrowawayDir(path.join(base, 'link', 'config'))).toThrow(
      /refusing to delete/
    );
  });

  it('judges a dangling symlink by where it points (review f434e6dc.2)', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'rdc-throwaway-'));
    made.push(base);
    // The target must not exist, or this is an ordinary link and the dangling path is never taken (review bf6289c7.3).
    expect(fs.existsSync(REAL_CONFIG_HOME)).toBe(false);
    fs.symlinkSync(REAL_CONFIG_HOME, path.join(base, 'dangling'));
    expect(() => assertThrowawayDir(path.join(base, 'dangling'))).toThrow(/refusing to delete/);
  });

  it('refuses a symlink loop instead of walking it forever (review bf6289c7.4)', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'rdc-throwaway-'));
    made.push(base);
    fs.symlinkSync(path.join(base, 'b'), path.join(base, 'a'));
    fs.symlinkSync(path.join(base, 'a'), path.join(base, 'b'));
    expect(() => assertThrowawayDir(path.join(base, 'a', 'config'))).toThrow(
      /refusing to delete .*too many symlinks/
    );
  });
});
