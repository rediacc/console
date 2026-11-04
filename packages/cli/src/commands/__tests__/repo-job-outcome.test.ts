import { beforeEach, describe, expect, it, vi } from 'vitest';

const { warn, setExitCode, renderFailure } = vi.hoisted(() => ({
  warn: vi.fn(),
  setExitCode: vi.fn(),
  renderFailure: vi.fn(),
}));

vi.mock('../../services/core/output.js', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  outputService: { warn },
}));
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  setExitCode,
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: renderFailure,
}));

const { settleRepoJob } = await import('../repo-job-outcome.js');

const steps = (failed: string[]) => ({ heldElsewhere: [], failed, deferred: [] });
const finished = (success: boolean, failed: string[] = []) =>
  ({
    kind: 'finished',
    result: { success },
    jobId: 'j1',
    ticket: {},
    steps: steps(failed),
  }) as never;

describe('settleRepoJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true for a finished job with every step done, and touches nothing', () => {
    expect(settleRepoJob('repo trim', finished(true), 'failed')).toBe(true);
    expect(warn).not.toHaveBeenCalled();
    expect(setExitCode).not.toHaveBeenCalled();
  });

  it('returns false, names the step and fails the command when a step did not finish', () => {
    expect(settleRepoJob('repo trim', finished(true, ['renderTrim']), 'failed')).toBe(false);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('renderTrim'));
    expect(setExitCode).toHaveBeenCalledWith(1);
  });

  it('returns false and renders the failure for a failed job', () => {
    expect(settleRepoJob('repo trim', finished(false), 'trim failed')).toBe(false);
    expect(renderFailure).toHaveBeenCalledWith({ success: false }, 'trim failed');
  });
});
