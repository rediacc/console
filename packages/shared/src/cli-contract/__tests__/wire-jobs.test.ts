/**
 * The job shapes of the proxy wire (agent/plans/PLAN-detached-jobs.md J2, J2b):
 * the request id, the overlap entry, the heartbeat line, the result's attach
 * fields, the `-b` envelope shared by the CLI and MCP, and the poll response.
 */
import { describe, expect, it } from 'vitest';
import {
  BackgroundEnvelopeSchema,
  CommandRequestSchema,
  JobOverlapSchema,
  JobPollResponseSchema,
  PROXY_ROUTES,
  StreamLineSchema,
} from '../wire.js';

const overlap = {
  jobId: 'j18f2a-0123abcd',
  function: 'repository_up',
  repoGuid: '6b1c',
  state: 'running',
  startedAt: '2026-10-29T10:00:00Z',
  origin: { client: 'rdc', sshUser: 'ops', config: { name: 'prod', id: 'ab12' } },
  action: 'refuse',
  attach: 'rdc job logs j18f2a-0123abcd -m prod-1 --follow',
} as const;

describe('JobOverlapSchema', () => {
  it('round-trips an overlap entry', () => {
    expect(JobOverlapSchema.parse(overlap)).toEqual(overlap);
  });

  it('refuses an entry that names no job', () => {
    const { jobId: _drop, ...noJob } = overlap;
    expect(JobOverlapSchema.safeParse(noJob).success).toBe(false);
  });

  it('accepts a scheduled backup unit, which has a unit and no job id', () => {
    const unit = {
      unit: 'rediacc-backup-nightly.service',
      action: 'warn',
      attach: 'rdc backup status -m prod-1',
    };
    expect(JobOverlapSchema.safeParse(unit).success).toBe(true);
  });
});

describe('StreamLineSchema job lines', () => {
  it('validates a heartbeat line', () => {
    expect(StreamLineSchema.parse({ kind: 'heartbeat' })).toEqual({ kind: 'heartbeat' });
  });

  it('carries the machine and the overlaps on the job line', () => {
    const line = StreamLineSchema.parse({
      kind: 'job',
      jobId: 'j1-deadbeef',
      machine: 'prod-1',
      sinceLine: 4,
      overlaps: [overlap],
    });
    expect(line).toMatchObject({ machine: 'prod-1', overlaps: [overlap] });
  });

  it('carries the attach fields on the result', () => {
    const line = StreamLineSchema.parse({
      kind: 'result',
      result: {
        success: true,
        exitCode: 0,
        durationMs: 20_000,
        jobId: 'j1-deadbeef',
        state: 'running',
        attached: false,
        overlaps: [overlap],
      },
    });
    expect(line.kind === 'result' && line.result.state).toBe('running');
  });

  it('refuses a result whose overlap names no job', () => {
    const { jobId: _drop, ...noJob } = overlap;
    const parsed = StreamLineSchema.safeParse({
      kind: 'result',
      result: { success: false, exitCode: 15, durationMs: 1, overlaps: [noJob] },
    });
    expect(parsed.success).toBe(false);
  });
});

describe('CommandRequestSchema requestId', () => {
  it('accepts a UUID request id and refuses one renet would reject', () => {
    const base = { contractVersion: 'dev', pathKey: 'repo up' };
    expect(
      CommandRequestSchema.safeParse({ ...base, requestId: '0b7a7c1e-4d2f-4c1b-9a3e-2f1d0c9b8a7e' })
        .success
    ).toBe(true);
    expect(CommandRequestSchema.safeParse({ ...base, requestId: '../etc' }).success).toBe(false);
  });
});

describe('BackgroundEnvelopeSchema', () => {
  it('parses the -b envelope and defaults overlaps to empty', () => {
    const env = BackgroundEnvelopeSchema.parse({
      jobId: 'j1-deadbeef',
      machine: 'prod-1',
      verb: 'repo up',
      repo: 'mail',
      state: 'running',
      follow: 'rdc job wait j1-deadbeef',
    });
    expect(env.overlaps).toEqual([]);
  });
});

describe('JobPollResponseSchema', () => {
  const sample = {
    events: [{ line: 3, event: { type: 'log', msg: 'pulling' } }],
    nextLine: 3,
    more: false,
    status: { state: 'running', function: 'repository_up' },
  };

  it('round-trips a poll response', () => {
    expect(JobPollResponseSchema.parse(sample)).toEqual(sample);
  });

  it('refuses a body without nextLine', () => {
    const { nextLine: _drop, ...noNext } = sample;
    expect(JobPollResponseSchema.safeParse(noNext).success).toBe(false);
  });
});

describe('PROXY_ROUTES job routes', () => {
  it('builds the poll and cancel routes from the same patterns the server mounts', () => {
    expect(PROXY_ROUTES.jobPoll('j1-deadbeef')).toBe(
      PROXY_ROUTES.jobPollPattern.replace(':id', 'j1-deadbeef')
    );
    expect(PROXY_ROUTES.jobCancel('j1-deadbeef')).toBe(
      PROXY_ROUTES.jobCancelPattern.replace(':id', 'j1-deadbeef')
    );
  });
});
