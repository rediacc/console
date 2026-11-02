import { chmod, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { findOnPath } from '../../services/tools/path-lookup.js';

/** A fake filesystem: the set of paths that exist and are runnable. */
function fs(...paths: string[]) {
  const set = new Set(paths);
  return (candidate: string) => set.has(candidate);
}

describe('findOnPath on Windows', () => {
  it('tries each PATHEXT extension in order, in each PATH directory in order', () => {
    const env = { Path: 'C:\\a;C:\\b', PATHEXT: '.COM;.EXE;.CMD' };
    expect(
      findOnPath('tofu', {
        env,
        platform: 'win32',
        isExecutable: fs('C:\\b\\tofu.exe', 'C:\\b\\tofu.cmd'),
      })
    ).toBe('C:\\b\\tofu.exe');
    expect(
      findOnPath('tofu', {
        env,
        platform: 'win32',
        isExecutable: fs('C:\\a\\tofu.cmd', 'C:\\b\\tofu.exe'),
      })
    ).toBe('C:\\a\\tofu.cmd');
  });

  it('reads PATH case-insensitively and falls back to a default PATHEXT', () => {
    expect(
      findOnPath('rsync', {
        env: { PATH: 'C:\\msys64\\usr\\bin' },
        platform: 'win32',
        isExecutable: fs('C:\\msys64\\usr\\bin\\rsync.exe'),
      })
    ).toBe('C:\\msys64\\usr\\bin\\rsync.exe');
  });

  it('takes a name that already carries a PATHEXT extension as given', () => {
    expect(
      findOnPath('tofu.exe', {
        env: { Path: 'C:\\t', PATHEXT: '.EXE' },
        platform: 'win32',
        isExecutable: fs('C:\\t\\tofu.exe'),
      })
    ).toBe('C:\\t\\tofu.exe');
  });

  it('strips quotes around PATH entries and skips empty ones', () => {
    expect(
      findOnPath('tofu', {
        env: { Path: ';"C:\\Program Files\\OpenTofu";', PATHEXT: '.EXE' },
        platform: 'win32',
        isExecutable: fs('C:\\Program Files\\OpenTofu\\tofu.exe'),
      })
    ).toBe('C:\\Program Files\\OpenTofu\\tofu.exe');
  });

  it('returns null when nothing matches', () => {
    expect(
      findOnPath('tofu', {
        env: { Path: 'C:\\a', PATHEXT: '.EXE' },
        platform: 'win32',
        isExecutable: fs('C:\\a\\tofu'),
      })
    ).toBeNull();
  });
});

describe('findOnPath on POSIX', () => {
  it('walks PATH in order with no extension guessing', () => {
    expect(
      findOnPath('tofu', {
        env: { PATH: '/usr/local/bin:/usr/bin' },
        platform: 'linux',
        isExecutable: fs('/usr/bin/tofu', '/usr/local/bin/tofu.exe'),
      })
    ).toBe('/usr/bin/tofu');
  });

  it('skips empty PATH entries rather than reading them as the current directory', () => {
    const seen: string[] = [];
    findOnPath('tofu', {
      env: { PATH: ':/usr/bin:' },
      platform: 'linux',
      isExecutable: (c) => {
        seen.push(c);
        return false;
      },
    });
    expect(seen).toEqual(['/usr/bin/tofu']);
  });
});

describe.skipIf(process.platform === 'win32')('findOnPath against the real filesystem', () => {
  const dirs: string[] = [];
  afterEach(async () => {
    await Promise.all(dirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
  });

  it('finds an executable file and ignores a non-executable one', async () => {
    const a = await mkdtemp(join(tmpdir(), 'rdc-path-a-'));
    const b = await mkdtemp(join(tmpdir(), 'rdc-path-b-'));
    dirs.push(a, b);
    await writeFile(join(a, 'tool'), 'not executable');
    await writeFile(join(b, 'tool'), '#!/bin/sh\n');
    await chmod(join(b, 'tool'), 0o755);
    expect(findOnPath('tool', { env: { PATH: `${a}:${b}` } })).toBe(join(b, 'tool'));
    expect(findOnPath('absent-tool', { env: { PATH: `${a}:${b}` } })).toBeNull();
  });
});
