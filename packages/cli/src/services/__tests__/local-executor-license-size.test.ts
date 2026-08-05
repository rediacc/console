/**
 * The repo-license SIZE probe must look where the repo actually lives.
 *
 * `resolveRepoLicenseContext` sized every pre-issuance from the MACHINE's
 * default datastore (`machine.datastore ?? /mnt/rediacc`). A repo created with
 * `repo create --datastore <d>` lives at `/mnt/rediacc-ds/<d>/repositories/…`,
 * so the stat found nothing, the probe's `|| echo 0` turned that into 0 bytes,
 * and the licence was requested at the 1 GB floor. `repo fork` and
 * `repo commit` expose no `--size`, so for them that floor was not a fallback —
 * it was the only number ever sent, for a repo of any size.
 *
 * These assertions read the exact command the executor put on the wire, not its
 * output: a check on the rendered message would have passed against the broken
 * build too.
 */
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
  mockRefreshRepoLicensesBatch,
  mockRefreshRepoLicenseIdentity,
  mockGetSubscriptionTokenState,
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
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockRefreshRepoLicenseIdentity: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
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

// Only the network-facing licence verbs are stubbed. `isDatastoreScopedId`
// stays REAL, so the identity this test feeds has to be one the licence writer
// would also accept.
vi.mock('../account/license.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../account/license.js')>()),
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  issueRepoLicense: mockIssueRepoLicense,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
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

const PARENT_GUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const FORK_GUID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const DATASTORE_ID = '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0';
const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';
const DEFAULT_MOUNT = '/mnt/rediacc';
const SEVEN_GIB = 7 * 1024 * 1024 * 1024;

/** The exact probe the executor should emit for one mount + guid. */
function expectedProbe(mount: string, guid: string): string {
  return `stat -c %s '${mount}/repositories/${guid}' 2>/dev/null || echo rediacc-size-unknown`;
}

/**
 * The DISTINCT `stat` commands that reached the machine.
 *
 * A provisioning verb probes twice — once for the pre-issuance and once for the
 * post-create identity refresh — and both must agree on the mount, so the set
 * is the interesting object. `probeCount()` keeps the repetition visible.
 */
function statCommands(): string[] {
  return [
    ...new Set(mockExec.mock.calls.map((c) => String(c[0])).filter((c) => c.startsWith('stat '))),
  ];
}

function probeCount(): number {
  return mockExec.mock.calls.map((c) => String(c[0])).filter((c) => c.startsWith('stat ')).length;
}

/** Every unmeasured-size warning, ignoring any unrelated chatter on the same channel. */
function sizeWarnings(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls
    .map((c) => String(c[0]))
    .filter((m) => m.includes('Could not measure the source repository image'));
}

/** Route the two remote reads this path makes: the size probe and the registry. */
function routeExec(statOutput: string): void {
  mockExec.mockImplementation((command: string) => {
    if (command.startsWith('stat ')) return Promise.resolve(statOutput);
    if (command.includes('datastore list --json')) {
      return Promise.resolve(JSON.stringify([{ name: 'tier1', datastoreId: DATASTORE_ID }]));
    }
    return Promise.resolve('');
  });
}

/**
 * A machine where the image exists on exactly ONE mount. Every other mount
 * answers with the sentinel, so a probe that looks in the wrong place cannot
 * accidentally read the right size — which is what makes the size assertion an
 * end-to-end control on the path, not just on the arithmetic.
 */
function routeExecImageAt(mount: string, statOutput: string): void {
  mockExec.mockImplementation((command: string) => {
    if (command.startsWith('stat ')) {
      return Promise.resolve(
        command.includes(`'${mount}/repositories/`) ? statOutput : 'rediacc-size-unknown\n'
      );
    }
    if (command.includes('datastore list --json')) {
      return Promise.resolve(JSON.stringify([{ name: 'tier1', datastoreId: DATASTORE_ID }]));
    }
    return Promise.resolve('');
  });
}

const forkOptions = {
  functionName: 'repository_fork',
  machineName: 'hostinger',
  params: { repository: 'app', tag: FORK_GUID, network_id: 7 },
  captureOutput: true,
};

/** The parent repo record, with or without a named-datastore placement. */
function parentRepo(placement?: { datastore: string } | { machine: string }) {
  return {
    repositoryGuid: PARENT_GUID,
    grandGuid: PARENT_GUID,
    tag: 'latest',
    ...(placement ? { placement } : {}),
  };
}

