/**
 * `subscription notices`: the listing window, paging, the names joined from the local config, the
 * read marks, and the no-token refusal.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockPrint = vi.hoisted(() => vi.fn());
const infos = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    report: vi.fn(),
    warn: vi.fn(),
    success: vi.fn(),
    print: mockPrint,
  },
}));

const tokenKind = vi.hoisted(() => ({ value: 'ready' }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: tokenKind.value, token: {} }),
  getSubscriptionScopeMismatch: () => null,
  getSubscriptionServerUrl: () => 'http://localhost',
}));
const mockConfig = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue(undefined),
    getCurrent: () => Promise.resolve(mockConfig.value),
  },
}));
const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
// subscription-actions pulls the renet and job graph in for the verbs this one does not run.
vi.mock('../../services/account/license.js', () => ({}));

import { setOutputFormat } from '../../utils/errors.js';
import { executeSubscriptionNotices, type NoticeWire } from '../subscription-notices.js';

const NOW = Date.parse('2026-11-12T12:00:00.000Z');
const DAY = 24 * 60 * 60 * 1000;
const iso = (daysAgo: number) => new Date(NOW - daysAgo * DAY).toISOString();

const WEB = '11111111-aaaa-4aaa-8aaa-000000000001';
const STRANGER = '44444444-dddd-4ddd-8ddd-000000000004';

function notice(id: string, daysAgo: number, extra: Partial<NoticeWire> = {}): NoticeWire {
  return {
    id,
    kind: 'repo_licence',
    severity: 'warning',
    createdAt: iso(daysAgo + 1),
    updatedAt: iso(daysAgo),
    readAt: null,
    dismissedAt: null,
    orgId: 'org1',
    teamId: null,
    subscriptionId: 'sub1',
    payload: {
      counts: { hardExpired: 1, refreshRecommended: 1 },
      items: [
        { guid: WEB, kind: 'grand', freshness: 'hard_expired' },
        { guid: STRANGER, kind: 'grand', freshness: 'refresh_recommended' },
      ],
    },
    ...extra,
  };
}

/** The listing GETs the CLI made, as URLSearchParams. */
function listQueries(): URLSearchParams[] {
  return mockFetch.mock.calls
    .map((c) => c[0] as string)
    .filter((p) => p.startsWith('/account/api/v1/notices?'))
    .map((p) => new URLSearchParams(p.split('?')[1]));
}

function readPosts(): string[] {
  return mockFetch.mock.calls
    .filter((c) => (c[1] as { method?: string } | undefined)?.method === 'POST')
    .map((c) => c[0] as string);
}

function respondWith(pages: { notices: NoticeWire[]; nextCursor: string | null }[]) {
  let call = 0;
  mockFetch.mockImplementation((_path: string, init?: { method?: string }) => {
    if (init?.method === 'POST') return Promise.resolve({});
    return Promise.resolve(pages[call++] ?? { notices: [], nextCursor: null });
  });
}

function printedRows(): Record<string, unknown>[] {
  return mockPrint.mock.calls[0][0] as Record<string, unknown>[];
}

