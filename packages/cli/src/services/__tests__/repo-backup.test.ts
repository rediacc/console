import { beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub — returns key:params so assertions can match on key fragments
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetSubscriptionTokenState = vi.hoisted(() => vi.fn());

vi.mock('../../services/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/local-executor.js', () => ({
  localExecutorService: { execute: mockExecute },
}));

const mockError = vi.hoisted(() => vi.fn());
vi.mock('../../services/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: mockError,
  },
}));

vi.mock('../../services/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));

// Suppress spinner/timeline
vi.mock('../../utils/spinner.js', () => ({
  startSpinner: vi.fn().mockReturnValue(null),
  stopSpinner: vi.fn(),
}));
vi.mock('../../utils/timeline.js', () => ({
  getActiveLabel: () => '...',
  getDoneLabel: () => 'done',
  formatStepDuration: () => '0s',
}));

const { postPushDeploy } = await import('../../commands/repo-backup.js');

describe('postPushDeploy pre-flight token check', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fails fast when subscription token is not ready', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    await postPushDeploy('myrepo', 'target-machine', {});

    expect(mockExecute).not.toHaveBeenCalled();
    expect(mockError).toHaveBeenCalledTimes(1);
    const errorMsg: string = mockError.mock.calls[0][0] as string;
    expect(errorMsg).toContain('errors.license.preflightTokenNotReady');
    expect(errorMsg).toContain('target-machine');
  });

  it('proceeds to deploy when subscription token is ready', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'rdt_test' },
    });
    mockExecute.mockResolvedValue({ success: true, allSteps: [], steps: [] });

    await postPushDeploy('myrepo', 'target-machine', {});

    expect(mockExecute).toHaveBeenCalledTimes(1);
    expect(mockError).not.toHaveBeenCalled();
  });
});
