/**
 * The store pick and fallback rules of a restore (multi-target C3).
 *
 * The ranking route is declared wire (`GET /backups/stores/lineage/:lineageGuid`), so the pick is tested against both
 * its answer and its absence: an older account server answers 404, which means `home` alone and says nothing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: mockFetch }));
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../../core/output.js', () => ({ outputService: { warn: mockWarn } }));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const { isStoreFailure, pickStores, runWithFallback, storeParam } = await import(
  '../backup-store-pick.js'
);

const row = (storeId: string, newestSnapshotId: string | null = 's') => ({
  storeId,
  newestSnapshotId,
  newestSnapshotAt: newestSnapshotId ? '2026-11-07T00:00:00Z' : null,
  lastVerifyOk: true,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('pickStores', () => {
  it('takes the named store alone and asks the server nothing', async () => {
    expect(await pickStores('L', 'eu-west')).toEqual({ stores: ['eu-west'], explicit: true });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('keeps the account ranking and drops a store that holds no snapshot', async () => {
    mockFetch.mockResolvedValue({ stores: [row('eu-west'), row('empty', null), row('home')] });
    expect(await pickStores('L')).toEqual({ stores: ['eu-west', 'home'], explicit: false });
    expect(mockFetch).toHaveBeenCalledWith('/account/api/v1/backups/stores/lineage/L');
  });

  it('answers home alone for an older account server (404)', async () => {
    mockFetch.mockRejectedValue(Object.assign(new Error('not found'), { status: 404 }));
    expect(await pickStores('L')).toEqual({ stores: ['home'], explicit: false });
  });

  it('answers home alone for an empty ranking', async () => {
    mockFetch.mockResolvedValue({ stores: [] });
    expect(await pickStores('L')).toEqual({ stores: ['home'], explicit: false });
  });

  it('reads the home store, with a warning, when the ranking cannot be read', async () => {
    mockFetch.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    expect(await pickStores('L')).toEqual({ stores: ['home'], explicit: false });
    expect(mockWarn).toHaveBeenCalledWith(
      `commands.backup.restore.storeRankingUnreadable ${JSON.stringify({ reason: 'boom' })}`
    );
  });
});

describe('storeParam', () => {
  it('omits home, which a renet without --store also accepts', () => {
    expect(storeParam('home')).toEqual({});
    expect(storeParam('eu-west')).toEqual({ store: 'eu-west' });
  });
});

describe('isStoreFailure', () => {
  it.each([
    'HTTP 502 bad gateway',
    'the grant was refused by the store',
    'dial tcp: ECONNREFUSED',
    'request timed out',
    'backup session refused: store suspended',
  ])('is the store at fault: %s', (error) => {
    expect(isStoreFailure({ error })).toBe(true);
  });

  it.each([
    'snapshot snap-1 not found',
    'manifest invalid',
    'verification failed for the snapshot',
    'something nobody classified',
  ])('is not the store at fault: %s', (error) => {
    expect(isStoreFailure({ error })).toBe(false);
  });

  it('lets the snapshot own fault win over a store word in the same output', () => {
    expect(isStoreFailure({ stderr: 'snapshot snap-1 not found (HTTP 502 from the proxy)' })).toBe(
      false
    );
  });
});

describe('runWithFallback', () => {
  const fail = (error: string) => ({ ok: false as const, failure: { error } });
  const ok = { ok: true as const, value: 'done' };

  it('serves from the first store that succeeds and names it', async () => {
    const attempt = vi.fn().mockResolvedValueOnce(fail('HTTP 503')).mockResolvedValueOnce(ok);
    const onFallback = vi.fn();
    const result = await runWithFallback(
      { stores: ['a', 'b', 'c'], explicit: false },
      attempt,
      onFallback
    );
    expect(result).toEqual({ ok: true, store: 'b', value: 'done' });
    expect(attempt).toHaveBeenCalledTimes(2);
    expect(onFallback).toHaveBeenCalledWith('a', 'b', { error: 'HTTP 503' });
  });

  it('stops at a snapshot own fault', async () => {
    const attempt = vi.fn().mockResolvedValue(fail('snapshot s not found'));
    const result = await runWithFallback({ stores: ['a', 'b'], explicit: false }, attempt);
    expect(result.ok).toBe(false);
    expect(result.store).toBe('a');
    expect(attempt).toHaveBeenCalledTimes(1);
  });

  it('never moves on from an explicit store', async () => {
    const attempt = vi.fn().mockResolvedValue(fail('HTTP 503'));
    const result = await runWithFallback({ stores: ['a', 'b'], explicit: true }, attempt);
    expect(result.ok).toBe(false);
    expect(attempt).toHaveBeenCalledTimes(1);
  });

  it('reports the last store when every one fails for its own reasons', async () => {
    const attempt = vi.fn().mockResolvedValue(fail('HTTP 503'));
    const result = await runWithFallback({ stores: ['a', 'b'], explicit: false }, attempt);
    expect(result).toEqual({ ok: false, store: 'b', failure: { error: 'HTTP 503' } });
  });
});
