import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

const mockExecuteRepoFunction = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: mockExecuteRepoFunction,
}));

const mockResolveRepoRef = vi.hoisted(() => vi.fn());
const mockResolveRepoRefLocal = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: mockResolveRepoRef,
  resolveRepoRefLocal: mockResolveRepoRefLocal,
}));

const mockRecordBackupRun = vi.hoisted(() => vi.fn());
vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: mockRecordBackupRun,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mockGetRepository },
}));

const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
    // real-ish format: join a marker so assertions can read rows back
    format: (rows: unknown) => JSON.stringify(rows),
  },
}));

vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: () => Promise.resolve({}),
  createGuidResolver: () => (guid: string) => (guid === 'lin-1' ? 'shop' : guid),
}));

vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { registerBackupStorageCommands } = await import('../backup-storage.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const backup = program.command('backup');
  registerBackupStorageCommands(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  process.exitCode = 0;
});

describe('backup usage', () => {
  it('fetches usage through the account tunnel and renders per-lineage rows', async () => {
    mockAccountServerFetch.mockResolvedValue({
      subscriptionId: 's1',
      storedBytes: 1024,
      chunkCount: 3,
      usageAdjustment: 0,
      leasedBytes: 0,
      activeLeases: 0,
      usedBytes: 1024,
      quotaBytes: 10 * 1024 ** 3,
      overLimit: false,
      retentionStartedAt: null,
      lineages: [
        {
          lineageGuid: 'lin-1',
          storedBytes: 1024,
          chunkCount: 3,
          logicalBytes: 2048,
          updatedAt: '2026-08-14T10:00:00.000Z',
        },
      ],
    });

    await run(['usage']);

    expect(mockAccountServerFetch).toHaveBeenCalledWith('/account/api/v1/backups/usage');
    // The rendered table (format() -> JSON here) resolves the lineage GUID to a name.
    const printed = mockPrint.mock.calls.map((c) => String(c[0])).join('\n');
    expect(printed).toContain('shop');
    expect(printed).toContain('lin-1');
  });
});

describe('backup verify', () => {
  beforeEach(() => {
    mockResolveRepoRef.mockResolvedValue({ repoKey: 'shop', machineName: 'm1', tag: 'latest' });
  });

  it('maps --deep to level=full and records a verified run on success', async () => {
    mockExecuteRepoFunction.mockResolvedValue({ success: true });
    await run(['verify', 'shop', '--deep']);

    const call = mockExecuteRepoFunction.mock.calls[0];
    expect(call[0]).toBe('backup_verify');
    expect(call[3]).toEqual({ level: 'full' });
    expect(mockRecordBackupRun).toHaveBeenCalledWith('shop', {
      kind: 'verify',
      status: 'verified',
    });
    expect(process.exitCode).not.toBe(1);
  });

  it('defaults to level=spot and surfaces a mismatch as exit 1', async () => {
    mockExecuteRepoFunction.mockResolvedValue({ success: false });
    await run(['verify', 'shop']);

    expect(mockExecuteRepoFunction.mock.calls[0][3]).toEqual({ level: 'spot' });
    expect(mockRecordBackupRun).toHaveBeenCalledWith('shop', {
      kind: 'verify',
      status: 'mismatch',
    });
    expect(process.exitCode).toBe(1);
  });
});

describe('backup manifests', () => {
  it('scopes to a repo lineage when a ref is given', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ manifests: [] });

    await run(['manifests', 'shop']);

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/manifests?lineage=lin-1'
    );
  });

  it('lists all lineages when no ref is given', async () => {
    mockAccountServerFetch.mockResolvedValue({ manifests: [] });
    await run(['manifests']);
    expect(mockAccountServerFetch).toHaveBeenCalledWith('/account/api/v1/backups/manifests');
  });
});

/**
 * `backup retention` — the operator's ONLY handle on which snapshots the server
 * DELETES, and it had no behavioural test at all until the testing-surface
 * audit named the gap. `check:ci-retention-knob-parity` compares spellings
 * across four layers; it says nothing about what the command actually sends.
 *
 * The failure mode is silent: a wrong flag-to-field mapping widens what
 * `retentionPolicySweep` deletes, the operator typed a correct command, and the
 * snapshots they asked to keep are gone.
 */
describe('backup retention', () => {
  it('shows the policy the SERVER is enforcing, scoped to the lineage', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'shop']);

    // Read back from the server, never printed from local config: what is shown
    // has to be what is enforced, on the surface that decides what is deleted.
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/retention?lineage=lin-1'
    );
  });

  it('set sends the declared knobs by their WIRE names, as numbers', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'set', 'shop', '--keep-last', '7', '--keep-monthly', '12']);

    const [url, init] = mockAccountServerFetch.mock.calls[0] as [
      string,
      { method: string; body: string },
    ];
    expect(url).toBe('/account/api/v1/backups/retention');
    expect(init.method).toBe('PUT');
    const body = JSON.parse(init.body) as Record<string, unknown>;
    // THE DEFECT: a flag mapped to the wrong field, or sent as a STRING. Zod
    // would reject a string, but a mis-mapped field is accepted and silently
    // changes which snapshots survive.
    expect(body).toEqual({ lineageGuid: 'lin-1', keepLast: 7, keepMonthly: 12 });
  });

  it('set REFUSES an empty knob set instead of silently clearing the policy', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });

    // The server REPLACES every knob rather than merging, so a knob-less PUT
    // would wipe the policy while reading like a no-op. That is data loss by
    // omission, so it must be refused rather than sent.
    await expect(run(['retention', 'set', 'shop'])).rejects.toThrow();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('set refuses a non-integer knob rather than coercing it', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });

    await expect(run(['retention', 'set', 'shop', '--keep-last', 'seven'])).rejects.toThrow();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('clear sends a DELETE scoped to the lineage', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'clear', 'shop']);

    const [url, init] = mockAccountServerFetch.mock.calls[0] as [string, { method: string }];
    // THE DEFECT: an UNSCOPED delete. Without the lineage this clears the
    // policy for a repository the operator did not name.
    expect(url).toBe('/account/api/v1/backups/retention?lineage=lin-1');
    expect(init.method).toBe('DELETE');
  });
});
