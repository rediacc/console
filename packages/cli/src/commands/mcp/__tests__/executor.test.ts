import { afterEach, describe, expect, it, vi } from 'vitest';
import { executeRdcCommand, resolveRdcBinary } from '../executor.js';

// Mock child_process.execFile
const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

function makeEnvelope(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    success: true,
    command: 'machine query server-1',
    data: { name: 'server-1', status: 'running' },
    errors: null,
    warnings: [],
    metrics: { duration_ms: 142 },
    ...overrides,
  });
}

// Simulate promisified execFile: the mock receives (command, args, options, callback)
function setupExecFile(result: { stdout?: string; stderr?: string; error?: ExecError | null }) {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) => {
      if (result.error) {
        const err = result.error;
        (err as Record<string, unknown>).stdout = result.stdout ?? '';
        (err as Record<string, unknown>).stderr = result.stderr ?? '';
        callback(err);
      } else {
        callback(null, { stdout: result.stdout ?? '', stderr: result.stderr ?? '' });
      }
    }
  );
}

interface ExecError extends Error {
  stdout?: string;
  stderr?: string;
  killed?: boolean;
  code?: string | number;
}

function makeExecError(overrides: Partial<ExecError> = {}): ExecError {
  const err = new Error(overrides.message ?? 'Command failed') as ExecError;
  Object.assign(err, overrides);
  return err;
}

afterEach(() => {
  vi.clearAllMocks();
});

const baseOptions = { defaultTimeoutMs: 120_000 };

