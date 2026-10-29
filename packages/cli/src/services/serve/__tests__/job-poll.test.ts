import { describe, expect, it, vi } from 'vitest';
import {
  buildJobPollArgv,
  createTerminalLedger,
  DEFAULT_MAX_LINES,
  JobPollParseError,
  MAX_BODY_BYTES,
  parseJobPollOutput,
} from '../job-poll.js';

const ID = 'j17c9f1a2b3c4d5e-deadbeef';

function trailer(extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    type: 'job_status',
    state: 'running',
    function: 'repository_fork',
    exit_code: null,
    ...extra,
  });
}

describe('buildJobPollArgv', () => {
  it('matches renet job logs flags (--id, not positional)', () => {
    expect(buildJobPollArgv(ID, 42, 100)).toEqual([
      'job',
      'logs',
      '--id',
      ID,
      '--since-line',
      '42',
      '--max-lines',
      '100',
      '--with-status',
    ]);
  });

  it('defaults the page to 500 lines and clamps nonsense', () => {
    expect(DEFAULT_MAX_LINES).toBe(500);
    expect(buildJobPollArgv(ID, 0).at(7)).toBe('500');
    expect(buildJobPollArgv(ID, -3, 0).slice(4, 8)).toEqual([
      '--since-line',
      '0',
      '--max-lines',
      '500',
    ]);
    expect(buildJobPollArgv(ID, 0, 99999).at(7)).toBe('500');
  });

  it('refuses an id renet could not have minted', () => {
    expect(() => buildJobPollArgv('j1-dead; rm -rf /', 0)).toThrow();
  });
});

