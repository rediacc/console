/**
 * `rdc backup download --store` and the ranked store pick (multi-target C3 follow-up).
 *
 * Without `--store` the image is read from the first ranked store that serves it: a 5xx from a mint or from renet
 * hands the fetch to the next store, which is named; a snapshot that is missing or fails its own verify is the same
 * everywhere and ends the run; an explicit `--store` is read alone.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../../core/output.js', () => ({ outputService: { warn: mockWarn, info: vi.fn() } }));

const { LUKS_MAGIC, runStoreFetch } = await import('../store-fetch.js');
type Deps = import('../store-fetch.js').StoreFetchDeps;

const LINEAGE = 'f6545d49-c46e-4c14-8006-0ad5b37f3e08';
const SNAP = '20260814T120000Z-0011223344556677';
const FETCHED = JSON.stringify({ status: 'fetched', snapshotId: SNAP, bytesFetched: 42 });
const RANKED = { stores: ['eu-west', 'home'], explicit: false };
const FALLBACK = `commands.backup.restore.storeFallback ${JSON.stringify({ failed: 'eu-west', next: 'home' })}`;

const httpError = (status: number, message: string, code?: string) =>
  Object.assign(new Error(message), { status, ...(code ? { code } : {}) });

/** Deps whose mint answers per store: a thrown error, or a session. */
function deps(mint: Record<string, unknown>, run?: Deps['runRenet']) {
  const mintSession = vi.fn((_lineage: string, store?: string) => {
    const outcome = mint[store ?? 'home'];
    return outcome instanceof Error
      ? Promise.reject(outcome)
      : Promise.resolve({ token: 't', lineageGuid: LINEAGE });
  });
  const runRenet = vi.fn(run ?? (async () => ({ code: 0, stdout: `${FETCHED}\n`, stderr: '' })));
  const base: Deps = {
    resolveLineage: async () => LINEAGE,
    resolveSnapshot: async () => SNAP,
    mintSession,
    pickStores: async () => RANKED,
    apiBase: () => 'https://account.example/account/api/v1/backups',
    renetPath: async () => '/usr/bin/renet',
    runRenet,
    readHead: async () => Buffer.concat([LUKS_MAGIC, Buffer.alloc(8)]),
    now: () => new Date('2026-08-14T12:00:00Z'),
  };
  return { base, mintSession, runRenet };
}
const minted = (d: { mintSession: ReturnType<typeof vi.fn> }) =>
  d.mintSession.mock.calls.map((c) => c[1]);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('backup download --store fallback', () => {
  it('falls back to the next store on a 5xx mint and names the store that served', async () => {
    const d = deps({ 'eu-west': httpError(502, 'bad gateway') });
    const result = await runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, d.base);
    expect(minted(d)).toEqual(['eu-west', undefined]);
    expect(result.store).toBe('home');
    expect(mockWarn).toHaveBeenCalledWith(FALLBACK);
  });

  it('falls back on a refused grant (a 403 naming no account-level code)', async () => {
    const d = deps({ 'eu-west': httpError(403, 'forbidden') });
    const result = await runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, d.base);
    expect(result.store).toBe('home');
    expect(mockWarn).toHaveBeenCalledWith(FALLBACK);
  });

  it('falls back when renet reports a 5xx from the store', async () => {
    let calls = 0;
    const d = deps({}, () => {
      calls += 1;
      return Promise.resolve(
        calls === 1
          ? {
              code: 1,
              stdout: `${JSON.stringify({ status: 'failed', reason: 'GET chunk: HTTP 503 service unavailable' })}\n`,
              stderr: '',
            }
          : { code: 0, stdout: `${FETCHED}\n`, stderr: '' }
      );
    });
    const result = await runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, d.base);
    expect(minted(d)).toEqual(['eu-west', undefined]);
    expect(result.store).toBe('home');
  });

  it('does not fall back when the snapshot is missing', async () => {
    const d = deps({}, async () => ({
      code: 1,
      stdout: `${JSON.stringify({ status: 'failed', reason: 'snapshot snap-1 not found in the manifest index' })}\n`,
      stderr: '',
    }));
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, d.base)).rejects.toThrow(
      'not found'
    );
    expect(minted(d)).toEqual(['eu-west']);
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('does not fall back when the snapshot fails its own verification', async () => {
    const d = deps({}, async () => ({
      code: 1,
      stdout: `${JSON.stringify({ status: 'failed', reason: 'chunk hash mismatch' })}\n`,
      stderr: '',
    }));
    await expect(runStoreFetch({ ref: 'mail', dest: '/d/x.img' }, d.base)).rejects.toThrow(
      'hash mismatch'
    );
    expect(minted(d)).toEqual(['eu-west']);
  });

  it('never falls back from an explicit --store, even on a 5xx', async () => {
    const d = deps({ 'eu-west': httpError(502, 'bad gateway') });
    await expect(
      runStoreFetch({ ref: 'mail', dest: '/d/x.img', store: 'eu-west' }, d.base)
    ).rejects.toThrow('bad gateway');
    expect(minted(d)).toEqual(['eu-west']);
    expect(mockWarn).not.toHaveBeenCalled();
  });
});

describe('failure classification', () => {
  it('keeps the own status of an unrelated error that carries a cause with another', async () => {
    const d = deps({}, () =>
      Promise.reject(
        Object.assign(httpError(400, 'renet spawn failed'), {
          cause: httpError(502, 'bad gateway'),
        })
      )
    );
    await expect(runStoreFetch({ ref: 'r', dest: '/d' }, d.base)).rejects.toThrow(
      'renet spawn failed'
    );
    expect(d.runRenet).toHaveBeenCalledTimes(1);
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('classifies an error whose status lives only in its cause by that status', async () => {
    const d = deps({}, () =>
      Promise.reject(
        Object.assign(new Error('renet spawn failed'), { cause: httpError(502, 'bad gateway') })
      )
    );
    await expect(runStoreFetch({ ref: 'r', dest: '/d' }, d.base)).rejects.toThrow();
    expect(d.runRenet).toHaveBeenCalledTimes(2);
    expect(mockWarn).toHaveBeenCalledWith(FALLBACK);
  });

  it('still reads the original of a refused session mint', async () => {
    const d = deps({ 'eu-west': httpError(502, 'bad gateway') });
    await runStoreFetch({ ref: 'r', dest: '/d' }, d.base);
    expect(minted(d)).toEqual(['eu-west', undefined]);
  });
});
