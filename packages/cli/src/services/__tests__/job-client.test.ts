/**
 * Tests for the detached-job client.
 *
 * Two things here are genuinely load-bearing and get the most attention:
 *
 *   1. The LINE ACCOUNTING (JobLogCursor). It is what makes a dropped
 *      connection recoverable. Miscount by one and the operator either loses a
 *      log line forever or sees one twice, and neither is detectable after the
 *      fact.
 *   2. The VERSION-SKEW detector. It gates a fallback that RE-RUNS the
 *      operation. Matching too broadly would re-run work that already started,
 *      which for a migration or a backup push is a genuinely destructive bug.
 */

import { describe, expect, it } from 'vitest';
import {
  assertJobId,
  InvalidJobIdError,
  isJobCommandUnsupported,
  JobLogCursor,
  jobDurationMs,
  jobStatusToExecuteResult,
  parseJobHandle,
  parseJobStatus,
  resumeHint,
} from '../executor/job-client.js';

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

describe('JobLogCursor', () => {
  it('a fresh cursor asks for everything', () => {
    expect(new JobLogCursor().sinceLine).toBe(0);
  });

  it('counts complete lines', () => {
    const cursor = new JobLogCursor();
    cursor.consume('{"a":1}\n{"b":2}\n{"c":3}\n');
    expect(cursor.sinceLine).toBe(3);
  });

  it('does NOT count a trailing partial line', () => {
    const cursor = new JobLogCursor();
    cursor.consume('{"a":1}\n{"b":2}\n{"c":3');
    // The third line has no newline yet: renet has not finished emitting it, so
    // counting it would make us resume PAST a line we never actually received.
    expect(cursor.sinceLine).toBe(2);
  });

  it('counts a line split across chunk boundaries exactly once', () => {
    const cursor = new JobLogCursor();
    cursor.consume('{"msg":"hel');
    expect(cursor.sinceLine).toBe(0);
    cursor.consume('lo"}\n');
    expect(cursor.sinceLine).toBe(1);
  });

  it('is unaffected by a multi-byte character split across chunks', () => {
    // The UTF-8 for "é" is 0xC3 0xA9. Splitting it must not corrupt the count,
    // which is why the cursor counts 0x0A BYTES rather than decoded characters.
    const line = Buffer.from('{"msg":"café"}\n', 'utf8');
    const cut = line.indexOf(0xc3) + 1;

    const cursor = new JobLogCursor();
    cursor.consume(line.subarray(0, cut));
    cursor.consume(line.subarray(cut));

    expect(cursor.sinceLine).toBe(1);
  });

  it('resumes from a starting offset', () => {
    const cursor = new JobLogCursor(42);
    expect(cursor.sinceLine).toBe(42);
    cursor.consume('a\nb\n');
    expect(cursor.sinceLine).toBe(44);
  });

  /**
   * The whole point, end to end: a stream cut mid-line, then resumed, must
   * deliver every line exactly once. This mirrors renet's Replay contract
   * (it re-sends any line it only half-delivered).
   */
  it('a drop mid-line then a resume yields every line exactly once', () => {
    const lines = ['{"n":1}', '{"n":2}', '{"n":3}', '{"n":4}'];
    const cursor = new JobLogCursor();

    // Attempt 1 dies after line 2 and half of line 3.
    cursor.consume(`${lines[0]}\n${lines[1]}\n${lines[2].slice(0, 4)}`);
    expect(cursor.sinceLine).toBe(2);

    // renet resumes at --since-line 2, so it re-sends line 3 IN FULL.
    const resumed = `${lines[2]}\n${lines[3]}\n`;
    cursor.consume(resumed);

    expect(cursor.sinceLine).toBe(4);
    // The renderer saw lines 1,2 then 3,4 — four lines, no gap, no duplicate.
  });

  it('empty chunks do not advance the cursor', () => {
    const cursor = new JobLogCursor();
    cursor.consume('');
    cursor.consume(Buffer.alloc(0));
    expect(cursor.sinceLine).toBe(0);
  });
});

describe('isJobCommandUnsupported', () => {
  it('matches the cobra error from a renet that predates the job model', () => {
    // Verbatim from a real run against an older installed renet.
    const stderr = [
      'Error: unknown command "job" for "renet"',
      '',
      'Did you mean this?',
      '\thub',
      '',
      `Run 'renet --help' for usage.`,
    ].join('\n');

    expect(isJobCommandUnsupported(stderr)).toBe(true);
  });

  /**
   * These are the dangerous ones. The skew detector gates a fallback that
   * RE-RUNS the operation, so anything that is not provably "nothing happened"
   * must not match. A job that failed AFTER its unit was spawned could already
   * be doing the work; re-running it would do the work twice.
   */
  it.each([
    ['a job that failed after starting', 'job j1-aaaaaaaa failed: cryptsetup: device busy'],
    ['a permission failure', 'sudo: a password is required'],
    ['an unrelated unknown command', 'Error: unknown command "jobs" for "renet"'],
    ['a repo mentioning the word job', 'Error: repository "job-runner" not found'],
    ['a systemd failure', 'systemd-run: Failed to start transient service'],
    ['an empty output', ''],
  ])('does NOT match %s', (_label, output) => {
    expect(isJobCommandUnsupported(output)).toBe(false);
  });
});

