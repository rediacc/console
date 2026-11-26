/**
 * Review 9a8dc910.1: a failed proxy request says whether it can have reached the executor. A connect-phase failure
 * (refused, unresolved, unroutable, a failed TLS handshake) cannot have started anything; a timeout, a reset or a
 * failure with no code can have. Across the start retries of one command, any attempt that may have reached keeps
 * the final error "may have reached".
 */

import { describe, expect, it } from 'vitest';
import { ProxyClient } from '../proxy-client.js';
import {
  fetchMayHaveReached,
  fetchWithTimeout,
  ProxyRequestError,
} from '../proxy-client-support.js';

const coded = (code: string) => Object.assign(new Error(`${code} x`), { code });
const fetchFailed = (cause?: unknown) => new TypeError('fetch failed', { cause });
const rejecting = (cause?: unknown) =>
  (() => Promise.reject(fetchFailed(cause))) as unknown as typeof fetch;

describe('fetchMayHaveReached', () => {
  it.each([
    'ECONNREFUSED',
    'ENOTFOUND',
    'EAI_AGAIN',
    'EHOSTUNREACH',
    'ENETUNREACH',
    'UND_ERR_CONNECT_TIMEOUT',
    'CERT_HAS_EXPIRED',
    'DEPTH_ZERO_SELF_SIGNED_CERT',
    'ERR_TLS_CERT_ALTNAME_INVALID',
    'ERR_SSL_WRONG_VERSION_NUMBER',
  ])('%s never reached the executor', (code) => {
    expect(fetchMayHaveReached(fetchFailed(coded(code)), false)).toBe(false);
  });

  it.each([
    'ECONNRESET',
    'UND_ERR_SOCKET',
    'EPIPE',
    'UND_ERR_HEADERS_TIMEOUT',
    'ERR_SSL_BAD_RECORD_MAC',
    'ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC',
  ])('%s may have reached it', (code) => {
    expect(fetchMayHaveReached(fetchFailed(coded(code)), false)).toBe(true);
  });

  it('a timeout may have reached it, whatever the cause says', () => {
    expect(fetchMayHaveReached(fetchFailed(coded('ECONNREFUSED')), true)).toBe(true);
  });

  it('a failure with no cause or no code may have reached it', () => {
    expect(fetchMayHaveReached(fetchFailed(), false)).toBe(true);
    expect(fetchMayHaveReached(fetchFailed(new Error('other side closed')), false)).toBe(true);
    expect(fetchMayHaveReached('not an error', false)).toBe(true);
  });

  it('an AggregateError never reached only when every address failed to connect', () => {
    const refusedAll = new AggregateError([coded('ECONNREFUSED'), coded('EHOSTUNREACH')]);
    const mixed = new AggregateError([coded('ECONNREFUSED'), coded('ECONNRESET')]);
    expect(fetchMayHaveReached(fetchFailed(refusedAll), false)).toBe(false);
    expect(fetchMayHaveReached(fetchFailed(mixed), false)).toBe(true);
    expect(fetchMayHaveReached(fetchFailed(new AggregateError([])), false)).toBe(true);
  });
});

describe('fetchWithTimeout', () => {
  it('raises a NETWORK_ERROR ProxyRequestError carrying the classification and the cause', async () => {
    const refused = await fetchWithTimeout(
      rejecting(coded('ECONNREFUSED')),
      1000,
      'http://executor.test:8080/x',
      {}
    ).catch((e: unknown) => e);
    expect(refused).toBeInstanceOf(ProxyRequestError);
    expect((refused as ProxyRequestError).code).toBe('NETWORK_ERROR');
    expect((refused as ProxyRequestError).retryable).toBe(true);
    expect((refused as ProxyRequestError).mayHaveReached).toBe(false);
    expect((refused as Error).cause).toBeInstanceOf(TypeError);

    const reset = await fetchWithTimeout(
      rejecting(coded('ECONNRESET')),
      1000,
      'http://executor.test:8080/x',
      {}
    ).catch((e: unknown) => e);
    expect((reset as ProxyRequestError).mayHaveReached).toBe(true);
  });
});

describe('a command start across its retries', () => {
  const client = (fetchImpl: typeof fetch) =>
    new ProxyClient({
      baseUrl: 'http://executor.test:8080',
      getToken: () => Promise.resolve('rdt_x'),
      contractVersion: 'y',
      fetchImpl,
      timeoutMs: 1000,
      sleep: () => Promise.resolve(),
      ticketStore: null,
    });

  it('every attempt refused: the start never reached the executor', async () => {
    const error = await client(rejecting(coded('ECONNREFUSED')))
      .run('repo create', {}, {}, () => undefined)
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ProxyRequestError);
    expect((error as ProxyRequestError).mayHaveReached).toBe(false);
  });

  it('an earlier attempt reset mid-request, the last refused: the start may have reached it (control)', async () => {
    let calls = 0;
    const fetchImpl = (() => {
      calls += 1;
      return Promise.reject(fetchFailed(coded(calls === 1 ? 'ECONNRESET' : 'ECONNREFUSED')));
    }) as unknown as typeof fetch;
    const error = await client(fetchImpl)
      .run('repo create', {}, {}, () => undefined)
      .catch((e: unknown) => e);
    expect(calls).toBeGreaterThan(1);
    expect(error).toBeInstanceOf(ProxyRequestError);
    expect((error as ProxyRequestError).mayHaveReached).toBe(true);
    expect((error as Error).message).toContain('ECONNREFUSED');
  });
});
