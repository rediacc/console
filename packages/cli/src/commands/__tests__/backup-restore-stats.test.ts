/**
 * `rdc backup restore --at` summary (plan L6): the numbers renet measured (cells known and punched,
 * the seed it started from and what probing cost) reach the table summary and the JSON output.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockFormat = vi.hoisted(() => ({ value: 'table' }));
const SOURCE_GUID = vi.hoisted(() => '0a1b2c3d-0000-4000-8000-00000000a11c');
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
    getOutputFormat: () => mockFormat.value,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { outputService } = await import('../../services/core/output.js');
const { registerBackupCommands } = await import('../backup.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const STATS = {
  guid: 'g',
  status: 'restored',
  cellsTotal: 100,
  cellsZero: 20,
  cellsKnown: 60,
  cellsPunched: 3,
  chunksWanted: 80,
  chunksFetched: 12,
  chunksReused: 68,
  bytesFetched: 50331648,
  cellBytes: 4194304,
  seed: 'sibling',
  seedGuid: 'seed-guid-1',
  seedsSkipped: ['other-guid: key mismatch'],
  seedProbeBytes: 8192,
};

const SAME_MACHINE_RESTORE = ['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--at', SNAPSHOT];

beforeEach(() => {
  vi.clearAllMocks();
  mockSource.current = {
    repositoryGuid: SOURCE_GUID,
    tag: 'latest',
    credential: SOURCE_CREDENTIAL,
  };
  mockAddRepository.mockResolvedValue(undefined);
  mockFormat.value = 'table';
});

describe('backup restore --at reports what the restore moved (L6)', () => {
  it('asks the executor to capture stdout, where renet writes the record', async () => {
    mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
    await run(SAME_MACHINE_RESTORE);
    const call = mockExecute.mock.calls.find((c) => c[0].functionName === 'backup_restore')?.[0];
    expect(call.captureOutput).toBe(true);
  });

  it('summarises fetched, reused, known and punched cells, and the seed, in the table summary', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      stdout: `noise\n${JSON.stringify(STATS)}\n`,
      durationMs: 1,
    });
    await run(SAME_MACHINE_RESTORE);

    const infos = vi.mocked(outputService.info).mock.calls.map((c) => String(c[0]));
    const stats = infos.find((m) => m.startsWith('commands.backup.restore.stats:'));
    expect(stats).toBeDefined();
    const params = JSON.parse(String(stats).slice('commands.backup.restore.stats:'.length));
    expect(params).toMatchObject({ fetched: 12, reused: 68, known: 60, punched: 3 });
    const seed = infos.find((m) => m.startsWith('commands.backup.restore.statsSeed:'));
    expect(String(seed)).toContain('seed-guid-1');
    expect(infos.some((m) => m.includes('other-guid: key mismatch'))).toBe(true);
  });

  it('prints the whole record, every renet stat included, in json', async () => {
    mockFormat.value = 'json';
    mockExecute.mockResolvedValue({ success: true, stdout: JSON.stringify(STATS), durationMs: 1 });
    await run(SAME_MACHINE_RESTORE);

    expect(outputService.print).toHaveBeenCalledTimes(1);
    const [printed, format] = vi.mocked(outputService.print).mock.calls[0] as [
      Record<string, unknown>,
      string,
    ];
    expect(format).toBe('json');
    for (const key of [
      'cellsKnown',
      'cellsPunched',
      'seed',
      'seedGuid',
      'seedsSkipped',
      'seedProbeBytes',
      'cellBytes',
    ]) {
      expect(printed).toHaveProperty(key, STATS[key as keyof typeof STATS]);
    }
  });

  it('still reports success when the record is absent (an older renet)', async () => {
    mockExecute.mockResolvedValue({ success: true, stdout: 'no json here', durationMs: 1 });
    await run(SAME_MACHINE_RESTORE);
    const infos = vi.mocked(outputService.info).mock.calls.map((c) => String(c[0]));
    expect(infos.some((m) => m.startsWith('commands.backup.restore.stats'))).toBe(false);
    expect(outputService.success).toHaveBeenCalled();
  });
});