describe('subscription notices', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    infos.length = 0;
    mockPrint.mockReset();
    mockFetch.mockReset();
    tokenKind.value = 'ready';
    setOutputFormat('table');
    mockConfig.value = {
      resources: {
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: WEB } },
          },
        },
      },
    };
  });

  afterEach(() => {
    vi.useRealTimers();
    setOutputFormat('table');
  });

  it('lists the undismissed notices with names joined from the config', async () => {
    respondWith([{ notices: [notice('n1', 1)], nextCursor: null }]);
    await executeSubscriptionNotices();
    expect(listQueries()).toHaveLength(1);
    expect(listQueries()[0].get('includeDismissed')).toBeNull();
    const [row] = printedRows();
    expect(row).toMatchObject({ age: '1d', kind: 'repo_licence', severity: 'warning' });
    expect(row.summary).toContain('"hardExpired":1');
    expect(row.summary).toContain('web@box');
    expect(row.summary).toContain('44444444');
    expect(row.summary).not.toContain(STRANGER);
  });

  it('stops at the first notice older than 30 days and lists only the recent ones', async () => {
    respondWith([
      { notices: [notice('new', 2), notice('old', 40)], nextCursor: 'c1' },
      { notices: [notice('older', 90)], nextCursor: null },
    ]);
    await executeSubscriptionNotices();
    expect(listQueries()).toHaveLength(1);
    expect(printedRows()).toHaveLength(1);
  });

  it('follows nextCursor to the end and includes dismissed notices with --all', async () => {
    respondWith([
      { notices: [notice('a', 2), notice('b', 3)], nextCursor: 'c1' },
      { notices: [notice('c', 50, { dismissedAt: iso(49) })], nextCursor: 'c2' },
      { notices: [notice('d', 200)], nextCursor: null },
    ]);
    await executeSubscriptionNotices({ all: true });
    const queries = listQueries();
    expect(queries).toHaveLength(3);
    expect(queries.every((q) => q.get('includeDismissed') === '1')).toBe(true);
    expect(queries.map((q) => q.get('cursor'))).toEqual([null, 'c1', 'c2']);
    expect(printedRows()).toHaveLength(4);
  });

  it('follows nextCursor in the default listing while the notices stay inside the window', async () => {
    respondWith([
      { notices: [notice('a', 2)], nextCursor: 'c1' },
      { notices: [notice('b', 5)], nextCursor: null },
    ]);
    await executeSubscriptionNotices();
    expect(listQueries().map((q) => q.get('cursor'))).toEqual([null, 'c1']);
    expect(printedRows()).toHaveLength(2);
  });

  it('refuses a server that answers the same cursor twice, instead of looping', async () => {
    respondWith([
      { notices: [notice('a', 2)], nextCursor: 'c1' },
      { notices: [notice('b', 3)], nextCursor: 'c1' },
    ]);
    await expect(executeSubscriptionNotices()).rejects.toThrow('cursor c1 twice');
  });

  it('adds name and machine to every licence item under -o json', async () => {
    respondWith([{ notices: [notice('n1', 1)], nextCursor: null }]);
    setOutputFormat('json');
    await executeSubscriptionNotices();
    const [out] = mockPrint.mock.calls[0][0] as NoticeWire[];
    expect(out.payload.items).toEqual([
      { guid: WEB, kind: 'grand', freshness: 'hard_expired', name: 'web', machine: 'box' },
      {
        guid: STRANGER,
        kind: 'grand',
        freshness: 'refresh_recommended',
        name: null,
        machine: null,
      },
    ]);
    expect(out.payload.counts).toEqual({ hardExpired: 1, refreshRecommended: 1 });
    expect(mockPrint.mock.calls[0][1]).toBe('json');
  });

  it('leaves a notice that is not a licence notice untouched under -o json (control)', async () => {
    const terms = notice('t1', 1, { kind: 'terms_notice', payload: { version: '2026-11' } });
    respondWith([{ notices: [terms], nextCursor: null }]);
    setOutputFormat('json');
    await executeSubscriptionNotices();
    expect(mockPrint.mock.calls[0][0]).toEqual([terms]);
  });

  it('summarizes the other kinds and names an unknown kind by itself', async () => {
    respondWith([
      {
        notices: [
          notice('t1', 1, {
            kind: 'terms_notice',
            payload: { version: '2026-11', effective: '2026-12-01T00:00:00Z' },
          }),
          notice('x1', 1, { kind: 'brand_new_kind', payload: {} }),
        ],
        nextCursor: null,
      },
    ]);
    await executeSubscriptionNotices();
    const summaries = printedRows().map((r) => r.summary);
    expect(summaries[0]).toBe(
      'commands.subscription.notices.summary.termsNotice:{"version":"2026-11","date":"2026-12-01"}'
    );
    expect(summaries[1]).toBe('brand_new_kind');
  });

  it('prints a line, not an empty table, when there are no notices', async () => {
    respondWith([{ notices: [], nextCursor: null }]);
    await executeSubscriptionNotices();
    expect(mockPrint).not.toHaveBeenCalled();
    expect(infos).toEqual(['commands.subscription.notices.empty']);
  });

  it('lists only unread notices with --unread, and all of them without it (control)', async () => {
    const read = notice('r1', 1, { readAt: iso(0) });
    respondWith([{ notices: [read, notice('u1', 2)], nextCursor: null }]);
    await executeSubscriptionNotices({ unread: true });
    expect(printedRows()).toHaveLength(1);
    mockPrint.mockReset();
    respondWith([{ notices: [read, notice('u1', 2)], nextCursor: null }]);
    await executeSubscriptionNotices();
    expect(printedRows()).toHaveLength(2);
  });

  it('posts read for each listed unread id with --mark-read, and not for one already read', async () => {
    respondWith([
      {
        notices: [notice('u1', 1), notice('r1', 2, { readAt: iso(1) }), notice('u2', 3)],
        nextCursor: null,
      },
    ]);
    await executeSubscriptionNotices({ markRead: true });
    expect(readPosts()).toEqual([
      '/account/api/v1/notices/u1/read',
      '/account/api/v1/notices/u2/read',
    ]);
    expect(infos).toEqual(['commands.subscription.notices.markedRead:{"count":2}']);
  });

  it('posts no read mark without --mark-read (control)', async () => {
    respondWith([{ notices: [notice('u1', 1)], nextCursor: null }]);
    await executeSubscriptionNotices();
    expect(readPosts()).toEqual([]);
  });

  it('keeps stdout to the data under -o json when marking read', async () => {
    respondWith([{ notices: [notice('u1', 1)], nextCursor: null }]);
    setOutputFormat('json');
    await executeSubscriptionNotices({ markRead: true });
    expect(readPosts()).toHaveLength(1);
    expect(infos).toEqual([]);
  });

  it('fails when a read mark is refused, after the list was printed', async () => {
    mockFetch.mockImplementation((_path: string, init?: { method?: string }) =>
      init?.method === 'POST'
        ? Promise.reject(new Error('403 forbidden'))
        : Promise.resolve({ notices: [notice('u1', 1)], nextCursor: null })
    );
    await expect(executeSubscriptionNotices({ markRead: true })).rejects.toThrow('403 forbidden');
    expect(mockPrint).toHaveBeenCalledTimes(1);
  });

  it('gives short GUIDs when there is no config', async () => {
    mockConfig.value = null;
    respondWith([{ notices: [notice('n1', 1)], nextCursor: null }]);
    await executeSubscriptionNotices();
    expect(printedRows()[0].summary).toContain('11111111');
  });

  it('refuses with the login diagnostic when there is no token, and calls nothing', async () => {
    tokenKind.value = 'missing';
    await expect(executeSubscriptionNotices()).rejects.toThrow('errors.subscription.notLoggedIn');
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
