import type { AddressInfo } from 'node:net';
import { createServer as createNetServer } from 'node:net';
import ssh2 from 'ssh2';
import { afterEach, describe, expect, it } from 'vitest';
import { HostKeyScanError, parseKnownHosts, scanHostKeys } from '../host-keys.js';

/** The public blob of a private host key, base64, as known_hosts records it. */
function publicBlob(privateKey: string): string {
  const parsed = ssh2.utils.parseKey(privateKey);
  if (parsed instanceof Error) throw parsed;
  const key = Array.isArray(parsed) ? parsed[0]! : parsed;
  return key.getPublicSSH().toString('base64');
}

const ed25519 = ssh2.utils.generateKeyPairSync('ed25519').private;
const rsa = ssh2.utils.generateKeyPairSync('rsa', { bits: 2048 }).private;

const servers: Array<{ close: () => void }> = [];
afterEach(() => {
  for (const s of servers.splice(0)) s.close();
});

/** A real ssh2 server on 127.0.0.1 holding the given host keys; nobody can authenticate. */
async function sshServer(hostKeys: string[]): Promise<number> {
  const server = new ssh2.Server({ hostKeys }, (client) => {
    client.on('authentication', (ctx) => ctx.reject());
    client.on('error', () => undefined);
  });
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  return (server.address() as AddressInfo).port;
}

/** A port that was just bound and released, so nothing answers on it. */
async function closedPort(): Promise<number> {
  const srv = createNetServer();
  await new Promise<void>((resolve) => srv.listen(0, '127.0.0.1', resolve));
  const { port } = srv.address() as AddressInfo;
  await new Promise<void>((resolve) => srv.close(() => resolve()));
  return port;
}

describe('scanHostKeys', () => {
  it('reads every host key the server holds, one known_hosts line per type', async () => {
    const port = await sshServer([ed25519, rsa]);
    const text = await scanHostKeys('127.0.0.1', port);

    const lines = text.split('\n');
    expect(lines).toHaveLength(2);
    // Non-22 ports use the bracketed host field ssh-keyscan writes.
    for (const l of lines) expect(l.startsWith(`[127.0.0.1]:${port} `)).toBe(true);
    // RSA is recorded as `ssh-rsa` even though it signs as rsa-sha2-512.
    expect(parseKnownHosts(text)).toEqual(
      expect.arrayContaining([
        { type: 'ssh-ed25519', key: publicBlob(ed25519) },
        { type: 'ssh-rsa', key: publicBlob(rsa) },
      ])
    );
  });

  it('succeeds with only the families the host has', async () => {
    const port = await sshServer([ed25519]);
    expect(parseKnownHosts(await scanHostKeys('127.0.0.1', port))).toEqual([
      { type: 'ssh-ed25519', key: publicBlob(ed25519) },
    ]);
  });

  it('rejects with the reason when nothing answers', async () => {
    const port = await closedPort();
    const err = await scanHostKeys('127.0.0.1', port, { timeoutMs: 3000 }).catch((e) => e);
    expect(err).toBeInstanceOf(HostKeyScanError);
    expect(err.kind).toBe('unreachable');
    expect(err.message).toContain('ECONNREFUSED');
    expect(err.message).toContain(`127.0.0.1:${port}`);
  });

  it('rejects as a timeout when the port accepts but never speaks SSH', async () => {
    const silent = createNetServer(() => undefined);
    servers.push(silent);
    await new Promise<void>((resolve) => silent.listen(0, '127.0.0.1', resolve));
    const { port } = silent.address() as AddressInfo;
    const err = await scanHostKeys('127.0.0.1', port, { timeoutMs: 500 }).catch((e) => e);
    expect(err).toBeInstanceOf(HostKeyScanError);
    expect(err.kind).toBe('timeout');
  });
});
