import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetOutputFormat,
  mockOutputError,
  mockGetCommandName,
  mockGetWarnings,
  mockGetDurationMs,
} = vi.hoisted(() => ({
  mockGetOutputFormat: vi.fn(),
  mockOutputError: vi.fn(),
  mockGetCommandName: vi.fn(() => 'repo push'),
  mockGetWarnings: vi.fn(() => []),
  mockGetDurationMs: vi.fn(() => 42),
}));

vi.mock('../errors.js', async () => {
  const actual = await vi.importActual('../errors.js');
  return {
    ...actual,
    getOutputFormat: mockGetOutputFormat,
  };
});

vi.mock('../../services/output.js', () => ({
  outputService: {
    error: mockOutputError,
    getCommandName: mockGetCommandName,
    getWarnings: mockGetWarnings,
    getDurationMs: mockGetDurationMs,
  },
}));

const { renderLocalExecutionFailure } = await import('../local-execution-failures.js');

describe('renderLocalExecutionFailure', () => {
  const stdoutWrite = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);

  beforeEach(() => {
    vi.clearAllMocks();
    process.exitCode = undefined;
  });

  it('prints text failures in non-json output mode', () => {
    mockGetOutputFormat.mockReturnValue('table');

    renderLocalExecutionFailure(
      {
        error: 'repo license refresh required',
        errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
        exitCode: 10,
      },
      'fallback'
    );

    expect(mockOutputError).toHaveBeenCalledWith('repo license refresh required');
    expect(stdoutWrite).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(10);
  });

  it('prints structured failures in json output mode', () => {
    mockGetOutputFormat.mockReturnValue('json');

    renderLocalExecutionFailure(
      {
        error: 'repo license refresh required',
        errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
        errorGuidance: 'Run: rdc subscription refresh -m hostinger',
        exitCode: 10,
      },
      'fallback'
    );

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
