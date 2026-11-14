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

  // A refused grant from the store is the store's fault, so a 403 the error carries only on its cause falls back too.
  it('reads a cause-only 403 with no code as a refused grant, and falls back', async () => {
    const d = deps({
      'eu-west': Object.assign(new Error('mint failed'), { cause: { status: 403 } }),
    });
    const result = await runStoreFetch({ ref: 'r', dest: '/d' }, d.base);
    expect(minted(d)).toEqual(['eu-west', undefined]);
    expect(result.store).toBe('home');
    expect(mockWarn).toHaveBeenCalledWith(FALLBACK);
  });

  // An account-level 403 (team scope, role, retention) is the same answer from every store.
  it('does not read a cause-only 403 carrying an account code as a store fault', async () => {
    const d = deps({
      'eu-west': Object.assign(new Error('mint failed'), {
        cause: { status: 403, code: 'TEAM_SCOPE_REQUIRED' },
      }),
    });
    await expect(runStoreFetch({ ref: 'r', dest: '/d' }, d.base)).rejects.toThrow();
    expect(minted(d)).toEqual(['eu-west']);
    expect(mockWarn).not.toHaveBeenCalled();
  });
});

describe('backup download --store resolves the time inside each store (item #acd03b8a)', () => {
  const AT = '2026-08-10T00:00:00Z';
  const IN_STORE: Record<string, string> = {
    'eu-west': '20260809T000000Z-aaaaaaaaaaaaaaaa',
    home: '20260808T000000Z-bbbbbbbbbbbbbbbb',
  };
  const snapshots = (d: { runRenet: ReturnType<typeof vi.fn> }) =>
    d.runRenet.mock.calls.map(
      (c) => (c[1] as string[])[(c[1] as string[]).indexOf('--snapshot') + 1]
    );

  it('with --store, resolves inside that store only', async () => {
    const d = deps({});
    const resolveSnapshot = vi.fn(
      async (_l: string, _at: string, store: string) => IN_STORE[store]
    );
    d.base.resolveSnapshot = resolveSnapshot;
    const result = await runStoreFetch({ ref: 'r', dest: '/d', at: AT, store: 'eu-west' }, d.base);
    expect(resolveSnapshot.mock.calls).toEqual([[LINEAGE, AT, 'eu-west']]);
    expect(result.snapshotId).toBe(IN_STORE['eu-west']);
  });

  it('on a fallback, fetches the snapshot the next store resolves, and reports it', async () => {
    const d = deps({ 'eu-west': httpError(502, 'bad gateway') });
    const resolveSnapshot = vi.fn(
      async (_l: string, _at: string, store: string) => IN_STORE[store]
    );
    d.base.resolveSnapshot = resolveSnapshot;
    const result = await runStoreFetch({ ref: 'r', dest: '/d', at: AT }, d.base);
    expect(resolveSnapshot.mock.calls.map((c) => c[2])).toEqual(['eu-west', 'home']);
    expect(snapshots(d)).toEqual([IN_STORE.home]);
    expect(result).toMatchObject({ store: 'home', snapshotId: IN_STORE.home });
  });

  it('keeps the backup:read refusal of a 403 from the resolve', async () => {
    const d = deps({});
    d.base.resolveSnapshot = async () => Promise.reject(httpError(403, 'forbidden'));
    await expect(runStoreFetch({ ref: 'r', dest: '/d', at: AT }, d.base)).rejects.toThrow(
      'errors.backupImage.storeNoScope'
    );
    expect(d.runRenet).not.toHaveBeenCalled();
  });
});
