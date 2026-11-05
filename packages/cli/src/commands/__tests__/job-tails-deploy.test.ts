/**
 * PLAN-detached-jobs J4: the plain `repository_up` that follows `repo push` and `repo pull`, and `rdc run`'s result
 * handler, print their success line only for a finished job. A job handed back under `--background` is still running.
 * The executor is a recording fake; each site has a finished control.
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
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
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

const { postPushDeploy, postPullDeploy } = await import('../repo-backup.js');
const { handleExecutionResult } = await import('../shortcuts.js');

const FINISHED = { success: true, exitCode: 0, durationMs: 5, state: 'succeeded' as const };
const BACKGROUND = { success: true, exitCode: 0, durationMs: 0, state: 'running' as const };
const DETACHED_LOST = { ...BACKGROUND, success: false, exitCode: 130 };

const SITES = [
  {
    name: 'repo push deploy',
    run: () => postPushDeploy('r1', 'm1', {}),
    line: 'commands.repo.push.deployed',
  },
  {
    name: 'repo pull deploy',
    run: () => postPullDeploy('r1', 'm1', {}),
    line: 'commands.repo.pull.deployed',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe.each(SITES)('$name under --background', ({ run, line }) => {
  it('hands the ticket back: no success line, no failure render', async () => {
    mockExecute.mockResolvedValue(BACKGROUND);
    await run();

    expect(mockExecute).toHaveBeenCalledWith(
      expect.objectContaining({ functionName: 'repository_up' })
    );
    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockRender).not.toHaveBeenCalled();
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('a lost tail keeps the executor exit code and prints no success line', async () => {
    mockExecute.mockResolvedValue(DETACHED_LOST);
    await run();

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockRender).not.toHaveBeenCalled();
    expect(mockSetExitCode).toHaveBeenCalledWith(130);
  });

  it('control: a finished job prints the success line', async () => {
    mockExecute.mockResolvedValue(FINISHED);
    await run();

    expect(mockSuccess).toHaveBeenCalledWith(expect.stringContaining(line));
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });
});

describe('rdc run result handler', () => {
  it('a running job prints no completion line', () => {
    handleExecutionResult(BACKGROUND);

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockRender).not.toHaveBeenCalled();
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('a lost tail keeps the executor exit code', () => {
    handleExecutionResult(DETACHED_LOST);

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockSetExitCode).toHaveBeenCalledWith(130);
  });

  it('control: a result without a state, and a finished one, still print completion', () => {
    handleExecutionResult({ success: true, durationMs: 3 });
    handleExecutionResult(FINISHED);

    expect(mockSuccess).toHaveBeenCalledTimes(2);
  });
});
