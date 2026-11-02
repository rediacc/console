/**
 * Strategy-level retention (plan F4, F7): the spec parser, the cron-fit check and the push of a
 * strategy's policy to its lineages.
 *
 * The push decides what the server DELETES, so the case that matters is ownership: the automatic
 * pushes must never undo a per-repo `retention set`, and only the explicit `strategy set` may
 * overwrite one.
 */
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../account/account-client.js', () => ({ accountServerFetch: mockFetch }));

const mockGetCurrent = vi.hoisted(() => vi.fn());
vi.mock('../config/config-resources.js', () => ({ configService: { getCurrent: mockGetCurrent } }));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));

const {
  cronCadence,
  parseRetentionSpec,
  pushStrategyRetention,
  retentionCronMismatches,
  RetentionSpecError,
  strategyLineages,
} = await import('../backup/backup-retention.js');

const rec = (guid: string, grand?: string) => ({ repositoryGuid: guid, grandGuid: grand });
const config = {
  resources: {
    repositories: {
      shop: {
        grand: 'latest',
        placement: { machine: 'm1' },
        tags: { latest: rec('g-shop'), fork: rec('f-shop', 'g-shop') },
      },
      mail: { grand: 'latest', placement: { machine: 'm2' }, tags: { latest: rec('g-mail') } },
      wiki: { grand: 'latest', placement: { machine: 'm1' }, tags: { latest: rec('g-wiki') } },
    },
  },
} as unknown as RdcConfig;

describe('parseRetentionSpec', () => {
  it('maps spec names to wire knobs', () => {
    expect(parseRetentionSpec('last=7, daily=7,weekly=4,monthly=6,hourly=2,yearly=1')).toEqual({
      keepLast: 7,
      keepDaily: 7,
      keepWeekly: 4,
      keepMonthly: 6,
      keepHourly: 2,
      keepYearly: 1,
    });
  });

  it('treats empty and none as a clear', () => {
    expect(parseRetentionSpec('')).toBeUndefined();
    expect(parseRetentionSpec(' None ')).toBeUndefined();
  });

  it.each(['daily=', 'daily=1=2', 'daily=-1', 'weeks=2', 'daily=1,daily=2', 'daily=1,'])(
    'refuses %s',
    (raw) => {
      expect(() => parseRetentionSpec(raw)).toThrow(RetentionSpecError);
    }
  );
});

describe('cron fit (F7)', () => {
  it.each([
    ['0 3 * * *', 'daily'],
    ['0 */6 * * *', 'subdaily'],
    ['*/15 * * * *', 'subdaily'],
    ['0 3 * * 0', 'weekly'],
    ['0 3 1 * *', 'monthly'],
    ['0 3 * * 1-5', 'daily'],
  ])('%s is %s', (cron, cadence) => {
    expect(cronCadence(cron)).toBe(cadence);
  });

  it('flags keepHourly on a daily cron', () => {
    expect(retentionCronMismatches({ keepHourly: 24, keepDaily: 7 }, '0 3 * * *')).toEqual([
      { knob: 'hourly', cadence: 'daily' },
    ]);
  });

  it('flags keepDaily on a weekly cron, and hourly with it', () => {
    const found = retentionCronMismatches(
      { keepHourly: 1, keepDaily: 7, keepWeekly: 4 },
      '0 3 * * 0'
    );
    expect(found.map((m) => m.knob)).toEqual(['hourly', 'daily']);
  });

  it('flags nothing when the cron is fine enough, or a knob is zero', () => {
    expect(retentionCronMismatches({ keepHourly: 24, keepDaily: 7 }, '0 * * * *')).toEqual([]);
    expect(retentionCronMismatches({ keepHourly: 0 }, '0 3 * * *')).toEqual([]);
    expect(retentionCronMismatches(undefined, '0 3 * * *')).toEqual([]);
  });
});

describe('strategyLineages', () => {
  it('covers every family, a fork through its parent lineage', () => {
    expect(strategyLineages({}, config)).toEqual(['g-mail', 'g-shop', 'g-wiki']);
  });

  it('honours include and exclude by family name and by name:tag', () => {
    expect(strategyLineages({ include: ['shop'] }, config)).toEqual(['g-shop']);
    expect(strategyLineages({ exclude: ['mail', 'wiki:latest'] }, config)).toEqual(['g-shop']);
  });

  it('narrows to the repositories placed on the machine', () => {
    expect(strategyLineages({}, config, 'm1')).toEqual(['g-shop', 'g-wiki']);
  });
});

describe('pushStrategyRetention', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockGetCurrent.mockResolvedValue(config);
  });

  const puts = () =>
    mockFetch.mock.calls
      .filter((c) => (c[1] as { method?: string } | undefined)?.method === 'PUT')
      .map((c) => (c[1] as { body: Record<string, unknown> }).body);

  it('passes the PUT body as an object, since accountServerFetch serializes it itself', async () => {
    mockFetch.mockResolvedValue({ policies: [] });
    await pushStrategyRetention({ retention: { keepLast: 3 } }, {
      overwrite: true,
      machineName: 'm1',
    } as never);
    const bodies = puts();
    expect(bodies.length).toBeGreaterThan(0);
    for (const body of bodies) expect(typeof body).toBe('object');
  });

  it('automatic push fills only lineages with no lineage-level policy, so a per-repo set wins', async () => {
    mockFetch.mockImplementation((_url: string, init?: { method?: string }) =>
      Promise.resolve(
        init?.method === 'PUT'
          ? { policies: [] }
          : {
              policies: [
                // shop was set by hand; wiki only has a stream-level row, which is not a lineage default.
                { lineageGuid: 'g-shop', streamId: null },
                { lineageGuid: 'g-wiki', streamId: 's-1' },
              ],
            }
      )
    );

    const result = await pushStrategyRetention(
      { retention: { keepDaily: 7 } },
      { overwrite: false }
    );

    expect(result).toEqual({ pushed: 2, kept: 1 });
    expect(puts()).toEqual([
      { lineageGuid: 'g-mail', keepDaily: 7 },
      { lineageGuid: 'g-wiki', keepDaily: 7 },
    ]);
  });

  it('explicit push overwrites every covered lineage and never reads the server first', async () => {
    mockFetch.mockResolvedValue({ policies: [] });

    const result = await pushStrategyRetention(
      { retention: { keepLast: 3 }, include: ['shop'] },
      { overwrite: true }
    );

    expect(result).toEqual({ pushed: 1, kept: 0 });
    expect(puts()).toEqual([{ lineageGuid: 'g-shop', keepLast: 3 }]);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('pushes nothing for a strategy with no retention', async () => {
    expect(await pushStrategyRetention({}, { overwrite: true })).toEqual({ pushed: 0, kept: 0 });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
