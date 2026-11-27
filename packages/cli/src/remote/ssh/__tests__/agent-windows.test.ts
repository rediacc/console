/**
 * rdc never adds its keys to the Win32-OpenSSH agent service.
 *
 * That agent persists every added key DPAPI-encrypted under HKCU\Software\OpenSSH\Agent\Keys, and the key
 * survives a service stop, Disabled and a reboot: measured on a Windows 11 VM, the key rdc had added was
 * still in the registry with the agent stopped. On win32 rdc passes the key file to ssh with -i and
 * IdentitiesOnly, whatever the service state; Linux and macOS keep their private agent, which dies with
 * the command.
 */
import { EventEmitter } from 'node:events';
import { existsSync } from 'node:fs';
import { PassThrough } from 'node:stream';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Platform = 'windows' | 'linux' | 'macos';

const h = vi.hoisted(() => ({
  platform: 'windows' as Platform,
  spawn: vi.fn(),
  execFile: vi.fn(),
}));

vi.mock('node:child_process', () => ({ spawn: h.spawn, execFile: h.execFile }));
vi.mock('../../utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/platform.js')>()),
  getPlatform: () => h.platform,
  commandExists: async () => true,
}));

import { addKeyToAgent, isSSHAgentAvailable, startSSHAgent } from '../agent.js';
import { SSHConnection } from '../connection.js';

const KEY =
  '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----\n';
const KNOWN_HOSTS = 'example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample';
const RUNNING =
  '\nSERVICE_NAME: ssh-agent\n        TYPE               : 10  WIN32_OWN_PROCESS\n        STATE              : 4  RUNNING\n';

/** A child process that prints `stdout` and exits 0 on the next tick. */
function fakeChild(stdout = ''): EventEmitter & {
  stdout: PassThrough;
  stderr: PassThrough;
  kill: () => void;
} {
  const child = Object.assign(new EventEmitter(), {
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: () => undefined,
  });
  setImmediate(() => {
    if (stdout) child.stdout.emit('data', Buffer.from(stdout));
    child.emit('close', 0);
  });
  return child;
}

function spawnedCommands(): string[] {
  return h.spawn.mock.calls.map((call) => String(call[0]));
}

let kill: ReturnType<typeof vi.spyOn>;
let stderr: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  h.platform = 'windows';
  h.spawn.mockReset();
  h.spawn.mockImplementation((cmd: string) =>
    fakeChild(
      cmd === 'ssh-agent'
        ? 'SSH_AUTH_SOCK=/tmp/ssh-rdc/agent.1; export SSH_AUTH_SOCK;\nSSH_AGENT_PID=4242; export SSH_AGENT_PID;\n'
        : ''
    )
  );
  // A running service, the case that leaked: the answer must not matter.
  h.execFile.mockReset();
  h.execFile.mockImplementation((_cmd, _args, _opts, cb) => cb(null, RUNNING));
  kill = vi.spyOn(process, 'kill').mockImplementation(() => true);
  stderr = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
});

afterEach(() => {
  kill.mockRestore();
  stderr.mockRestore();
});

describe('win32 with the ssh-agent service running', () => {
  it('reports no agent and never spawns ssh-agent or ssh-add', async () => {
    await expect(isSSHAgentAvailable()).resolves.toBe(false);
    await expect(startSSHAgent()).rejects.toThrow(/registry/);
    await expect(addKeyToAgent(KEY, '\\\\.\\pipe\\openssh-ssh-agent')).rejects.toThrow(/registry/);
    expect(spawnedCommands()).not.toContain('ssh-add');
    expect(spawnedCommands()).not.toContain('ssh-agent');
  });

  it('SSHConnection uses the key file with -i and IdentitiesOnly, with no agent socket', async () => {
    const conn = new SSHConnection(KEY, KNOWN_HOSTS, { host: '10.0.0.1', port: 22 });
    let keyFilePath: string | undefined;
    try {
      const result = await conn.setup();
      keyFilePath = result.keyFilePath;
      expect(result.connectionMethod).toBe('file-based');
      expect(conn.agentSocketPath).toBeUndefined();
      expect(result.keyFilePath).toBeTruthy();
      const iAt = result.sshOptions.indexOf('-i');
      expect(iAt).toBeGreaterThan(-1);
      expect(result.sshOptions[iAt + 1]).toBe(result.keyFilePath!.replaceAll('\\', '/'));
      expect(result.sshOptions.join(' ')).toContain('-o IdentitiesOnly=yes');
      expect(spawnedCommands()).toEqual([]);
      // No "agent setup failed" warning: the file path is the design, not a fallback.
      expect(stderr).not.toHaveBeenCalled();
      expect(existsSync(result.keyFilePath!)).toBe(true);
    } finally {
      await conn.cleanup();
    }
    // The temp key file is the only copy of the key on disk, so cleanup must remove it.
    expect(existsSync(keyFilePath!)).toBe(false);
  });
});

describe.each(['linux', 'macos'] as const)('%s keeps its private agent', (platform) => {
  it('spawns `ssh-agent -s`, adds the key with ssh-add and passes no key file', async () => {
    h.platform = platform;
    await expect(isSSHAgentAvailable()).resolves.toBe(true);
    const conn = new SSHConnection(KEY, KNOWN_HOSTS, { host: '10.0.0.1', port: 22 });
    try {
      const result = await conn.setup();
      expect(result.connectionMethod).toBe('ssh-agent');
      expect(conn.agentSocketPath).toBe('/tmp/ssh-rdc/agent.1');
      expect(result.sshOptions).not.toContain('-i');
      expect(h.spawn.mock.calls[0].slice(0, 2)).toEqual(['ssh-agent', ['-s']]);
      expect(spawnedCommands()).toEqual(['ssh-agent', 'ssh-add']);
      expect(h.spawn.mock.calls[1][2].env.SSH_AUTH_SOCK).toBe('/tmp/ssh-rdc/agent.1');
      expect(h.execFile).not.toHaveBeenCalled();
    } finally {
      await conn.cleanup();
    }
    // The private agent dies with the command.
    expect(kill).toHaveBeenCalledWith(4242);
  });
});
