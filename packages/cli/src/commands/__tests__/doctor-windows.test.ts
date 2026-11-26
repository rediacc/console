import { describe, expect, it } from 'vitest';
import type { PathLookupOptions } from '../../services/tools/path-lookup.js';
import { checkEnvironment, checkTools } from '../doctor.js';
import { parseSshAgentState, type WindowsClientDeps } from '../doctor-windows.js';

const TOFU_MISSING = async () => ({ ok: false as const, reason: 'missing' as const });
const NO_RSYNC: PathLookupOptions = { env: { PATH: '' }, platform: 'win32' };

const ALL_GOOD: WindowsClientDeps = {
  findVSCode: async () => ({ path: 'C:\\Code\\Code.exe', version: '1.95.0' }),
  hasRemoteSsh: async () => true,
  sshAgentState: () => 'running',
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

  it('reports VS Code, Remote-SSH, the OpenSSH client and a running ssh-agent', async () => {
    const section = await tools('win32');
    expect(section.checks.slice(2)).toEqual([
      { name: 'VS Code', value: '1.95.0', status: 'ok' },
      { name: 'Remote-SSH extension', value: 'installed', status: 'ok' },
      { name: 'OpenSSH client', value: 'OpenSSH_for_Windows_9.5p1', status: 'ok' },
      { name: 'ssh-agent service', value: 'running', status: 'ok' },
    ]);
  });

  it.each([
    ['stopped', 'stopped'],
    ['disabled', 'disabled'],
  ] as const)('warns with the exact enable command when ssh-agent is %s', async (state, value) => {
    const section = await tools('win32', { ...ALL_GOOD, sshAgentState: () => state });
    const agent = section.checks.find((c) => c.name === 'ssh-agent service');
    expect(agent).toMatchObject({ value, status: 'warn' });
    expect(agent?.hint).toContain(
      'Set-Service ssh-agent -StartupType Automatic; Start-Service ssh-agent'
    );
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
    expect(ext?.hint).toContain('code --install-extension ms-vscode-remote.remote-ssh');
  });

  it('warns when no OpenSSH client runs', async () => {
    const section = await tools('win32', { ...ALL_GOOD, sshVersion: () => null });
    expect(section.checks.find((c) => c.name === 'OpenSSH client')).toMatchObject({
      value: 'not installed',
      status: 'warn',
    });
  });

  it('parses Get-Service output', () => {
    expect(parseSshAgentState('Running|Automatic')).toBe('running');
    expect(parseSshAgentState('Stopped|Manual')).toBe('stopped');
    expect(parseSshAgentState('Stopped|Disabled\r\n')).toBe('disabled');
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
      accountServer: () => 'https://eu.rediacc.cloud',
    });
    expect(section.checks).toContainEqual({
      name: 'Account server',
      value: 'https://eu.rediacc.cloud',
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
