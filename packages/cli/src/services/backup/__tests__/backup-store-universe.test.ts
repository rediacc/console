/**
 * A backup-session verb refuses when the repository's installed licence was issued by another account server than the
 * active config's, because renet derives the backup store from that licence (hostinger runner finding D-a: a
 * `backup snapshot ...@hostinger --config eu-bench` wrote to the eu production store).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const env = vi.hoisted(() => ({ server: 'https://bench.rediacc.com', config: 'eu-bench' }));
vi.mock('../../account/subscription-auth.js', () => ({
  getSubscriptionServerUrl: () => env.server,
}));
vi.mock('../../config/config-name.js', () => ({
  getEffectiveConfigName: () => env.config,
}));

const GUID = 'db315abd-e300-47e4-bbb6-c383d6defe81';
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getRepository: (name: string) =>
      Promise.resolve(name === 'mail' ? { repositoryGuid: GUID } : undefined),
  },
}));

const {
  assertBackupStoreUniverse,
  LISTING_COMPLETE_MARKER,
  licenseOriginsFromListing,
  withExpectedAccountServer,
} = await import('../backup-store-universe.js');

/** One licence file as the remote read prints it: the file's bytes, base64 on one line. */
function licenseLine(renewalUrl: string | undefined): string {
  const payload = Buffer.from(
    JSON.stringify({ repositoryGuid: GUID, ...(renewalUrl ? { renewalUrl } : {}) })
  ).toString('base64');
  return Buffer.from(JSON.stringify({ payload, signature: 'sig', publicKeyId: 'a'.repeat(16) }))
    .toString('base64')
    .concat('\n');
}

function machineWith(...lines: string[]) {
  const commands: string[] = [];
  return {
    commands,
    sftp: {
      exec: (cmd: string) => {
        commands.push(cmd);
        return Promise.resolve(`${lines.join('')}${LISTING_COMPLETE_MARKER}\n`);
      },
    },
  };
}

const EU = 'https://eu.rediacc.com/account/api/v1/licenses/renew';
const BENCH = 'https://bench.rediacc.com/account/api/v1/licenses/renew';

beforeEach(() => {
  env.server = 'https://bench.rediacc.com';
  env.config = 'eu-bench';
});

