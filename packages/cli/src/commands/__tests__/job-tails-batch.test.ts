/**
 * PLAN-detached-jobs J4: `repo up --all` and `repo down --all` hand back a running job under `--background`. A handed-back job
 * prints no completion line (it has not completed) and carries the executor's exit code; a finished one prints it. The
 * executor is a recording fake.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoTarget: () => Promise.resolve({ machineName: 'm1' }),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployAllRepoKeys: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { listRepositories: vi.fn().mockResolvedValue([]) },
}));
const mockRender = vi.hoisted(() => vi.fn());
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRender,
}));
const mockSuccess = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: mockSuccess,
    warn: vi.fn(),
    error: vi.fn(),
    print: vi.fn(),
    getCommandName: () => undefined,
  },
}));
const mockSetExitCode = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/request-context.js')>()),
  setExitCode: mockSetExitCode,
}));

const { handleUpAll, handleDownAll } = await import('../repo-batch-utils.js');

const FINISHED = { success: true, exitCode: 0, durationMs: 5, state: 'succeeded' as const };
const BACKGROUND = { success: true, exitCode: 0, durationMs: 0, state: 'running' as const };
const DETACHED_LOST = { ...BACKGROUND, success: false, exitCode: 130 };
const FAILED = { success: false, exitCode: 1, durationMs: 5, state: 'failed' as const };

const VERBS = [
  { name: 'up --all', run: () => handleUpAll({ machine: 'm1' }), fn: 'repository_up_all' },
  {
    name: 'down --all',
    run: () => handleDownAll({ machine: 'm1', yes: true }),
    fn: 'repository_down_all',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe.each(VERBS)('repo $name under --background', ({ run, fn }) => {
  it('hands the ticket back: no completion line, no failure render', async () => {
    mockExecute.mockResolvedValue(BACKGROUND);
    await run();

    expect(mockExecute).toHaveBeenCalledWith(expect.objectContaining({ functionName: fn }));
    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockRender).not.toHaveBeenCalled();
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('a lost tail keeps the executor exit code and still prints no completion', async () => {
    mockExecute.mockResolvedValue(DETACHED_LOST);
    await run();

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockSetExitCode).toHaveBeenCalledExactlyOnceWith(130);
  });

  it('control: a finished job prints its completion line', async () => {
    mockExecute.mockResolvedValue(FINISHED);
    await run();

    expect(mockSuccess).toHaveBeenCalledTimes(1);
    expect(mockRender).not.toHaveBeenCalled();
  });

  it('control: a failed job renders its failure and prints no completion', async () => {
    mockExecute.mockResolvedValue(FAILED);
    await run();

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockRender).toHaveBeenCalledTimes(1);
  });
});
