/**
 * The store pick and fallback rules of a restore (multi-target C3).
 *
 * The ranking route is declared wire (`GET /backups/stores/lineage/:lineageGuid`), so the pick is tested against both
 * its answer and its absence: an older account server answers 404, which means `home` alone and says nothing.
 */
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
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
  executeWithStoreFallback,
  isStoreFailure,
  pickStores,
  runWithFallback,
  runWithFallbackAt,
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

// The strings renet really prints (pkg/i18n/locales/en.go session.*) and Go net/http errors it passes through (#5eb1d4c7).
describe('isStoreFailure on renet and Go error strings', () => {
  it.each([
    'Get "https://store.example/c/ab": dial tcp 10.0.0.9:443: i/o timeout',
    'Get "https://store.example/c/ab": context deadline exceeded',
    'Get "https://store.example/c/ab": net/http: request canceled (Client.Timeout exceeded while awaiting headers)',
    'Get "https://store.example/c/ab": net/http: TLS handshake timeout',
    'Get "https://store.example/c/ab": dial tcp: lookup store.example on 127.0.0.53:53: no such host',
    'the storage session was re-minted and the server still refuses it',
    'grant response was not JSON',
    'read-grant response was not JSON',
    'session response was not JSON',
  ])('falls back on %s', (error) => {
    expect(isStoreFailure({ error })).toBe(true);
  });

  it.each([
    'the account server opened the backup session on store eu-west, not the requested office; nothing is sent to another store',
    "the account server did not confirm backup store office; a server without stores serves only the home store, so the session is refused rather than filling home under another store's name",
  ])('never falls back on a misconfigured server: %s', (error) => {
    expect(isStoreFailure({ error })).toBe(false);
  });

  it.each([
    'snapshot snap-1 not found in the manifest index: i/o timeout',
    'chunk verification failed: context deadline exceeded',
    '{"code":"ROLLED_BACK","message":"copy failed: no such host"}',
    '{"code":"ROLLBACK_INCOMPLETE","message":"copy failed: TLS handshake timeout"}',
  ])('keeps a snapshot or machine fault over a Go store word: %s', (error) => {
    expect(isStoreFailure({ error })).toBe(false);
  });
});

describe('isStoreFailure on a path restore', () => {
  it('is not a store failure when the path is absent, has no listing, or the copy-out rolled back', () => {
    expect(isStoreFailure({ exitCode: 19, error: 'HTTP 502 bad gateway' })).toBe(false);
    expect(isStoreFailure({ exitCode: 18, error: 'timed out' })).toBe(false);
    expect(
      isStoreFailure({ stderr: '{"code":"ROLLED_BACK","message":"copy failed: timed out"}' })
    ).toBe(false);
  });
});

describe('isStoreFailure on a coded rollback', () => {
  it.each(['ROLLED_BACK', 'ROLLBACK_INCOMPLETE'])(
    'is not a store failure when renet says %s',
    (code) => {
      const line = JSON.stringify({ code, message: 'copy failed: connection reset (translated)' });
      expect(isStoreFailure({ stdout: line })).toBe(false);
      expect(isStoreFailure({ stderr: line })).toBe(false);
    }
  );
});

/** renet's restore-path codes, read from its source so the CLI's classifier cannot drift from what renet prints. */
const PLAN_GO = fileURLToPath(
  new URL('../../../../../../private/renet/pkg/restorepath/plan.go', import.meta.url)
);
const RENET_ABSENT = !existsSync(PLAN_GO);

describe('isStoreFailure against renet restorepath codes (parity)', () => {
  it.skipIf(RENET_ABSENT)(
    RENET_ABSENT
      ? 'SKIPPED: private/renet/pkg/restorepath/plan.go is absent (the renet submodule is not checked out), so parity with renet codes is unproven'
      : 'reads each copy-out and path code from private/renet/pkg/restorepath/plan.go',
    () => {
      const source = readFileSync(PLAN_GO, 'utf8');
      for (const name of [
        'CodeRolledBack',
        'CodeRollbackIncomplete',
        'CodeNoSuchPath',
        'CodeNoListing',
      ]) {
        const value = new RegExp(`\\b${name}\\s*=\\s*"([A-Z_]+)"`).exec(source)?.[1];
        expect(value, `${name} is declared in plan.go`).toBeDefined();
        // A store word in the same line would move the restore on, unless the code is recognised as the machine's own.
        const line = JSON.stringify({ code: value, message: 'copy failed: HTTP 502 bad gateway' });
        expect(isStoreFailure({ stdout: line }), `${name}=${value}`).toBe(false);
      }
      // Control: the same line without a recognised code is a store failure.
      expect(
        isStoreFailure({
          stdout: JSON.stringify({ code: 'X', message: 'copy failed: HTTP 502 bad gateway' }),
        })
      ).toBe(true);
    }
  );
});