describe('parseJobPollOutput', () => {
  it('splits events from the status trailer and numbers lines from sinceLine', () => {
    const out = `${[JSON.stringify({ type: 'a' }), JSON.stringify({ type: 'b' }), trailer()].join('\n')}\n`;
    const body = parseJobPollOutput(out, { sinceLine: 10, maxLines: 500 });
    expect(body.events).toEqual([
      { line: 10, event: { type: 'a' } },
      { line: 11, event: { type: 'b' } },
    ]);
    expect(body.nextLine).toBe(12);
    expect(body.more).toBe(false);
    expect(body.status).toEqual({ state: 'running', function: 'repository_fork' });
  });

  it('maps a terminal trailer to exitCode and finishedAt', () => {
    const out = trailer({ state: 'failed', exit_code: 3, finished_at: '2026-10-29T01:02:03Z' });
    const body = parseJobPollOutput(out, { sinceLine: 0, maxLines: 500 });
    expect(body.events).toEqual([]);
    expect(body.nextLine).toBe(0);
    expect(body.status).toEqual({
      state: 'failed',
      exitCode: 3,
      finishedAt: '2026-10-29T01:02:03Z',
      function: 'repository_fork',
    });
  });

  it('sets more when the page is full', () => {
    const lines = Array.from({ length: 3 }, (_, i) => JSON.stringify({ n: i }));
    const body = parseJobPollOutput([...lines, trailer()].join('\n'), {
      sinceLine: 0,
      maxLines: 3,
    });
    expect(body.more).toBe(true);
  });

  it('keeps a non-JSON line as a raw event instead of dropping it', () => {
    const body = parseJobPollOutput(['not json', trailer()].join('\n'), {
      sinceLine: 0,
      maxLines: 5,
    });
    expect(body.events).toEqual([{ line: 0, event: { type: 'raw', text: 'not json' } }]);
    expect(body.nextLine).toBe(1);
  });

  it('caps the body at 256 KiB, sets more, and resumes at the first unsent line', () => {
    const big = JSON.stringify({ type: 'log', text: 'x'.repeat(60 * 1024) });
    const out = [big, big, big, big, big, big, trailer()].join('\n');
    const body = parseJobPollOutput(out, { sinceLine: 0, maxLines: 500 });
    expect(Buffer.byteLength(JSON.stringify(body))).toBeLessThanOrEqual(MAX_BODY_BYTES);
    expect(body.events.length).toBe(4);
    expect(body.nextLine).toBe(4);
    expect(body.more).toBe(true);
  });

  it('replaces a single oversized event so the cursor still advances', () => {
    const huge = JSON.stringify({ type: 'log', text: 'x'.repeat(MAX_BODY_BYTES + 10) });
    const body = parseJobPollOutput([huge, trailer()].join('\n'), {
      sinceLine: 5,
      maxLines: 500,
    });
    expect(Buffer.byteLength(JSON.stringify(body))).toBeLessThanOrEqual(MAX_BODY_BYTES);
    expect(body.events).toHaveLength(1);
    expect(body.events[0]?.line).toBe(5);
    expect(body.events[0]?.event).toMatchObject({ type: 'truncated' });
    expect(body.nextLine).toBe(6);
  });

  it('numbers lines by their real position, a blank line still counts', () => {
    const out = ['{"type":"a"}', '', '{"type":"b"}', trailer()].join('\n');
    const body = parseJobPollOutput(out, { sinceLine: 10, maxLines: 500 });
    expect(body.events.map((e) => e.line)).toEqual([10, 12]);
    expect(body.nextLine).toBe(13);
  });

  it('throws JobPollParseError when the last line is the JSON literal null', () => {
    expect(() => parseJobPollOutput('{"type":"a"}\nnull\n', { sinceLine: 0 })).toThrow(
      JobPollParseError
    );
    expect(() => parseJobPollOutput('3\n', { sinceLine: 0 })).toThrow(JobPollParseError);
  });

  it('clamps a negative or non-finite sinceLine like the argv builder', () => {
    const out = ['{"type":"a"}', trailer()].join('\n');
    for (const bad of [-3, Number.NaN, Number.NEGATIVE_INFINITY]) {
      const body = parseJobPollOutput(out, { sinceLine: bad });
      expect(body.events[0]?.line).toBe(0);
      expect(body.nextLine).toBe(1);
      expect(buildJobPollArgv(ID, bad)).toContain('0');
    }
  });

  it('measures the body size incrementally, not by re-serializing the whole body per line', () => {
    const lines = Array.from({ length: 400 }, (_, i) => JSON.stringify({ type: 'log', n: i }));
    const out = [...lines, trailer()].join('\n');
    const spy = vi.spyOn(JSON, 'stringify');
    let body: ReturnType<typeof parseJobPollOutput>;
    try {
      body = parseJobPollOutput(out, { sinceLine: 0, maxLines: 500 });
    } finally {
      spy.mockRestore();
    }
    const serialized = spy.mock.results.reduce(
      (sum, r) => sum + (typeof r.value === 'string' ? r.value.length : 0),
      0
    );
    expect(body.events).toHaveLength(400);
    // Linear: about the size of the output itself, where a per-line full serialization is quadratic.
    expect(serialized).toBeLessThan(out.length * 4);
  });

  it('keeps the exact byte cap with the incremental count', () => {
    const big = JSON.stringify({ type: 'log', text: 'x'.repeat(30 * 1024) });
    const out = [...Array.from({ length: 12 }, () => big), trailer()].join('\n');
    const body = parseJobPollOutput(out, { sinceLine: 98, maxLines: 500 });
    expect(Buffer.byteLength(JSON.stringify(body))).toBeLessThanOrEqual(MAX_BODY_BYTES);
    expect(body.more).toBe(true);
    const next = parseJobPollOutput([big, trailer()].join('\n'), { sinceLine: body.nextLine });
    expect(next.events[0]?.line).toBe(body.nextLine);
  });

  it('throws when the status trailer is missing', () => {
    expect(() => parseJobPollOutput('{"type":"a"}\n', { sinceLine: 0, maxLines: 5 })).toThrow(
      JobPollParseError
    );
    expect(() => parseJobPollOutput('', { sinceLine: 0, maxLines: 5 })).toThrow(JobPollParseError);
  });
});

describe('createTerminalLedger', () => {
  it('reports a terminal state once per job id', () => {
    const ledger = createTerminalLedger();
    expect(ledger.firstTerminal(ID, 'running')).toBe(false);
    expect(ledger.firstTerminal(ID, 'succeeded')).toBe(true);
    expect(ledger.firstTerminal(ID, 'succeeded')).toBe(false);
    expect(ledger.firstTerminal('j2-00000000', 'cancelled')).toBe(true);
  });

  it('forgets the oldest ids past its capacity', () => {
    const ledger = createTerminalLedger(2);
    ledger.firstTerminal('a', 'failed');
    ledger.firstTerminal('b', 'failed');
    ledger.firstTerminal('c', 'failed');
    expect(ledger.firstTerminal('c', 'failed')).toBe(false);
    expect(ledger.firstTerminal('a', 'failed')).toBe(true);
  });
});
