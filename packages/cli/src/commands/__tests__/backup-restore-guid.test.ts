/**
 * `rdc backup restore <src> --as <name> --at <snapshot>` must register the
 * restored repo under a FRESH GUID (box E1).
 *
 * It reused the source's. The restore target is the vault repo's GUID, so the
 * image landed at `repositories/<source-guid>`: on the source's own machine
 * that wrote the snapshot over the live source image. renet now refuses a
 * restore onto an existing image unless `--replace <guid>` names it on purpose,
 * so with a reused GUID every same-machine `--as` restore was refused, safely
 * but wrongly. A fresh GUID is a fresh path and a fresh credential map slot.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const SOURCE_GUID = vi.hoisted(() => '0a1b2c3d-0000-4000-8000-00000000a11c');
const GRAND_GUID = vi.hoisted(() => '0a1b2c3d-0000-4000-8000-00000000974d');
const SOURCE_CREDENTIAL = vi.hoisted(() => 'source-credential-not-random');
const SNAPSHOT = '20260815T041418Z-c1e8778364245163';

const mockAddRepository = vi.hoisted(() => vi.fn());
const mockSource = vi.hoisted(() => ({
  current: {
    repositoryGuid: '',
    tag: 'latest',
    credential: '',
  } as { repositoryGuid: string; tag: string; credential: string; grandGuid?: string },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ state: {}, resources: { repositories: {} } }),
    addRepository: mockAddRepository,
    removeRepository: vi.fn().mockResolvedValue(undefined),
    allocateNetworkId: vi.fn().mockResolvedValue(4242),
    getRepository: (ref: string) => Promise.resolve(ref === 'src' ? mockSource.current : undefined),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/backup/dr-nudge.js', () => ({
  warnIfConfigStorageUnenrolled: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/addressing/ref-parser.js', () => ({
  parseRef: (raw: string) => ({ place: raw.split(':')[0], name: raw.split(':')[1] ?? 'src' }),
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../repo-backup-list.js', () => ({
  fetchBackupList: vi.fn().mockResolvedValue([]),
  renderBackupList: vi.fn(),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/agent-guard.js', () => ({
  assertAgentRepoCreate: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../backup-ops.js', () => ({ registerBackupOpsCommands: vi.fn() }));
vi.mock('../backup-strategy.js', () => ({ registerBackupStrategyCommands: vi.fn() }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
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

const { registerBackupCommands } = await import('../backup.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

function registered(): { repositoryGuid: string; grandGuid?: string; credential: string } {
  expect(mockAddRepository).toHaveBeenCalledTimes(1);
  return mockAddRepository.mock.calls[0][1];
}

function restoreCall() {
  return mockExecute.mock.calls.find((c) => c[0].functionName === 'backup_restore')?.[0];
}

const SAME_MACHINE_RESTORE = ['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--at', SNAPSHOT];

beforeEach(() => {
  vi.clearAllMocks();
  mockSource.current = {
    repositoryGuid: SOURCE_GUID,
    tag: 'latest',
    credential: SOURCE_CREDENTIAL,
  };
  mockAddRepository.mockResolvedValue(undefined);
  mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
});

describe('backup restore --as --at mints a fresh GUID (E1)', () => {
  it('registers the restored repo under a new GUID, never the source GUID', async () => {
    await run(SAME_MACHINE_RESTORE);

    const record = registered();
    // THE DEFECT: repositoryGuid === SOURCE_GUID, so renet's restore target
    // was the source's own image path.
    expect(record.repositoryGuid).not.toBe(SOURCE_GUID);
    expect(record.repositoryGuid).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });

  it('refuses a restore with no --as, since the default target is the source name itself', async () => {
    // The source must exist in the config to be restored, so without --as the target collides with it. No record is registered and no GUID is minted.
    await expect(run(['restore', 'm1:src', '-m', 'm1', '--at', SNAPSHOT])).rejects.toThrow(
      /targetExists/
    );
    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  it('two restores of one source get two distinct GUIDs', async () => {
    await run(SAME_MACHINE_RESTORE);
    await run(['restore', 'm1:src', '--as', 'copy2', '-m', 'm1', '--at', SNAPSHOT]);

    const [a, b] = mockAddRepository.mock.calls.map((c) => c[1].repositoryGuid);
    expect(a).not.toBe(b);
  });

  it('inherits the source credential under the new GUID (a new map entry)', async () => {
    await run(SAME_MACHINE_RESTORE);

    // The image is the source's ciphertext; only the source passphrase unlocks it.
    expect(registered().credential).toBe(SOURCE_CREDENTIAL);
  });

  it('carries a grand source lineage as grandGuid and restores from it', async () => {
    await run(SAME_MACHINE_RESTORE);

    expect(registered().grandGuid).toBe(SOURCE_GUID);
    expect(restoreCall()?.params).toMatchObject({
      repository: 'copy',
      lineage: SOURCE_GUID,
      at: SNAPSHOT,
    });
  });

  it("carries a fork source's grand GUID as the lineage, not the fork's GUID", async () => {
    mockSource.current = { ...mockSource.current, grandGuid: GRAND_GUID };
    await run(SAME_MACHINE_RESTORE);

    expect(registered().grandGuid).toBe(GRAND_GUID);
    expect(restoreCall()?.params.lineage).toBe(GRAND_GUID);
  });

  it('does not pass a --replace to renet (a restore never overwrites on purpose)', async () => {
    await run(SAME_MACHINE_RESTORE);

    expect(restoreCall()?.params).not.toHaveProperty('replace');
  });
});
