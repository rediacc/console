/**
 * Win32-OpenSSH's agent is a service on \\.\pipe\openssh-ssh-agent, not a process `ssh-agent -s` can start.
 * Measured on a stock Windows 11 VM: the spawn exited 255 (error 1058, service Disabled) or hung for 10 s,
 * and cost a warning on every term/vscode command.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  platform: 'windows' as 'windows' | 'linux',
  scQuery: '' as string | Error,
  spawn: vi.fn(),
  execFile: vi.fn(),
}));

vi.mock('node:child_process', () => ({ spawn: h.spawn, execFile: h.execFile }));
vi.mock('../../utils/platform.js', () => ({
  getPlatform: () => h.platform,
  commandExists: async () => true,
}));

import {
  isSSHAgentAvailable,
  isWindowsSSHAgentServiceRunning,
  startSSHAgent,
  WINDOWS_SSH_AGENT_PIPE,
} from '../agent.js';

const RUNNING =
  '\nSERVICE_NAME: ssh-agent\n        TYPE               : 10  WIN32_OWN_PROCESS\n        STATE              : 4  RUNNING\n';
const STOPPED =
  '\nSERVICE_NAME: ssh-agent\n        TYPE               : 10  WIN32_OWN_PROCESS\n        STATE              : 1  STOPPED\n';

beforeEach(() => {
  h.platform = 'windows';
  h.spawn.mockReset();
  h.execFile.mockReset();
  h.execFile.mockImplementation((_cmd, _args, _opts, cb) => {
    if (h.scQuery instanceof Error) cb(h.scQuery, '');
    else cb(null, h.scQuery);
  });
});

describe('ssh-agent on win32', () => {
  it('never spawns `ssh-agent -s`, whatever the service state', async () => {
    for (const state of [RUNNING, STOPPED, new Error('1060')]) {
      h.scQuery = state;
      await startSSHAgent().catch(() => undefined);
      await isSSHAgentAvailable();
    }
    expect(h.spawn).not.toHaveBeenCalled();
  });

  it('a RUNNING service gives the named pipe and no pid to kill', async () => {
    h.scQuery = RUNNING;
    await expect(startSSHAgent()).resolves.toEqual({
      socketPath: WINDOWS_SSH_AGENT_PIPE,
      agentPid: '',
    });
    expect(WINDOWS_SSH_AGENT_PIPE).toBe('\\\\.\\pipe\\openssh-ssh-agent');
    await expect(isSSHAgentAvailable()).resolves.toBe(true);
  });

  it('a stopped, disabled or missing service is unavailable at once, with no warning', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const err = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
    for (const state of [STOPPED, new Error('The specified service does not exist')]) {
      h.scQuery = state;
      await expect(isWindowsSSHAgentServiceRunning()).resolves.toBe(false);
      await expect(isSSHAgentAvailable()).resolves.toBe(false);
    }
    expect(warn).not.toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
    warn.mockRestore();
    err.mockRestore();
  });

  it('the probe is bounded by a short timeout', async () => {
    h.scQuery = RUNNING;
    await isWindowsSSHAgentServiceRunning();
    expect(h.execFile.mock.calls[0][2].timeout).toBeLessThanOrEqual(5000);
  });
});

describe('ssh-agent off win32', () => {
  it('still spawns `ssh-agent -s` and never probes the service', async () => {
    h.platform = 'linux';
    h.spawn.mockImplementation(() => {
      throw new Error('spawned');
    });
    await expect(startSSHAgent()).rejects.toThrow('spawned');
    expect(h.spawn.mock.calls[0].slice(0, 2)).toEqual(['ssh-agent', ['-s']]);
    expect(h.execFile).not.toHaveBeenCalled();
    await expect(isSSHAgentAvailable()).resolves.toBe(true);
    expect(h.execFile).not.toHaveBeenCalled();
  });
});
