/**
 * `backup restore` must license the TARGET machine before renet runs.
 *
 * The disaster-recovery target is, by construction, a fresh replacement box
 * holding no repository licence at all. renet's restore path needs one as its
 * chunk-store credential AND as its address book (the session URL is derived
 * from the blob's RenewalURL), so on a bare machine the verb refused exactly
 * where it is needed, and the only way through was creating a throwaway carrier
 * repo first — a trick no operator in a real DR situation would know.
 *
 * These tests drive `localExecutorService.execute()` directly, and that is the
 * point rather than a preference. EVERY command-level restore test mocks the
 * executor wholesale (`getExecutor: () => ({ execute: mockExecute })`), so
 * nothing in local-executor.ts runs in any of them: a test written at command
 * level cannot catch this class of defect no matter how thorough it is. Nor
 * could an exit-code assertion have caught it, because renet's own restore
 * failure is a plain error string and never the structured LICENSE_REQUIRED
 * that the CLI's recovery framework watches for.
 */
import type { MockInstance } from 'vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockConnect,
  mockClose,
  mockExec,
  mockExecStreaming,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockGetRepository,
  mockListStorages,
  mockListRepositories,
  mockIssueRepoLicense,
  mockReadRuntimeRepoLicenseStatuses,
  mockRefreshRepoLicensesBatch,
  mockRefreshRepoLicenseIdentity,
  mockGetSubscriptionTokenState,
  mockAccountServerFetch,
} = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockClose: vi.fn(),
  mockExec: vi.fn(),
  mockExecStreaming: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetRepository: vi.fn(),
  mockListStorages: vi.fn(),
  mockListRepositories: vi.fn(),
  mockIssueRepoLicense: vi.fn(),
  mockReadRuntimeRepoLicenseStatuses: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockRefreshRepoLicenseIdentity: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
  mockAccountServerFetch: vi.fn(),
}));

vi.mock('../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    isConnected = () => true;
  },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getRepository: mockGetRepository,
    listStorages: mockListStorages,
    listRepositories: mockListRepositories,
  },
}));

// Only the network- and machine-facing licence verbs are stubbed.
// `isDatastoreScopedId` stays REAL, so the datastore identity these tests feed
// has to be one the licence writer — and the skip probe's scope comparison —
// would also accept.
vi.mock('../account/license.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../account/license.js')>()),
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
  issueRepoLicense: mockIssueRepoLicense,
  readRuntimeRepoLicenseStatuses: mockReadRuntimeRepoLicenseStatuses,
}));

vi.mock('../account/account-client.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../account/account-client.js')>()),
  accountServerFetch: mockAccountServerFetch,
}));

vi.mock('../account/license-refresh-state.js', () => ({
  isRefreshDue: vi.fn(() => Promise.resolve(false)),
  markRefreshAttempted: vi.fn(() => Promise.resolve()),
  LICENSE_REFRESH_COOLDOWN_MS: 12 * 60 * 60 * 1000,
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: vi.fn(),
}));

vi.mock('../../utils/agent-guard.js', () => ({
  isAgentEnvironment: vi.fn().mockReturnValue(false),
}));

vi.mock('../renet/renet-execution.js', () => ({
  buildLocalVault: vi.fn(() => '{"vault":"ok"}'),
  provisionRenetToRemote: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  readSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  readOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  verifyMachineSetup: vi.fn(),
  getLocalRenetPath: vi.fn(),
}));

const { outputService } = await import('../core/output.js');
const { localExecutorService } = await import('../executor/local-executor.js');
const { isRepoProvisioningFunction, isRestoreLicenseFunction, getRenetFunctionLicenseTier } =
  await import('../renet/renet-license-contract.js');

/** The SOURCE repo's guid. The restored record reuses it, so this is what gets licensed. */
const SOURCE_GUID = 'd2fe7d2c-ebb2-4aee-adaa-5c9bf03f5b13';
/** A DIFFERENT repo's guid: the carrier a candidate-(b) implementation would license instead. */
const CARRIER_GUID = '7a41b4dc-bff1-45ac-8be4-8d684d87590a';
/** A fork's grand, used to prove `kind` follows the lineage rather than being hard-coded. */
const FORK_CHILD_GUID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const DATASTORE_ID = '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0';
const OTHER_DATASTORE_ID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';
const SNAPSHOT_ID = '20260815T041418Z-c1e8778364245163';
/** Deliberately not a whole number of GiB: the request must round UP, never truncate. */
const SNAPSHOT_BYTES = 12 * 1024 * 1024 * 1024 + 1;

/** `backup restore --at <snapshot> --datastore tier1`, as backup.ts dispatches it. */
const restoreOptions = {
  functionName: 'backup_restore',
  machineName: 'w2',
  params: {
    repository: 'rtcli',
    // The command computes this as `source.grandGuid ?? source.repositoryGuid`
    // and hands the SAME value to the chunk store as the lineage.
    lineage: SOURCE_GUID,
    at: SNAPSHOT_ID,
    dry_run: false,
  },
  captureOutput: true,
};

