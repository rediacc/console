/**
 * The MCP attach window (PLAN-detached-jobs J8b).
 *
 * Every tool that starts a machine job runs the child `rdc` with the 20 s attach window (the child reads
 * REDIACC_JOB_CLIENT=mcp into its window), so a short run returns its result and a long one the ticket with
 * `next: "job_status"`. Overlaps are a structured field of the result. A tool that starts no job carries no window.
 */

import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JOB_ATTACH_WINDOW_MS, JOB_CLIENT_ENV } from '../../../services/jobs/attach.js';
import { executeRdcCommand } from '../executor.js';
import { hasAttachWindow } from '../tool-factory.js';
import { buildAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

function childPrints(stdout: string, error?: Error & { stdout?: string }) {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) => {
      if (error) {
        error.stdout = stdout;
        callback(error);
      } else {
        callback(null, { stdout, stderr: '' });
      }
    }
  );
}

const childEnv = () => (mockExecFile.mock.calls[0]?.[2] as { env: Record<string, string> }).env;
const base = { defaultTimeoutMs: 120_000 };
const TICKET = {
  jobId: 'j18c1c04dd251ce26-0ccf9fe5',
  machine: 'prod-1',
  verb: 'backup snapshot',
  state: 'running',
  follow: 'rdc job wait j18c1c04dd251ce26-0ccf9fe5',
  overlaps: [],
};

afterEach(() => vi.clearAllMocks());

describe('MCP attach window', () => {
  it('every tool whose command starts a machine job carries the window and says so', () => {
    const windowed = CLI_CONTRACT.commands.filter(hasAttachWindow).map((c) => c.pathKey);
    const tools = buildAllTools();
    let seen = 0;
    for (const tool of tools) {
      const cmd = CLI_CONTRACT.commands.find((c) => c.pathKey === tool.name.replaceAll('_', ' '));
      if (!cmd) continue;
      if (windowed.includes(cmd.pathKey)) {
        seen++;
        expect(tool.attachWindowMs, tool.name).toBe(JOB_ATTACH_WINDOW_MS);
        expect(tool.description, tool.name).toContain('about 20 s');
      } else {
        expect(tool.attachWindowMs, tool.name).toBeUndefined();
      }
    }
    expect(seen).toBeGreaterThan(10);
  });

  it('control: an other-plane tool (backup usage) carries no window', () => {
    const usage = buildAllTools().find((t) => t.name === 'backup_usage');
    expect(usage?.attachWindowMs).toBeUndefined();
    expect(usage?.description).not.toContain('about 20 s');
  });

  it('runs a windowed command with the mcp client kind, and an unwindowed one without it', async () => {
    childPrints('');
    await executeRdcCommand(['repo', 'create', 'shop', '--machine', 'prod-1'], base);
    expect(childEnv()[JOB_CLIENT_ENV]).toBe('mcp');
    mockExecFile.mockReset();
    childPrints('');
    await executeRdcCommand(['backup', 'usage'], base);
    expect(childEnv()[JOB_CLIENT_ENV]).toBeUndefined();
  });

  it('returns the ticket with next job_status when the run outlasted the window', async () => {
    childPrints(
      `${JSON.stringify({ ...TICKET, overlaps: [{ jobId: 'j-x', action: 'warn', attach: 'rdc job logs j-x -m prod-1 --follow' }] })}\n`
    );
    const result = await executeRdcCommand(['backup', 'snapshot', 'shop'], base);
    expect(result).toMatchObject({
      success: true,
      next: 'job_status',
      job: { jobId: TICKET.jobId, machine: 'prod-1' },
    });
    expect(result.overlaps?.[0]?.attach).toContain('rdc job logs j-x');
  });

  it('returns the command result as before when the run finished inside the window', async () => {
    childPrints(
      JSON.stringify({
        success: true,
        command: 'repo create',
        data: { ok: 1 },
        errors: null,
        warnings: [],
        metrics: { duration_ms: 2000 },
      })
    );
    const result = await executeRdcCommand(['repo', 'create', 'shop'], base);
    expect(result).toMatchObject({ success: true, data: { ok: 1 } });
    expect(result.next).toBeUndefined();
    expect(result.job).toBeUndefined();
  });

  it('a BUSY refusal is an error result carrying the overlaps', async () => {
    const overlaps = [
      { jobId: 'j-x', action: 'refuse', attach: 'rdc job logs j-x -m prod-1 --follow' },
    ];
    childPrints(
      JSON.stringify({
        success: false,
        command: 'repo up',
        data: null,
        errors: [{ code: 'BUSY', message: 'Refused to start the job', overlaps }],
        warnings: [],
        metrics: { duration_ms: 5 },
      }),
      Object.assign(new Error('exit 15'), {})
    );
    const result = await executeRdcCommand(['repo', 'up', 'shop'], base);
    expect(result.success).toBe(false);
    expect(result.overlaps?.[0]?.attach).toContain('rdc job logs j-x');
  });
});
