/**
 * `/v1/internal/occupancy` (PLAN-rmcp-executor-hardening.md box EH8, D52): the coordinator count answers only a request whose internal credential the ISSUER binding verifies; every other caller gets the bare 404 of an unknown path.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import worker, { type Env } from '../index';
import { type ExecutorIssuerRpc, resetIssuedTokenCache } from '../issued-token';
import { resetReadyCache } from '../ready';

const GOOD = 'good-credential';
const COUNT = { total: 3, heavy: 1, cap: 25, heavyCap: 5 };

function issuer(verify: (credential: string) => Promise<boolean>): Service<ExecutorIssuerRpc> {
  return { verifyInternal: verify } as unknown as Service<ExecutorIssuerRpc>;
}

function capacity(count: () => unknown, calls: { n: number }): Env['EXECUTOR_CAPACITY'] {
  const stub = {
    count: () => {
      calls.n += 1;
      return Promise.resolve(count());
    },
  };
  return {
    idFromName: (name: string) => ({ toString: () => name }),
    get: () => stub,
  } as unknown as Env['EXECUTOR_CAPACITY'];
}

function env(extra: Partial<Env>): Env {
  return { ACCOUNT_URL: 'https://account.test', ...extra };
}

async function call(e: Env, headers: Record<string, string> = {}, method = 'GET') {
  const response = await worker.fetch(
    new Request('https://proxy.test/v1/internal/occupancy', { method, headers }),
    e
  );
  return { status: response.status, text: await response.text() };
}

beforeEach(() => {
  resetIssuedTokenCache();
  resetReadyCache();
  vi.restoreAllMocks();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('/v1/internal/occupancy', () => {
  it('answers the count, only its four integers, to a credential the issuer verifies', async () => {
    const calls = { n: 0 };
    const e = env({
      ISSUER: issuer(async (credential) => credential === GOOD),
      EXECUTOR_CAPACITY: capacity(() => ({ ...COUNT, extra: 'org-a' }), calls),
    });
    const answer = await call(e, { 'x-rediacc-internal': GOOD });
    expect(answer.status).toBe(200);
    expect(JSON.parse(answer.text)).toEqual({ executors: COUNT });
    expect(calls.n).toBe(1);
  });

  it('answers 404 with the unknown-path body when the credential is missing, forged or expired, and never reads the coordinator', async () => {
    const calls = { n: 0 };
    const e = env({
      ISSUER: issuer(async (credential) => credential === GOOD),
      EXECUTOR_CAPACITY: capacity(() => COUNT, calls),
    });
    for (const headers of [
      {},
      { 'x-rediacc-internal': 'forged' },
      { 'x-rediacc-internal': '' },
    ] as Record<string, string>[]) {
      expect(await call(e, headers)).toEqual({ status: 404, text: 'Not Found' });
    }
    expect(calls.n).toBe(0);
  });

  it('answers 404 when the issuer cannot answer, is missing, or the method is not GET', async () => {
    const calls = { n: 0 };
    const failing = env({
      ISSUER: issuer(() => Promise.reject(new Error('down'))),
      EXECUTOR_CAPACITY: capacity(() => COUNT, calls),
    });
    expect((await call(failing, { 'x-rediacc-internal': GOOD })).status).toBe(404);
    const unbound = env({ EXECUTOR_CAPACITY: capacity(() => COUNT, calls) });
    expect((await call(unbound, { 'x-rediacc-internal': GOOD })).status).toBe(404);
    const verifying = env({
      ISSUER: issuer(async () => true),
      EXECUTOR_CAPACITY: capacity(() => COUNT, calls),
    });
    expect((await call(verifying, { 'x-rediacc-internal': GOOD }, 'POST')).status).toBe(404);
    expect(calls.n).toBe(0);
  });

  it('answers 503 to a verified caller when the coordinator cannot answer', async () => {
    const calls = { n: 0 };
    const e = env({
      ISSUER: issuer(async () => true),
      EXECUTOR_CAPACITY: capacity(() => {
        throw new Error('coordinator down');
      }, calls),
    });
    expect((await call(e, { 'x-rediacc-internal': GOOD })).status).toBe(503);
  });

  it('control: a verifier that accepts anything is told apart from the real one by the forged case', async () => {
    const calls = { n: 0 };
    const lax = env({
      ISSUER: issuer(async () => true),
      EXECUTOR_CAPACITY: capacity(() => COUNT, calls),
    });
    expect((await call(lax, { 'x-rediacc-internal': 'forged' })).status).toBe(200);
  });
});
