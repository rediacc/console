import path from 'node:path';
import { getRediaccDirs } from '@rediacc/shared/paths';
import { afterEach, describe, expect, it } from 'vitest';

function inside(child: string | undefined, parent: string | undefined): boolean {
  if (!child || !parent) return false;
  const rel = path.relative(parent, child);
  return rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel);
}

describe('isolate-config-home setup (D13 step 0)', () => {
  const realPlatform = Object.getOwnPropertyDescriptor(process, 'platform');
  afterEach(() => {
    if (realPlatform) Object.defineProperty(process, 'platform', realPlatform);
  });

  it('points TEMP and TMP, with TMPDIR, at one run directory', () => {
    expect(process.env.TMPDIR).toBeTruthy();
    expect(process.env.TEMP).toBe(process.env.TMPDIR);
    expect(process.env.TMP).toBe(process.env.TMPDIR);
  });

  it('puts APPDATA and LOCALAPPDATA under the run temporary directory', () => {
    expect(inside(process.env.APPDATA, process.env.TMPDIR)).toBe(true);
    expect(inside(process.env.LOCALAPPDATA, process.env.TMPDIR)).toBe(true);
  });

  it('resolves win32 rediacc dirs inside the throwaway home', () => {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    const dirs = getRediaccDirs();
    for (const d of [dirs.config, dirs.state, dirs.cache]) {
      expect(inside(d, process.env.TMPDIR)).toBe(true);
    }
  });
});
