import type { FeedbackListItem } from '@rediacc/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: vi.fn(), success: vi.fn() },
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import { displayStatus } from '../../services/feedback/list.js';
import type { FeedbackAuth, FetchFn } from '../../services/feedback/send.js';
import { runList, runShow } from '../feedback.js';

const item = (over: Partial<FeedbackListItem>): FeedbackListItem => ({
  id: 'rep-aaaa1111',
  fingerprint: 'abcdef012345',
  kind: 'bug',
  status: 'new',
  fixedIn: null,
  commandPath: 'repo up',
  occurrenceCount: 2,
  firstSeenAt: '2026-11-01T00:00:00.000Z',
  lastSeenAt: '2026-11-02T00:00:00.000Z',
  ...over,
});

const REPORTS = [
  item({}),
  item({ id: 'rep-bbbb2222', status: 'fixed', fixedIn: '1.4.0' }),
  item({ id: 'rep-bbbb3333', status: 'fixed', fixedIn: null }),
];
const BLOB = { payload: 'p', signature: 's', publicKeyId: '0123456789abcdef' };
const FREE: FeedbackAuth = {
  kind: 'free',
  credential: { license: BLOB, machineId: 'm-1' },
};

function deps(auth: FeedbackAuth = { kind: 'token' }) {
  const fetchFn = vi.fn().mockResolvedValue({ reports: REPORTS });
  return {
    fetchFn,
    full: { resolveAuth: async () => auth, fetchFn: fetchFn as unknown as FetchFn },
  };
}

beforeEach(() => {
  m.format.current = 'table';
  vi.clearAllMocks();
});

describe('displayStatus', () => {
  it('renders a fixed report as fixed-in-v<x>, without doubling a v', () => {
    expect(displayStatus({ status: 'fixed', fixedIn: '1.4.0' })).toBe('fixed-in-v1.4.0');
    expect(displayStatus({ status: 'fixed', fixedIn: 'v1.4.0' })).toBe('fixed-in-v1.4.0');
  });

  it('keeps the plain status when not fixed or when fixedIn is empty (controls)', () => {
    expect(displayStatus({ status: 'planned', fixedIn: '1.4.0' })).toBe('planned');
    expect(displayStatus({ status: 'fixed', fixedIn: null })).toBe('fixed');
  });
});

describe('rdc feedback list', () => {
  it('a token user reads GET /feedback with the stored credential', async () => {
    const { full, fetchFn } = deps();
    await runList({}, full);
    expect(fetchFn).toHaveBeenCalledWith('/account/api/v1/feedback', {
      method: 'GET',
      body: undefined,
    });
  });

  it('a FREE machine POSTs the blob and machine id to /feedback/query with no stored credential', async () => {
    const { full, fetchFn } = deps(FREE);
    await runList({ status: 'fixed,new' }, full);
    expect(fetchFn).toHaveBeenCalledWith('/account/api/v1/feedback/query', {
      method: 'POST',
      body: { license: BLOB, machineId: 'm-1', status: ['fixed', 'new'] },
      noAuth: true,
    });
  });

  it('--status goes into the GET query string', async () => {
    const { full, fetchFn } = deps();
    await runList({ status: 'new,planned' }, full);
    expect(fetchFn.mock.calls[0][0]).toBe('/account/api/v1/feedback?status=new%2Cplanned');
  });

  it('an unknown status is refused before any request (control)', async () => {
    const { full, fetchFn } = deps();
    await expect(runList({ status: 'new,bogus' }, full)).rejects.toThrow('feedback.badStatus');
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it('text lists id, short fingerprint, status and both dates, a fixed one as fixed-in-v<x>', async () => {
    const { full } = deps();
    await runList({}, full);
    const text = m.print.mock.calls[0][0] as string;
    const lines = text.split('\n');
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe(
      'rep-aaaa1111  abcdef012345  new  2026-11-01T00:00:00.000Z  2026-11-02T00:00:00.000Z  repo up'
    );
    expect(lines[1]).toContain('fixed-in-v1.4.0');
    expect(lines[0]).not.toContain('fixed-in');
  });

  it('-o json carries every field plus the rendered status', async () => {
    m.format.current = 'json';
    const { full } = deps();
    await runList({}, full);
    const [data, format] = m.print.mock.calls[0];
    expect(format).toBe('json');
    expect(data.reports[1]).toMatchObject({
      id: 'rep-bbbb2222',
      fingerprint: 'abcdef012345',
      status: 'fixed',
      fixedIn: '1.4.0',
      statusText: 'fixed-in-v1.4.0',
      firstSeenAt: '2026-11-01T00:00:00.000Z',
      lastSeenAt: '2026-11-02T00:00:00.000Z',
    });
    expect(data.reports[0].statusText).toBe('new');
  });

  it('an empty list says so', async () => {
    const { full, fetchFn } = deps();
    fetchFn.mockResolvedValue({ reports: [] });
    await runList({}, full);
    expect(m.print).toHaveBeenCalledWith('feedback.noReports');
  });
});

describe('rdc feedback show', () => {
  it('shows one report by exact id with fixed-in-v<x>', async () => {
    const { full } = deps();
    await runShow('rep-bbbb2222', full);
    const text = m.print.mock.calls[0][0] as string;
    expect(text).toContain('rep-bbbb2222');
    expect(text).toContain('fixed-in-v1.4.0');
    expect(text).not.toContain('rep-aaaa1111');
  });

  it('a unique prefix resolves, an ambiguous one and an unknown one are refused (controls)', async () => {
    await runShow('rep-aaaa', deps().full);
    expect(m.print.mock.calls[0][0]).toContain('rep-aaaa1111');
    await expect(runShow('rep-bbbb', deps().full)).rejects.toThrow('feedback.ambiguousId');
    await expect(runShow('nope', deps().full)).rejects.toThrow('feedback.noSuchReport');
    await expect(runShow('', deps().full)).rejects.toThrow('feedback.noSuchReport');
  });

  it('-o json prints the one report with its rendered status', async () => {
    m.format.current = 'json';
    await runShow('rep-bbbb2222', deps().full);
    expect(m.print.mock.calls[0][0]).toMatchObject({
      id: 'rep-bbbb2222',
      statusText: 'fixed-in-v1.4.0',
    });
  });

  it('a FREE machine reads through POST /feedback/query', async () => {
    const { full, fetchFn } = deps(FREE);
    await runShow('rep-aaaa1111', full);
    expect(fetchFn.mock.calls[0][0]).toBe('/account/api/v1/feedback/query');
  });
});
