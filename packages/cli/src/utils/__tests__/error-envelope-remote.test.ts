import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// outputService is what the error renderer writes to. We capture every call so the assertions can read what the user/agent would have seen.
const stdoutChunks: string[] = [];
const stderrChunks: string[] = [];

const mockOutputService = {
  getCommandName: vi.fn(() => 'test cmd'),
  getWarnings: vi.fn(() => []),
  getDurationMs: vi.fn(() => 0),
  error: vi.fn((s: string) => {
    stderrChunks.push(s);
  }),
};

vi.mock('../../services/core/output.js', () => ({ outputService: mockOutputService }));

// Telemetry is a no-op in tests (the real service awaits flushes that hang).
vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: {
    trackError: vi.fn(),
    shutdown: vi.fn().mockResolvedValue(undefined),
  },
}));

const { handleError, setOutputFormat } = await import('../errors.js');
const { ERROR_CODES } = await import('../../types/errors.js');

// process.exit is called inside handleError. Stub it to throw so tests can observe the renderer's output without aborting the test runner.
const exitMock = vi.spyOn(process, 'exit').mockImplementation(() => {
  throw new Error('process.exit called');
});

const stdoutWriteMock = vi
  .spyOn(process.stdout, 'write')
  .mockImplementation((chunk: string | Uint8Array) => {
    stdoutChunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
    return true;
  });

/**
 * The remote-config adapter's errors carry a specific code, not GENERAL_ERROR. The eu live test (2026-09-26) showed
 * a device whose key a CEK rotation had outdated told "re-enroll" under GENERAL_ERROR, which an agent cannot tell
 * from a crash.
 */
function named(name: string, message: string): Error {
  const error = new Error(message);
  error.name = name;
  return error;
}

function envelopeFor(error: Error) {
  stdoutChunks.length = 0;
  setOutputFormat('json');
  expect(() => handleError(error)).toThrow(/process\.exit/);
  return JSON.parse(stdoutChunks.join('')).errors[0];
}

describe('error envelope: remote-config errors', () => {
  beforeEach(() => {
    exitMock.mockClear();
    stdoutWriteMock.mockClear();
  });

  afterEach(() => {
    setOutputFormat('table');
  });

  it('a stale key slot is AUTH_REQUIRED, not retryable, and its guidance is its own remedy', () => {
    const got = envelopeFor(
      named('RemoteStaleSlotError', 'Re-enroll with: rdc config remote enable')
    );
    expect(got.code).toBe(ERROR_CODES.AUTH_REQUIRED);
    expect(got.retryable).toBe(false);
    expect(got.guidance).toContain('rdc config remote enable');
  });

  it('an unreachable server is NETWORK_ERROR and retryable', () => {
    const got = envelopeFor(named('RemoteUnreachableError', 'Config server x is unreachable'));
    expect(got.code).toBe(ERROR_CODES.NETWORK_ERROR);
    expect(got.retryable).toBe(true);
  });

  it('CONTROL: an unrelated error is still GENERAL_ERROR', () => {
    expect(envelopeFor(new Error('plain failure')).code).toBe(ERROR_CODES.GENERAL_ERROR);
  });
});
