/**
 * `repo migrate` installs the repo licence on its TARGET (#89f10804).
 *
 * e2e suite 23 test 3: `rdc repo migrate app@machine-11 --to machine-12` ended with
 * `repository_up failed: LICENSE_REQUIRED: missing: no license data`, and machine-12's licence store
 * held no blob for the migrated GUID. These assertions read what was issued, for which GUID and on
 * which machine, not the command's output.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const GUID = '22222222-2222-4222-8222-222222222222';
const GRAND = '33333333-3333-4333-8333-333333333333';

const h = vi.hoisted(() => ({
  repo: null as { repositoryGuid?: string; grandGuid?: string } | null,
  scan: [] as Record<string, unknown>[],
  installed: false,
  authority: 'token' as 'token' | 'free',
  issued: true,
  released: 0,
  acquiredFor: [] as string[],
}));

const machine = { ip: '10.0.0.2', user: 'root' };
const sftp = { exec: vi.fn() };

vi.mock('../config/config-resources.js', () => ({
  configService: { getRepository: vi.fn(() => Promise.resolve(h.repo)) },
}));
vi.mock('../machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn((name: string) => {
      h.acquiredFor.push(name);
      return Promise.resolve({
        machine,
        sshPrivateKey: 'key',
        sftp,
        release: () => {
          h.released += 1;
        },
      });
    }),
  },
}));
vi.mock('../account/license-machine.js', () => ({
  DEFAULT_DATASTORE: '/mnt/rediacc',
  scanRemoteRepoLicenses: vi.fn(() => Promise.resolve(h.scan)),
}));
vi.mock('../executor/repo-license-context.js', () => ({
  restoreLicenseAlreadyInstalled: vi.fn(() => Promise.resolve(h.installed)),
}));
vi.mock('../account/free-license.js', () => ({
  resolveLicenseAuthority: vi.fn(() => Promise.resolve(h.authority)),
  issueFreeRepoLicense: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../account/license.js', () => ({
  refreshRepoLicenseIdentity: vi.fn(() => Promise.resolve(h.issued)),
}));
vi.mock('../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: vi.fn(),
}));

import { issueFreeRepoLicense } from '../account/free-license.js';
import { refreshRepoLicenseIdentity } from '../account/license.js';
import { restoreLicenseAlreadyInstalled } from '../executor/repo-license-context.js';
import { ensureTargetRepoLicense } from '../repo-migrate-license.js';

beforeEach(() => {
  vi.clearAllMocks();
  h.repo = { repositoryGuid: GUID };
  h.scan = [
    {
      repositoryGuid: GUID,
      requestedSizeGb: 2,
      datastorePath: '/mnt/rediacc',
      storageFingerprint: 'fp',
    },
  ];
  h.installed = false;
  h.authority = 'token';
  h.issued = true;
  h.released = 0;
  h.acquiredFor = [];
});

describe('ensureTargetRepoLicense', () => {
  it('issues for the migrated GUID on the TARGET when its store holds no licence', async () => {
    await ensureTargetRepoLicense('app', 'machine-12');

    expect(h.acquiredFor).toEqual(['machine-12']);
    expect(refreshRepoLicenseIdentity).toHaveBeenCalledTimes(1);
    const [onMachine, , params] = vi.mocked(refreshRepoLicenseIdentity).mock.calls[0];
    expect(onMachine).toBe(machine);
    expect(params).toMatchObject({ repositoryGuid: GUID, grandGuid: GUID, kind: 'grand' });
    expect(h.released).toBe(1);
  });

  it('probes THIS GUID on the target, so a blob for any other repo does not count', async () => {
    await ensureTargetRepoLicense('app', 'machine-12');
    const [ctx] = vi.mocked(restoreLicenseAlreadyInstalled).mock.calls[0];
    expect(ctx.repositoryGuid).toBe(GUID);
  });

  it('issues nothing when a licence valid on the target is already installed', async () => {
    h.installed = true;
    await ensureTargetRepoLicense('app', 'machine-12');
    expect(refreshRepoLicenseIdentity).not.toHaveBeenCalled();
    expect(issueFreeRepoLicense).not.toHaveBeenCalled();
    expect(h.released).toBe(1);
  });

  it('takes the FREE licence with no login, sized from the landed image', async () => {
    h.authority = 'free';
    await ensureTargetRepoLicense('app', 'machine-12');
    expect(refreshRepoLicenseIdentity).not.toHaveBeenCalled();
    const [, , params] = vi.mocked(issueFreeRepoLicense).mock.calls[0];
    expect(params).toMatchObject({ repositoryGuid: GUID, kind: 'grand', requestedSizeGb: 2 });
  });

  it('carries the lineage of a fork', async () => {
    h.repo = { repositoryGuid: GUID, grandGuid: GRAND };
    await ensureTargetRepoLicense('app', 'machine-12');
    const [, , params] = vi.mocked(refreshRepoLicenseIdentity).mock.calls[0];
    expect(params).toMatchObject({ repositoryGuid: GUID, grandGuid: GRAND, kind: 'fork' });
  });

  it('throws when issuance does not happen, and still releases the connection', async () => {
    h.issued = false;
    await expect(ensureTargetRepoLicense('app', 'machine-12')).rejects.toThrow(
      'errors.subscription.activationFailed'
    );
    expect(h.released).toBe(1);
  });

  it('does nothing for a repo with no GUID in the config', async () => {
    h.repo = null;
    await ensureTargetRepoLicense('app', 'machine-12');
    expect(h.acquiredFor).toEqual([]);
  });
});
