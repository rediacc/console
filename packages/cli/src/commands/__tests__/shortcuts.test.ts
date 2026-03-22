import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetOutputFormat,
  mockOutputSuccess,
  mockOutputError,
  mockGetCommandName,
  mockGetWarnings,
  mockGetDurationMs,
} = vi.hoisted(() => ({
  mockGetOutputFormat: vi.fn(),
  mockOutputSuccess: vi.fn(),
  mockOutputError: vi.fn(),
  mockGetCommandName: vi.fn(() => 'run'),
  mockGetWarnings: vi.fn(() => []),
  mockGetDurationMs: vi.fn(() => 12),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, string | number>) =>
    vars && 'duration' in vars ? `${key}:${vars.duration}` : key,
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    success: mockOutputSuccess,
    error: mockOutputError,
    getCommandName: mockGetCommandName,
    getWarnings: mockGetWarnings,
    getDurationMs: mockGetDurationMs,
  },
}));

vi.mock('../../utils/errors.js', async () => {
  const actual = await vi.importActual('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: mockGetOutputFormat,
  };
});

vi.mock('../../providers/index.js', () => ({
  getStateProvider: vi.fn(),
}));

vi.mock('../../services/config-resources.js', () => ({
  configService: {},
}));

vi.mock('../../services/local-executor.js', () => ({
  localExecutorService: {},
}));

const { handleExecutionResult } = await import('../shortcuts.js');

describe('handleExecutionResult', () => {
  const stdoutWrite = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);

  beforeEach(() => {
    vi.clearAllMocks();
    process.exitCode = undefined;
  });

  it('prints a structured json failure envelope for repo-license failures', () => {
    mockGetOutputFormat.mockReturnValue('json');

    handleExecutionResult({
      success: false,
      error: 'repo license refresh required',
      errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
      errorGuidance: 'Run: rdc subscription refresh -m hostinger',
      exitCode: 10,
    });

    expect(stdoutWrite).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(stdoutWrite.mock.calls[0][0] as string) as {
      success: boolean;
      errors: { code: string; message: string; guidance?: string }[];
    };
    expect(payload.success).toBe(false);
    expect(payload.errors[0]).toEqual({
      code: 'REPO_LICENSE_REFRESH_REQUIRED',
      message: 'repo license refresh required',
      guidance: 'Run: rdc subscription refresh -m hostinger',
      retryable: false,
    });
    expect(process.exitCode).toBe(10);
  });
});
