/**
 * `accountServerFetch` inside a container-mode dispatch (PLAN-executor-account-routes EA4, Design 7).
 *
 * The proxy egress refuses the sealed tunnel, so inside a dispatch a call the executor route table lists goes plain to
 * `/account/api/v1/proxy/account/<inner>` with the placeholder bearer and the principal in `X-Rediacc-On-Behalf-Of`; an
 * unlisted call throws by name before any network. Each served backup caller is driven through its own exported
 * function, or through its registered command where the caller is private to the command file.
 */

import {
  EXECUTOR_ACCOUNT_ROUTES,
  type ExecutorAccountRoute,
} from '@rediacc/shared/subscription/executor-account-routes';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const LINEAGE = vi.hoisted(() => 'aaaaaaaa-1111-4111-8111-111111111111');
const SNAPSHOT = '20261127T101010Z-0123456789abcdef';
const SERVER = 'http://account.internal';
const PLACEHOLDER = 'PLACEHOLDER';

vi.mock('../subscription-auth.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../subscription-auth.js')>()),
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    serverUrl: 'http://account.internal',
    token: { token: 'PLACEHOLDER' },
  }),
  getSubscriptionServerUrl: () => 'http://account.internal',
}));
vi.mock('../free-license.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../free-license.js')>()),
  assertHostedBackupAccount: () => undefined,
}));
vi.mock('../../../utils/repo-target.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/repo-target.js')>()),
  resolveRepoRef: () => Promise.resolve({ repoKey: 'repo', machineName: 'm' }),
}));
vi.mock('../../../commands/backup-storage-browse.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../commands/backup-storage-browse.js')>()),
  resolveLineage: () => Promise.resolve(LINEAGE),
}));
vi.mock('../../config/config-resources.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/config-resources.js')>();
  return {
    ...actual,
    configService: Object.assign(Object.create(actual.configService), {
      getRepository: () => Promise.resolve({ repositoryGuid: LINEAGE, credential: 'c' }),
    }),
  };
});
vi.mock('../../../utils/guid-resolver.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/guid-resolver.js')>()),
  loadGuidMap: () => Promise.resolve({}),
}));
vi.mock('../../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    commandErrors.push(error);
  },
}));
const commandErrors = vi.hoisted(() => [] as unknown[]);

import { purgeLineageRounds } from '../../../commands/backup-purge.js';
import { resolveSnapshotAt } from '../../../commands/backup-restore-chunk.js';
import { lineageHasSnapshots } from '../../../commands/backup-restore-route.js';
import { registerBackupStorageCommands } from '../../../commands/backup-storage.js';
import { runStoreVerify } from '../../../commands/backup-store-verify.js';
import { postVerification } from '../../../commands/backup-verification.js';
import { settleCloudBackups } from '../../../commands/repo-delete-settle.js';
import { pickStores, readStoreStatuses } from '../../backup/backup-store-pick.js';
import { resolveRestoreSizeGb } from '../../executor/repo-license-context.js';
import {
  type AccountFetchError,
  accountServerFetch,
  EXECUTOR_ROUTE_NOT_SERVED,
  ON_BEHALF_OF_HEADER,
} from '../account-client.js';
import { withExecutorPrincipal } from '../executor-principal.js';

const fetchMock = vi.fn();
let answers: Response[] = [];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  answers = [];
  commandErrors.length = 0;
  fetchMock.mockReset().mockImplementation(() => Promise.resolve(answers.shift() ?? json({})));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

