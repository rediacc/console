/**
 * The licence callers of served commands inside a container-mode dispatch (PLAN-executor-account-routes EA4).
 *
 * `licenceFetch` is gone: the licence report, the activation, the batch, the retire and the machine deactivate all call
 * `accountServerFetch`, whose container branch sends each one plain to `/account/api/v1/proxy/account/<inner>` with the
 * placeholder bearer and the principal in `X-Rediacc-On-Behalf-Of`. Each is driven through its own exported function.
 */

import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { WK_ACCOUNT_EGRESS_HOST } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const GUID = '11111111-1111-4111-8111-111111111111';
const MACHINE_ID = vi.hoisted(() => 'ab'.repeat(32));
const SERVER = `http://${WK_ACCOUNT_EGRESS_HOST}`;
const configDir = vi.hoisted(() => ({ path: '' }));
const warnMock = vi.hoisted(() => vi.fn());

vi.mock('@rediacc/shared/paths', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@rediacc/shared/paths')>();
  const { mkdtempSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join: joinPath } = await import('node:path');
  configDir.path = mkdtempSync(joinPath(tmpdir(), 'ea4-'));
  return { ...actual, getConfigDir: () => configDir.path };
});
vi.mock('../subscription-auth.js', async (importOriginal) => {
  const wk = await import('@rediacc/shared/config/well-known.generated');
  const server = `http://${wk.WK_ACCOUNT_EGRESS_HOST}`;
  return {
    ...(await importOriginal<typeof import('../subscription-auth.js')>()),
    getSubscriptionTokenState: () => ({
      kind: 'ready',
      serverUrl: server,
      token: { token: 'PLACEHOLDER' },
    }),
    getSubscriptionServerUrl: () => server,
  };
});
vi.mock('../license-machine.js', () => ({
  DEFAULT_DATASTORE: 'default',
  clusterIdFor: () => undefined,
  isDatastoreScopedId: () => false,
  measureRepoSizeGb: () => Promise.resolve(1),
  readRemoteMachineId: () => Promise.resolve(MACHINE_ID),
  scanRemoteLicenseStatuses: () => Promise.resolve([]),
  scanRemoteRepoLicenses: () => Promise.resolve([]),
  writeRepoLicense: () => Promise.resolve(undefined),
}));
vi.mock('../client-machine-id.js', () => ({
  readLocalMachineId: () => Promise.resolve('client'),
}));
vi.mock('../../machine/machine-connection.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../machine/machine-connection.js')>()),
  sftpConfigForMachine: () => ({}),
  withSharedOrPooledSftp: (sftp: unknown, _c: unknown, fn: (s: unknown) => unknown) => fn(sftp),
  machineConnections: {
    acquireFor: () => Promise.resolve({ sftp: {}, release: () => undefined }),
  },
}));
vi.mock('../../config/config-resources.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/config-resources.js')>();
  return {
    ...actual,
    configService: Object.assign(Object.create(actual.configService), {
      listRepositories: () =>
        Promise.resolve([{ name: 'repo', config: { repositoryGuid: GUID, grandGuid: GUID } }]),
      getLocalConfig: () =>
        Promise.resolve({ machines: { m: { ip: '10.0.0.1' } }, sshPrivateKey: 'k', ssh: {} }),
      removeMachine: () => Promise.resolve(undefined),
    }),
  };
});
vi.mock('../../tofu/executor.js', () => ({
  TofuExecutor: class {
    destroy() {
      return Promise.resolve();
    }
    cleanup() {
      return Promise.resolve();
    }
  },
}));
vi.mock('../../core/output.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../core/output.js')>();
  return {
    ...actual,
    outputService: Object.assign(Object.create(actual.outputService), {
      warn: warnMock,
      info: () => undefined,
      success: () => undefined,
    }),
  };
});

import { destroyCloudMachine } from '../../tofu/provision.js';
import { ON_BEHALF_OF_HEADER } from '../account-client.js';
import { inContainerDispatch, withExecutorPrincipal } from '../executor-principal.js';
import { fetchSubscriptionLicenseReportOrThrow, issueRepoLicense } from '../license.js';
import { refreshRepoLicensesBatch } from '../license-batch.js';
import { retireRepoLicense } from '../license-retire.js';

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
  warnMock.mockReset();
  fetchMock.mockReset().mockImplementation(() => Promise.resolve(answers.shift() ?? json({})));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function lastRequest(): { url: URL; init: RequestInit; body: unknown } {
  const call = fetchMock.mock.calls.at(-1) as [string, RequestInit] | undefined;
  if (!call) throw new Error('no request was sent');
  const [url, init] = call;
  return {
    url: new URL(url),
    init,
    body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
  };
}

