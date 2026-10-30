import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
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

const outputFormat = vi.hoisted(() => ({ value: 'table' }));

vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => outputFormat.value,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { outputService } = await import('../../services/core/output.js');
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
  outputFormat.value = 'table';
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

  /** The step plan the verify job carries (PLAN-detached-jobs J4): its records and the verdict print run once the job is seen finished. */
  const plannedSteps = (call: unknown[]) =>
    (call[4] as { job: { steps: { name: string; params: Record<string, unknown> }[] } }).job.steps;

  it('maps --deep to level=full and plans the verdict and a verified run on the job ticket', async () => {
    mockExecuteRepoFunction.mockResolvedValue({ success: true });
    await run(['verify', 'shop', '--deep']);

    const call = mockExecuteRepoFunction.mock.calls[0];
    expect(call[0]).toBe('backup_verify');
    expect(call[3]).toEqual({ level: 'full' });
    const steps = plannedSteps(call);
    expect(steps.map((s) => s.name)).toEqual([
      'reportVerifyVerdict',
      'recordBackupRun',
      'recordBackupRunFailed',
    ]);
    expect(steps[1].params).toEqual({ repo: 'shop', kind: 'verify', status: 'verified' });
    // Nothing is recorded or printed outside the job's steps.
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
    expect(mockPrint).not.toHaveBeenCalled();
    expect(process.exitCode).not.toBe(1);
  });

  it('defaults to level=spot and leaves a mismatch to the rendered failure, printing nothing more', async () => {
    // The real executor renders the failure envelope and sets the exit code; verify must add no second document.
    mockExecuteRepoFunction.mockImplementation(() => {
      process.exitCode = 1;
      return Promise.resolve({ success: false });
    });
    await run(['verify', 'shop']);

    expect(mockPrint).not.toHaveBeenCalled();

    const call = mockExecuteRepoFunction.mock.calls[0];
    expect(call[3]).toEqual({ level: 'spot' });
    expect(plannedSteps(call)[2].params).toEqual({
      repo: 'shop',
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

  const entry = (over: Record<string, unknown>) => ({
    snapshotId: 'snap-aaaaaaaaaaaa',
    lineageGuid: 'lin-1',
    streamId: 's-1',
    cellSizeBytes: 1048576,
    totalBytes: 2147483648,
    addedBytes: 1048576,
    addedChunkCount: 3,
    createdAt: '2026-10-01T10:00:00.000Z',
    ...over,
  });

  it('renders newest first with repo name, short parent, humanized sizes and index', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        entry({
          snapshotId: '20261001T100000Z-aaaaaaaabbbbbbbb',
          createdAt: '2026-10-01T10:00:00Z',
        }),
        entry({
          snapshotId: '20261002T100000Z-ccccccccdddddddd',
          lineageGuid: 'lin-9',
          parentSnapshotId: '20261001T100000Z-aaaaaaaabbbbbbbb',
          hasIndex: true,
          createdAt: '2026-10-02T10:00:00Z',
        }),
      ],
    });
    await run(['manifests']);
    const rows = JSON.parse(mockPrint.mock.calls[0]?.[0] as string);
    expect(rows.map((r: { id: string }) => r.id)).toEqual(['cccccccc', 'aaaaaaaa']);
    expect(rows[0]).toMatchObject({
      repo: 'lin-9'.slice(0, 8),
      parent: 'aaaaaaaa',
      snapshot: '2026-10-02 10:00:00',
      index: 'yes',
      added: '1M / 3',
    });
    expect(rows[1]).toMatchObject({ repo: 'shop', parent: '-', index: 'no', total: '2G' });
  });

  it('orders mixed fractional and whole-second timestamps by time', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        entry({ snapshotId: 'a-aaaaaaaa', createdAt: '2026-10-01T10:00:00.500Z' }),
        entry({ snapshotId: 'b-bbbbbbbb', createdAt: '2026-10-01T10:00:00Z' }),
        entry({ snapshotId: 'c-cccccccc', createdAt: '2026-10-01T10:00:01Z' }),
      ],
    });
    await run(['manifests']);
    const rows = JSON.parse(mockPrint.mock.calls[0]?.[0] as string);
    expect(rows.map((r: { id: string }) => r.id)).toEqual(['cccccccc', 'aaaaaaaa', 'bbbbbbbb']);
  });

  it('json keeps every wire field, adds repo (full GUID never truncated, null when unknown) and sorts newest first', async () => {
    outputFormat.value = 'json';
    mockAccountServerFetch.mockResolvedValue({
      truncated: false,
      manifests: [
        entry({ snapshotId: 'old-1', createdAt: '2026-10-01T10:00:00Z' }),
        entry({
          snapshotId: 'new-2',
          lineageGuid: 'lineage-unknown-0123456789',
          createdAt: '2026-10-02T10:00:00Z',
        }),
      ],
    });
    await run(['manifests']);
    const [payload, format] = mockPrint.mock.calls[0] as [Record<string, unknown>, string];
    expect(format).toBe('json');
    expect(payload.truncated).toBe(false);
    const manifests = payload.manifests as Record<string, unknown>[];
    expect(manifests.map((m) => m.snapshotId)).toEqual(['new-2', 'old-1']);
    expect(manifests[0]).toMatchObject({ repo: null, lineageGuid: 'lineage-unknown-0123456789' });
    expect(manifests[1]).toMatchObject({ repo: 'shop', streamId: 's-1', totalBytes: 2147483648 });
  });
});

