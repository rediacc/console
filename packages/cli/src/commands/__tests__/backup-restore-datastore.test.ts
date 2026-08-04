/**
 * `rdc backup restore --datastore <name>` must actually restore INTO that
 * datastore (#74).
 *
 * The flag existed and was honoured only halfway: it was used to look up which
 * machine currently holds the datastore, and then dropped. The pull ran with no
 * datastore declared, so renet wrote the image into that machine's DEFAULT pool
 * — the operator named a datastore and the data landed somewhere else — and no
 * placement was recorded either, so every later verb on the restored repo
 * derived the default too and the divergence was permanent.
 *
 * Both halves are pinned here: the transfer declares the mount, and the birth
 * record carries the placement (the same field `repo create` writes).
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: mockGetCurrent,
    addRepository: mockAddRepository,
    removeRepository: vi.fn().mockResolvedValue(undefined),
    allocateNetworkId: vi.fn().mockResolvedValue(4242),
    // The SOURCE exists; the restore TARGET must not (restore refuses to overwrite).
    getRepository: (ref: string) =>
      Promise.resolve(ref === 'src' ? { repositoryGuid: 'guid-src', tag: 'latest' } : undefined),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../services/addressing/ref-parser.js', () => ({
  parseRef: (raw: string) => ({ place: raw.split(':')[0], name: raw.split(':')[1] ?? 'src' }),
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../repo-backup-list.js', () => ({
  fetchBackupList: vi
    .fn()
    .mockResolvedValue([{ name: 'src', repositoryGuid: 'guid-src', tag: 'latest' }]),
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

const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

function callFor(fn: string) {
  return mockExecute.mock.calls.find((c) => c[0].functionName === fn)?.[0];
}

beforeEach(() => {
  vi.clearAllMocks();
  // `tier1` is attached to m1 — the hint the restore already used to pick a machine.
  mockGetCurrent.mockResolvedValue({
    state: { datastores: { tier1: { attachedTo: 'm1' } } },
    resources: { repositories: {} },
  });
  mockAddRepository.mockResolvedValue(undefined);
  mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
});

describe('backup restore honours --datastore (#74)', () => {
  it('pulls INTO the named datastore, not the machine default', async () => {
    await run(['restore', 'store1:src', '--as', 'copy', '--datastore', 'tier1', '-y']);

    expect(callFor('backup_pull')?.datastore).toBe(NAMED_MOUNT);
  });

  it('records the placement so later verbs derive the same mount', async () => {
    await run(['restore', 'store1:src', '--as', 'copy', '--datastore', 'tier1', '-y']);

    expect(mockAddRepository).toHaveBeenCalled();
    const [, config] = mockAddRepository.mock.calls[0];
    expect(config.placement).toEqual({ datastore: 'tier1' });
  });

  it('deploys --up into the same mount the pull wrote', async () => {
    await run(['restore', 'store1:src', '--as', 'copy', '--datastore', 'tier1', '--up', '-y']);

    expect(callFor('repository_up')?.datastore).toBe(NAMED_MOUNT);
  });

  it('records a machine placement and declares nothing for --machine', async () => {
    await run(['restore', 'store1:src', '--as', 'copy', '--machine', 'm1', '-y']);

    expect(callFor('backup_pull')?.datastore).toBeUndefined();
    const [, config] = mockAddRepository.mock.calls[0];
    expect(config.placement).toEqual({ machine: 'm1' });
  });
});
