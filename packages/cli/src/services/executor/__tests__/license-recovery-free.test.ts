/**
 * PLAN-free-license F5 at the executor's licence paths: with no login the
 * provisioning and restore pre-flights license through a FREE licence when the
 * authority says so (an agent or `--yes` without asking), the opportunistic
 * refresh and the expired-licence recovery renew through renet's own
 * blob-authenticated path, which is how a FREE licence is renewed, and a login
 * keeps the account path untouched.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  tokenState: vi.fn(),
  resolveAuthority: vi.fn(),
  issueFree: vi.fn(),
  renew: vi.fn(),
  issueRepoLicense: vi.fn(),
  refreshBatch: vi.fn(),
  deviceAuth: vi.fn(),
  isRefreshDue: vi.fn(),
  markRefreshAttempted: vi.fn(),
  resolveCtx: vi.fn(),
}));

vi.mock('../../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../account/subscription-auth.js', () => ({ getSubscriptionTokenState: m.tokenState }));
vi.mock('../../account/free-license.js', () => ({
  resolveLicenseAuthority: m.resolveAuthority,
  issueFreeRepoLicense: m.issueFree,
  renewInstalledLicenses: m.renew,
}));
vi.mock('../../account/license.js', () => ({
  issueRepoLicense: m.issueRepoLicense,
  refreshRepoLicensesBatch: m.refreshBatch,
  refreshRepoLicenseIdentity: vi.fn(),
}));
vi.mock('../../account/license-preflight.js', () => ({
  isMachineSlotLimitError: () => false,
  machineSlotLimitMessage: vi.fn(),
  readMachineSlotStatus: vi.fn(),
}));
vi.mock('../../account/license-refresh-state.js', () => ({
  isRefreshDue: m.isRefreshDue,
  markRefreshAttempted: m.markRefreshAttempted,
}));
vi.mock('../../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: m.deviceAuth,
}));
vi.mock('../../config/state-write-failure.js', () => ({ reportStateWriteRefused: vi.fn() }));
vi.mock('../../core/output.js', () => ({ outputService: { info: vi.fn(), warn: vi.fn() } }));
vi.mock('../../machine/machine-connection.js', () => ({ machineConnections: {} }));
vi.mock('../../telemetry/telemetry.js', () => ({
  telemetryService: { trackEvent: vi.fn(), trackError: vi.fn() },
}));
vi.mock('../../../utils/agent-guard.js', () => ({ isAgentEnvironment: () => true }));
vi.mock('../repo-license-context.js', () => ({
  resolveRepoLicenseContext: m.resolveCtx,
  resolveRestoreLicenseContext: vi.fn(),
  resolveRestoreSizeGb: vi.fn(),
  restoreLicenseAlreadyInstalled: vi.fn(),
}));

import {
  ensureRepoLicenseForProvisioning,
  maybeRefreshRepoLicenses,
  resolveLicenseFailure,
} from '../license-recovery.js';

const MACHINE = { ip: '10.0.0.1', user: 'root' } as never;
const SFTP = { exec: vi.fn() } as never;
const GUID = '11111111-2222-4333-8444-555555555555';
const CTX = { repositoryGuid: GUID, kind: 'grand', requestedSizeGb: 2, datastoreId: 'ds-1' };
const CREATE = { functionName: 'repository_create', machineName: 'm1', params: {} } as never;

beforeEach(() => {
  vi.clearAllMocks();
  m.tokenState.mockReturnValue({ kind: 'missing' });
  m.resolveCtx.mockResolvedValue(CTX);
  m.issueFree.mockResolvedValue(undefined);
  m.issueRepoLicense.mockResolvedValue(true);
  m.isRefreshDue.mockResolvedValue(true);
  // What the batch answers with no token (license-batch.ts): the renewal below is the fallback.
  m.refreshBatch.mockResolvedValue({ recoveryFailureMode: 'token_not_ready' });
});

describe('ensureRepoLicenseForProvisioning with no login', () => {
  it('takes a FREE licence for the repo when the authority is free, and never the account path', async () => {
    m.resolveAuthority.mockResolvedValue('free');
    await ensureRepoLicenseForProvisioning(CREATE, MACHINE, 'key', '/usr/bin/renet', SFTP);
    expect(m.issueFree).toHaveBeenCalledWith(
      MACHINE,
      'key',
      {
        repositoryGuid: GUID,
        grandGuid: undefined,
        kind: 'grand',
        requestedSizeGb: 2,
        datastoreId: 'ds-1',
      },
      '/usr/bin/renet',
      SFTP
    );
    expect(m.issueRepoLicense).not.toHaveBeenCalled();
    // The old agent refusal (errors.subscription.tokenRequired) is gone: the agent is licensed.
    expect(m.deviceAuth).not.toHaveBeenCalled();
  });

  it('issues through the account when the authority is the token', async () => {
    m.resolveAuthority.mockResolvedValue('token');
    await ensureRepoLicenseForProvisioning(CREATE, MACHINE, 'key', '/usr/bin/renet', SFTP);
    expect(m.issueRepoLicense).toHaveBeenCalledTimes(1);
    expect(m.issueFree).not.toHaveBeenCalled();
  });

  it('hands the device-code login to the authority as the login choice', async () => {
    m.resolveAuthority.mockImplementation(async (login: () => Promise<unknown>) => {
      await login();
      return 'token';
    });
    await ensureRepoLicenseForProvisioning(CREATE, MACHINE, 'key', '/usr/bin/renet', SFTP);
    expect(m.deviceAuth).toHaveBeenCalledTimes(1);
  });
});

describe('FREE renewal with no login', () => {
  it('the opportunistic refresh renews due blobs through renet, not the token batch', async () => {
    m.renew.mockResolvedValue({ renewed: 1, results: [] });
    await maybeRefreshRepoLicenses(MACHINE, 'm1', 'key', '/usr/bin/renet', SFTP);
    expect(m.markRefreshAttempted).toHaveBeenCalledWith('m1');
    expect(m.renew).toHaveBeenCalledWith(MACHINE, 'key', {
      remoteRenetPath: '/usr/bin/renet',
      sftp: SFTP,
    });
    expect(m.refreshBatch).not.toHaveBeenCalled();
  });

  it('the opportunistic refresh honours the cooldown', async () => {
    m.isRefreshDue.mockResolvedValue(false);
    await maybeRefreshRepoLicenses(MACHINE, 'm1', 'key', '/usr/bin/renet', SFTP);
    expect(m.renew).not.toHaveBeenCalled();
  });

  it('an expired licence recovers by a forced renet renewal, and the run is retried', async () => {
    m.renew.mockResolvedValue({ renewed: 1, results: [] });
    const result = { success: false, exitCode: 10 } as never;
    const out = await resolveLicenseFailure(
      result,
      { reason: 'expired' } as never,
      { functionName: 'repository_up', machineName: 'm1', params: {} } as never,
      MACHINE,
      'key',
      '/usr/bin/renet',
      SFTP,
      Date.now()
    );
    expect(out).toBeNull();
    expect(m.renew).toHaveBeenCalledWith(MACHINE, 'key', {
      force: true,
      remoteRenetPath: '/usr/bin/renet',
      sftp: SFTP,
    });
  });

  it('a renewal that renewed nothing reports the token-not-ready guidance', async () => {
    m.renew.mockResolvedValue({ renewed: 0, results: [] });
    const out = await resolveLicenseFailure(
      { success: false, exitCode: 10 } as never,
      { reason: 'expired' } as never,
      { functionName: 'repository_up', machineName: 'm1', params: {} } as never,
      MACHINE,
      'key',
      '/usr/bin/renet',
      SFTP,
      Date.now()
    );
    expect(out).toMatchObject({ errorCode: 'REPO_LICENSE_REFRESH_REQUIRED' });
  });
});