describe('runWithFallbackAt', () => {
  const fail = (error: string) => ({ ok: false as const, failure: { error } });
  const IN: Record<string, string> = { a: 'snap-a', b: 'snap-b', c: 'snap-c' };
  const resolveIn = (missing: string[] = []) =>
    vi.fn((store: string) =>
      missing.includes(store)
        ? Promise.reject(new Error(`no snapshot in ${store}`))
        : Promise.resolve(IN[store])
    );

  it('resolves only the first store when it serves', async () => {
    const resolve = resolveIn();
    const attempt = vi.fn(async () => ({ ok: true as const, value: 'done' }));
    const result = await runWithFallbackAt(
      { stores: ['a', 'b'], explicit: false },
      resolve,
      attempt
    );
    expect(result).toEqual({ ok: true, store: 'a', value: 'done', snapshotId: 'snap-a' });
    expect(resolve.mock.calls).toEqual([['a']]);
  });

  it('resolves the time again inside the store a failure falls back to', async () => {
    const resolve = resolveIn();
    const attempt = vi
      .fn()
      .mockResolvedValueOnce(fail('HTTP 503'))
      .mockResolvedValueOnce({ ok: true, value: 'done' });
    const onFallback = vi.fn();
    const result = await runWithFallbackAt(
      { stores: ['a', 'b'], explicit: false },
      resolve,
      attempt,
      onFallback
    );
    expect(attempt.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ['a', 'snap-a'],
      ['b', 'snap-b'],
    ]);
    expect(result).toMatchObject({ ok: true, store: 'b', snapshotId: 'snap-b' });
    expect(onFallback).toHaveBeenCalledWith('a', 'b', { error: 'HTTP 503' });
  });

  it('passes over a store holding no snapshot, both first and on a fallback', async () => {
    const resolve = resolveIn(['a', 'b']);
    const attempt = vi.fn(async () => ({ ok: true as const, value: 'done' }));
    const result = await runWithFallbackAt(
      { stores: ['a', 'b', 'c'], explicit: false },
      resolve,
      attempt
    );
    expect(result).toMatchObject({ ok: true, store: 'c', snapshotId: 'snap-c' });

    const fallback = vi.fn();
    const twice = vi
      .fn()
      .mockResolvedValueOnce(fail('HTTP 503'))
      .mockResolvedValueOnce({ ok: true, value: 'done' });
    const moved = await runWithFallbackAt(
      { stores: ['a', 'b', 'c'], explicit: false },
      resolveIn(['b']),
      twice,
      fallback
    );
    expect(moved).toMatchObject({ ok: true, store: 'c', snapshotId: 'snap-c' });
    expect(fallback).toHaveBeenCalledWith('a', 'c', { error: 'HTTP 503' });
  });

  it('ends on a store failure when no later store resolves, telling the attempt it does not move on', async () => {
    let said: boolean | undefined;
    const attempt = vi.fn(async (_s: string, _id: string, movesOn) => {
      said = await movesOn({ error: 'HTTP 503' });
      return fail('HTTP 503');
    });
    const result = await runWithFallbackAt(
      { stores: ['a', 'b'], explicit: false },
      resolveIn(['b']),
      attempt
    );
    expect(said).toBe(false);
    expect(result).toMatchObject({ ok: false, store: 'a', snapshotId: 'snap-a' });
    expect(attempt).toHaveBeenCalledTimes(1);
  });

  it('throws the first store refusal when no store resolves', async () => {
    await expect(
      runWithFallbackAt({ stores: ['a', 'b'], explicit: false }, resolveIn(['a', 'b']), vi.fn())
    ).rejects.toThrow('no snapshot in a');
  });

  it('resolves an explicit store alone and throws its refusal as is', async () => {
    const resolve = resolveIn(['a']);
    await expect(
      runWithFallbackAt({ stores: ['a'], explicit: true }, resolve, vi.fn())
    ).rejects.toThrow('no snapshot in a');
    expect(resolve).toHaveBeenCalledTimes(1);
  });

  it('throws an account error from the first resolve rather than passing the store over', async () => {
    const resolve = vi.fn(() => Promise.reject(Object.assign(new Error('boom'), { status: 500 })));
    await expect(
      runWithFallbackAt({ stores: ['a', 'b'], explicit: false }, resolve, vi.fn())
    ).rejects.toThrow('boom');
    expect(resolve).toHaveBeenCalledTimes(1);
  });
});

describe('executeWithStoreFallback', () => {
  const ok = { success: true, exitCode: 0, durationMs: 1 };
  const bad = (error: string) => ({ success: false, exitCode: 1, error, durationMs: 1 });

  it('returns the first success, announcing a non-home store, and renders nothing', async () => {
    const run = vi.fn(async () => ok);
    const out = await executeWithStoreFallback(
      { stores: ['eu-west'], explicit: true },
      async () => 'snap',
      run,
      'failed'
    );
    expect(out.store).toBe('eu-west');
    expect(mockInfo).toHaveBeenCalledTimes(1);
    expect(mockRender).not.toHaveBeenCalled();
  });

  it('says nothing for home alone served first, as before stores existed', async () => {
    await executeWithStoreFallback(
      { stores: ['home'], explicit: false },
      async () => 'snap',
      async () => ok,
      'failed'
    );
    expect(mockInfo).not.toHaveBeenCalled();
  });

  it('renders the failure that ends the run, with the executor message or the fallback text', async () => {
    const run = vi.fn(async () => bad('HTTP 502 bad gateway'));
    const out = await executeWithStoreFallback(
      { stores: ['a', 'b'], explicit: false },
      async (store) => `snap-${store}`,
      run,
      'failed'
    );
    expect(run).toHaveBeenCalledTimes(2);
    expect(out.store).toBe('b');
    expect(out.snapshotId).toBe('snap-b');
    expect(run.mock.calls).toEqual([
      ['a', 'snap-a'],
      ['b', 'snap-b'],
    ]);
    expect(mockRender).toHaveBeenCalledTimes(1);
    expect(mockRender.mock.calls[0][1]).toBe('HTTP 502 bad gateway');
  });
});