describe('executeRdcCommand', () => {
  it('parses a successful JSON envelope', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    const result = await executeRdcCommand(['machine', 'info', 'server-1'], baseOptions);

    expect(result.success).toBe(true);
    expect(result.command).toBe('machine query server-1');
    expect(result.data).toEqual({ name: 'server-1', status: 'running' });
    expect(result.errors).toBeNull();
    expect(result.duration_ms).toBe(142);
  });

  it('returns success with null data for empty stdout', async () => {
    setupExecFile({ stdout: '' });

    const result = await executeRdcCommand(['config', 'repositories'], baseOptions);

    expect(result.success).toBe(true);
    expect(result.data).toBeNull();
  });

  it('returns success with null data for whitespace-only stdout', async () => {
    setupExecFile({ stdout: '   \n  \n' });

    const result = await executeRdcCommand(['config', 'repositories'], baseOptions);

    expect(result.success).toBe(true);
    expect(result.data).toBeNull();
  });

  it('preserves warnings from the envelope', async () => {
    setupExecFile({
      stdout: makeEnvelope({ warnings: ['disk usage above 90%', 'certificate expires soon'] }),
    });

    const result = await executeRdcCommand(['machine', 'health', 'prod'], baseOptions);

    expect(result.success).toBe(true);
    expect(result.warnings).toEqual(['disk usage above 90%', 'certificate expires soon']);
  });

  it('parses a failed command that returns JSON on stdout', async () => {
    const envelope = makeEnvelope({
      success: false,
      errors: [{ code: 'NOT_FOUND', message: 'Machine not found' }],
    });

    setupExecFile({
      stdout: envelope,
      error: makeExecError({ code: 5 }),
    });

    const result = await executeRdcCommand(['machine', 'info', 'bad'], baseOptions);

    expect(result.success).toBe(false);
    expect(result.errors).toEqual([{ code: 'NOT_FOUND', message: 'Machine not found' }]);
  });

  it('returns TIMEOUT error when command is killed', async () => {
    setupExecFile({
      error: makeExecError({ killed: true, message: 'killed' }),
    });

    const result = await executeRdcCommand(['machine', 'health', 'slow'], {
      defaultTimeoutMs: 5000,
    });

    expect(result.success).toBe(false);
    expect(result.errors).toEqual([{ code: 'TIMEOUT', message: 'Command timed out after 5000ms' }]);
    expect(result.duration_ms).toBe(5000);
  });

  it('returns EXECUTION_ERROR for a crash with no output', async () => {
    setupExecFile({
      error: makeExecError({ message: 'spawn ENOENT' }),
    });

    const result = await executeRdcCommand(['machine', 'info', 'x'], baseOptions);

    expect(result.success).toBe(false);
    expect(result.errors).toEqual([{ code: 'EXECUTION_ERROR', message: 'spawn ENOENT' }]);
  });

  it('returns EXECUTION_ERROR for invalid JSON on stdout', async () => {
    setupExecFile({
      stdout: 'not valid json at all',
      error: makeExecError({ code: 1, message: 'exit code 1' }),
    });

    const result = await executeRdcCommand(['machine', 'info', 'x'], baseOptions);

    expect(result.success).toBe(false);
    expect(result.errors?.[0]).toEqual(expect.objectContaining({ code: 'EXECUTION_ERROR' }));
  });

  it('does not include --config when configName is undefined', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    await executeRdcCommand(['machine', 'info', 'prod'], baseOptions);

    const callArgs = mockExecFile.mock.calls[0][1] as string[];
    expect(callArgs).not.toContain('--config');
  });

  it('returns EXECUTION_ERROR when maxBuffer is exceeded', async () => {
    setupExecFile({
      error: makeExecError({
        message: 'stdout maxBuffer length exceeded',
        code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER',
      }),
    });

    const result = await executeRdcCommand(['machine', 'info', 'huge'], baseOptions);

    expect(result.success).toBe(false);
    expect(result.errors?.[0]).toEqual(
      expect.objectContaining({
        code: 'EXECUTION_ERROR',
        message: expect.stringContaining('maxBuffer'),
      })
    );
  });

  it('passes --config flag when configName is set', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    await executeRdcCommand(['machine', 'info', 'prod'], {
      ...baseOptions,
      configName: 'production',
    });

    // The second argument to execFile is the args array
    const callArgs = mockExecFile.mock.calls[0][1] as string[];
    expect(callArgs).toContain('--config');
    expect(callArgs).toContain('production');
    // --config should come before the command args
    const configIdx = callArgs.indexOf('--config');
    const machineIdx = callArgs.indexOf('machine');
    expect(configIdx).toBeLessThan(machineIdx);
  });

  it('always appends --output json --yes --quiet', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    await executeRdcCommand(['machine', 'info', 'prod'], baseOptions);

    const callArgs = mockExecFile.mock.calls[0][1] as string[];
    expect(callArgs).toContain('--output');
    expect(callArgs).toContain('json');
    expect(callArgs).toContain('--yes');
    expect(callArgs).toContain('--quiet');
  });

  it('sets non-interactive environment variables', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    await executeRdcCommand(['machine', 'info', 'prod'], baseOptions);

    const callOpts = mockExecFile.mock.calls[0][2] as { env: Record<string, string> };
    expect(callOpts.env.REDIACC_YES).toBe('1');
    expect(callOpts.env.NO_COLOR).toBe('1');
    expect(callOpts.env.REDIACC_NO_COLOR).toBe('1');
  });

  it('uses custom timeoutMs when provided', async () => {
    setupExecFile({ stdout: makeEnvelope() });

    await executeRdcCommand(['repo', 'up', 'app', '-m', 'prod'], {
      ...baseOptions,
      timeoutMs: 300_000,
    });

    const callOpts = mockExecFile.mock.calls[0][2] as { timeout: number };
    expect(callOpts.timeout).toBe(300_000);
  });
});

describe('resolveRdcBinary', () => {
  const originalArgv = process.argv;
  const originalExecPath = process.execPath;

  afterEach(() => {
    process.argv = originalArgv;
    Object.defineProperty(process, 'execPath', { value: originalExecPath, writable: true });
  });

  it('returns execPath with no prefix args when argv[1] matches execPath (SEA mode)', () => {
    Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
    process.argv = ['/usr/local/bin/rdc', '/usr/local/bin/rdc'];

    const result = resolveRdcBinary();
    expect(result.command).toBe('/usr/local/bin/rdc');
    expect(result.prefixArgs).toEqual([]);
  });

  it('returns node + script path in development mode', () => {
    Object.defineProperty(process, 'execPath', { value: '/usr/bin/node', writable: true });
    process.argv = ['/usr/bin/node', '/home/user/project/src/index.ts'];

    const result = resolveRdcBinary();
    expect(result.command).toBe('/usr/bin/node');
    expect(result.prefixArgs).toEqual(['/home/user/project/src/index.ts']);
  });
});
