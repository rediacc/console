/**
 * job_wait (PLAN-rmcp-local-mcp LM6, Design 5): repeat `rdc job status` through the executor until the job is
 * terminal, and return by the 50 s ceiling with the job id and a nextPollSeconds hint when it is not.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { JOB_WAIT_CEILING_MS, JOB_WAIT_INTERVAL_MS } from '../custom-tools.js';
import { buildAllTools, registerAllTools } from '../tools.js';

vi.mock('../executor.js', () => ({
  executeRdcCommand: vi.fn(),
  resolveRdcBinary: () => ({ command: 'node', prefixArgs: ['index.js'] }),
}));

type Handler = (args: Record<string, unknown>) => Promise<{
  content: { type: string; text: string }[];
  isError: boolean;
}>;

function handlerFor(name: string): Handler {
  let found: Handler | undefined;
  registerAllTools(
    {
      registerTool: (toolName: string, _config: unknown, handler: Handler) => {
        if (toolName === name) found = handler;
      },
    } as never,
    { defaultTimeoutMs: 120_000 }
  );
  if (!found) throw new Error(`no MCP tool ${name}`);
  return found;
}

/** A job that runs for `runsMs` from the test's start, read through `job status`. */
async function jobLasting(runsMs: number) {
  const { executeRdcCommand } = await import('../executor.js');
  const start = Date.now();
  vi.mocked(executeRdcCommand).mockReset();
  vi.mocked(executeRdcCommand).mockImplementation((argv) => {
    const finished = Date.now() - start >= runsMs;
    return Promise.resolve({
      success: true,
      command: argv.join(' '),
      data: {
        job_id: 'j-1',
        function: 'repo_up',
        state: finished ? 'succeeded' : 'running',
        exit_code: finished ? 0 : null,
        started_at: '2026-11-25T00:00:00Z',
      },
      errors: null,
      warnings: [],
      duration_ms: 1,
    });
  });
  return vi.mocked(executeRdcCommand);
}

async function call(args: Record<string, unknown>) {
  const pending = handlerFor('job_wait')(args);
  await vi.advanceTimersByTimeAsync(JOB_WAIT_CEILING_MS + JOB_WAIT_INTERVAL_MS);
  const result = await pending;
  return { result, body: JSON.parse(result.content[0].text) };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('job_wait', () => {
  it('a 120 s job returns at the 50 s ceiling with the job id and nextPollSeconds', async () => {
    const exec = await jobLasting(120_000);
    const t0 = Date.now();
    const pending = handlerFor('job_wait')({ 'job-id': 'j-1' });
    let settledAt: number | undefined;
    void pending.then(() => {
      settledAt = Date.now() - t0;
    });
    await vi.advanceTimersByTimeAsync(120_000);
    const result = await pending;
    const body = JSON.parse(result.content[0].text);
    expect(settledAt).toBeLessThanOrEqual(JOB_WAIT_CEILING_MS);
    expect(settledAt).toBeGreaterThanOrEqual(JOB_WAIT_CEILING_MS - JOB_WAIT_INTERVAL_MS);
    expect(result.isError).toBe(false);
    expect(body.data.job_id).toBe('j-1');
    expect(body.data.state).toBe('running');
    expect(body.next).toBe('job_wait');
    expect(body.nextPollSeconds).toBe(JOB_WAIT_INTERVAL_MS / 1000);
    expect(exec).toHaveBeenCalledWith(['job', 'status', 'j-1'], expect.any(Object));
    expect(exec.mock.calls.length).toBe(JOB_WAIT_CEILING_MS / JOB_WAIT_INTERVAL_MS);
  });

  it('control: a job that ends inside the window returns its terminal status without a poll hint', async () => {
    const exec = await jobLasting(12_000);
    const { result, body } = await call({ 'job-id': 'j-1', machine: 'prod-1' });
    expect(result.isError).toBe(false);
    expect(body.data.state).toBe('succeeded');
    expect(body.nextPollSeconds).toBeUndefined();
    expect(body.next).toBeUndefined();
    expect(body.waited_ms).toBe(15_000);
    expect(exec).toHaveBeenLastCalledWith(
      ['job', 'status', 'j-1', '--machine', 'prod-1'],
      expect.any(Object)
    );
  });

  it('gives every read only the time left before the ceiling (review 1a62c834.1)', async () => {
    const exec = await jobLasting(120_000);
    const t0 = Date.now();
    const reads: { at: number; timeoutMs: number }[] = [];
    exec.mockImplementation((_argv, options) => {
      reads.push({ at: Date.now() - t0, timeoutMs: (options as { timeoutMs: number }).timeoutMs });
      return Promise.resolve({
        success: true,
        command: 'job status j-1',
        data: { job_id: 'j-1', state: 'running' },
        errors: null,
        warnings: [],
        duration_ms: 1,
      });
    });
    const pending = handlerFor('job_wait')({ 'job-id': 'j-1' });
    await vi.advanceTimersByTimeAsync(120_000);
    await pending;
    expect(reads.length).toBeGreaterThan(1);
    for (const read of reads)
      expect(read.at + read.timeoutMs).toBeLessThanOrEqual(JOB_WAIT_CEILING_MS);
    // Control: the first read is not squeezed, it gets the whole window.
    expect(reads[0].timeoutMs).toBe(JOB_WAIT_CEILING_MS);
  });

  it('a failed status read returns at once as an error, without polling again', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockReset();
    vi.mocked(executeRdcCommand).mockResolvedValue({
      success: false,
      command: 'job status j-9',
      data: null,
      errors: [{ code: 'NOT_FOUND', message: 'no job j-9' }],
      warnings: [],
      duration_ms: 1,
    });
    const { result, body } = await call({ 'job-id': 'j-9' });
    expect(result.isError).toBe(true);
    expect(body.errors[0].code).toBe('NOT_FOUND');
    expect(vi.mocked(executeRdcCommand)).toHaveBeenCalledTimes(1);
  });

  it('is advertised read-only and idempotent, with the job id required', () => {
    const tool = buildAllTools().find((t) => t.name === 'job_wait');
    expect(tool?.isDestructive).toBe(false);
    expect(tool?.isIdempotent).toBe(true);
    expect(tool?.timeoutClass).toBe('read');
    expect(tool?.commandPath).toBe('job status');
    expect(Object.keys(tool?.schema ?? {})).toEqual(['job-id', 'machine']);
  });
});
