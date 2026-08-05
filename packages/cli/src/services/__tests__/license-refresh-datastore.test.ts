/**
 * `refreshRepoLicenseIdentity` must measure the repo image where the repo
 * actually lives (#74, sibling of the local-executor size probe).
 *
 * WHAT WAS ACTUALLY BROKEN, and what was not. The function derives ONE path,
 * `machine.datastore ?? /mnt/rediacc`, and feeds it to two consumers:
 *
 *   - the licence SCAN — NOT a bug. `licenseScanCommand` passes
 *     `--all-datastores`, and renet's `licenseScanTargets`
 *     (cmd/renet/license_scope.go) then walks every ATTACHED named datastore on
 *     top of that path, tagging each entry with its own datastoreId and
 *     datastorePath. A named-datastore repo is found, priced and identified.
 *   - the SIZE probe — a real bug, reached only when the scan cannot price the
 *     repo (no licence installed yet, or a scan that failed). It stat'd the
 *     machine default for a repo at /mnt/rediacc-ds/<d>/repositories/<guid>,
 *     the `else echo 0` turned the miss into 0 bytes, and the reissue asked for
 *     the 1 GB floor as though it had measured it.
 *
 * `rdc subscription refresh --repo <ref>` is the live path: it is the only
 * caller that passes no requestedSizeGb, so it is the only one that reaches the
 * probe. These assertions read the exact commands that reached the machine.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';

const MACHINE_ID = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';
const DATASTORE_ID = '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0';
const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';
const DEFAULT_MOUNT = '/mnt/rediacc';
const SEVEN_GIB = 7 * 1024 * 1024 * 1024;

vi.mock('node:fs/promises', () => ({
  readFile: vi.fn().mockResolvedValue('client-machine-001\n'),
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: 'http://localhost:4800',
    token: { token: 'rdt_test' },
  })),
}));

const mockAccountServerFetch = vi.fn();
vi.mock('../account/account-client.js', () => ({
  accountServerFetch: (...args: unknown[]) => mockAccountServerFetch(...args),
}));

vi.mock('../config/config-resources.js', () => ({
  configService: { listRepositories: vi.fn().mockResolvedValue([]) },
}));

vi.mock('../telemetry/telemetry.js', () => ({
  telemetryService: { setUserContext: vi.fn(), trackError: vi.fn() },
}));

const { outputService } = await import('../core/output.js');
const { refreshRepoLicenseIdentity } = await import('../account/license.js');

const machine: MachineConfig = {
  machineName: 'hostinger',
  ip: '127.0.0.1',
  user: 'root',
  port: 22,
};

/** One scan entry, with control over whether it prices the repo. */
function scanEntry(extra: Record<string, unknown>) {
  return { repositoryGuid: REPO_GUID, luksUuid: 'luks-uuid-0001', ...extra };
}

/**
 * A fake machine. `scan` is what `repository license-scan` returns; `images`
 * maps a datastore mount to the byte size found there — any mount not listed
 * answers the probe's unknown sentinel, which is what makes a probe of the
 * WRONG mount observably different from a probe of the right one.
 */
function createSftp(scan: unknown[], images: Record<string, number> = {}) {
  const exec = vi.fn((command: string) => {
    if (command.includes('machine-id')) return Promise.resolve(`${MACHINE_ID}\n`);
    if (command.includes('license-scan')) return Promise.resolve(JSON.stringify(scan));
    if (command.includes('license-status')) return Promise.resolve('[]');
    if (command.includes('stat -c %s')) {
      const mount = Object.keys(images).find((m) => command.includes(`"${m}/repositories/`));
      return Promise.resolve(mount === undefined ? 'rediacc-size-unknown\n' : `${images[mount]}\n`);
    }
    return Promise.resolve('');
  });
  const sftp = {
    exec,
    execStreaming: vi.fn().mockResolvedValue(0),
    connect: vi.fn(),
    close: vi.fn(),
  };
  return { sftp: sftp as unknown as SFTPClient, exec };
}

/** Every size-probe command that reached the machine, deduplicated. */
function probes(exec: ReturnType<typeof vi.fn>): string[] {
  return [
    ...new Set(exec.mock.calls.map((c) => String(c[0])).filter((c) => c.includes('stat -c %s'))),
  ];
}

/** The exact probe the code should emit for one mount. */
function expectedProbe(mount: string): string {
  const p = `${mount}/repositories/${REPO_GUID}`;
  return `sudo sh -lc 'if [ -e "${p}" ]; then stat -c %s "${p}" 2>/dev/null || echo rediacc-size-unknown; else echo rediacc-size-unknown; fi'`;
}

/** The requestedSizeGb that reached the account server. */
function issuedSizeGb(): unknown {
  const call = mockAccountServerFetch.mock.calls[0] as [string, { body: Record<string, unknown> }];
  return call[1].body.requestedSizeGb;
}

function sizeWarnings(spy: { mock: { calls: unknown[][] } }): string[] {
  return spy.mock.calls.map((c) => String(c[0])).filter((m) => m.includes('Could not measure'));
}

