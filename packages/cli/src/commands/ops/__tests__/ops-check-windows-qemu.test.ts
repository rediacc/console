import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const execSync = vi.fn();
const spawnSync = vi.fn();
const existsSync = vi.fn();

vi.mock('node:child_process', () => ({
  execSync: (...args: unknown[]) => execSync(...args),
  spawnSync: (...args: unknown[]) => spawnSync(...args),
}));
vi.mock('node:fs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:fs')>()),
  existsSync: (...args: unknown[]) => existsSync(...args),
}));

const { WINDOWS_QEMU_IMG, checkWindowsPrereqs, resolveToolCommand } = await import('../check.js');

const realPlatform = process.platform;
function setPlatform(value: NodeJS.Platform): void {
  Object.defineProperty(process, 'platform', { value, configurable: true });
}

describe('qemu-img lookup and hint on Windows', () => {
  beforeEach(() => {
    execSync.mockReset().mockImplementation(() => {
      throw new Error('INFO: Could not find files for the given pattern(s).');
    });
    spawnSync.mockReset().mockReturnValue({ status: 0, stdout: 'qemu-img version 9.2.0\n' });
    existsSync.mockReset().mockReturnValue(false);
    setPlatform('win32');
  });
  afterEach(() => setPlatform(realPlatform));

  it('finds qemu-img at the installer path when PATH lacks it', () => {
    existsSync.mockImplementation((p: unknown) => p === WINDOWS_QEMU_IMG);
    expect(resolveToolCommand('qemu-img')).toBe(WINDOWS_QEMU_IMG);
    const qemu = checkWindowsPrereqs().find((c) => c.name === 'qemu-img');
    expect(qemu?.status).toBe('ok');
    expect(spawnSync.mock.calls.some((call) => call[0] === WINDOWS_QEMU_IMG)).toBe(true);
  });

  it('does not probe the installer path for other tools or other platforms', () => {
    existsSync.mockReturnValue(true);
    expect(resolveToolCommand('ssh')).toBeNull();
    setPlatform('linux');
    expect(resolveToolCommand('qemu-img')).toBeNull();
  });

  it('points a missing qemu-img at rdc ops setup, not winget', () => {
    const qemu = checkWindowsPrereqs().find((c) => c.name === 'qemu-img');
    expect(qemu?.status).toBe('fail');
    expect(qemu?.hint).toBe('Install QEMU: rdc ops setup');
  });
});
