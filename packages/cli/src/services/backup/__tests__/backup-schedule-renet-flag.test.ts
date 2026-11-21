/**
 * `--expect-account-server` reaches a scheduled unit only when the machine's renet lists the flag: an older renet dies at
 * cobra's flag parse at 03:00 and the backup silently never runs.
 */
import { describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../../remote/sftp/index.js';
import { accountServerForRenet } from '../backup-schedule-reconcile.js';

const ORIGIN = 'https://account.example.com';
const RENET = '/usr/bin/renet';

function machineWith(help: string, exit = 0): { sftp: SFTPClient; commands: string[] } {
  const commands: string[] = [];
  const sftp = {
    execStreaming: vi.fn(
      (cmd: string, opts?: { onStdout?: (d: Buffer) => void; onStderr?: (d: Buffer) => void }) => {
        commands.push(cmd);
        opts?.onStdout?.(Buffer.from(help));
        return Promise.resolve(exit);
      }
    ),
  } as unknown as SFTPClient;
  return { sftp, commands };
}

describe('accountServerForRenet', () => {
  it('passes the origin when the installed renet lists the flag (new renet)', async () => {
    const { sftp, commands } = machineWith(
      '  --expect-account-server string   refuse a foreign licence\n'
    );
    await expect(accountServerForRenet(sftp, RENET, ORIGIN)).resolves.toBe(ORIGIN);
    expect(commands).toEqual([`${RENET} backup snapshot --help 2>&1`]);
  });

  it('omits the origin when the installed renet predates the flag (old renet)', async () => {
    const { sftp } = machineWith('  --bwlimit string   cap uploads\n');
    await expect(accountServerForRenet(sftp, RENET, ORIGIN)).resolves.toBeUndefined();
  });

  it('refuses when the probe itself fails, rather than dropping the licence check', async () => {
    const { sftp } = machineWith('renet: not found', 127);
    await expect(accountServerForRenet(sftp, RENET, ORIGIN)).rejects.toThrow(/exit 127/);
  });

  it('does not probe when the config has no account server', async () => {
    const { sftp, commands } = machineWith('');
    await expect(accountServerForRenet(sftp, RENET, undefined)).resolves.toBeUndefined();
    expect(commands).toEqual([]);
  });
});
