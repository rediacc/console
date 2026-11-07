/**
 * The store pick and fallback rules of a restore (multi-target C3).
 *
 * The ranking route is declared wire (`GET /backups/stores/lineage/:lineageGuid`), so the pick is tested against both
 * its answer and its absence: an older account server answers 404, which means `home` alone and says nothing.
 */
import { existsSync, readFileSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: mockFetch }));
const mockWarn = vi.hoisted(() => vi.fn());
const mockInfo = vi.hoisted(() => vi.fn());
vi.mock('../../core/output.js', () => ({ outputService: { warn: mockWarn, info: mockInfo } }));
const mockRender = vi.hoisted(() => vi.fn());
vi.mock('../../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRender,
}));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const {
  ROLLBACK_LINES,
  executeWithStoreFallback,
  isStoreFailure,
  pickStores,
  runWithFallback,
  storeParam,
} = await import('../backup-store-pick.js');

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

describe('isStoreFailure on a path restore', () => {
  it('is not a store failure when the path is absent, has no listing, or the copy-out rolled back', () => {
    expect(isStoreFailure({ exitCode: 19, error: 'HTTP 502 bad gateway' })).toBe(false);
    expect(isStoreFailure({ exitCode: 18, error: 'timed out' })).toBe(false);
    expect(
      isStoreFailure({ stderr: 'copy failed: timed out (every path this run created was removed)' })
    ).toBe(false);
  });
});

describe('isStoreFailure on a rollback line in any renet locale', () => {
  it.each(ROLLBACK_LINES)('is not a store failure when the line reads %s', (line) => {
    expect(isStoreFailure({ stderr: `copy failed: connection reset (${line})` })).toBe(false);
  });

  it('lists every locale of both renet catalog entries', () => {
    const dir = new URL('../../../../../../private/renet/pkg/i18n/locales/', import.meta.url);
    expect(existsSync(dir), 'renet locale catalogs are not checked out').toBe(true);
    const lines: string[] = [];
    for (const lang of [
      'ar',
      'de',
      'en',
      'es',
      'et',
      'fr',
      'it',
      'ja',
      'ko',
      'pt',
      'ru',
      'tr',
      'zh',
    ]) {
      const source = readFileSync(new URL(`${lang}.go`, dir), 'utf8');
      for (const key of ['rolled_back', 'rollback_incomplete']) {
        const found = new RegExp(`"restorepath\\.${key}", "(.*)"\\)`).exec(source);
        expect(found, `${lang} ${key}`).not.toBeNull();
        lines.push((found?.[1] ?? '').split(/\s*[:：]|%s/)[0]);
      }
    }
    for (const line of lines) expect(ROLLBACK_LINES).toContain(line);
  });
});

describe('executeWithStoreFallback', () => {
  const ok = { success: true, exitCode: 0, durationMs: 1 };
  const bad = (error: string) => ({ success: false, exitCode: 1, error, durationMs: 1 });

  it('returns the first success, announcing a non-home store, and renders nothing', async () => {
    const run = vi.fn(async () => ok);
    const out = await executeWithStoreFallback(
      { stores: ['eu-west'], explicit: true },
      run,
      'failed'
    );
    expect(out.store).toBe('eu-west');
    expect(mockInfo).toHaveBeenCalledTimes(1);
    expect(mockRender).not.toHaveBeenCalled();
  });

  it('says nothing for home alone served first, as before stores existed', async () => {
    await executeWithStoreFallback({ stores: ['home'], explicit: false }, async () => ok, 'failed');
    expect(mockInfo).not.toHaveBeenCalled();
  });

  it('renders the failure that ends the run, with the executor message or the fallback text', async () => {
    const run = vi.fn(async () => bad('HTTP 502 bad gateway'));
    const out = await executeWithStoreFallback(
      { stores: ['a', 'b'], explicit: false },
      run,
      'failed'
    );
    expect(run).toHaveBeenCalledTimes(2);
    expect(out.store).toBe('b');
    expect(mockRender).toHaveBeenCalledTimes(1);
    expect(mockRender.mock.calls[0][1]).toBe('HTTP 502 bad gateway');
  });
});