describe('repo-license size probe: which datastore it stats', () => {
  const savedSkipActivation = process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      sshPublicKey: 'PUBLIC_KEY',
      ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockListStorages.mockResolvedValue([]);
    mockListRepositories.mockResolvedValue([]);
    mockIssueRepoLicense.mockResolvedValue(true);
    mockRefreshRepoLicenseIdentity.mockResolvedValue(undefined);
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test' },
    });
    mockExecStreaming.mockResolvedValue(0);
    routeExec(`${SEVEN_GIB}\n`);
  });

  afterEach(() => {
    warnSpy.mockRestore();
    if (savedSkipActivation !== undefined) {
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION = savedSkipActivation;
    }
  });

  it('stats the NAMED datastore the parent is placed on, never the machine default', async () => {
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    const result = await localExecutorService.execute(forkOptions);

    expect(result.success).toBe(true);
    // Full-command equality, not `toContain`: any drift in the mount OR the
    // guid fails, which is what makes the mount-mutation control below bite.
    expect(statCommands()).toEqual([expectedProbe(NAMED_MOUNT, PARENT_GUID)]);
    // Both probes (pre-issuance and post-create refresh) ran, and they agreed.
    expect(probeCount()).toBe(2);
    // The bug, stated as an assertion: the default mount must never be probed
    // for a named-datastore repo.
    expect(statCommands().join('\n')).not.toContain(`${DEFAULT_MOUNT}/repositories/`);
  });

  it('sizes the fork licence from the parent image found on the named datastore', async () => {
    // The image exists ONLY on the named mount; the default mount answers the
    // sentinel. Reading 7 GB therefore proves the probe went to the right place.
    routeExecImageAt(NAMED_MOUNT, `${SEVEN_GIB}\n`);
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute(forkOptions);

    expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1);
    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({
      repositoryGuid: FORK_GUID,
      kind: 'fork',
      // 7 GiB measured, not the 1 GB floor the broken probe reported.
      requestedSizeGb: 7,
      datastoreId: DATASTORE_ID,
    });
    expect(sizeWarnings(warnSpy)).toEqual([]);
  });

  // CONTROL, direction 2: the same assertion applied to a repo with NO named
  // placement must produce the DEFAULT mount. A fix that hard-coded the named
  // mount would pass the test above and fail this one.
  it('keeps the machine default for a repo with no named-datastore placement', async () => {
    mockGetRepository.mockResolvedValue(parentRepo());

    const result = await localExecutorService.execute(forkOptions);

    expect(result.success).toBe(true);
    expect(statCommands()).toEqual([expectedProbe(DEFAULT_MOUNT, PARENT_GUID)]);
    expect(statCommands().join('\n')).not.toContain(NAMED_MOUNT);
    // No named placement means no registry lookup and no scoped identity.
    expect(mockIssueRepoLicense.mock.calls[0][2].datastoreId).toBeUndefined();
  });

  it('keeps the machine default for an explicit {machine} placement', async () => {
    mockGetRepository.mockResolvedValue(parentRepo({ machine: 'hostinger' }));

    await localExecutorService.execute(forkOptions);

    expect(statCommands()).toEqual([expectedProbe(DEFAULT_MOUNT, PARENT_GUID)]);
  });

  // CONTROL, direction 3: the machine's own datastore override still wins over
  // the compiled-in default when the repo declares no named datastore.
  it("honours the machine's datastore override for an unplaced repo", async () => {
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
      datastore: '/srv/pool',
    });
    mockGetRepository.mockResolvedValue(parentRepo());

    await localExecutorService.execute(forkOptions);

    expect(statCommands()).toEqual([expectedProbe('/srv/pool', PARENT_GUID)]);
  });

  // The mount-mutation control the campaign asks for, written as an assertion
  // rather than a comment: the expected string is the thing under test, so a
  // single wrong character in it must fail the comparison.
  it('the mount assertion is falsifiable: a mutated mount does not match', async () => {
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute(forkOptions);

    expect(statCommands()).not.toEqual([expectedProbe(`${NAMED_MOUNT}-mutated`, PARENT_GUID)]);
    expect(statCommands()).not.toEqual([expectedProbe(NAMED_MOUNT, FORK_GUID)]);
    expect(statCommands()).not.toEqual([expectedProbe(DEFAULT_MOUNT, PARENT_GUID)]);
  });
});

describe('repo-license size probe: a failed stat is not a measurement', () => {
  const savedSkipActivation = process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      sshPublicKey: 'PUBLIC_KEY',
      ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockListStorages.mockResolvedValue([]);
    mockListRepositories.mockResolvedValue([]);
    mockIssueRepoLicense.mockResolvedValue(true);
    mockRefreshRepoLicenseIdentity.mockResolvedValue(undefined);
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test' },
    });
    mockExecStreaming.mockResolvedValue(0);
  });

  afterEach(() => {
    warnSpy.mockRestore();
    if (savedSkipActivation !== undefined) {
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION = savedSkipActivation;
    }
  });

  it('says so on stderr when the source image could not be measured for a fork', async () => {
    routeExec('rediacc-size-unknown\n');
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute(forkOptions);

    // Falls back to the floor, but never silently.
    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 1 });
    const warnings = sizeWarnings(warnSpy);
    expect(warnings.length).toBeGreaterThan(0);
    expect(warnings[0]).toContain(`${NAMED_MOUNT}/repositories/${PARENT_GUID}`);
    expect(warnings[0]).toContain('1 GB minimum');
  });

  // CONTROL: `repository_create` probes a repo that does not exist yet BY
  // CONSTRUCTION, so an unanswerable stat is normal there and must stay quiet.
  // A fix that warned unconditionally would fail this.
  it('stays quiet for repository_create, whose target cannot exist yet', async () => {
    routeExec('rediacc-size-unknown\n');
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute({
      functionName: 'repository_create',
      machineName: 'hostinger',
      params: { repository: 'app', guid: PARENT_GUID, network_id: 7 },
      captureOutput: true,
    });

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 1 });
    expect(sizeWarnings(warnSpy)).toEqual([]);
  });

  // The sentinel is what makes the distinction expressible: under `|| echo 0`
  // this run and a genuine 0-byte image were the same bytes. A real zero is a
  // MEASUREMENT, so it still floors to 1 GB and still says nothing.
  it('treats a genuine zero-byte image as measured, not as a failed probe', async () => {
    routeExec('0\n');
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute(forkOptions);

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 1 });
    expect(sizeWarnings(warnSpy)).toEqual([]);
  });

  it('rounds a partial gigabyte up rather than down', async () => {
    routeExec(`${3 * 1024 * 1024 * 1024 + 1}\n`);
    mockGetRepository.mockResolvedValue(parentRepo({ datastore: 'tier1' }));

    await localExecutorService.execute(forkOptions);

    expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ requestedSizeGb: 4 });
  });
});
