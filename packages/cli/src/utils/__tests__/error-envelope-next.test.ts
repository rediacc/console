import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// outputService is what the error renderer writes to. We capture every call
// so the assertions can read what the user/agent would have seen.
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

vi.mock('../../services/output.js', () => ({ outputService: mockOutputService }));

// Telemetry is a no-op in tests (the real service awaits flushes that hang).
vi.mock('../../services/telemetry.js', () => ({
  telemetryService: {
    trackError: vi.fn(),
    shutdown: vi.fn().mockResolvedValue(undefined),
  },
}));

const { handleError, setOutputFormat, PreconditionValidationError } = await import('../errors.js');
const { ERROR_CODES } = await import('../../types/errors.js');
import type { NextAction } from '../../types/errors.js';

const sampleNext: NextAction = {
  summary: 'Provide the current value or acknowledge rotation',
  options: [
    {
      description: 'Re-read current digest, then retry with --current',
      run: 'rdc repo secret get --name mail --key STRIPE',
    },
    {
      description: 'Skip the precondition (rotation)',
      run: 'rdc repo secret set --name mail --key STRIPE --value v --rotate-secret',
    },
  ],
};

// process.exit is called inside handleError. Stub it to throw so tests can
// observe the renderer's output without aborting the test runner.
const exitMock = vi.spyOn(process, 'exit').mockImplementation(() => {
  throw new Error('process.exit called');
});

const stdoutWriteMock = vi
  .spyOn(process.stdout, 'write')
  .mockImplementation((chunk: string | Uint8Array) => {
    stdoutChunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
    return true;
  });

describe('error envelope — next field', () => {
  beforeEach(() => {
    stdoutChunks.length = 0;
    stderrChunks.length = 0;
    exitMock.mockClear();
    stdoutWriteMock.mockClear();
  });

  afterEach(() => {
    setOutputFormat('table');
  });

  it('JSON output includes errors[0].next when error carries one', () => {
    setOutputFormat('json');
    expect(() =>
      handleError(new PreconditionValidationError('digest mismatch', sampleNext))
    ).toThrow(/process\.exit/);

    const json = stdoutChunks.join('');
    const env = JSON.parse(json);
    expect(env.success).toBe(false);
    expect(env.errors).toHaveLength(1);
    expect(env.errors[0].code).toBe(ERROR_CODES.PRECONDITION_MISMATCH);
    expect(env.errors[0].next).toEqual(sampleNext);
  });

  it('JSON output omits next when error has none', () => {
    setOutputFormat('json');
    expect(() => handleError(new Error('plain failure'))).toThrow(/process\.exit/);

    const env = JSON.parse(stdoutChunks.join(''));
    expect(env.errors[0].code).toBe(ERROR_CODES.GENERAL_ERROR);
    expect(env.errors[0]).not.toHaveProperty('next');
  });

  it('TTY output renders "What to do:" with bulleted options', () => {
    setOutputFormat('table');
    expect(() =>
      handleError(new PreconditionValidationError('digest mismatch', sampleNext))
    ).toThrow(/process\.exit/);

    const out = stderrChunks.join('\n');
    expect(out).toContain('Error: digest mismatch');
    expect(out).toContain('What to do: Provide the current value or acknowledge rotation');
    expect(out).toContain('Re-read current digest, then retry with --current');
    expect(out).toContain('rdc repo secret get --name mail --key STRIPE');
    expect(out).toContain('Skip the precondition (rotation)');
    expect(out).toContain('--rotate-secret');
  });

  it('TTY output without next renders only the error line', () => {
    setOutputFormat('table');
    expect(() => handleError(new Error('plain failure'))).toThrow(/process\.exit/);

    const out = stderrChunks.join('\n');
    expect(out).toContain('Error: plain failure');
    expect(out).not.toContain('What to do:');
  });

  it('PreconditionValidationError carries a custom code when provided', () => {
    setOutputFormat('json');
    expect(() =>
      handleError(new PreconditionValidationError('boom', sampleNext, 'CUSTOM_CODE'))
    ).toThrow(/process\.exit/);

    const env = JSON.parse(stdoutChunks.join(''));
    expect(env.errors[0].code).toBe('CUSTOM_CODE');
  });
});
