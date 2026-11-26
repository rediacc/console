import { join, resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

const spawn = vi.hoisted(() => ({ spawnSync: vi.fn() }));
vi.mock('node:child_process', async (orig) => ({
  ...(await orig<typeof import('node:child_process')>()),
  spawnSync: spawn.spawnSync,
}));

import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import type { PathLookupOptions } from '../../services/tools/path-lookup.js';
import {
  checkEnvironment,
  checkTools,
  dropDuplicateClientRows,
  findRenetSource,
} from '../doctor.js';
import type { WindowsClientDeps } from '../doctor-windows.js';

const TOFU_MISSING = async () => ({ ok: false as const, reason: 'missing' as const });
const NO_RSYNC: PathLookupOptions = { env: { PATH: '' }, platform: 'win32' };

const ALL_GOOD: WindowsClientDeps = {
  findVSCode: async () => ({ path: 'C:\\Code\\Code.exe', version: '1.95.0' }),
  hasRemoteSsh: async () => true,
  sshVersion: () => 'OpenSSH_for_Windows_9.5p1, LibreSSL 3.8.2',
};

function tools(platform: NodeJS.Platform, windows: WindowsClientDeps = ALL_GOOD) {
  return checkTools({
    resolveTofu: TOFU_MISSING,
    pathLookup: { ...NO_RSYNC, platform },
    platform,
    windows,
  });
}

describe('doctor Tools section on Windows', () => {
  it('points the rsync hint at rdc tools install rsync and MSYS2, not a system package manager', async () => {
    const section = await tools('win32');
    const rsync = section.checks.find((c) => c.name === 'rsync');
    expect(rsync?.hint).toContain('rdc tools install rsync');
    expect(rsync?.hint).toContain('pacman -S rsync');
    expect(rsync?.hint).not.toContain('system package manager');
  });

  it('keeps the original rsync hint and adds no client checks off Windows', async () => {
    const section = await tools('linux');
    expect(section.checks.map((c) => c.name)).toEqual(['OpenTofu', 'rsync']);
    expect(section.checks[1].hint).toBe('Install rsync with the system package manager');
  });

  it('reports VS Code, Remote-SSH and the OpenSSH client', async () => {
    const section = await tools('win32');
    expect(section.checks.slice(2)).toEqual([
      { name: 'VS Code', value: '1.95.0', status: 'ok' },
      { name: 'Remote-SSH extension', value: 'installed', status: 'ok' },
      { name: 'OpenSSH client', value: 'OpenSSH_for_Windows_9.5p1', status: 'ok' },
    ]);
  });

  it('warns when VS Code is missing and skips the extension check', async () => {
    const section = await tools('win32', { ...ALL_GOOD, findVSCode: async () => null });
    expect(section.checks.find((c) => c.name === 'VS Code')).toMatchObject({
      value: 'not installed',
      status: 'warn',
    });
    expect(section.checks.some((c) => c.name === 'Remote-SSH extension')).toBe(false);
  });

  it('warns when the Remote-SSH extension is missing, naming the install command', async () => {
    const section = await tools('win32', { ...ALL_GOOD, hasRemoteSsh: async () => false });
    const ext = section.checks.find((c) => c.name === 'Remote-SSH extension');
    expect(ext).toMatchObject({ value: 'not detected', status: 'warn' });
    expect(ext?.hint).toContain('Remote - SSH extension (ms-vscode-remote.remote-ssh)');
  });

  it('warns when no OpenSSH client runs', async () => {
    const section = await tools('win32', { ...ALL_GOOD, sshVersion: () => null });
    expect(section.checks.find((c) => c.name === 'OpenSSH client')).toMatchObject({
      value: 'not installed',
      status: 'warn',
    });
  });

  it('has no ssh-agent row, since rdc uses a key file and never the agent service', async () => {
    const section = await tools('win32');
    expect(section.checks.some((c) => /ssh-agent/i.test(c.name))).toBe(false);
    expect(spawn.spawnSync).not.toHaveBeenCalled();
  });
});

describe('doctor Environment section', () => {
  const names = (s: ReturnType<typeof checkEnvironment>) => s.checks.map((c) => c.name);

  it('omits the Account server row when the config names none', () => {
    const section = checkEnvironment({ isDevTree: () => false, accountServer: () => undefined });
    expect(names(section)).not.toContain('Account server');
  });

  it('shows the Account server row when the config names one', () => {
    const section = checkEnvironment({
      isDevTree: () => false,
      accountServer: () => WK_ACCOUNT_DEFAULT_ORIGIN,
    });
    expect(section.checks).toContainEqual({
      name: 'Account server',
      value: WK_ACCOUNT_DEFAULT_ORIGIN,
      status: 'ok',
    });
  });

  it('has no Go or Docker row on a client machine', () => {
    const section = checkEnvironment({ isDevTree: () => false, accountServer: () => undefined });
    expect(names(section)).not.toContain('Go');
    expect(names(section)).not.toContain('Docker');
  });

  it('keeps the Go and Docker rows for a dev tree', () => {
    const section = checkEnvironment({ isDevTree: () => true, accountServer: () => undefined });
    expect(names(section)).toEqual(expect.arrayContaining(['Go', 'Docker']));
  });
});

describe('doctor dev-tree and client-row helpers', () => {
  it('finds private/renet from a subdirectory of the checkout', () => {
    const root = resolve('/work/console');
    const exists = (p: string) => p === join(root, 'private', 'renet');
    expect(findRenetSource(join(root, 'packages', 'cli', 'src'), exists)).toBe(root);
    expect(findRenetSource(root, exists)).toBe(root);
    expect(findRenetSource(resolve('/elsewhere/deep'), exists)).toBeNull();
  });

  it('drops renet ssh row on win32 only, since Tools already reports the OpenSSH client', () => {
    const rows = [{ name: 'qemu-img' }, { name: 'ssh' }];
    expect(dropDuplicateClientRows(rows, 'win32')).toEqual([{ name: 'qemu-img' }]);
    expect(dropDuplicateClientRows(rows, 'linux')).toEqual(rows);
  });
});
