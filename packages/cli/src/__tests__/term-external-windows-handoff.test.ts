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
vi.mock('../remote/terminal/index.js', () => ({
  getDefaultTerminalType: () => 'windows-terminal',
  launchTerminal: (...a: unknown[]) => launchTerminal(...a),
}));
vi.mock('../remote/utils/platform.js', () => ({ getPlatform: () => 'windows' }));

import { launchExternalTerminal } from '../commands/term-external.js';
import { SSHConnection } from '../remote/ssh/connection.js';

const details = { environment: {}, workingDirectory: undefined } as never;

function fakeConnection(keyFilePath: string, knownHostsPath: string) {
  const conn = new SSHConnection('k', 'h', { preferAgent: false });
  Object.assign(conn, {
    setupResult: {
      sshOptions: ['-i', keyFilePath],
      knownHostsPath,
      keyFilePath,
      connectionMethod: 'file-based',
    },
    isSetup: true,
  });
  return conn;
}

describe('windows external terminal handoff', () => {
  beforeEach(() => {
    launchTerminal.mockReset();
    launchTerminal.mockReturnValue({ success: true });
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
});
