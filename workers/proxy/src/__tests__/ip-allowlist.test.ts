import { describe, expect, it } from 'vitest';

import worker, { type Env } from '../index';
import { allowlistRefusal, LICENSE_RENEW_PATH } from '../ip-allowlist';

const LISTED = '203.0.113.7';
const OUTSIDE = '198.51.100.9';

function req(method: string, path: string, ip?: string): Request {
  return new Request(`https://proxy.test${path}`, {
    method,
    headers: ip ? { 'cf-connecting-ip': ip } : {},
  });
}

describe('allowlistRefusal', () => {
  it('is off when ALLOW_IPS is unset or empty', () => {
    expect(allowlistRefusal(req('GET', '/x', OUTSIDE), undefined)).toBeUndefined();
    expect(allowlistRefusal(req('GET', '/x', OUTSIDE), ' ')).toBeUndefined();
  });

  it('admits a listed address and an address inside a listed range', () => {
    expect(allowlistRefusal(req('GET', '/x', LISTED), LISTED)).toBeUndefined();
    expect(allowlistRefusal(req('GET', '/x', LISTED), '203.0.113.0/24')).toBeUndefined();
  });

  it('refuses an unlisted address and a request with no address', () => {
    expect(allowlistRefusal(req('GET', '/x', OUTSIDE), LISTED)?.status).toBe(403);
    expect(allowlistRefusal(req('GET', '/x', OUTSIDE), '203.0.113.0/24')?.status).toBe(403);
    expect(allowlistRefusal(req('GET', '/x'), LISTED)?.status).toBe(403);
  });

  it('refuses through a malformed range rather than matching every address', () => {
    for (const entry of ['203.0.113.0/', '203.0.113.0/0x0', '203.0.113.0/ 8', '203.0.113.0/33']) {
      expect(allowlistRefusal(req('GET', '/x', OUTSIDE), entry)?.status).toBe(403);
    }
  });

  it('exempts POST on the renew path only', () => {
    expect(allowlistRefusal(req('POST', LICENSE_RENEW_PATH, OUTSIDE), LISTED)).toBeUndefined();
    expect(allowlistRefusal(req('GET', LICENSE_RENEW_PATH, OUTSIDE), LISTED)?.status).toBe(403);
    expect(allowlistRefusal(req('POST', '/account/api/v1/other', OUTSIDE), LISTED)?.status).toBe(
      403
    );
    expect(allowlistRefusal(req('POST', `${LICENSE_RENEW_PATH}/x`, OUTSIDE), LISTED)?.status).toBe(
      403
    );
  });
});

describe('the default fetch handler', () => {
  const env = { ACCOUNT_URL: 'https://account.test', ALLOW_IPS: LISTED } as Env;

  it('refuses an unlisted caller before any route, health included', async () => {
    const res = await worker.fetch(req('GET', '/v1/health', OUTSIDE), env);
    expect(res.status).toBe(403);
  });

  it('serves a listed caller', async () => {
    const res = await worker.fetch(req('GET', '/v1/health', LISTED), env);
    expect(res.status).toBe(200);
  });

  it('lets POST on the renew path past the allowlist but not GET', async () => {
    const post = await worker.fetch(req('POST', LICENSE_RENEW_PATH, OUTSIDE), env);
    expect(post.status).not.toBe(403);
    const get = await worker.fetch(req('GET', LICENSE_RENEW_PATH, OUTSIDE), env);
    expect(get.status).toBe(403);
  });
});