function expectExecutorRequest(method: string, inner: string, tokenId = 'tok-1'): unknown {
  const { url, init, body } = lastRequest();
  expect(url.origin).toBe(SERVER);
  expect(url.pathname).toBe(`/account/api/v1/proxy/account/${inner}`);
  expect(url.search).toBe('');
  expect(init.method).toBe(method);
  const headers = init.headers as Record<string, string>;
  expect(headers.Authorization).toBe('Bearer PLACEHOLDER');
  expect(headers[ON_BEHALF_OF_HEADER]).toBe(tokenId);
  return body;
}

const inDispatch = <T>(fn: () => Promise<T>, tokenId = 'tok-1') =>
  withExecutorPrincipal({ tokenId }, fn);

describe('licence calls in a container dispatch', () => {
  it('control: outside a dispatch the retire never takes the executor path', async () => {
    expect(inContainerDispatch()).toBe(false);
    await retireRepoLicense(GUID).catch(() => undefined);
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.some((u) => u.includes('/proxy/'))).toBe(false);
    expect(urls.every((u) => !u.endsWith(`/licenses/repos/${GUID}/retire`))).toBe(true);
  });

  it('subscription status reads the licence report (fetchSubscriptionLicenseReportOrThrow)', async () => {
    answers.push(json({ subscriptionId: 's', planCode: 'p', status: 'active', recent: [] }));
    await inDispatch(() => fetchSubscriptionLicenseReportOrThrow());
    expect(expectExecutorRequest('GET', 'licenses/report')).toBeUndefined();
  });

  it('the activation (issueRepoLicense) carries its body and no onBehalfOfTokenId', async () => {
    answers.push(json({ license: { blob: 'b' } }));
    await expect(
      inDispatch(() =>
        issueRepoLicense('m', {} as never, 'key', {
          repositoryGuid: GUID,
          kind: 'grand',
          requestedSizeGb: 1,
        })
      )
    ).resolves.toBe(true);
    const body = expectExecutorRequest('POST', 'licenses/activate-repo') as Record<string, unknown>;
    expect(body).toMatchObject({
      machineId: MACHINE_ID,
      clientMachineId: 'client',
      repositoryGuid: GUID,
    });
    expect(body).not.toHaveProperty('onBehalfOfTokenId');
  });

  it('the batch refresh (refreshRepoLicensesBatch)', async () => {
    answers.push(
      json({ results: [{ repositoryGuid: GUID, status: 'refreshed', license: { blob: 'b' } }] })
    );
    await inDispatch(() =>
      refreshRepoLicensesBatch('m', {} as never, 'key', undefined, {} as never, undefined, [
        { repositoryGuid: GUID, requestedSizeGb: 1 } as never,
      ])
    );
    const body = expectExecutorRequest('POST', 'licenses/activate-repo-batch') as {
      repos: { repositoryGuid: string }[];
    };
    expect(body.repos.map((r) => r.repositoryGuid)).toEqual([GUID]);
  });

  it('the retire (retireRepoLicense) sends no body', async () => {
    answers.push(json({ retired: true, repositoryGuid: GUID }));
    await inDispatch(() => retireRepoLicense(GUID), 'tok-2');
    expect(expectExecutorRequest('POST', `licenses/repos/${GUID}/retire`, 'tok-2')).toBeUndefined();
  });

  describe('machine deprovision releases the activation slot (destroyCloudMachine)', () => {
    beforeEach(() => mkdirSync(join(configDir.path, 'tofu', 'm'), { recursive: true }));

    it('sends the deactivate plain for the activated machine id', async () => {
      await inDispatch(() => destroyCloudMachine('m'));
      expectExecutorRequest('POST', `licenses/machines/${MACHINE_ID}/deactivate`);
      expect(warnMock).not.toHaveBeenCalled();
    });

    it('a plain 404 with a code means no activation held the slot: no warning', async () => {
      answers.push(json({ error: 'none', code: 'ACTIVATION_NOT_FOUND' }, 404));
      await inDispatch(() => destroyCloudMachine('m'));
      expect(warnMock).not.toHaveBeenCalled();
    });

    it('a plain router 404 without a code warns deactivateFailed, as on the tunnel', async () => {
      answers.push(new Response('404 Not Found', { status: 404 }));
      await inDispatch(() => destroyCloudMachine('m'));
      expect(warnMock).toHaveBeenCalledTimes(1);
      expect(String(warnMock.mock.calls[0]?.[0])).toContain('404');
    });
  });

  it('fails named, with no request, when the principal has no token id', async () => {
    await expect(
      withExecutorPrincipal({ tokenId: undefined }, () => retireRepoLicense(GUID))
    ).rejects.toThrow(/carries no token id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('throws the server refusal with its status and code', async () => {
    answers.push(json({ error: 'no', code: 'ON_BEHALF_TOKEN_FORBIDDEN' }, 403));
    await expect(inDispatch(() => retireRepoLicense(GUID))).rejects.toMatchObject({
      status: 403,
      code: 'ON_BEHALF_TOKEN_FORBIDDEN',
    });
  });
});
