import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  platform: 'windows' as 'windows' | 'linux' | 'macos',
  managed: null as string | null,
  existing: new Set<string>(),
}));

vi.mock('../../utils/platform.js', () => ({ getPlatform: () => state.platform }));
vi.mock('../../../services/tools/rsync.js', () => ({
  findInstalledRsync: () => state.managed,
}));
vi.mock('node:fs', async (importOriginal) => {
  const real = await importOriginal<typeof import('node:fs')>();
  return { ...real, existsSync: (p: string) => state.existing.has(String(p)) };
});

/** A fresh module per test: paths.ts caches every lookup for the process. */
function load() {
  vi.resetModules();
  return import('../paths.js');
}

const MANAGED = ['C:', 'tools', 'msys2-rsync', '3.5.2-2-abc', 'usr', 'bin', 'rsync.exe'].join('/');

beforeEach(() => {
  state.platform = 'windows';
  state.managed = null;
  state.existing = new Set();
  vi.stubEnv('MSYS2_ROOT', '/sys-msys');
});

describe('getRsyncPath', () => {
  it('prefers the rdc-managed rsync over a system MSYS2 rsync', async () => {
    state.managed = MANAGED;
    state.existing = new Set(['/sys-msys/usr/bin', '/sys-msys/usr\\bin/rsync.exe']);
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe(MANAGED);
  });

  it('falls back to the system MSYS2 rsync when rdc installed none', async () => {
    const { join } = await import('node:path');
    const systemRsync = join('/sys-msys', 'usr\\bin', 'rsync.exe');
    state.existing = new Set([join('/sys-msys', 'usr', 'bin'), systemRsync]);
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe(systemRsync);
  });

  it('falls back to rsync on PATH when neither exists', async () => {
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe('rsync');
  });

  it('never looks in the tools directory off Windows', async () => {
    state.platform = 'linux';
    state.managed = MANAGED;
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe('rsync');
  });
});

describe('getMsys2Environment', () => {
  it('uses the rdc-managed tree as the MSYS2 root when no other MSYS2 exists', async () => {
    state.managed = MANAGED;
    const { join } = await import('node:path');
    const { getMsys2Environment } = await load();
    const env = getMsys2Environment();
    const root = ['C:', 'tools', 'msys2-rsync', '3.5.2-2-abc'].join('/');
    expect(env.PATH?.startsWith(`${join(root, 'usr', 'bin')};`)).toBe(true);
    expect(env.MSYS_NO_PATHCONV).toBe('1');
  });
});
