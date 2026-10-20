import { beforeEach, describe, expect, it, vi } from 'vitest';

const launchTerminal = vi.fn();
vi.mock('../remote/terminal/index.js', () => ({
  getDefaultTerminalType: () => 'gnome-terminal',
  launchTerminal: (...a: unknown[]) => launchTerminal(...a),
}));
vi.mock('../remote/utils/platform.js', () => ({ getPlatform: () => 'linux' }));

import { buildHandoffArgv, launchExternalTerminal } from '../commands/term.js';
import { SSHConnection } from '../remote/ssh/connection.js';

const details = { environment: {}, workingDirectory: undefined } as never;

function fakeConnection(res: Record<string, string | undefined>) {
  const conn = new SSHConnection('k', 'h', { preferAgent: false });
  // Seed private state directly: no real key material or ssh-agent involved.
  Object.assign(conn, {
    setupResult: {
      sshOptions: ['-o', 'X=1'],
      knownHostsPath: res.knownHostsPath ?? '/tmp/kh',
      keyFilePath: res.keyFilePath,
      agentPid: res.agentPid,
      agentSocketPath: res.agentSocketPath,
      connectionMethod: res.agentPid ? 'ssh-agent' : 'file-based',
    },
    isSetup: true,
  });
  return conn;
}

describe('external terminal credential handoff', () => {
  beforeEach(() => {
    launchTerminal.mockReset();
    launchTerminal.mockReturnValue({ success: true });
  });

  it('file-based key: wrapper removes the key, parent releases without deleting', async () => {
    const conn = fakeConnection({ keyFilePath: '/tmp/rdc-key' });
    await launchExternalTerminal(conn, 'u@h', undefined, 't', details);
    const opts = launchTerminal.mock.calls[0][1];
    expect(opts.argv.slice(0, 2)).toEqual(['sh', '-c']);
    expect(opts.argv[2]).toContain("rm -f -- '/tmp/rdc-key' '/tmp/kh'");
    expect(opts.argv.slice(4)).toEqual(['ssh', '-o', 'X=1', 'u@h']);
    // ownership moved: the parent's finally-cleanup finds nothing to delete
    expect(conn.handoffResources.keyFilePath).toBeUndefined();
  });

  it('agent: passes SSH_AUTH_SOCK, wrapper kills the agent, parent does not', async () => {
    const conn = fakeConnection({ agentPid: '4242', agentSocketPath: '/tmp/agent.sock' });
    const kill = vi.spyOn(process, 'kill').mockImplementation(() => true);
    await launchExternalTerminal(conn, 'u@h', undefined, 't', details);
    const opts = launchTerminal.mock.calls[0][1];
    expect(opts.environmentVariables.SSH_AUTH_SOCK).toBe('/tmp/agent.sock');
    expect(opts.argv[2]).toContain('kill 4242');
    await conn.cleanup();
    expect(kill).not.toHaveBeenCalled();
    kill.mockRestore();
  });

  it('launch failure keeps ownership so the parent still cleans up', async () => {
    launchTerminal.mockReturnValue({ success: false, error: 'nope' });
    const conn = fakeConnection({ agentPid: '4242', agentSocketPath: '/tmp/agent.sock' });
    await expect(launchExternalTerminal(conn, 'u@h', undefined, 't', details)).rejects.toThrow();
    expect(conn.handoffResources.agentPid).toBe('4242');
  });

  it('in-process path: cleanup still kills the agent', async () => {
    const conn = fakeConnection({ agentPid: '4242', agentSocketPath: '/tmp/agent.sock' });
    const kill = vi.spyOn(process, 'kill').mockImplementation(() => true);
    await conn.cleanup();
    expect(kill).toHaveBeenCalledWith(4242);
    kill.mockRestore();
  });

  it('a non-numeric pid is never put in the shell script', () => {
    expect(buildHandoffArgv(['ssh', 'h'], { agentPid: '1; rm -rf /' })).toEqual(['ssh', 'h']);
  });

  it('an agent the wrapper cannot stop stays with the parent', async () => {
    const conn = fakeConnection({ agentPid: 'not-a-pid', agentSocketPath: '/tmp/agent.sock' });
    await launchExternalTerminal(conn, 'u@h', undefined, 't', details);
    const opts = launchTerminal.mock.calls[0][1];
    expect(opts.argv[0]).toBe('ssh');
    expect(opts.environmentVariables.SSH_AUTH_SOCK).toBeUndefined();
    expect(conn.handoffResources.agentPid).toBe('not-a-pid');
  });
});
