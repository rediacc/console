/**
 * Design 7 of PLAN-rmcp-executor-hardening: the `--proxy` client re-grants once
 * when the executor no longer holds its session (404 EXECUTOR_SESSION_UNKNOWN)
 * and retries with the same request id, and consecutive runs reuse the session
 * the first one granted through the session cache instead of repeating
 * server-info, the session open and the CEK grant.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { generateCek, toBase64 } from '@rediacc/shared/config-crypto';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ProxyClient, resetProxySessions } from '../proxy-client.js';
import { PROXY_SESSION_TTL_MS, ProxySessionCache } from '../proxy-session-cache.js';

const SESSION_UNKNOWN = {
  error: 'Unknown or expired session. Open a new one.',
  code: 'EXECUTOR_SESSION_UNKNOWN',
};

function ndjsonResult(): Response {
  const line = {
    kind: 'result',
    result: { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' },
    stdout: 'ok',
  };
  return new Response(`${JSON.stringify(line)}\n`, { status: 200 });
}

interface Executor {
  fetchImpl: typeof fetch;
  calls: string[];
  /** The X-Config-Session header and request id of each command POST. */
  commands: { session: string | null; requestId: string }[];
  /** Session ids the executor still holds; a test drops one to model a redeploy. */
  live: Set<string>;
}

async function fakeContainerExecutor(): Promise<Executor> {
  const keyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, false, [
    'deriveBits',
  ])) as CryptoKeyPair;
  const publicKey = toBase64(
    new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey))
  );
  const calls: string[] = [];
  const commands: Executor['commands'] = [];
  const live = new Set<string>();
  let opened = 0;

  const fetchImpl = ((url: string | URL, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    calls.push(`${init?.method ?? 'GET'} ${path}`);
    if (path === PROXY_ROUTES.serverInfo) {
      return Promise.resolve(
        Response.json({ cliVersion: 'x', contractVersion: 'y', mode: 'container' })
      );
    }
    if (path === PROXY_ROUTES.session) {
      opened += 1;
      const sessionId = `s${opened}`;
      live.add(sessionId);
      return Promise.resolve(Response.json({ sessionId, publicKey }));
    }
    if (path.endsWith('/cek')) return Promise.resolve(Response.json({ ok: true }));
    if (path === PROXY_ROUTES.command) return Promise.resolve(command(init));
    return Promise.reject(new Error(`unexpected call ${path}`));
  }) as typeof fetch;

  /** POST /v1/command: refused with the session code when the named session is gone. */
  function command(init?: RequestInit): Response {
    const headers = (init?.headers ?? {}) as Record<string, string | undefined>;
    const session = headers['x-config-session'] ?? null;
    const { requestId } = JSON.parse(String(init?.body)) as { requestId: string };
    commands.push({ session, requestId });
    if (session && !live.has(session)) return Response.json(SESSION_UNKNOWN, { status: 404 });
    return ndjsonResult();
  }

  return { fetchImpl, calls, commands, live };
}

describe('ProxyClient re-grant and cross-run reuse', () => {
  const dirs: string[] = [];
  let cek: CryptoKey;
  let cekReads: number;

  beforeEach(async () => {
    resetProxySessions();
    cek = await generateCek();
    cekReads = 0;
  });

  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  function cacheDir(): string {
    const dir = mkdtempSync(join(tmpdir(), 'proxy-sessions-'));
    dirs.push(dir);
    return dir;
  }

  function client(executor: Executor, sessionCache?: ProxySessionCache): ProxyClient {
    return new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve('rdt_user'),
      contractVersion: 'contract-v1',
      fetchImpl: executor.fetchImpl,
      ticketStore: null,
      sleep: () => Promise.resolve(),
      getCek: () => {
        cekReads += 1;
        return Promise.resolve(cek);
      },
      ...(sessionCache ? { sessionCache } : {}),
    });
  }

  const sessionOpens = (executor: Executor) =>
    executor.calls.filter((c) => c === `POST ${PROXY_ROUTES.session}`).length;

  it('re-grants once on EXECUTOR_SESSION_UNKNOWN and retries with the same request id', async () => {
    const executor = await fakeContainerExecutor();
    const proxy = client(executor);
    await proxy.run('repo list', {}, {}, () => undefined);
    expect(executor.commands).toHaveLength(1);

    // The executor is redeployed: the granted session is gone.
    executor.live.clear();
    const outcome = await proxy.run('repo list', {}, {}, () => undefined);

    expect(outcome.exitCode).toBe(0);
    expect(sessionOpens(executor)).toBe(2);
    const [, refused, retried] = executor.commands;
    expect(refused.session).toBe('s1');
    expect(retried.session).toBe('s2');
    expect(retried.requestId).toBe(refused.requestId);
    expect(executor.commands).toHaveLength(3);
  });

  it('gives up after one re-grant when the new session is refused too', async () => {
    const executor = await fakeContainerExecutor();
    const proxy = client(executor);
    await proxy.run('repo list', {}, {}, () => undefined);
    executor.live.clear();
    // Every session the executor opens from here is forgotten at once.
    const realAdd = executor.live.add.bind(executor.live);
    executor.live.add = (value: string) => {
      realAdd(value);
      executor.live.delete(value);
      return executor.live;
    };

    await expect(proxy.run('repo list', {}, {}, () => undefined)).rejects.toThrow(
      /EXECUTOR_SESSION_UNKNOWN/
    );
    expect(sessionOpens(executor)).toBe(2);
  });

  it('does not re-grant on a 404 without the session code (control)', async () => {
    const executor = await fakeContainerExecutor();
    const fetchImpl = ((url: string | URL, init?: RequestInit) =>
      new URL(String(url)).pathname === PROXY_ROUTES.command
        ? Promise.resolve(Response.json({ error: 'no config key yet' }, { status: 404 }))
        : executor.fetchImpl(url, init)) as typeof fetch;
    const proxy = client({ ...executor, fetchImpl });

    await expect(proxy.run('repo list', {}, {}, () => undefined)).rejects.toThrow(/404/);
    expect(sessionOpens(executor)).toBe(1);
  });

  it('opens one session in total across two consecutive runs', async () => {
    const executor = await fakeContainerExecutor();
    const dir = cacheDir();

    await client(executor, new ProxySessionCache({ dir })).run(
      'repo list',
      {},
      {},
      () => undefined
    );
    // A new process: nothing in memory carries over, only the cache file.
    resetProxySessions();
    await client(executor, new ProxySessionCache({ dir })).run(
      'repo list',
      {},
      {},
      () => undefined
    );

    expect(sessionOpens(executor)).toBe(1);
    expect(executor.calls.filter((c) => c.endsWith(PROXY_ROUTES.serverInfo))).toHaveLength(1);
    expect(cekReads).toBe(1);
    expect(executor.commands.map((c) => c.session)).toEqual(['s1', 's1']);
  });

  it('grants afresh once the cached session is past the executor TTL (control)', async () => {
    const executor = await fakeContainerExecutor();
    const dir = cacheDir();
    let clock = 1_000_000;
    const cache = () => new ProxySessionCache({ dir, now: () => clock });

    await client(executor, cache()).run('repo list', {}, {}, () => undefined);
    resetProxySessions();
    clock += PROXY_SESSION_TTL_MS + 1;
    await client(executor, cache()).run('repo list', {}, {}, () => undefined);

    expect(sessionOpens(executor)).toBe(2);
  });
});
