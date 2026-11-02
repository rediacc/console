/**
 * The `--proxy` client's request phase: a stalled executor times out instead of hanging, a network failure
 * names the host and undici's cause (fetch alone reports a bare "fetch failed"), and the timeout bounds only
 * the time to the response headers, never the stream that follows.
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { ProxyClient } from '../proxy-client.js';

function client(fetchImpl: typeof fetch, timeoutMs = 50): ProxyClient {
  return new ProxyClient({
    baseUrl: 'http://executor.test:8080',
    getToken: () => Promise.resolve('rdt_x'),
    contractVersion: 'y',
    fetchImpl,
    timeoutMs,
  });
}

/** A fetch that never answers, and rejects like undici when its signal aborts. */
const stalledFetch = ((_url: string | URL, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () =>
      reject(new DOMException('aborted', 'AbortError'))
    );
  })) as typeof fetch;

describe('proxy client request phase', () => {
  it('times out a serverInfo that never answers', async () => {
    const error = await client(stalledFetch)
      .serverInfo()
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CliExitError);
    expect((error as CliExitError).code).toBe('NETWORK_ERROR');
    expect((error as Error).message).toContain('executor.test:8080');
    expect((error as Error).message).toMatch(/did not answer/);
  });

  it('times out a command POST that never answers', async () => {
    const error = await client(stalledFetch)
      .run('repo up', {}, {}, () => undefined)
      .catch((e: unknown) => e);
    expect((error as Error).message).toMatch(/did not answer/);
  });

  it('names the underlying cause of a network failure and keeps it on `cause`', async () => {
    const cause = Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:8080'), {
      code: 'ECONNREFUSED',
    });
    const failing = (() =>
      Promise.reject(new TypeError('fetch failed', { cause }))) as unknown as typeof fetch;

    const error = await client(failing)
      .serverInfo()
      .catch((e: unknown) => e);

    expect((error as Error).message).toContain('ECONNREFUSED');
    expect((error as Error).message).toContain('executor.test:8080');
    expect((error as Error).cause).toBeInstanceOf(TypeError);
  });

  it('does not cut a stream that is still flowing after the headers arrived', async () => {
    const result = JSON.stringify({
      kind: 'result',
      result: { success: true, exitCode: 0, durationMs: 1 },
      stdout: 'done',
      stderr: '',
    });
    const slowStream = ((url: string | URL, init?: RequestInit) => {
      if (new URL(String(url)).pathname !== PROXY_ROUTES.command) throw new Error('unexpected');
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          // Like undici, an abort of the request's signal errors the body too.
          init?.signal?.addEventListener('abort', () => controller.error(new Error('aborted')));
          // Longer than the 50ms request timeout, and the headers are already out.
          await new Promise((r) => setTimeout(r, 200));
          controller.enqueue(new TextEncoder().encode(`${result}\n`));
          controller.close();
        },
      });
      return Promise.resolve(new Response(body, { status: 200 }));
    }) as unknown as typeof fetch;

    const outcome = await client(slowStream).run('repo up', {}, {}, () => undefined);

    expect(outcome.success).toBe(true);
    expect(outcome.stdout).toBe('done');
  });
});
