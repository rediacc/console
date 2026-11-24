import { describe, expect, it } from 'vitest';
import {
  applyExecutorEvents,
  type MachineRepoVerdict,
  parseExecutorEvents,
} from '../orphan-repos.js';

const MATCHED = 'e9304ffc-0c96-47f2-a2fb-6076c1df6f52';
const UNMATCHED = '7a1c0e55-2222-4333-8444-555566667777';
const PROTECTED = 'b9521afd-0cbd-4481-92ed-f798268a69dd';
const OLD_REASON = 'not in any config';

function row(guid: string, verdict: 'orphaned' | 'protected', reason: string): MachineRepoVerdict {
  return {
    guid,
    verdict,
    reason,
    mounted: false,
    running: false,
    containers: 0,
    isFork: false,
    size: '1G',
    modified: 'now',
  };
}

const ROWS = [
  row(MATCHED, 'orphaned', OLD_REASON),
  row(UNMATCHED, 'orphaned', OLD_REASON),
  row(PROTECTED, 'protected', 'in the current config'),
];

function line(fields: Record<string, string | null>): string {
  return JSON.stringify({ org: 'org12345', function: 'repository_create', ...fields });
}

describe('applyExecutorEvents', () => {
  const events = parseExecutorEvents(
    [
      line({
        machine: 'm1',
        repo: 'alpha',
        guid: MATCHED.toUpperCase(),
        at: '2026-11-20T10:00:00Z',
      }),
      line({ machine: 'm1', repo: 'beta', guid: PROTECTED, at: '2026-11-20T11:00:00Z' }),
      '',
    ].join('\n')
  );

  it('gives a matched orphan the executor reason with the event time', () => {
    const [matched] = applyExecutorEvents(ROWS, events, 'm1');
    expect(matched.verdict).toBe('orphaned');
    expect(matched.reason).not.toBe(OLD_REASON);
    expect(matched.reason).toContain('2026-11-20T10:00:00Z');
  });

  it('keeps the old reason of an unmatched orphan', () => {
    const joined = applyExecutorEvents(ROWS, events, 'm1');
    expect(joined[1]).toEqual(ROWS[1]);
  });

  it('keeps a protected image protected even when an event names it', () => {
    const joined = applyExecutorEvents(ROWS, events, 'm1');
    expect(joined[2]).toEqual(ROWS[2]);
  });

  it('ignores an event of another machine (control)', () => {
    const joined = applyExecutorEvents(ROWS, events, 'm2');
    expect(joined[0]).toEqual(ROWS[0]);
  });

  it('matches an event that carries no GUID on the repo name', () => {
    const byName = parseExecutorEvents(
      line({ machine: null, repo: MATCHED, guid: null, at: null })
    );
    const [matched] = applyExecutorEvents(ROWS, byName, 'm1');
    expect(matched.reason).not.toBe(OLD_REASON);
  });
});

describe('parseExecutorEvents', () => {
  it('refuses a line that is not a JSON object, naming the line', () => {
    expect(() => parseExecutorEvents(`${line({ machine: 'm1' })}\nnot json`)).toThrow(/2/);
  });
});
