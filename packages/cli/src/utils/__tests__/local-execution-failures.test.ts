import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetOutputFormat,
  mockOutputError,
  mockGetCommandName,
  mockGetWarnings,
  mockGetDurationMs,
  mockIsAgent,
} = vi.hoisted(() => ({
  mockGetOutputFormat: vi.fn(),
  mockOutputError: vi.fn(),
  mockGetCommandName: vi.fn(() => 'repo push'),
  mockGetWarnings: vi.fn(() => []),
  mockGetDurationMs: vi.fn(() => 42),
  mockIsAgent: vi.fn(() => false),
}));

vi.mock('../errors.js', async () => {
  const actual = await vi.importActual('../errors.js');
  return {
    ...actual,
    getOutputFormat: mockGetOutputFormat,
  };
});

vi.mock('../agent-guard.js', () => ({
  isAgentEnvironment: mockIsAgent,
}));

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
    mockIsAgent.mockReturnValue(false);

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

  it('calls process.exit() in agent mode for json failures', () => {
    mockGetOutputFormat.mockReturnValue('json');
    mockIsAgent.mockReturnValue(true);
    const mockExit = vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('exit');
    });

    expect(() =>
      renderLocalExecutionFailure({ error: 'fail', errorCode: 'TEST', exitCode: 10 }, 'fallback')
    ).toThrow('exit');

    expect(mockExit).toHaveBeenCalledWith(10);
    mockExit.mockRestore();
  });

  it('calls process.exit() in agent mode for text failures', () => {
    mockGetOutputFormat.mockReturnValue('table');
    mockIsAgent.mockReturnValue(true);
    const mockExit = vi.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('exit');
    });

    expect(() =>
      renderLocalExecutionFailure({ error: 'fail', errorCode: 'TEST', exitCode: 5 }, 'fallback')
    ).toThrow('exit');

    expect(mockExit).toHaveBeenCalledWith(5);
    mockExit.mockRestore();
  });

  it('does NOT call process.exit() in non-agent mode', () => {
    mockGetOutputFormat.mockReturnValue('json');
    mockIsAgent.mockReturnValue(false);
    const mockExit = vi.spyOn(process, 'exit');

    renderLocalExecutionFailure({ error: 'fail', errorCode: 'TEST', exitCode: 10 }, 'fallback');

    expect(mockExit).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(10);
    mockExit.mockRestore();
  });

  it('prints a stderr tail under text failures when it adds information', () => {
    mockGetOutputFormat.mockReturnValue('table');
    const stderrWrite = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);

    renderLocalExecutionFailure(
      {
        error: 'renet exited with code 1',
        exitCode: 1,
        stderr: 'time=... level=info msg="starting"\nError: repository abc is not mounted\n',
      },
      'fallback'
    );

    expect(mockOutputError).toHaveBeenCalledWith('renet exited with code 1');
    const written = stderrWrite.mock.calls.map((c) => String(c[0])).join('');
    expect(written).toContain('repository abc is not mounted');
    stderrWrite.mockRestore();
  });

  it('does not repeat a single-line tail already contained in the error', () => {
    mockGetOutputFormat.mockReturnValue('table');
    const stderrWrite = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);

    renderLocalExecutionFailure(
      {
        error: 'renet exited with code 1: repository abc is not mounted',
        exitCode: 1,
        stderr: 'Error: repository abc is not mounted',
      },
      'fallback'
    );

    expect(stderrWrite).not.toHaveBeenCalled();
    stderrWrite.mockRestore();
  });

  it('skips the tail entirely when the executor already echoed the output', () => {
    mockGetOutputFormat.mockReturnValue('table');
    const stderrWrite = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);

    renderLocalExecutionFailure(
      {
        error: 'renet exited with code 1',
        exitCode: 1,
        stderr: 'line one\nline two\nError: something broke',
        outputEchoed: true,
      },
      'fallback'
    );

    expect(stderrWrite).not.toHaveBeenCalled();
    stderrWrite.mockRestore();
  });
});
