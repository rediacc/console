/**
 * B4: the `--proxy` client grants its config key to a CONTAINER executor.
 *
 * Before this, ProxyClient called only /v1/command, /v1/server-info and
 * /v1/jobs. A container executor starts with no key, so it answered every
 * command "This session has no config key yet", and only the web console could
 * complete the grant. These pin the client half: it opens a session, seals the
 * CEK to the executor's X25519 key (for real: the test opens the blob with the
 * executor's private key), posts it once per process, and never sends it to a
 * daemon.
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import {
  type CekHandoffBlob,
  cekHandoffDecrypt,
  exportAesKey,
  generateCek,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ProxyClient, resetProxySessions } from '../proxy-client.js';

interface FakeExecutor {
  fetchImpl: typeof fetch;
  calls: string[];
  blobs: CekHandoffBlob[];
  privateKey: CryptoKey;
}

async function fakeExecutor(
  mode: 'container' | 'daemon',
  opts: { failGrantOnce?: boolean } = {}
): Promise<FakeExecutor> {
  const keyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, false, [
    'deriveBits',
  ])) as CryptoKeyPair;
  const publicKey = toBase64(
    new Uint8Array(await crypto.subtle.exportKey('spki', keyPair.publicKey))
  );
  const calls: string[] = [];
  const blobs: CekHandoffBlob[] = [];
  let failGrant = opts.failGrantOnce ?? false;
  let sessions = 0;

  const fetchImpl = ((url: string | URL, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    calls.push(`${init?.method ?? 'GET'} ${path}`);
    if (path === PROXY_ROUTES.serverInfo) {
      return Promise.resolve(Response.json({ cliVersion: 'x', contractVersion: 'y', mode }));
    }
    if (path === PROXY_ROUTES.session) {
      sessions += 1;
      return Promise.resolve(Response.json({ sessionId: `s${sessions}`, publicKey }));
    }
    if (path.endsWith('/cek')) {
      if (failGrant) {
        failGrant = false;
        return Promise.resolve(new Response('try again', { status: 500 }));
      }
      blobs.push(JSON.parse(String(init?.body)) as CekHandoffBlob);
      return Promise.resolve(Response.json({ ok: true }));
    }
    return Promise.reject(new Error(`unexpected call ${path}`));
  }) as typeof fetch;

  return { fetchImpl, calls, blobs, privateKey: keyPair.privateKey };
}

describe('ProxyClient.ensureSession', () => {
  let cek: CryptoKey;
  let cekReads: number;

  beforeEach(async () => {
    resetProxySessions();
    cek = await generateCek();
    cekReads = 0;
  });

  afterEach(() => {
    resetProxySessions();
  });

  function client(executor: FakeExecutor, token = 'rdt_owner'): ProxyClient {
    return new ProxyClient({
      baseUrl: 'http://executor.test',
      getToken: () => Promise.resolve(token),
      contractVersion: 'y',
      fetchImpl: executor.fetchImpl,
      getCek: () => {
        cekReads += 1;
        return Promise.resolve(cek);
      },
    });
  }

  it('seals the CEK to the container executor key, which opens it to the same key', async () => {
    const executor = await fakeExecutor('container');

    await client(executor).ensureSession();

    expect(executor.calls).toEqual([
      'GET /v1/server-info',
      'POST /v1/session',
      'POST /v1/session/s1/cek',
    ]);
    expect(executor.blobs).toHaveLength(1);
    // The executor's private key opens it, and inside is exactly the caller's CEK.
    const opened = await cekHandoffDecrypt(executor.blobs[0], executor.privateKey);
    expect(toBase64(opened)).toBe(toBase64(await exportAesKey(cek)));
    // And it never travelled in the clear.
    expect(JSON.stringify(executor.blobs[0])).not.toContain(toBase64(await exportAesKey(cek)));
  });

  it('grants once per process, however many commands and clients follow', async () => {
    const executor = await fakeExecutor('container');

    await Promise.all([client(executor).ensureSession(), client(executor).ensureSession()]);
    await client(executor).ensureSession();

    expect(executor.calls.filter((c) => c === 'POST /v1/session')).toHaveLength(1);
    expect(executor.blobs).toHaveLength(1);
    expect(cekReads).toBe(1);
  });

  it('grants again for a different caller token', async () => {
    const executor = await fakeExecutor('container');

    await client(executor, 'rdt_a').ensureSession();
    await client(executor, 'rdt_b').ensureSession();

    expect(executor.blobs).toHaveLength(2);
  });

  it('never sends the key to a daemon, which derives its own', async () => {
    const executor = await fakeExecutor('daemon');

    await client(executor).ensureSession();

    expect(executor.calls).toEqual(['GET /v1/server-info']);
    expect(cekReads).toBe(0);
  });

  it('does not remember a failed grant: the next command retries it', async () => {
    const executor = await fakeExecutor('container', { failGrantOnce: true });

    await expect(client(executor).ensureSession()).rejects.toThrow(/500/);
    await client(executor).ensureSession();

    expect(executor.blobs).toHaveLength(1);
  });
});
