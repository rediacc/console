import { WK_ACCOUNT_EGRESS_HOST } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const tunnelMock = vi.hoisted(() => vi.fn());
const stateMock = vi.hoisted(() => vi.fn());

vi.mock('../account-client.js', () => ({ accountServerFetch: tunnelMock }));
vi.mock('../subscription-auth.js', () => ({ getSubscriptionTokenState: stateMock }));

import { inContainerDispatch, licenceFetch, withExecutorPrincipal } from '../executor-principal.js';
import { retireRepoLicense } from '../license-retire.js';

const GUID = '11111111-1111-4111-8111-111111111111';
const EGRESS = `http://${WK_ACCOUNT_EGRESS_HOST}`;
const fetchMock = vi.fn();

beforeEach(() => {
  tunnelMock.mockReset().mockResolvedValue({ retired: true, repositoryGuid: GUID });
  fetchMock
    .mockReset()
    .mockResolvedValue(
      new Response(JSON.stringify({ retired: true, repositoryGuid: GUID }), { status: 200 })
    );
  stateMock.mockReset().mockReturnValue({
    kind: 'ready',
    serverUrl: EGRESS,
    token: { token: 'PLACEHOLDER' },
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('licence calls in a container dispatch', () => {
  it('control: outside a dispatch the call goes through the tunnel', async () => {
    expect(inContainerDispatch()).toBe(false);
    await retireRepoLicense(GUID);
    expect(tunnelMock).toHaveBeenCalledWith(`/account/api/v1/licenses/repos/${GUID}/retire`, {
      method: 'POST',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends the retire plain to the executor route with the placeholder bearer and the principal', async () => {
    await withExecutorPrincipal({ tokenId: 'tok-1' }, () => retireRepoLicense(GUID));
    expect(tunnelMock).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${EGRESS}/account/api/v1/proxy/licenses/repos/${GUID}/retire`);
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer PLACEHOLDER');
    expect(JSON.parse(init.body as string)).toEqual({ onBehalfOfTokenId: 'tok-1' });
  });

  it('adds onBehalfOfTokenId to an activation body on the activate route', async () => {
    await withExecutorPrincipal({ tokenId: 'tok-2' }, () =>
      licenceFetch(
        '/account/api/v1/licenses/activate-repo',
        '/account/api/v1/proxy/licenses/activate-repo',
        { repositoryGuid: GUID }
      )
    );
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${EGRESS}/account/api/v1/proxy/licenses/activate-repo`);
    expect(JSON.parse(init.body as string)).toEqual({
      repositoryGuid: GUID,
      onBehalfOfTokenId: 'tok-2',
    });
  });

  it('fails named, with no tunnel fallback, when the principal has no token id', async () => {
    await expect(
      withExecutorPrincipal({ tokenId: undefined }, () => retireRepoLicense(GUID))
    ).rejects.toThrow(/carries no token id/);
    expect(tunnelMock).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('throws the server refusal with its status and code', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: 'no', code: 'ON_BEHALF_TOKEN_FORBIDDEN' }), {
        status: 403,
      })
    );
    await expect(
      withExecutorPrincipal({ tokenId: 'tok-1' }, () => retireRepoLicense(GUID))
    ).rejects.toMatchObject({ status: 403, code: 'ON_BEHALF_TOKEN_FORBIDDEN' });
  });
});
