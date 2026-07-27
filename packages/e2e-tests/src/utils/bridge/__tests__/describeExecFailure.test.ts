import { describe, expect, it } from 'vitest';
import { describeExecFailure, EXEC_MAX_BUFFER } from '../BridgeTestRunner';

/**
 * WHAT BROKE. Every bridge and VM command in every E2E suite runs through
 * `child_process.exec`, which defaults to a 1 MB capture buffer and KILLS the
 * child when it overflows. Two things then went wrong at once:
 *
 *   1. The kill was invisible as a kill. Node reports it with a STRING code,
 *      `ERR_CHILD_PROCESS_STDIO_MAXBUFFER`, and both call sites did
 *      `err.code ?? 1` -- so a string landed in a field typed `number` and the
 *      assertion read `Expected: 0  Received: "ERR_CHILD_PROCESS_STDIO_MAXBUFFER"`.
 *   2. `killed` was treated as proof of a timeout, so a buffer kill would have
 *      been reported as "Command timed out", sending the reader after a slow
 *      command that was in fact merely verbose.
 *
 * Observed on run 30307775327, `Tests + Infra / E2E Migrate` test 4:
 * `renet backup push --strategy physical` streams transfer progress and
 * overflowed the default buffer.
 *
 * The buffer itself is now 64 MB, but a buffer can always be exceeded, so the
 * DIAGNOSTIC is what these tests pin: whatever the limit, overflowing it must
 * say so in those words and must not masquerade as a timeout or an exit code.
 */
describe('describeExecFailure', () => {
  it('reports a buffer overflow as its own failure mode, not a timeout', () => {
    const r = describeExecFailure({ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' }, 600_000);
    expect(r.code).toBe(125);
    expect(r.prefix).toContain('output');
    expect(r.prefix).not.toContain('timed out');
  });

  it('still reports a buffer overflow correctly when Node also set killed', () => {
    // The dangerous ordering: `killed` is checked AFTER the buffer code, because
    // Node may set both and a timeout message would be actively misleading.
    const r = describeExecFailure({ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER', killed: true }, 1000);
    expect(r.code).toBe(125);
    expect(r.prefix).not.toContain('timed out');
  });

  it('names the byte limit so the reader can act on it', () => {
    const r = describeExecFailure({ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' }, 1000);
    expect(r.prefix).toContain(String(EXEC_MAX_BUFFER));
  });

  it('still reports a real timeout as a timeout', () => {
    const r = describeExecFailure({ killed: true }, 42_000);
    expect(r.code).toBe(124);
    expect(r.prefix).toContain('timed out after 42000ms');
  });

  it('passes a real numeric exit code through untouched', () => {
    expect(describeExecFailure({ code: 3 }, 1000)).toEqual({ code: 3, prefix: '' });
    // Zero must survive: `err.code ?? 1` would have kept it, but a truthiness
    // test would silently turn a success-shaped failure into 1.
    expect(describeExecFailure({ code: 0 }, 1000)).toEqual({ code: 0, prefix: '' });
  });

  it('never returns a non-numeric code, whatever Node reports', () => {
    // ExecResult.code is typed `number`. Any other string error code must be
    // coerced rather than leaked into an equality assertion.
    const r = describeExecFailure({ code: 'ERR_CHILD_PROCESS_EPIPE' }, 1000);
    expect(typeof r.code).toBe('number');
    expect(r.code).toBe(1);
    expect(r.prefix).toContain('ERR_CHILD_PROCESS_EPIPE');
  });

  it('falls back to 1 when there is no code at all', () => {
    expect(describeExecFailure({}, 1000)).toEqual({ code: 1, prefix: '' });
  });
});
