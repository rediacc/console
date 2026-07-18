/**
 * Exit-code table + CliExitError tests (spec/03 §1). Covers `errorToExitCode`,
 * the CliExitError constructor (code -> exit code), and the `handleError`
 * round-trip that surfaces a refusal-class error through the JSON envelope with
 * both its exit code and its `errors[].code`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const stdoutChunks: string[] = [];

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    getCommandName: vi.fn(() => 'test cmd'),
    getWarnings: vi.fn(() => []),
    getDurationMs: vi.fn(() => 0),
    error: vi.fn(),
  },
}));

vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: {
    trackError: vi.fn(),
    shutdown: vi.fn().mockResolvedValue(undefined),
  },
}));

const { handleError, setOutputFormat } = await import('../errors.js');
const { CliExitError, ambiguous, stateMismatch, notFound } = await import('../cli-exit-error.js');
const { ERROR_CODES, errorToExitCode } = await import('../../types/errors.js');
const { EXIT_CODES } = await import('../../types/index.js');

const exitMock = vi.spyOn(process, 'exit').mockImplementation(() => {
  throw new Error('process.exit called');
});

const stdoutWriteMock = vi
  .spyOn(process.stdout, 'write')
  .mockImplementation((chunk: string | Uint8Array) => {
    stdoutChunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
    return true;
  });

describe('EXIT_CODES — new P4 refusal classes', () => {
  it('assigns 11-15 and 130 without renumbering 0-9', () => {
    expect(EXIT_CODES.AMBIGUOUS).toBe(11);
    expect(EXIT_CODES.STATE_MISMATCH).toBe(12);
    expect(EXIT_CODES.HEALTH_GATE_FAILED).toBe(13);
    expect(EXIT_CODES.INFRA_FAILED).toBe(14);
    expect(EXIT_CODES.BUSY).toBe(15);
    expect(EXIT_CODES.DETACHED).toBe(130);
    // Untouched legacy codes.
    expect(EXIT_CODES.SUCCESS).toBe(0);
    expect(EXIT_CODES.INVALID_ARGUMENTS).toBe(2);
    expect(EXIT_CODES.NOT_FOUND).toBe(5);
    expect(EXIT_CODES.RATE_LIMITED).toBe(9);
  });
});

describe('errorToExitCode', () => {
  it('maps each new refusal-class code to its exit code', () => {
    expect(errorToExitCode(ERROR_CODES.AMBIGUOUS)).toBe(11);
    expect(errorToExitCode(ERROR_CODES.STATE_MISMATCH)).toBe(12);
    expect(errorToExitCode(ERROR_CODES.HEALTH_GATE_FAILED)).toBe(13);
    expect(errorToExitCode(ERROR_CODES.INFRA_FAILED)).toBe(14);
    expect(errorToExitCode(ERROR_CODES.BUSY)).toBe(15);
    expect(errorToExitCode(ERROR_CODES.DETACHED)).toBe(130);
  });

  it('maps the legacy codes to their historical exit codes', () => {
    expect(errorToExitCode(ERROR_CODES.VALIDATION_ERROR)).toBe(2);
    expect(errorToExitCode(ERROR_CODES.INVALID_REQUEST)).toBe(2);
    expect(errorToExitCode(ERROR_CODES.PRECONDITION_MISMATCH)).toBe(2);
    expect(errorToExitCode(ERROR_CODES.AUTH_REQUIRED)).toBe(3);
    expect(errorToExitCode(ERROR_CODES.PERMISSION_DENIED)).toBe(4);
    expect(errorToExitCode(ERROR_CODES.NOT_FOUND)).toBe(5);
    expect(errorToExitCode(ERROR_CODES.NETWORK_ERROR)).toBe(6);
    expect(errorToExitCode(ERROR_CODES.SERVER_ERROR)).toBe(7);
  });

  it('falls back to GENERAL_ERROR for an unknown code', () => {
    expect(errorToExitCode('NOT_A_REAL_CODE')).toBe(1);
  });
});

describe('CliExitError', () => {
  it('derives its exit code from its code', () => {
    expect(new CliExitError(ERROR_CODES.BUSY, 'busy').exitCode).toBe(15);
    expect(ambiguous('a').exitCode).toBe(11);
    expect(stateMismatch('b').exitCode).toBe(12);
    expect(notFound('c').exitCode).toBe(5);
  });

  it('honors an explicit exit-code override', () => {
    const err = new CliExitError(ERROR_CODES.DETACHED, 'x', { exitCode: 42 });
    expect(err.exitCode).toBe(42);
  });

  it('carries details and next through to the fields', () => {
    const err = ambiguous('pick one', { details: ['a', 'b'], retryable: false });
    expect(err.details).toEqual(['a', 'b']);
    expect(err.retryable).toBe(false);
  });
});

describe('handleError round-trip (JSON envelope)', () => {
  beforeEach(() => {
    stdoutChunks.length = 0;
    exitMock.mockClear();
    stdoutWriteMock.mockClear();
    setOutputFormat('json');
  });

  afterEach(() => {
    setOutputFormat('table');
  });

  it('surfaces a CliExitError with its exit code and mirrored code', () => {
    expect(() => handleError(stateMismatch('config disagrees'))).toThrow(/process\.exit/);
    expect(exitMock).toHaveBeenCalledWith(12);

    const env = JSON.parse(stdoutChunks.join(''));
    expect(env.success).toBe(false);
    expect(env.errors[0].code).toBe('STATE_MISMATCH');
    expect(env.errors[0].message).toBe('config disagrees');
  });

  it('passes details through the envelope', () => {
    expect(() =>
      handleError(notFound('ghost missing', { details: ['known: shop, mail'] }))
    ).toThrow(/process\.exit/);
    expect(exitMock).toHaveBeenCalledWith(5);
    const env = JSON.parse(stdoutChunks.join(''));
    expect(env.errors[0].details).toEqual(['known: shop, mail']);
  });
});