/**
 * The restored repo's config record, as `backup restore` writes it BEFORE the
 * executor runs: the SOURCE's guid, and NO grandGuid (addRepository is called
 * with five fields and that is not one of them).
 */
function restoredRepo(placement?: { datastore: string } | { machine: string }) {
  return {
    repositoryGuid: SOURCE_GUID,
    tag: 'latest',
    ...(placement ? { placement } : {}),
  };
}

/** One entry of renet's `repository license-status --all-datastores` output. */
function installedLicence(repositoryGuid: string, datastoreId?: string) {
  return {
    repositoryGuid,
    status: 'valid',
    runtimeValid: true,
    installed: true,
    ...(datastoreId ? { datastoreId } : {}),
  };
}

describe('backup restore: licensing the target machine', () => {
  const savedSkipActivation = process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
  let warnSpy: MockInstance<typeof outputService.warn>;

  beforeEach(() => {
    vi.clearAllMocks();
    // Without this the whole pre-flight early-returns, and every assertion
    // below would pass for a reason that has nothing to do with the fix.
    delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      sshPublicKey: 'PUBLIC_KEY',
      ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'w2',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockGetRepository.mockResolvedValue(restoredRepo({ datastore: 'tier1' }));
    mockListStorages.mockResolvedValue([]);
    mockListRepositories.mockResolvedValue([]);
    mockIssueRepoLicense.mockResolvedValue(true);
    mockRefreshRepoLicenseIdentity.mockResolvedValue(undefined);
    // The bare DR machine: nothing installed, which is the whole scenario.
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([]);
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test' },
    });
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        { snapshotId: SNAPSHOT_ID, lineageGuid: SOURCE_GUID, totalBytes: SNAPSHOT_BYTES },
        { snapshotId: 'older-one', lineageGuid: SOURCE_GUID, totalBytes: 999 * 1024 ** 3 },
      ],
    });
    mockExecStreaming.mockResolvedValue(0);
    mockExec.mockImplementation((command: string) => {
      if (command.includes('datastore list --json')) {
        return Promise.resolve(JSON.stringify([{ name: 'tier1', datastoreId: DATASTORE_ID }]));
      }
      return Promise.resolve('');
    });
  });

  afterEach(() => {
    warnSpy.mockRestore();
    if (savedSkipActivation === undefined) {
      delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    } else {
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION = savedSkipActivation;
    }
  });

  // T1 — the required test. Delete the restore arm at the provisionAndVerify
  // seam, or invert its predicate, and this goes red.
  it('issues a repo licence before renet runs, on a machine holding none', async () => {
    const result = await localExecutorService.execute(restoreOptions);

    expect(result.success).toBe(true);
    expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1);
  });

  // T2 — T1 alone is satisfied by ANY implementation that calls the mint with
  // anything at all. This pins WHICH licence, and it is the assertion that
  // fails if the carrier-repo workaround is ever shipped as the product.
  it('licenses the SOURCE guid, in the TARGET datastore scope', async () => {
    await localExecutorService.execute(restoreOptions);

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({
      // Not a carrier, not a fresh guid, not the target NAME: the source guid,
      // which is the licence `repository_up` will look for after `--up`,
      // guid-specifically and with no any-repo fallback.
      repositoryGuid: SOURCE_GUID,
      grandGuid: SOURCE_GUID,
      kind: 'grand',
      // The blob has to land where `datastore.IdentityAt` looks for it.
      // Unscoped here is a licence installed somewhere nothing reads.
      datastoreId: DATASTORE_ID,
    });
  });

  // T2b — the lineage comes from `params.lineage`, and it MUST, because the
  // restored config record carries no grandGuid at all. An implementation that
  // read the record would send `kind: 'grand'` for a fork's restore.
  it('takes the lineage from the restore params, so a fork restores as a fork', async () => {
    mockGetRepository.mockResolvedValue({
      repositoryGuid: FORK_CHILD_GUID,
      tag: 'latest',
      placement: { datastore: 'tier1' },
    });

    await localExecutorService.execute({
      ...restoreOptions,
      params: { ...restoreOptions.params, lineage: SOURCE_GUID },
    });

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({
      repositoryGuid: FORK_CHILD_GUID,
      grandGuid: SOURCE_GUID,
      kind: 'fork',
    });
  });

  // T3 — the size cannot come from the machine: the image being licensed does
  // not exist there yet. A stat-based fallback caps a restored 500 GB repo at
  // the 1 GB floor for the rest of its life, because MaxRepositorySizeGb is
  // signed into the payload.
  it('sizes the licence from the snapshot manifest, rounded up', async () => {
    await localExecutorService.execute(restoreOptions);

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 13 });
    // The lookup is exact, not "newest": the 999 GB decoy manifest in the same
    // lineage must not be the one that was read.
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      `/account/api/v1/backups/manifests?lineage=${SOURCE_GUID}`
    );
    // No stat probe: there is nothing on the target to measure.
    expect(
      mockExec.mock.calls.map((c) => String(c[0])).filter((c) => c.startsWith('stat '))
    ).toEqual([]);
  });

  // T3b — control on the direction of the fallback. A manifest index that
  // cannot answer must under-size and SAY so, never refuse: a failed size
  // lookup is not a reason to fail a disaster recovery.
  it('falls back to the floor with a warning when the manifest index cannot answer', async () => {
    mockAccountServerFetch.mockRejectedValue(new Error('offline'));

    const result = await localExecutorService.execute(restoreOptions);

    expect(result.success).toBe(true);
    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 1 });
    expect(warnSpy.mock.calls.map((c) => String(c[0])).join('\n')).toContain(
      'Could not read the size of snapshot'
    );
  });

  // T4 — negative control. A predicate widened to "any backup verb" would make
  // T1 pass for the wrong reason and would burn an issuance on every read.
  it.each(['backup_list', 'backup_pull', 'backup_snapshot'])(
    'issues nothing for %s',
    async (functionName) => {
      await localExecutorService.execute({ ...restoreOptions, functionName });

      expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    }
  );

  // T5 — the cost control. `claimRepoLicenseIssuanceSlot` dedupes by nothing:
  // not by repo, not by machine. Without the skip probe a DR session that fails
  // three times on an unrelated error spends four monthly issuances.
  it('skips issuance when the target already holds a valid licence for the source guid', async () => {
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([
      installedLicence(SOURCE_GUID, DATASTORE_ID),
    ]);

    const result = await localExecutorService.execute(restoreOptions);

    expect(result.success).toBe(true);
    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    // And it costs no round trip either: the size lookup sits behind the probe.
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  // T5b — the probe must NOT be "any licence on the machine". That reading
  // reproduces the carrier-repo bug from the other direction: issuance skipped,
  // restore passes through renet's any-repo fallback, and the `--up` that
  // follows fails for want of a licence for THIS guid.
  it('still issues when the machine holds only an unrelated repo licence', async () => {
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([
      installedLicence(CARRIER_GUID, DATASTORE_ID),
    ]);

    await localExecutorService.execute(restoreOptions);

    expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1);
    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ repositoryGuid: SOURCE_GUID });
  });

  // T5c — nor is it "the right guid, anywhere". A blob in a different datastore
  // population is one renet will not read for this restore.
  it('still issues when the right guid is licensed in the WRONG datastore scope', async () => {
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([
      installedLicence(SOURCE_GUID, OTHER_DATASTORE_ID),
    ]);

    await localExecutorService.execute(restoreOptions);

    expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1);
  });

  // T5d — and an installed-but-invalid blob is not a licence. `runtimeValid`
  // is the field that distinguishes "present" from "usable".
  it('still issues when the installed licence for the guid is not runtime-valid', async () => {
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([
      { ...installedLicence(SOURCE_GUID, DATASTORE_ID), status: 'expired', runtimeValid: false },
    ]);

    await localExecutorService.execute(restoreOptions);

    expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1);
  });

  // The bypass must stay honoured: nolicense/CI builds have no subscription
  // server to mint against.
  it('honours REDIACC_SKIP_MACHINE_ACTIVATION', async () => {
    process.env.REDIACC_SKIP_MACHINE_ACTIVATION = '1';

    const result = await localExecutorService.execute(restoreOptions);

    expect(result.success).toBe(true);
    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
  });
});

