/**
 * A failed `repo up` job: renet's log lines must reach stderr under --debug, and
 * the failure carries a bounded tail of them even without it.
 */

import { describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { createJobOutputCollector, jobStatusToExecuteResult } from '../job-client.js';
import { renderJobEvent, renderJobEventDebug } from '../job-remote.js';
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

describe('step rendering through the job path', () => {
  const render = async (detail: string | undefined): Promise<string> => {
    const context = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };
    await runInRequestContext(context, () => {
      renderJobEvent({ type: 'step_done', name: 'compose_up', duration_ms: 1200, detail });
      return Promise.resolve();
    });
    return context.stdout.join('');
  };

  it('draws a step that ended in failure with its failed label', async () => {
    const text = await render('failed');
    expect(text).toContain('Service start failed');
    expect(text).not.toContain('Services started');
  });

  it('control: the same step without the failed detail keeps its done label', async () => {
    const text = await render(undefined);
    expect(text).toContain('Services started');
    expect(text).not.toContain('failed');
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

  it('keeps an error logged before the tail window ahead of the tail', () => {
    const collector = createJobOutputCollector();
    collector.consume({ type: 'log', level: 'error', msg: 'disk full on /mnt/x' });
    for (let i = 0; i < 100; i++) collector.consume(infoLine(`step ${i}`));
    const result = jobStatusToExecuteResult(status, 10, collector);
    expect(result.stderr).toContain('disk full on /mnt/x');
    expect(result.stderr).toContain('step 99');
  });

  it('bounds the older error lines too, keeping the newest', () => {
    const collector = createJobOutputCollector();
    for (let i = 0; i < 200; i++)
      collector.consume({ type: 'log', level: 'error', msg: `err ${i}` });
    const result = jobStatusToExecuteResult(status, 10, collector);
    expect((result.stderr ?? '').split('\n').length).toBeLessThanOrEqual(40);
    expect(result.stderr).toContain('err 199');
    expect(result.stderr).not.toContain('err 0\n');
  });

  it('never leaves a lone surrogate when a long line is cut at the width', () => {
    const collector = createJobOutputCollector();
    // A pair straddles the 300-unit cut: the high surrogate lands at index 299.
    collector.consume(infoLine(`${'a'.repeat(299)}\u{1F600}${'b'.repeat(10)}`));
    const result = jobStatusToExecuteResult(status, 10, collector);
    expect(result.stderr).not.toMatch(/[\ud800-\udbff](?![\udc00-\udfff])/);
  });

  it('control: an error still inside the tail window is not repeated', () => {
    const collector = createJobOutputCollector();
    collector.consume({ type: 'log', level: 'error', msg: 'disk full on /mnt/x' });
    collector.consume(infoLine('step 1'));
    const result = jobStatusToExecuteResult(status, 10, collector);
    expect(result.stderr?.match(/disk full/g)).toHaveLength(1);
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
