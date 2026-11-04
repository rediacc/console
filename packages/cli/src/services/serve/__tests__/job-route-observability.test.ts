/**
 * The observability of the job routes (PLAN-detached-jobs Design 4, 5 and 13): the route span attribute, the job id and
 * outcome on an audit event, the job's own duration from its status, and the poll pacing and budget.
 */

import { AuditEventsRequestSchema } from '@rediacc/shared';
import { describe, expect, it, vi } from 'vitest';
import { annotatePolled, jobSpanAttributes } from '../../executor/job-span.js';
import { jittered, PROXY_LOST_BUDGET_MS } from '../../executor/proxy-follow.js';
import {
  currentRequestTelemetry,
  runWithRequestTelemetry,
} from '../../telemetry/request-telemetry.js';
import { telemetryService } from '../../telemetry/telemetry.js';
import { createExecutorAudit } from '../audit.js';
import { parseJobPollOutput } from '../job-poll.js';
import { withRouteSpan } from '../route-span.js';

const principal = {
  userId: 'u1',
  orgId: 'o1',
  teamId: null,
  orgRole: 'member' as const,
  userEmail: 'a@b.test',
  tokenId: '11111111-1111-4111-8111-111111111111',
};

describe('poll pacing and budget', () => {
  it('jitters by at most 20 percent either way', () => {
    expect(jittered(1000, () => 1)).toBe(1200);
    expect(jittered(1000, () => 0)).toBe(800);
  });

  it('retries failed polls for 10 minutes before the follow is lost', () => {
    expect(PROXY_LOST_BUDGET_MS).toBe(600_000);
  });
});

describe('rediacc.job.polls', () => {
  it('carries the count of a followed run', () => {
    expect(
      jobSpanAttributes({
        jobId: 'j1',
        function: 'repository_up',
        follow: 'poll',
        outcome: 'succeeded',
        polls: 3,
      })
    ).toMatchObject({ 'rediacc.job.follow': 'poll', 'rediacc.job.polls': 3 });
  });

  it('annotatePolled writes it onto the open command span', () => {
    const spy = vi.spyOn(telemetryService, 'annotateCommand').mockImplementation(() => {});
    annotatePolled('j1', 'repository_up', 'succeeded', 4);
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ 'rediacc.job.polls': 4 }));
    spy.mockRestore();
  });
});

describe('rediacc.proxy.route', () => {
  it('a job route runs its handler inside a scope that names the route, and ends the span with the status', async () => {
    const start = vi.spyOn(telemetryService, 'startCommand').mockImplementation(() => {});
    const end = vi.spyOn(telemetryService, 'endCommand').mockImplementation(() => {});
    let seen: string | undefined;
    const response = await withRouteSpan('job-poll', principal, () => {
      seen = currentRequestTelemetry()?.route;
      return Promise.resolve(new Response('{}', { status: 500 }));
    });
    expect(response.status).toBe(500);
    expect(seen).toBe('job-poll');
    expect(start).toHaveBeenCalledWith(
      'job-poll',
      expect.objectContaining({ spanKey: expect.any(String) })
    );
    expect(end).toHaveBeenCalledWith(
      'job-poll',
      expect.objectContaining({ success: false }),
      expect.any(String)
    );
    start.mockRestore();
    end.mockRestore();
  });

  it('control: a request scope opened without a route names none', () => {
    runWithRequestTelemetry(undefined, () => {
      expect(currentRequestTelemetry()?.route).toBeUndefined();
    });
  });
});

describe('the audit event of a job', () => {
  it('carries the job id and outcome, and the wire schema accepts them', async () => {
    let body: unknown;
    const audit = createExecutorAudit({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl: ((_url: string, init: RequestInit) => {
        body = JSON.parse(String(init.body));
        return Promise.resolve(new Response('{}', { status: 200 }));
      }) as unknown as typeof fetch,
    });
    await audit({
      principal,
      commandPath: 'repo up',
      functionName: 'repository_up',
      machineName: 'm1',
      params: {},
      success: true,
      exitCode: 0,
      durationMs: 5,
      destructive: false,
      jobId: 'j1-00000001',
      outcome: 'started',
    });
    expect(AuditEventsRequestSchema.safeParse(body).success).toBe(true);
    expect(JSON.stringify(body)).toContain('"outcome":"started"');
    expect(JSON.stringify(body)).toContain('"jobId":"j1-00000001"');
  });
});

describe('the job status trailer', () => {
  it('keeps when the job started, so its duration is the job', () => {
    const trailer = JSON.stringify({
      type: 'job_status',
      state: 'succeeded',
      function: 'repository_up',
      exit_code: 0,
      started_at: '2026-11-04T10:00:00Z',
      finished_at: '2026-11-04T10:05:00Z',
    });
    const body = parseJobPollOutput(`${trailer}\n`, { sinceLine: 0 });
    expect(body.status.startedAt).toBe('2026-11-04T10:00:00Z');
    expect(body.status.finishedAt).toBe('2026-11-04T10:05:00Z');
  });
});
