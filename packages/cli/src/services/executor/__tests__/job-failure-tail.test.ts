/**
 * A failed `repo up` job: renet's log lines must reach stderr under --debug, and
 * the failure carries a bounded tail of them even without it.
 */

import { describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { createJobOutputCollector, jobStatusToExecuteResult } from '../job-client.js';
import { renderJobEventDebug } from '../job-remote.js';
import type { RenetEvent } from '../types.js';

const infoLine = (msg: string): RenetEvent => ({ type: 'log', level: 'info', msg });

describe('--debug job rendering', () => {
  it('writes info-level renet log lines to stderr and none to stdout', async () => {
    const context = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };
    await runInRequestContext(context, () => {
      renderJobEventDebug(infoLine('placing observability in cgroup'));
      return Promise.resolve();
    });
    expect(context.stderr.join('')).toContain('placing observability in cgroup');
    expect(context.stdout.join('')).toBe('');
  });
});

describe('failed job result', () => {
  const status = {
    job_id: 'j1',
    state: 'failed',
    exit_code: 255,
    error: 'function up failed in observability: signal: killed',
    started_at: '2026-11-06T00:00:00Z',
  } as never;

  it('carries the bounded tail of info-level log lines', () => {
    const collector = createJobOutputCollector();
    for (let i = 0; i < 100; i++) collector.consume(infoLine(`step ${i} ${'x'.repeat(1000)}`));
    const result = jobStatusToExecuteResult(status, 10, collector);
    expect(result.stderr).toContain('step 99');
    expect(result.stderr).not.toContain('step 50 ');
    expect((result.stderr ?? '').length).toBeLessThan(20 * 310);
  });

  it('leaves a successful job stderr untouched', () => {
    const collector = createJobOutputCollector();
    collector.consume(infoLine('chatter'));
    const ok = jobStatusToExecuteResult(
      { ...(status as object), state: 'succeeded', exit_code: 0 } as never,
      1,
      collector
    );
    expect(ok.stderr).toBe('');
  });
});