describe('assertJobId', () => {
  it('accepts an id renet could have produced', () => {
    expect(assertJobId(JOB_ID)).toBe(JOB_ID);
  });

  /**
   * The job id comes back as JSON from the machine and is then interpolated
   * into a remote shell command. A machine that returned a crafted id would
   * otherwise get command injection for free.
   */
  it.each([
    ['shell injection', 'j1-deadbeef; rm -rf /'],
    ['command substitution', 'j1-deadbeef$(whoami)'],
    ['backtick substitution', 'j1-deadbeef`id`'],
    ['path traversal', '../../etc/passwd'],
    ['newline injection', 'j1-deadbeef\nrm -rf /'],
    ['empty', ''],
    ['wrong shape', 'not-a-job-id'],
  ])('rejects %s', (_label, bad) => {
    expect(() => assertJobId(bad)).toThrow(InvalidJobIdError);
  });
});

describe('parseJobHandle', () => {
  it('parses what `job start --json` prints', () => {
    const stdout = JSON.stringify({
      job_id: JOB_ID,
      unit: `rediacc-job-${JOB_ID}.service`,
      log_path: `/var/lib/rediacc/jobs/${JOB_ID}/events.ndjson`,
    });

    expect(parseJobHandle(stdout).job_id).toBe(JOB_ID);
  });

  it('tolerates noise printed before the JSON (sudo banners, warnings)', () => {
    const stdout = `sudo: unable to resolve host box\n{"job_id":"${JOB_ID}","unit":"u","log_path":"p"}\n`;
    expect(parseJobHandle(stdout).job_id).toBe(JOB_ID);
  });

  it('refuses a handle whose job id could not have come from renet', () => {
    const stdout = JSON.stringify({ job_id: 'j1-x; rm -rf /', unit: 'u', log_path: 'p' });
    expect(() => parseJobHandle(stdout)).toThrow(InvalidJobIdError);
  });

  it('errors clearly when renet printed no JSON at all', () => {
    expect(() => parseJobHandle('command not found')).toThrow(/Expected JSON from renet/);
  });
});

describe('parseJobStatus + jobStatusToExecuteResult', () => {
  const base = {
    job_id: JOB_ID,
    function: 'repository_up',
    started_at: '2026-07-12T16:58:10.000Z',
  };

  it('maps a succeeded job onto a successful result', () => {
    const status = parseJobStatus(
      JSON.stringify({
        ...base,
        state: 'succeeded',
        exit_code: 0,
        finished_at: '2026-07-12T16:58:12.500Z',
      })
    );

    const result = jobStatusToExecuteResult(status, 9999);

    expect(result.success).toBe(true);
    expect(result.exitCode).toBe(0);
    expect(result.error).toBeUndefined();
    // The operation duration is the JOB's own elapsed time, not how long the
    // CLI happened to be watching it. For a detached job those differ.
    expect(result.operationDurationMs).toBe(2500);
    expect(result.durationMs).toBe(9999);
  });

  it('maps a failed job, carrying renet error text through', () => {
    const status = parseJobStatus(
      JSON.stringify({
        ...base,
        state: 'failed',
        exit_code: 1,
        finished_at: '2026-07-12T16:58:11.000Z',
        error: 'command failed: exit status 1\ncryptsetup: device busy',
      })
    );

    const result = jobStatusToExecuteResult(status, 1000);

    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(1);
    expect(result.error).toContain('cryptsetup: device busy');
  });

  it('maps a cancelled job, preserving renet exit code 130', () => {
    const status = parseJobStatus(
      JSON.stringify({
        ...base,
        state: 'cancelled',
        exit_code: 130,
        finished_at: '2026-07-12T16:58:20.000Z',
      })
    );

    const result = jobStatusToExecuteResult(status, 1000);

    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(130);
  });

  it('a running job with no exit code still reports a non-zero failure', () => {
    // Should not normally happen (we only read status after the tail ends), but
    // reporting "success" for a job that never finished would be a lie.
    const status = parseJobStatus(JSON.stringify({ ...base, state: 'running', exit_code: null }));
    const result = jobStatusToExecuteResult(status, 500);

    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(1);
  });

  it('falls back to wall time when the job timestamps are unusable', () => {
    const status = parseJobStatus(JSON.stringify({ ...base, state: 'succeeded', exit_code: 0 }));
    expect(jobDurationMs(status)).toBeNull();
    expect(jobStatusToExecuteResult(status, 4242).operationDurationMs).toBe(4242);
  });

  it('ignores a finish stamp that precedes the start stamp', () => {
    const status = parseJobStatus(
      JSON.stringify({
        ...base,
        state: 'succeeded',
        exit_code: 0,
        finished_at: '2020-01-01T00:00:00.000Z',
      })
    );
    expect(jobDurationMs(status)).toBeNull();
  });
});

describe('resumeHint', () => {
  it('says plainly that the job survives, and how to get back to it', () => {
    const hint = resumeHint(JOB_ID, 'prod-1');

    // The single most important thing to communicate: Ctrl-C did NOT kill it.
    expect(hint).toContain('STILL RUNNING');
    expect(hint).toContain('NOT cancelled');
    expect(hint).toContain(JOB_ID);

    // Every command it offers must be a real one. It now points at the
    // first-class `rdc job` surface rather than telling the operator to shell
    // into the machine and drive renet by hand.
    expect(hint).toContain(`rdc job logs -m prod-1 --id ${JOB_ID} --follow`);
    expect(hint).toContain(`rdc job status -m prod-1 --id ${JOB_ID}`);
    expect(hint).toContain(`rdc job cancel -m prod-1 --id ${JOB_ID}`);
    expect(hint).not.toContain('rdc term connect');
  });
});