describe('assertBackupStoreUniverse', () => {
  it('refuses a snapshot whose repository holds a licence from another account server, naming both', async () => {
    const m = machineWith(licenseLine(EU));

    const run = assertBackupStoreUniverse(
      'backup_snapshot',
      'hostinger',
      { repository: 'mail' },
      m.sftp
    );

    await expect(run).rejects.toThrow(/errors\.license\.backupStoreMismatch/);
    await expect(run).rejects.toThrow(/"installed":"https:\/\/eu\.rediacc\.com"/);
    await expect(run).rejects.toThrow(/"expected":"https:\/\/bench\.rediacc\.com"/);
    await expect(run).rejects.toThrow(/"config":"eu-bench"/);
    expect(m.commands[0]).toContain(`/var/lib/rediacc/license/repos/${GUID}/*.json`);
    expect(m.commands[0]).toContain(`/var/lib/rediacc/license/datastores/*/repos/${GUID}/*.json`);
  });

  it('refuses when a matching licence sits beside a foreign one, since renet picks by signer', async () => {
    const m = machineWith(licenseLine(BENCH), licenseLine(EU));

    await expect(
      assertBackupStoreUniverse('backup_restore', 'hostinger', { repository: 'mail' }, m.sftp)
    ).rejects.toThrow(/backupStoreMismatch/);
  });

  it('control: a licence from this config account server passes', async () => {
    const m = machineWith(licenseLine(BENCH));

    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'mail' }, m.sftp)
    ).resolves.toBeUndefined();
  });

  it('control: the same machine passes through the config whose server issued the licence', async () => {
    env.server = 'https://eu.rediacc.com/';
    env.config = 'eu-remote';
    const m = machineWith(licenseLine(EU));

    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'mail' }, m.sftp)
    ).resolves.toBeUndefined();
  });

  it('passes when no licence is installed, and never reads the machine for a verb with no backup session', async () => {
    const empty = machineWith();
    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'mail' }, empty.sftp)
    ).resolves.toBeUndefined();

    const other = machineWith(licenseLine(EU));
    await expect(
      assertBackupStoreUniverse('repository_up', 'hostinger', { repository: 'mail' }, other.sftp)
    ).resolves.toBeUndefined();
    expect(other.commands).toEqual([]);
  });

  it('refuses when the licence listing is cut short (no completion marker), instead of passing on an empty read', async () => {
    const m = {
      sftp: { exec: () => Promise.resolve(licenseLine(BENCH)) },
    };
    const run = assertBackupStoreUniverse(
      'backup_snapshot',
      'hostinger',
      { repository: 'mail' },
      m.sftp
    );
    await expect(run).rejects.toThrow(/errors\.license\.backupStoreUnreadable/);
    await expect(run).rejects.toThrow(/"machine":"hostinger"/);
  });

  it('refuses when the licence listing command fails (sudo refused or the read errors)', async () => {
    const m = {
      sftp: { exec: () => Promise.reject(new Error('sudo: a password is required')) },
    };
    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'mail' }, m.sftp)
    ).rejects.toThrow(/errors\.license\.backupStoreUnreadable/);
  });

  it('refuses a licence whose renewalUrl does not parse, since renet may still select it', async () => {
    const m = machineWith(licenseLine('not a url'));
    const run = assertBackupStoreUniverse(
      'backup_snapshot',
      'hostinger',
      { repository: 'mail' },
      m.sftp
    );
    await expect(run).rejects.toThrow(/backupStoreMismatch/);
    await expect(run).rejects.toThrow(/"installed":"not a url"/);
  });

  it('refuses when this config server URL does not parse, instead of switching the guard off', async () => {
    env.server = 'not a url';
    const m = machineWith(licenseLine(BENCH));
    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'mail' }, m.sftp)
    ).rejects.toThrow(/backupStoreMismatch/);
  });

  it('skips a repository the config does not track', async () => {
    const m = machineWith(licenseLine(EU));
    await expect(
      assertBackupStoreUniverse('backup_snapshot', 'hostinger', { repository: 'nope' }, m.sftp)
    ).resolves.toBeUndefined();
    expect(m.commands).toEqual([]);
  });
});

describe('licenseOriginsFromListing', () => {
  it('reads each renewalUrl origin once and skips lines that are not a licence', () => {
    const listing = [
      licenseLine(EU),
      licenseLine(EU),
      licenseLine(undefined),
      'not base64 json\n',
      licenseLine(BENCH),
    ].join('');
    expect(licenseOriginsFromListing(listing)).toEqual([
      'https://bench.rediacc.com',
      'https://eu.rediacc.com',
    ]);
  });
});

// The executor's params for a session verb carry the config's account-server origin, so renet refuses a licence from
// another account server itself (`--expect-account-server`), whatever licence it picks.
describe('withExpectedAccountServer', () => {
  it.each([
    'backup_snapshot',
    'backup_restore',
    'backup_restore_path',
    'backup_browse_at',
    'backup_repair',
  ])('adds the config origin to %s', (fn) => {
    env.server = 'https://bench.rediacc.com/account/';
    expect(withExpectedAccountServer(fn, { repository: 'mail' })).toEqual({
      repository: 'mail',
      expect_account_server: 'https://bench.rediacc.com',
    });
  });

  it('leaves every other function untouched', () => {
    const params = { repository: 'mail' };
    expect(withExpectedAccountServer('backup_verify', params)).toBe(params);
    expect(withExpectedAccountServer('repository_up', params)).toBe(params);
  });

  it('adds nothing when the config names no usable server', () => {
    env.server = 'not a url';
    expect(withExpectedAccountServer('backup_snapshot', { repository: 'mail' })).toEqual({
      repository: 'mail',
    });
  });
});