describe('refreshRepoLicenseIdentity: which datastore the size probe measures', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});
    mockAccountServerFetch.mockResolvedValue({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });
  });

  afterEach(() => warnSpy.mockRestore());

  // The scan half, asserted rather than assumed: this is the flag that makes a
  // named-datastore repo visible, and it is why the scan was never the bug.
  it('scans every attached datastore, not only the machine default', async () => {
    const { sftp, exec } = createSftp([scanEntry({ requestedSizeGb: 4 })]);

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    const scan = exec.mock.calls.map((c) => String(c[0])).find((c) => c.includes('license-scan'));
    expect(scan).toBe(
      `sudo /usr/bin/renet repository license-scan --datastore '${DEFAULT_MOUNT}' --all-datastores --output json`
    );
  });

  it('does not probe at all when the scan already priced the repo', async () => {
    const { sftp, exec } = createSftp([scanEntry({ requestedSizeGb: 4 })]);

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([]);
    expect(issuedSizeGb()).toBe(4);
  });

  it("measures the datastore the MACHINE reports for the repo, not the machine's default", async () => {
    // The scan found the repo but could not price it; it does know where it lives.
    const { sftp, exec } = createSftp(
      [scanEntry({ datastoreId: DATASTORE_ID, datastorePath: NAMED_MOUNT })],
      { [NAMED_MOUNT]: SEVEN_GIB }
    );

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([expectedProbe(NAMED_MOUNT)]);
    expect(probes(exec).join('\n')).not.toContain(`${DEFAULT_MOUNT}/repositories/`);
    expect(issuedSizeGb()).toBe(7);
    expect(sizeWarnings(warnSpy)).toEqual([]);
  });

  it("falls back to the caller's recorded placement when the scan cannot answer", async () => {
    // Empty scan: no licence installed yet. This is the `rdc subscription
    // refresh --repo` first-issuance shape, and the only thing that knows where
    // the repo lives is the placement the caller recorded.
    const { sftp, exec } = createSftp([], { [NAMED_MOUNT]: SEVEN_GIB });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: NAMED_MOUNT },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([expectedProbe(NAMED_MOUNT)]);
    expect(issuedSizeGb()).toBe(7);
  });

  // CONTROL, direction 2: no placement and no scan answer must leave the
  // machine default in place. A fix that hard-coded a named mount fails here.
  it('keeps the machine default when neither the scan nor the caller names a datastore', async () => {
    const { sftp, exec } = createSftp([], { [DEFAULT_MOUNT]: SEVEN_GIB });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([expectedProbe(DEFAULT_MOUNT)]);
    expect(issuedSizeGb()).toBe(7);
  });

  // CONTROL, direction 3: the machine's own datastore override still wins over
  // the compiled-in default.
  it("honours the machine's datastore override", async () => {
    const { sftp, exec } = createSftp([], { '/srv/pool': SEVEN_GIB });

    await refreshRepoLicenseIdentity(
      { ...machine, datastore: '/srv/pool' },
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([expectedProbe('/srv/pool')]);
  });

  // The machine's own answer outranks the caller's, because the scan reads
  // where the repo actually is and the config only says where it was put.
  it('prefers the scan-reported mount over the caller-supplied one when they disagree', async () => {
    const { sftp, exec } = createSftp(
      [scanEntry({ datastoreId: DATASTORE_ID, datastorePath: NAMED_MOUNT })],
      { [NAMED_MOUNT]: SEVEN_GIB, '/mnt/rediacc-ds/stale': 1024 }
    );

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: '/mnt/rediacc-ds/stale' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).toEqual([expectedProbe(NAMED_MOUNT)]);
    expect(issuedSizeGb()).toBe(7);
  });

  // The mount-mutation control, written as an assertion: a single wrong
  // character in the expected command must not match.
  it('the mount assertion is falsifiable: a mutated mount does not match', async () => {
    const { sftp, exec } = createSftp([scanEntry({ datastorePath: NAMED_MOUNT })], {
      [NAMED_MOUNT]: SEVEN_GIB,
    });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand' },
      '/usr/bin/renet',
      sftp
    );

    expect(probes(exec)).not.toEqual([expectedProbe(`${NAMED_MOUNT}-mutated`)]);
    expect(probes(exec)).not.toEqual([expectedProbe(DEFAULT_MOUNT)]);
  });

  it('never forwards the client-side mount hint to the account server', async () => {
    const { sftp } = createSftp([], { [NAMED_MOUNT]: SEVEN_GIB });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: NAMED_MOUNT },
      '/usr/bin/renet',
      sftp
    );

    const body = (mockAccountServerFetch.mock.calls[0]?.[1] as { body: Record<string, unknown> })
      .body;
    expect(body).not.toHaveProperty('datastoreMount');
  });
});

describe('refreshRepoLicenseIdentity: a failed probe is not a measurement', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});
    mockAccountServerFetch.mockResolvedValue({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });
  });

  afterEach(() => warnSpy.mockRestore());

  it('says so, and floors, when no candidate mount could be measured', async () => {
    // No image anywhere: every probe answers the sentinel.
    const { sftp } = createSftp([]);

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: NAMED_MOUNT },
      '/usr/bin/renet',
      sftp
    );

    expect(issuedSizeGb()).toBe(1);
    const warnings = sizeWarnings(warnSpy);
    expect(warnings.length).toBe(1);
    expect(warnings[0]).toContain(NAMED_MOUNT);
    expect(warnings[0]).toContain(REPO_GUID);
  });

  // The sentinel is what makes this expressible: under `else echo 0` a missing
  // image and a real zero were the same bytes. A real zero is a MEASUREMENT,
  // so it floors to 1 GB and says nothing.
  it('treats a genuine zero-byte image as measured, not as a failed probe', async () => {
    const { sftp } = createSftp([], { [NAMED_MOUNT]: 0 });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: NAMED_MOUNT },
      '/usr/bin/renet',
      sftp
    );

    expect(issuedSizeGb()).toBe(1);
    expect(sizeWarnings(warnSpy)).toEqual([]);
  });

  it('rounds a partial gigabyte up rather than down', async () => {
    const { sftp } = createSftp([], { [NAMED_MOUNT]: 3 * 1024 * 1024 * 1024 + 1 });

    await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', datastoreMount: NAMED_MOUNT },
      '/usr/bin/renet',
      sftp
    );

    expect(issuedSizeGb()).toBe(4);
  });
});