/**
 * The classification itself, pinned separately from the behaviour.
 *
 * renet makes `backup_restore` TierNone deliberately: "it is the DISASTER
 * RECOVERY verb. A tier gate on it would mean an expired licence can lock a
 * customer out of their own backed-up data". The tempting shortcut for the fix
 * above is to fold restore into the repo-provisioning class so it inherits the
 * pre-flight for free — and that shortcut reintroduces exactly the lockout the
 * fix exists to remove, silently, in a diff that looks like a simplification.
 */
describe('backup_restore is licensed as a restore, never as a provisioning verb', () => {
  it('is not a repo-provisioning function', () => {
    expect(isRepoProvisioningFunction('backup_restore')).toBe(false);
    // The two ways it could become one: the prefix, and the tier.
    expect('backup_restore'.startsWith('repository_')).toBe(false);
    expect(getRenetFunctionLicenseTier('backup_restore')).not.toBe('create');
  });

  it('is the restore-licence function, and nothing else is', () => {
    expect(isRestoreLicenseFunction('backup_restore')).toBe(true);
    for (const name of [
      'backup_list',
      'backup_pull',
      'backup_push',
      'backup_snapshot',
      'repository_create',
      'repository_fork',
    ]) {
      expect(isRestoreLicenseFunction(name)).toBe(false);
    }
  });
});
