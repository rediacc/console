/**
 * Windows external terminal: the launch line deletes the temp key and
 * known_hosts when ssh ends (`& del /q ...`), so the parent can exit at once
 * without removing them. The line builder quotes paths for cmd.exe and refuses
 * the ones it cannot quote.
 */
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const launchTerminal = vi.fn();
let terminalType = 'windows-terminal';
vi.mock('../remote/terminal/index.js', () => ({
  getDefaultTerminalType: () => terminalType,
  launchTerminal: (...a: unknown[]) => launchTerminal(...a),
}));
vi.mock('../remote/utils/platform.js', () => ({ getPlatform: () => 'windows' }));

import { launchExternalTerminal } from '../commands/term-external.js';
import { SSHConnection } from '../remote/ssh/connection.js';

const details = { environment: {}, workingDirectory: undefined } as never;

function fakeConnection(keyFilePath: string, knownHostsPath: string, agentPid?: string) {
  const conn = new SSHConnection('k', 'h', { host: '10.0.0.1', preferAgent: false });
  Object.assign(conn, {
    setupResult: {
      sshOptions: ['-i', keyFilePath],
      knownHostsPath,
      keyFilePath,
      connectionMethod: 'file-based',
      ...(agentPid && { agentPid }),
    },
    isSetup: true,
  });
  return conn;
}

describe('windows external terminal handoff', () => {
  beforeEach(() => {
    launchTerminal.mockReset();
    launchTerminal.mockReturnValue({ success: true });
    terminalType = 'windows-terminal';
  });

  it('hands the key and known_hosts to the launcher and the parent deletes neither', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'rdc-win-'));
    const key = join(dir, 'ssh-key-ab.pem');
    const kh = join(dir, 'known_hosts');
    writeFileSync(key, 'k');
    writeFileSync(kh, 'h');
    const conn = fakeConnection(key, kh);
    await launchExternalTerminal(conn, 'u@h', undefined, 't', details);
    const opts = launchTerminal.mock.calls[0][1];
    expect(opts.cleanupFiles).toEqual([key, kh]);
    expect(opts.argv[0]).toBe('ssh');
    await conn.cleanup();
    expect(existsSync(key)).toBe(true);
    expect(existsSync(kh)).toBe(true);
  });

  it('a launch failure keeps ownership so the parent still cleans up', async () => {
    launchTerminal.mockReturnValue({ success: false, error: 'nope' });
    const conn = fakeConnection('C:/t/key.pem', 'C:/t/kh');
    await expect(launchExternalTerminal(conn, 'u@h', undefined, 't', details)).rejects.toThrow();
    expect(conn.handoffResources.keyFilePath).toBe('C:/t/key.pem');
  });

  it('the remote command reaches the launcher as base64 text with no line break', async () => {
    const conn = fakeConnection('C:/t/key.pem', 'C:/t/kh');
    await launchExternalTerminal(conn, 'u@h', 'cd /x\nexport A=1 && exec bash', 't', details);
    const argv = launchTerminal.mock.calls[0][1].argv as string[];
    expect(argv.at(-1)).toMatch(
      /^f=\$\(mktemp\)&&echo [A-Za-z0-9+/=]+\|base64 -d\|gzip -dc>\$f&&exec env RDC_BASH_ENV=\$BASH_ENV BASH_ENV= bash \$f$/
    );
  });

  it('mintty is outside the cleanup terminals: no handoff, no cleanupFiles, the parent still owns the files', async () => {
    terminalType = 'mintty';
    const conn = fakeConnection('C:/t/key.pem', 'C:/t/kh');
    await launchExternalTerminal(conn, 'u@h', 'echo hi', 't', details);
    const opts = launchTerminal.mock.calls[0][1];
    expect(opts.cleanupFiles).toBeUndefined();
    expect(opts.argv.at(-1)).toBe('echo hi');
    expect(conn.handoffResources.keyFilePath).toBe('C:/t/key.pem');
  });

  it('an agent pid keeps everything with the parent, since no Windows launcher stops the agent', async () => {
    const conn = fakeConnection('C:/t/key.pem', 'C:/t/kh', '4242');
    await launchExternalTerminal(conn, 'u@h', undefined, 't', details);
    expect(launchTerminal.mock.calls[0][1].cleanupFiles).toBeUndefined();
    expect(conn.handoffResources.keyFilePath).toBe('C:/t/key.pem');
  });
});