interface Sent {
  url: URL;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function sent(index = 0): Sent {
  const call = fetchMock.mock.calls[index] as [string, RequestInit] | undefined;
  if (!call) throw new Error(`no request #${index} was sent`);
  const [url, init] = call;
  return {
    url: new URL(url),
    method: init.method ?? 'GET',
    headers: init.headers as Record<string, string>,
    body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
  };
}

/** The plain executor request: the executor path, the placeholder bearer and the principal header. */
function expectExecutorRequest(
  request: Sent,
  method: string,
  inner: string,
  query: Record<string, string> = {}
): void {
  expect(request.url.origin).toBe(SERVER);
  expect(request.url.pathname).toBe(`/account/api/v1/proxy/account/${inner}`);
  expect(Object.fromEntries(request.url.searchParams)).toEqual(query);
  expect(request.method).toBe(method);
  expect(request.headers.Authorization).toBe(`Bearer ${PLACEHOLDER}`);
  expect(request.headers[ON_BEHALF_OF_HEADER]).toBe('tok-1');
}

function inDispatch<T>(fn: () => Promise<T>, principal = { tokenId: 'tok-1' }): Promise<T> {
  return withExecutorPrincipal(principal, fn);
}

/** Run one `rdc backup ...` command inside a dispatch; a failure after the request is the command's own, not this test's. */
async function runBackup(...argv: string[]): Promise<void> {
  const program = new Command('rdc');
  program.exitOverride();
  registerBackupStorageCommands(program.command('backup'));
  await inDispatch(() => program.parseAsync(['backup', ...argv], { from: 'user' })).catch(
    () => undefined
  );
}

const SAMPLE_SEGMENTS: Record<string, string> = {
  ':lineage': LINEAGE,
  ':snapshot': SNAPSHOT,
  ':machine': 'ab'.repeat(32),
  ':uuid': '11111111-1111-4111-8111-111111111111',
};

function samplePath(route: ExecutorAccountRoute): string {
  const inner = route.inner
    .split('/')
    .map((segment) => SAMPLE_SEGMENTS[segment] ?? segment)
    .join('/');
  return `/account/api/v1/${inner}`;
}

async function testServerKey(): Promise<{ key: CryptoKey; keyId: string }> {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as CryptoKeyPair;
  return { key: pair.publicKey, keyId: 'test' };
}

describe('outside a container dispatch', () => {
  it.each(
    EXECUTOR_ACCOUNT_ROUTES.map((route) => [`${route.method} ${route.inner}`, route] as const)
  )('control: %s still goes through the sealed tunnel', async (_label, route) => {
    const tunnel = vi
      .fn()
      .mockResolvedValue(json({ error: 'tunnel reached' }, 503)) as unknown as typeof fetch;
    await expect(
      accountServerFetch(samplePath(route), {
        method: route.method,
        serverKey: await testServerKey(),
        fetchImpl: tunnel,
      })
    ).rejects.toMatchObject({ status: 503 });
    const calls = (tunnel as unknown as ReturnType<typeof vi.fn>).mock.calls as [
      string,
      RequestInit,
    ][];
    expect(calls).toHaveLength(1);
    expect(calls[0]?.[0]).toBe(`${SERVER}/account/api/v1/tunnel`);
    expect(calls[0]?.[1].method).toBe('POST');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('inside a container dispatch: refusals before any network', () => {
  it.each([
    ['PUT', '/account/api/v1/backups/immutability'],
    ['POST', '/account/api/v1/backups/session'],
    ['GET', '/account/api/v1/backups/manifests?teamId=x'],
    ['GET', '/account/api/v1/tunnel'],
  ])('control: %s %s is not served and throws the named error', async (method, path) => {
    const failure = await inDispatch(() => accountServerFetch(path, { method })).catch(
      (error: unknown) => error
    );
    expect(failure).toMatchObject({ code: EXECUTOR_ROUTE_NOT_SERVED });
    expect((failure as Error).message).toContain('not served in a container');
    expect((failure as Error).message).toContain(`${method} ${path}`);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('a dispatch whose principal carries no token id fails named and sends nothing', async () => {
    await expect(
      inDispatch(() => accountServerFetch('/account/api/v1/backups/usage'), {
        tokenId: undefined,
      } as never)
    ).rejects.toThrow(/carries no token id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('inside a container dispatch: each served backup caller', () => {
  it('backup usage', async () => {
    await runBackup('usage');
    expectExecutorRequest(sent(), 'GET', 'backups/usage');
  });

  it('backup manifests with every flag', async () => {
    await runBackup('manifests', 'repo', '--limit', '5', '--before', 'cur', '--include-deleted');
    expectExecutorRequest(sent(), 'GET', 'backups/manifests', {
      lineage: LINEAGE,
      limit: '5',
      before: 'cur',
      includeDeleted: '1',
    });
  });

  it('backup check reads the newest snapshot', async () => {
    answers.push(json({ manifests: [] }));
    await runBackup('check', 'repo');
    expectExecutorRequest(sent(), 'GET', 'backups/manifests', { lineage: LINEAGE, limit: '1' });
  });

  it('backup check posts its verdict (postVerification)', async () => {
    await inDispatch(() => postVerification(SNAPSHOT, 'file', 'proven'));
    expectExecutorRequest(sent(), 'POST', `backups/snapshots/${SNAPSHOT}/verification`);
    expect(sent().body).toEqual({ level: 'file', status: 'proven' });
  });

  it('backup verify --store (runStoreVerify)', async () => {
    answers.push(json({ chunks: { checked: 1, missing: [], corrupt: [], nextAfter: null } }));
    await inDispatch(() => runStoreVerify(LINEAGE));
    expectExecutorRequest(sent(), 'POST', 'backups/verify');
    expect(sent().body).toEqual({ lineageGuid: LINEAGE, level: 'chunks' });
  });

  it('backup repair --dry-run asks the server after the verify', async () => {
    answers.push(json({ chunks: { checked: 1, missing: ['h1'], corrupt: [], nextAfter: null } }));
    answers.push(json({ deleted: [], stillGood: ['h1'], absent: [], affectedSnapshots: [] }));
    await runBackup('repair', 'repo', '--dry-run');
    expectExecutorRequest(sent(0), 'POST', 'backups/verify');
    expectExecutorRequest(sent(1), 'POST', 'backups/chunks/repair');
    expect(sent(1).body).toEqual({ lineageGuid: LINEAGE, hashes: ['h1'], dryRun: true });
  });

  it('backup restore --at resolves the time (resolveSnapshotAt)', async () => {
    answers.push(json({ snapshotId: SNAPSHOT, createdAt: '2026-11-01T00:00:00Z', hasIndex: true }));
    await expect(
      inDispatch(() => resolveSnapshotAt(LINEAGE, '2026-11-01T00:00:00Z'))
    ).resolves.toBe(SNAPSHOT);
    expectExecutorRequest(sent(), 'GET', 'backups/snapshots/resolve', {
      lineage: LINEAGE,
      anyStream: '1',
      at: '2026-11-01T00:00:00.000Z',
    });
  });

  it('backup restore checks the lineage has snapshots (lineageHasSnapshots)', async () => {
    answers.push(json({ manifests: [{ snapshotId: SNAPSHOT }] }));
    await expect(inDispatch(() => lineageHasSnapshots(LINEAGE, 'repo'))).resolves.toBe(true);
    expectExecutorRequest(sent(), 'GET', 'backups/manifests', { lineage: LINEAGE, limit: '1' });
  });

  it('backup restore, schedule and browse pick the stores (pickStores)', async () => {
    answers.push(json({ stores: [{ storeId: 'home', newestSnapshotId: SNAPSHOT }] }));
    await inDispatch(() => pickStores(LINEAGE));
    expectExecutorRequest(sent(), 'GET', `backups/stores/lineage/${LINEAGE}`);
  });

  it('backup restore sizes the licence from the snapshot (resolveRestoreSizeGb)', async () => {
    answers.push(json({ snapshotId: SNAPSHOT, totalBytes: 5 * 1024 ** 3 }));
    await expect(inDispatch(() => resolveRestoreSizeGb(LINEAGE, SNAPSHOT))).resolves.toBe(5);
    expectExecutorRequest(sent(), 'GET', 'backups/snapshots/resolve', {
      lineage: LINEAGE,
      anchorSnapshotId: SNAPSHOT,
      includeDeleted: '1',
    });
  });

  it('backup reconcile --dry-run', async () => {
    answers.push(json({ lineages: [] }));
    await runBackup('reconcile', 'repo', '--dry-run');
    expectExecutorRequest(sent(), 'POST', 'backups/reconcile');
    expect(sent().body).toEqual({ lineageGuid: LINEAGE, dryRun: true });
  });

  it('backup retention <repo> reads the policy and the effective preview', async () => {
    await runBackup('retention', 'repo');
    expectExecutorRequest(sent(0), 'GET', 'backups/retention', { lineage: LINEAGE });
    expectExecutorRequest(sent(1), 'GET', 'backups/retention/preview', { lineage: LINEAGE });
  });

  it('backup retention preview <repo>', async () => {
    await runBackup('retention', 'preview', 'repo');
    expectExecutorRequest(sent(), 'GET', 'backups/retention/preview', { lineage: LINEAGE });
  });

  it('backup immutability show', async () => {
    await runBackup('immutability', 'show');
    expectExecutorRequest(sent(), 'GET', 'backups/immutability');
  });

  it('backup undelete <snapshot>', async () => {
    await runBackup('undelete', SNAPSHOT);
    expectExecutorRequest(sent(), 'POST', `backups/snapshots/${SNAPSHOT}/undelete`);
  });

  it('backup status reads the store columns (readStoreStatuses)', async () => {
    await inDispatch(() => readStoreStatuses([LINEAGE]));
    expectExecutorRequest(sent(), 'GET', 'backups/status');
  });

  it('repo delete --purge-backups purges the lineage (purgeLineageRounds)', async () => {
    answers.push(json({ deletedChunks: 0, deletedBytes: 0, done: true }));
    await inDispatch(() => purgeLineageRounds('repo', LINEAGE, String));
    expectExecutorRequest(sent(), 'DELETE', `backups/lineages/${LINEAGE}`);
  });

  it('repo delete orphans the lineage (settleCloudBackups)', async () => {
    answers.push(json({ orphanExpiresAt: '2026-12-27T00:00:00Z' }));
    await inDispatch(() => settleCloudBackups('repo', { repositoryGuid: LINEAGE } as never, false));
    expectExecutorRequest(sent(), 'POST', `backups/lineages/${LINEAGE}/orphan`);
  });

  it('every command above surfaced no error from the request itself', () => {
    expect(
      commandErrors.filter(
        (e) => (e as { code?: unknown } | null)?.code === EXECUTOR_ROUTE_NOT_SERVED
      )
    ).toEqual([]);
  });
});

describe('inside a container dispatch: responses reach the callers as the tunnel’s would', () => {
  it('a plain 404 with a code throws status, code and details', async () => {
    answers.push(json({ error: 'no activation', code: 'ACTIVATION_NOT_FOUND' }, 404));
    const failure = (await inDispatch(() =>
      accountServerFetch(`/account/api/v1/backups/stores/lineage/${LINEAGE}`)
    ).catch((error: unknown) => error)) as AccountFetchError;
    expect(failure.status).toBe(404);
    expect(failure.code).toBe('ACTIVATION_NOT_FOUND');
    expect(failure.details).toMatchObject({ code: 'ACTIVATION_NOT_FOUND' });
    expect(failure.message).toBe('no activation');
  });

  it('a plain router 404 without a code throws the status and no code', async () => {
    answers.push(new Response('404 Not Found', { status: 404 }));
    const failure = (await inDispatch(() =>
      accountServerFetch(`/account/api/v1/backups/stores/lineage/${LINEAGE}`)
    ).catch((error: unknown) => error)) as AccountFetchError;
    expect(failure.status).toBe(404);
    expect(failure.code).toBeUndefined();
  });

  it('pickStores treats the route 404 as an older server, as on the tunnel', async () => {
    answers.push(new Response('404 Not Found', { status: 404 }));
    await expect(inDispatch(() => pickStores(LINEAGE))).resolves.toMatchObject({
      explicit: false,
    });
  });

  it('a 202 body is returned like a 200 (the delayed purge)', async () => {
    answers.push(
      json({ deletedChunks: 0, deletedBytes: 0, delayed: true, purgeAfter: '2026-12-01' }, 202)
    );
    await expect(
      inDispatch(() => purgeLineageRounds('repo', LINEAGE, String))
    ).resolves.toMatchObject({ delayed: true, purgeAfter: '2026-12-01' });
  });
});
