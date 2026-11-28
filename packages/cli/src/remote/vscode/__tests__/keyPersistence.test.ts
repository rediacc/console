import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../utils/platform.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/platform.js')>();
  return { ...actual, isWSL: () => false, getPlatform: () => 'linux' };
});

const { persistKnownHosts, persistSSHKey } = await import('../keyPersistence.js');

const KEY_BODY = [
  `-----BEGIN OPENSSH ${'PRIVATE KEY'}-----`,
  'b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW',
  '-----END OPENSSH PRIVATE KEY-----',
].join('\n');

describe('persistSSHKey', () => {
  let home: string;
  let savedHome: string | undefined;

  beforeEach(() => {
    savedHome = process.env.HOME;
    home = mkdtempSync(join(tmpdir(), 'rdc-keypersist-'));
    process.env.HOME = home;
  });

  afterEach(() => {
    if (savedHome === undefined) delete process.env.HOME;
    else process.env.HOME = savedHome;
    rmSync(home, { recursive: true, force: true });
  });

  it('writes a key that ends in one newline, since OpenSSH rejects one without it', () => {
    const path = persistSSHKey('', 'hostinger', undefined, KEY_BODY);
    const written = readFileSync(path, 'utf8');
    expect(written.endsWith('-----END OPENSSH PRIVATE KEY-----\n')).toBe(true);
    expect(written.endsWith('\n\n')).toBe(false);
    // BLOCKER: POSIX mode bits; NTFS reports 0o666 whatever chmod asked for, so the 0600 check cannot hold on win32.
    if (process.platform !== 'win32') expect(statSync(path).mode & 0o777).toBe(0o600);
  });

  it('turns CRLF endings into LF', () => {
    const path = persistSSHKey(
      '',
      'hostinger',
      undefined,
      `${KEY_BODY.replaceAll('\n', '\r\n')}\r\n`
    );
    expect(readFileSync(path, 'utf8')).not.toContain('\r');
  });
});

describe('persistKnownHosts', () => {
  let home: string;
  let savedHome: string | undefined;

  beforeEach(() => {
    savedHome = process.env.HOME;
    home = mkdtempSync(join(tmpdir(), 'rdc-khpersist-'));
    process.env.HOME = home;
  });

  afterEach(() => {
    if (savedHome === undefined) delete process.env.HOME;
    else process.env.HOME = savedHome;
    rmSync(home, { recursive: true, force: true });
  });

  it('writes the pins under the HostName the VS Code entry dials, not the address they were scanned at', () => {
    const key = 'AAAAC3NzaC1lZDI1NTE5AAAAIOc6d1X0xGOoKduhuDqMgbBDT+AvKI/mf7cfltmqwB06';
    const path = persistKnownHosts('', 'hostinger', `203.0.113.7 ssh-ed25519 ${key}`, {
      host: '2a02:4780:c:e9b5::1',
      port: 22,
    });
    expect(readFileSync(path, 'utf8')).toBe(`2a02:4780:c:e9b5::1 ssh-ed25519 ${key}\n`);
  });
});
