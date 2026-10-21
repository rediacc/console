/**
 * rdc.sh's dev-config seeder (the `node -e` block of its RDC_DEV path) writes the CLI's dev config
 * by the CLI's rules. These tests run that exact block, read out of rdc.sh, against a temp config
 * dir: a key belongs to the server it came from, and a slash-only difference is the same server.
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { WK_ACCOUNT_DEV_PORT } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const RDC_SH = resolve(__dirname, '../../../../../rdc.sh');

/** The seeder's script text: the lines between `node -e '` and `' "$dev_server" "$dev_e2e_key"`. */
function seederScript(): string {
  const lines = readFileSync(RDC_SH, 'utf8').split('\n');
  const start = lines.findIndex((line) => line.trim() === "node -e '");
  const end = lines.findIndex((line, i) => i > start && line.trim().startsWith(`' "$dev_server"`));
  if (start < 0 || end < 0) throw new Error('rdc.sh dev seeder block not found');
  return lines.slice(start + 1, end).join('\n');
}

describe('rdc.sh dev-config seeder', () => {
  let home: string;

  beforeEach(() => {
    home = mkdtempSync(join(tmpdir(), 'rdc-sh-seed-'));
    mkdirSync(join(home, 'rediacc'), { recursive: true });
  });

  afterEach(() => {
    rmSync(home, { recursive: true, force: true });
  });

  function seed(account: Record<string, string>, server: string, key: string) {
    const path = join(home, 'rediacc', 'dev.json');
    writeFileSync(
      path,
      JSON.stringify({
        schemaVersion: 3,
        id: 'x',
        version: 1,
        encryption: { mode: 'plaintext' },
        account,
      })
    );
    execFileSync(process.execPath, ['-e', seederScript(), server, key], {
      env: { ...process.env, XDG_CONFIG_HOME: home },
    });
    return (JSON.parse(readFileSync(path, 'utf8')) as { account: Record<string, string> }).account;
  }

  it('keeps the saved key when the gateway advertised none and only a trailing slash differs', () => {
    const account = seed(
      { accountServer: `http://localhost:${WK_ACCOUNT_DEV_PORT}/`, e2ePublicKey: 'DEV-KEY' },
      `http://localhost:${WK_ACCOUNT_DEV_PORT}`,
      ''
    );
    expect(account).toEqual({
      accountServer: `http://localhost:${WK_ACCOUNT_DEV_PORT}`,
      e2ePublicKey: 'DEV-KEY',
    });
  });

  it('drops the old key when the gateway moved and advertised none', () => {
    const account = seed(
      { accountServer: `http://localhost:${WK_ACCOUNT_DEV_PORT}`, e2ePublicKey: 'OLD-KEY' },
      'http://localhost:4900',
      ''
    );
    expect(account).toEqual({ accountServer: 'http://localhost:4900' });
  });

  it('takes the key the gateway advertised', () => {
    const account = seed(
      { accountServer: `http://localhost:${WK_ACCOUNT_DEV_PORT}` },
      'http://localhost:4900',
      'NEW'
    );
    expect(account).toEqual({ accountServer: 'http://localhost:4900', e2ePublicKey: 'NEW' });
  });
});
