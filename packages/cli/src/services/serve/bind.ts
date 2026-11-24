/**
 * Where `rdc serve` listens, and whether it must speak TLS (Design 9 of
 * PLAN-rmcp-executor-hardening).
 *
 * A DAEMON runs on a customer's host and used to bind every interface over
 * plain HTTP, so bearer tokens crossed the network in the clear. It now binds
 * loopback unless told otherwise, and a non-loopback address is refused unless
 * a certificate and key are given, in which case it serves HTTPS.
 *
 * A CONTAINER keeps binding every interface over HTTP: its port is reachable
 * only from its own Durable Object inside Cloudflare, which terminates TLS at
 * the edge (workers/proxy/Dockerfile runs it with no --host).
 */

import { readFileSync } from 'node:fs';
import { createServer as createHttpsServer } from 'node:https';
import { isIP } from 'node:net';
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';

export interface ServeBindOptions {
  mode: 'daemon' | 'container';
  host?: string;
  tlsCert?: string;
  tlsKey?: string;
}

export interface ServeBind {
  hostname: string;
  /** PEM certificate and key; present means HTTPS. */
  tls?: { cert: Buffer; key: Buffer };
}

/** The address each mode binds when --host is absent. */
const DEFAULT_HOST = { daemon: '127.0.0.1', container: '0.0.0.0' } as const;

/** True for an address only this host can reach: 127.0.0.0/8, ::1 and `localhost`. */
export function isLoopbackHost(host: string): boolean {
  const bare = host.replace(/^\[(.*)\]$/, '$1').toLowerCase();
  if (bare === 'localhost') return true;
  if (isIP(bare) === 4) return bare.startsWith('127.');
  if (isIP(bare) === 6) return bare === '::1' || bare === '0:0:0:0:0:0:0:1';
  return false;
}

/**
 * Resolve the bind address and TLS material, or refuse. `readFile` is a test
 * seam; an unreadable certificate or key is refused naming the path.
 */
export function resolveServeBind(
  options: ServeBindOptions,
  readFile: (path: string) => Buffer = readFileSync
): ServeBind {
  const hostname = options.host ?? DEFAULT_HOST[options.mode];
  const { tlsCert, tlsKey } = options;

  if ((tlsCert === undefined) !== (tlsKey === undefined)) {
    throw new ValidationError(t('commands.serve.errors.tlsPairIncomplete'));
  }
  if (tlsCert !== undefined && tlsKey !== undefined) {
    return { hostname, tls: { cert: read(tlsCert, readFile), key: read(tlsKey, readFile) } };
  }
  if (options.mode === 'daemon' && !isLoopbackHost(hostname)) {
    throw new ValidationError(t('commands.serve.errors.tlsRequired', { host: hostname }));
  }
  return { hostname };
}

function read(path: string, readFile: (path: string) => Buffer): Buffer {
  try {
    return readFile(path);
  } catch (error) {
    throw new ValidationError(
      t('commands.serve.errors.tlsUnreadable', {
        path,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * The listen options `@hono/node-server`'s `serve` takes for a resolved bind:
 * the hostname, and an HTTPS server carrying the certificate when TLS is on.
 */
export function serveListenOptions(bind: ServeBind): {
  hostname: string;
  createServer?: typeof createHttpsServer;
  serverOptions?: { cert: Buffer; key: Buffer };
} {
  if (!bind.tls) return { hostname: bind.hostname };
  return {
    hostname: bind.hostname,
    createServer: createHttpsServer,
    serverOptions: { cert: bind.tls.cert, key: bind.tls.key },
  };
}
