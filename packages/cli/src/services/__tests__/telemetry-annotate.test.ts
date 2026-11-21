/**
 * annotateCommand puts attributes on the one command span the process opened,
 * and on the request's own span inside a dispatch (PLAN-detached-jobs Design 13).
 */

import { describe, expect, it, vi } from 'vitest';
import { jobSpanAttributes } from '../executor/job-span.js';
import {
  currentRequestTelemetry,
  runWithRequestTelemetry,
} from '../telemetry/request-telemetry.js';
import { telemetryService } from '../telemetry/telemetry.js';

interface FakeSpan {
  setAttributes: ReturnType<typeof vi.fn>;
  setStatus: ReturnType<typeof vi.fn>;
  end: ReturnType<typeof vi.fn>;
}

function installTracer(): FakeSpan[] {
  const spans: FakeSpan[] = [];
  const tracer = {
    startSpan: () => {
      const span: FakeSpan = { setAttributes: vi.fn(), setStatus: vi.fn(), end: vi.fn() };
      spans.push(span);
      return span;
    },
  };
  Object.assign(telemetryService, { tracer, isEnabled: true });
  return spans;
}

describe('annotateCommand', () => {
  it('sets the attributes on the process command span', () => {
    const spans = installTracer();
    telemetryService.startCommand('repo up');

    telemetryService.annotateCommand({ 'rediacc.job.id': 'j1' });

    expect(spans[0]?.setAttributes).toHaveBeenLastCalledWith({ 'rediacc.job.id': 'j1' });
    telemetryService.endCommand('repo up', { success: true });
  });

  it('sets them on the request span a dispatch opened', () => {
    const spans = installTracer();
    telemetryService.startCommand('repo up', { spanKey: 'req-1' });

    runWithRequestTelemetry(undefined, () => {
      const scope = currentRequestTelemetry();
      if (scope) scope.open = { commandName: 'repo up', spanKey: 'req-1' };
      telemetryService.annotateCommand({ 'rediacc.job.id': 'j2' });
    });

    expect(spans[0]?.setAttributes).toHaveBeenLastCalledWith({ 'rediacc.job.id': 'j2' });
    telemetryService.endCommand('repo up', { success: true }, 'req-1');
  });

  it('control: with no span open it does nothing and does not throw', () => {
    const spans = installTracer();
    expect(() => telemetryService.annotateCommand({ 'rediacc.job.id': 'j3' })).not.toThrow();
    expect(spans).toHaveLength(0);
  });
});

describe('jobSpanAttributes', () => {
  it('leaves out what is unknown', () => {
    expect(
      jobSpanAttributes({ function: 'repository_up', follow: 'tail', outcome: 'running' })
    ).toEqual({
      'rediacc.job.function': 'repository_up',
      'rediacc.job.follow': 'tail',
      'rediacc.job.outcome': 'running',
    });
  });

  it('carries the poll count and start latency when given', () => {
    expect(
      jobSpanAttributes({
        jobId: 'j',
        function: 'f',
        follow: 'poll',
        outcome: 'succeeded',
        startLatencyMs: 120,
        polls: 4,
      })
    ).toMatchObject({ 'rediacc.job.polls': 4, 'rediacc.job.start_latency_ms': 120 });
  });
});
