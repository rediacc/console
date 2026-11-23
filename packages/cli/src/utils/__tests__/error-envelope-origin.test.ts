import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const stdoutChunks: string[] = [];

const mockOutputService = {
  getCommandName: vi.fn(() => 'test cmd'),
  getWarnings: vi.fn(() => []),
  getDurationMs: vi.fn(() => 0),
  error: vi.fn(),
};

vi.mock('../../services/core/output.js', () => ({ outputService: mockOutputService }));
vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: {
    trackError: vi.fn(),
    shutdown: vi.fn().mockResolvedValue(undefined),
  },
}));

const { handleError, setOutputFormat } = await import('../errors.js');
const { CliExitError } = await import('../cli-exit-error.js');
const { ERROR_CODES } = await import('../../types/errors.js');

vi.spyOn(process, 'exit').mockImplementation(() => {
  throw new Error('process.exit called');
});
vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
  stdoutChunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
  return true;
});

function envelopeOf(error: unknown): { errors: Record<string, unknown>[] } {
  stdoutChunks.length = 0;
  setOutputFormat('json');
  expect(() => handleError(error)).toThrow(/process\.exit/);
  return JSON.parse(stdoutChunks.join(''));
}

describe('error envelope origin', () => {
  beforeEach(() => {
    vi.stubEnv('REDIACC_FEEDBACK_HINT', '0');
  });

  afterEach(() => {
    setOutputFormat('table');
    vi.unstubAllEnvs();
  });

  it('carries the origin of the envelope code beside code', () => {
    const env = envelopeOf(new CliExitError(ERROR_CODES.NOT_FOUND, 'missing'));
    expect(env.errors[0].origin).toBe('user');
    expect(Object.keys(env.errors[0]).slice(0, 2)).toEqual(['code', 'origin']);
  });

  it('carries the origin of a named code over its envelope code', () => {
    // An SSH connect failure rides GENERAL_ERROR (environment) and names SSH_AUTH_FAILED (user).
    const error = Object.assign(new Error('Permission denied'), {
      name: 'SshConnectError',
      exitCode: 1,
      errorCode: 'SSH_AUTH_FAILED',
    });
    const env = envelopeOf(error);
    expect(env.errors[0].code).toBe(ERROR_CODES.GENERAL_ERROR);
    expect(env.errors[0].errorCode).toBe('SSH_AUTH_FAILED');
    expect(env.errors[0].origin).toBe('user');
  });

  it('omits origin for a code no table knows (control)', () => {
    const env = envelopeOf(new CliExitError('RENET_REPORTED_THIS', 'forwarded'));
    expect(env.errors[0]).not.toHaveProperty('origin');
  });
});
