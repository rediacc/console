import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Real files, unlike paths.test.ts: the cache re-stats what it handed out.
const state = vi.hoisted(() => ({ managed: null as string | null }));

vi.mock('../../utils/platform.js', () => ({ getPlatform: () => 'windows' }));
vi.mock('../../../services/tools/rsync.js', () => ({
  findInstalledRsync: () => state.managed,
}));

/** A fresh module per test so SYSTEM_MSYS2_PATHS reads the stubbed MSYS2_ROOT. */
function load() {
  vi.resetModules();
  return import('../paths.js');
}

describe('msys2 path cache', () => {
  let root: string;
  let binDir: string;
  beforeEach(() => {
    state.managed = null;
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'msys2-cache-'));
    // The system search joins the literal subdirectory name 'usr\bin'.
    fs.mkdirSync(path.join(root, 'usr', 'bin'), { recursive: true });
    binDir = path.join(root, 'usr\\bin');
    fs.mkdirSync(binDir, { recursive: true });
    vi.stubEnv('MSYS2_ROOT', root);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    fs.rmSync(root, { recursive: true, force: true });
  });

  it('finds an rsync installed after an earlier miss', async () => {
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe('rsync');
    const exe = path.join(binDir, 'rsync.exe');
    fs.writeFileSync(exe, 'one');
    expect(getRsyncPath()).toBe(exe);
  });

  it('stops handing out an rsync that was removed', async () => {
    const exe = path.join(binDir, 'rsync.exe');
    fs.writeFileSync(exe, 'one');
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe(exe);
    fs.rmSync(exe);
    expect(getRsyncPath()).toBe('rsync');
  });

  it('prefers an rdc-managed rsync installed after a system answer was cached', async () => {
    const exe = path.join(binDir, 'rsync.exe');
    fs.writeFileSync(exe, 'one');
    const { getRsyncPath } = await load();
    expect(getRsyncPath()).toBe(exe);
    state.managed = '/managed/usr/bin/rsync.exe';
    expect(getRsyncPath()).toBe('/managed/usr/bin/rsync.exe');
  });
});