/**
 * `backup retention`, the operator's ONLY handle on which snapshots the server
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
    mockAccountServerFetch.mockResolvedValue({ policies: [], streams: [] });

    await run(['retention', 'shop']);

    // Read back from the server, never printed from local config: what is shown has to be what is enforced, on the surface that decides what is deleted.
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/retention?lineage=lin-1'
    );
  });

  it('names the effective policy and where it came from (F5)', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    const knobs = {
      keepLast: 3,
      keepHourly: null,
      keepDaily: 7,
      keepWeekly: null,
      keepMonthly: null,
      keepYearly: null,
    };
    mockAccountServerFetch.mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('/retention/preview')
          ? {
              lineageGuid: 'lin-1',
              policySource: 'plan',
              streams: [{ streamId: 's-1', policySource: 'plan', policy: knobs }],
              deleted: [],
              keptSnapshots: 4,
              freedBytes: 0,
              freedChunks: 0,
            }
          : { policies: [] }
      )
    );

    await run(['retention', 'shop']);

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/retention/preview?lineage=lin-1'
    );
    const infos = vi.mocked(outputService.info).mock.calls.map((c) => String(c[0]));
    expect(infos.join('\n')).toContain('commands.backup.retention.effective');
    expect(infos.join('\n')).toContain('commands.backup.retention.source.plan');
    // The per-stream rows carry the same source and the knob counts.
    const printed = mockPrint.mock.calls.map((c) => String(c[0])).join('\n');
    expect(printed).toContain('"stream":"s-1"');
    expect(printed).toContain('"daily":7');
  });

  it('retention preview lists the snapshots the next sweep deletes and the bytes freed (F6)', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({
      lineageGuid: 'lin-1',
      policySource: 'default',
      streams: [],
      deleted: [{ snapshotId: 'snap-old', streamId: 's-1', createdAt: '2026-01-01T00:00:00.000Z' }],
      keptSnapshots: 7,
      freedBytes: 4096,
      freedChunks: 1,
    });

    await run(['retention', 'preview', 'shop']);

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/retention/preview?lineage=lin-1'
    );
    expect(mockPrint.mock.calls.map((c) => String(c[0])).join('\n')).toContain('snap-old');
    const infos = vi.mocked(outputService.info).mock.calls.map((c) => String(c[0]));
    expect(infos.join('\n')).toContain('commands.backup.retention.preview.summary');
  });

  it('set --stream declares the policy for that stream alone (F1)', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'set', 'shop', '--keep-daily', '3', '--stream', 's-1']);

    // accountServerFetch serializes the body itself, so the command passes the object.
    const [, init] = mockAccountServerFetch.mock.calls[0] as [string, { body: unknown }];
    expect(init.body).toEqual({ lineageGuid: 'lin-1', streamId: 's-1', keepDaily: 3 });
  });

  it('clear --stream scopes the delete to that stream', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'clear', 'shop', '--stream', 's-1']);

    expect(mockAccountServerFetch.mock.calls[0][0]).toBe(
      '/account/api/v1/backups/retention?lineage=lin-1&stream=s-1'
    );
  });

  it('set sends the declared knobs by their WIRE names, as numbers', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValue({ policies: [] });

    await run(['retention', 'set', 'shop', '--keep-last', '7', '--keep-monthly', '12']);

    const [url, init] = mockAccountServerFetch.mock.calls[0] as [
      string,
      { method: string; body: unknown },
    ];
    expect(url).toBe('/account/api/v1/backups/retention');
    expect(init.method).toBe('PUT');
    const body = init.body as Record<string, unknown>;
    // THE DEFECT: a flag mapped to the wrong field, or sent as a STRING. Zod would reject a string, but a mis-mapped field is accepted and silently changes which snapshots survive.
    expect(body).toEqual({ lineageGuid: 'lin-1', keepLast: 7, keepMonthly: 12 });
  });

  it('set REFUSES an empty knob set instead of silently clearing the policy', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });

    // The server REPLACES every knob rather than merging, so a knob-less PUT would wipe the policy while reading like a no-op. That is data loss by omission, so it must be refused rather than sent.
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
    // THE DEFECT: an UNSCOPED delete. Without the lineage this clears the policy for a repository the operator did not name.
    expect(url).toBe('/account/api/v1/backups/retention?lineage=lin-1');
    expect(init.method).toBe('DELETE');
  });
});

/**
 * `backup snapshots delete <repo> <id>` (plan F10): the manual delete the quota error's "prune old
 * snapshots" points at. The id is checked against the named repository's history first, so an id
 * from another repository never reaches the delete route.
 */
describe('backup snapshots delete', () => {
  const history = {
    manifests: [{ snapshotId: 'snap-1', lineageGuid: 'lin-1', streamId: 's-1', createdAt: 'x' }],
  };

  it('deletes through the account route once the id is in the repository history', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch
      .mockResolvedValueOnce(history)
      .mockResolvedValueOnce({ deleted: ['snap-1'] });

    await run(['snapshots', 'delete', 'shop', 'snap-1']);

    expect(mockAccountServerFetch.mock.calls[0][0]).toBe(
      '/account/api/v1/backups/manifests?lineage=lin-1'
    );
    const [url, init] = mockAccountServerFetch.mock.calls[1] as [string, { method: string }];
    expect(url).toBe('/account/api/v1/backups/snapshots/snap-1');
    expect(init.method).toBe('DELETE');
  });

  it('refuses an id that is not in the named repository, without calling the delete route', async () => {
    mockResolveRepoRefLocal.mockResolvedValue({ repoKey: 'shop', name: 'shop', tag: 'latest' });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-1', grandGuid: 'lin-1' });
    mockAccountServerFetch.mockResolvedValueOnce(history);

    await expect(run(['snapshots', 'delete', 'shop', 'snap-other'])).rejects.toThrow(
      'commands.backup.snapshots.delete.notInRepo'
    );
    expect(mockAccountServerFetch).toHaveBeenCalledTimes(1);
  });
});
