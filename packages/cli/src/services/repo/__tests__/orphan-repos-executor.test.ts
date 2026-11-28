import { describe, expect, it, vi } from 'vitest';
import {
  applyExecutorEvents,
  archivedNames,
  type MachineRepoVerdict,
  parseExecutorEvents,
} from '../orphan-repos.js';

const MATCHED = 'e9304ffc-0c96-47f2-a2fb-6076c1df6f52';
const UNMATCHED = '7a1c0e55-2222-4333-8444-555566667777';
const PROTECTED = 'b9521afd-0cbd-4481-92ed-f798268a69dd';
const NAMED = '3c5d7e9f-1111-4222-8333-444455556666';
const OLD_REASON = 'not in any config';

function row(
  guid: string,
  verdict: 'orphaned' | 'protected',
  reason: string,
  name: string | null = null
): MachineRepoVerdict {
  return {
    guid,
    name,
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
  row(NAMED, 'orphaned', OLD_REASON, 'alpha'),
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

  it('matches an event that carries no GUID on the archived name of the orphan', () => {
    const byName = parseExecutorEvents(
      line({ machine: 'm1', repo: 'alpha', guid: null, at: '2026-11-20T12:00:00Z' })
    );
    const joined = applyExecutorEvents(ROWS, byName, 'm1');
    expect(joined[3].reason).toContain('2026-11-20T12:00:00Z');
    expect(joined.slice(0, 3)).toEqual(ROWS.slice(0, 3));
  });

  it('does not match an event that carries neither a GUID nor a repo name', () => {
    const anonymous = parseExecutorEvents(
      line({ machine: 'm1', repo: null, guid: null, at: '2026-11-20T13:00:00Z' })
    );
    expect(applyExecutorEvents(ROWS, anonymous, 'm1')).toEqual(ROWS);
  });

  it('does not match a GUID-less event to an orphan with no archived name (control)', () => {
    const byName = parseExecutorEvents(
      line({ machine: 'm1', repo: 'gamma', guid: null, at: null })
    );
    expect(applyExecutorEvents(ROWS, byName, 'm1')).toEqual(ROWS);
  });

  it('does not fall back to the name when the event carries a GUID that names another image (control)', () => {
    const other = parseExecutorEvents(
      line({ machine: 'm1', repo: 'alpha', guid: UNMATCHED.replace('7a1c', '0000'), at: null })
    );
    expect(applyExecutorEvents(ROWS, other, 'm1')).toEqual(ROWS);
  });

  it('ignores an event that names no machine (control)', () => {
    const noMachine = parseExecutorEvents(
      [
        line({ machine: null, repo: 'alpha', guid: MATCHED, at: null }),
        line({ machine: null, repo: 'alpha', guid: null, at: null }),
      ].join('\n')
    );
    expect(applyExecutorEvents(ROWS, noMachine, 'm1')).toEqual(ROWS);
  });

  it('ignores a GUID-less event of another machine (control)', () => {
    const byName = parseExecutorEvents(
      line({ machine: 'm2', repo: 'alpha', guid: null, at: null })
    );
    expect(applyExecutorEvents(ROWS, byName, 'm1')).toEqual(ROWS);
  });
});

describe('parseExecutorEvents', () => {
  it('refuses a line that is not a JSON object, naming the line', () => {
    expect(() => parseExecutorEvents(`${line({ machine: 'm1' })}\nnot json`)).toThrow(
      'Executor events file, line 2 is not a JSON object'
    );
  });
});

describe('tagged archived names (review 0ba0b83a.1)', () => {
  const tagged = [row(NAMED, 'orphaned', OLD_REASON, 'alpha:v2')];
  const base = { machine: 'm1', guid: null, at: '2026-11-20T10:00:00Z' };

  it('a GUID-less event matches the orphan whose archived ref is name:tag, by name or by whole ref', () => {
    for (const repo of ['alpha', 'alpha:v2']) {
      const events = parseExecutorEvents(line({ ...base, repo }));
      expect(applyExecutorEvents(tagged, events, 'm1')[0].reason).not.toBe(OLD_REASON);
    }
  });

  it('control: another repo name leaves the orphan reason alone', () => {
    const events = parseExecutorEvents(line({ ...base, repo: 'beta' }));
    expect(applyExecutorEvents(tagged, events, 'm1')[0].reason).toBe(OLD_REASON);
  });
});

describe('two orphans sharing a name with different tags (review 4475304c.2)', () => {
  const V1 = '3c5d7e9f-1111-4222-8333-444455556661';
  const V2 = '3c5d7e9f-1111-4222-8333-444455556662';
  const pair = [
    row(V1, 'orphaned', OLD_REASON, 'alpha:v1'),
    row(V2, 'orphaned', OLD_REASON, 'alpha:v2'),
  ];
  const base = { machine: 'm1', guid: null, at: '2026-11-20T10:00:00Z' };

  it('an event naming the whole ref marks only that orphan', () => {
    const events = parseExecutorEvents(line({ ...base, repo: 'alpha:v2' }));
    const reasons = applyExecutorEvents(pair, events, 'm1').map((r) => r.reason);
    expect(reasons[0]).toBe(OLD_REASON);
    expect(reasons[1]).not.toBe(OLD_REASON);
  });

  it('an event naming only the name cannot pick a tag and marks every orphan of that name', () => {
    const events = parseExecutorEvents(line({ ...base, repo: 'alpha' }));
    const reasons = applyExecutorEvents(pair, events, 'm1').map((r) => r.reason);
    expect(reasons[0]).not.toBe(OLD_REASON);
    expect(reasons[1]).toBe(reasons[0]);
  });
});

describe('archivedNames (review 0ba0b83a.2)', () => {
  it('keys archived records by lowercase GUID and composes name:tag', async () => {
    const { configService } = await import('../../config/config-resources.js');
    const spy = vi
      .spyOn(configService, 'listArchivedRepositories')
      .mockResolvedValue([
        { name: 'alpha', tag: 'v2', repositoryGuid: 'ABCDEF00-0000-4000-8000-000000000001' },
        { name: 'beta', repositoryGuid: 'ABCDEF00-0000-4000-8000-000000000002' },
        { name: 'noguid' },
      ] as never);
    try {
      const names = await archivedNames();
      expect(names.get('abcdef00-0000-4000-8000-000000000001')).toBe('alpha:v2');
      expect(names.get('abcdef00-0000-4000-8000-000000000002')).toBe('beta');
      expect(names.size).toBe(2);
    } finally {
      spy.mockRestore();
    }
  });
});
