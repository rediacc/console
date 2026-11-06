import { type ChildProcess, execFileSync, spawn } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const rsyncMock = vi.hoisted(() => vi.fn());
vi.mock('../../../remote/sync/index.js', () => ({
  executeRsync: rsyncMock,
  getRsyncCommand: vi.fn(),
}));

import { buildDeltaSshOptions, deltaSyncBinary } from '../renet-binary-transfer.js';

const KEY = '-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n';
const KNOWN =
  '[203.0.113.9]:22 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPLACEHOLDERPLACEHOLDERPLACEHOLDER12';

afterEach(() => rsyncMock.mockReset());

describe('deltaSyncBinary host-key pinning', () => {
  it('a recorded key pins ssh to a 0600 file that is removed afterwards, and never disables checking', async () => {
    let seen: { opts: string; file: string; mode: number; content: string } | undefined;
    rsyncMock.mockImplementation((o: { sshOptions: string }) => {
      const file = /UserKnownHostsFile="([^"]+)"/.exec(o.sshOptions)?.[1] ?? '';
      seen = {
        opts: o.sshOptions,
        file,
        mode: fs.statSync(file).mode & 0o777,
        content: fs.readFileSync(file, 'utf8'),
      };
      return { success: true, errors: [] };
    });
    await deltaSyncBinary(
      { host: '203.0.113.9', username: 'u', privateKey: KEY, knownHosts: KNOWN },
      Buffer.from('x'),
      '/tmp/stage',
      '/usr/bin/rsync'
    );
    expect(seen).toBeDefined();
    expect(seen?.opts).toContain('StrictHostKeyChecking=yes');
    expect(seen?.opts).toContain('GlobalKnownHostsFile=/dev/null');
    expect(seen?.opts).not.toContain('StrictHostKeyChecking=no');
    expect(seen?.opts).not.toContain('UserKnownHostsFile=/dev/null');
    expect(seen?.mode).toBe(0o600);
    expect(seen?.content).toBe(`${KNOWN}\n`);
    expect(fs.existsSync(seen?.file ?? '')).toBe(false);
  });

  it('removes the known_hosts file when the transfer fails', async () => {
    let file = '';
    rsyncMock.mockImplementation((o: { sshOptions: string }) => {
      file = /UserKnownHostsFile="([^"]+)"/.exec(o.sshOptions)?.[1] ?? '';
      return { success: false, errors: ['refused'] };
    });
    await expect(
      deltaSyncBinary(
        { host: 'h', username: 'u', privateKey: KEY, knownHosts: KNOWN },
        Buffer.from('x'),
        '/tmp/stage',
        '/usr/bin/rsync'
      )
    ).rejects.toThrow('refused');
    expect(file).not.toBe('');
    expect(fs.existsSync(file)).toBe(false);
  });

  it('no recorded key keeps the unchecked transport, as the SFTP path does', () => {
    const opts = buildDeltaSshOptions({ port: 22 }, '/k', null);
    expect(opts).toContain('StrictHostKeyChecking=no');
    expect(opts).toContain('UserKnownHostsFile=/dev/null');
  });
});

const haveOpenSsh = fs.existsSync('/usr/sbin/sshd') && fs.existsSync('/usr/bin/ssh-keygen');

describe.skipIf(!haveOpenSsh)('real OpenSSH with the built options', () => {
  let sshd: ChildProcess | undefined;
  afterEach(() => sshd?.kill());

  it('accepts the recorded host key and refuses an impostor', async () => {
    // The ssh argv below is rebuilt by splitting the option string on spaces, so the paths in it must hold none.
    const base = /\s/.test(os.tmpdir()) ? '/tmp' : os.tmpdir();
    const dir = fs.mkdtempSync(path.join(base, 'pin-ssh-'));
    try {
      const gen = (n: string) =>
        execFileSync('ssh-keygen', ['-q', '-t', 'ed25519', '-N', '', '-f', path.join(dir, n)]);
      for (const n of ['host', 'impostor', 'client']) gen(n);
      fs.copyFileSync(path.join(dir, 'client.pub'), path.join(dir, 'authorized'));
      const port = 20000 + Math.floor(Math.random() * 20000);
      fs.writeFileSync(
        path.join(dir, 'sshd_config'),
        [
          `Port ${port}`,
          'ListenAddress 127.0.0.1',
          `HostKey ${dir}/host`,
          `AuthorizedKeysFile ${dir}/authorized`,
          `PidFile ${dir}/pid`,
          'UsePAM no',
          'StrictModes no',
          'PasswordAuthentication no',
        ].join('\n')
      );
      sshd = spawn('/usr/sbin/sshd', ['-D', '-e', '-f', path.join(dir, 'sshd_config')], {
        stdio: 'ignore',
      });
      await new Promise((r) => setTimeout(r, 800));
      const line = (n: string) => {
        const [algo, key] = fs.readFileSync(path.join(dir, `${n}.pub`), 'utf8').split(' ');
        return `[127.0.0.1]:${port} ${algo} ${key}\n`;
      };
      const attempt = (n: string) => {
        const kh = path.join(dir, `kh-${n}`);
        fs.writeFileSync(kh, line(n), { mode: 0o600 });
        const opts = buildDeltaSshOptions({ port }, path.join(dir, 'client'), kh);
        const argv = opts.replaceAll('"', '').split(' ').filter(Boolean);
        return () =>
          execFileSync('ssh', [...argv, `${os.userInfo().username}@127.0.0.1`, 'true'], {
            stdio: 'pipe',
          });
      };
      expect(attempt('host')).not.toThrow();
      expect(attempt('impostor')).toThrow(/Host key verification failed/);
    } finally {
      sshd?.kill();
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, 30_000);
});
