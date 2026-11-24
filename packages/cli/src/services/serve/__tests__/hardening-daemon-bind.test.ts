/**
 * Design 9 of PLAN-rmcp-executor-hardening: a daemon executor binds loopback
 * by default, refuses a non-loopback address without TLS, and with a
 * certificate and key serves HTTPS. A container keeps its 0.0.0.0 default,
 * since its port is reachable only from its own Durable Object.
 *
 * The certificate is a real self-signed pair minted by openssl, and the HTTPS
 * case is a real listening server answering a real request.
 */

import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { request } from 'node:https';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { ValidationError } from '../../../utils/errors.js';
import { isLoopbackHost, resolveServeBind, serveListenOptions } from '../bind.js';

let dir = '';
let certPath = '';
let keyPath = '';

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'serve-tls-'));
  certPath = join(dir, 'cert.pem');
  keyPath = join(dir, 'key.pem');
  execFileSync(
    'openssl',
    [
      'req',
      '-x509',
      '-newkey',
      'ec',
      '-pkeyopt',
      'ec_paramgen_curve:prime256v1',
      '-nodes',
      '-keyout',
      keyPath,
      '-out',
      certPath,
      '-days',
      '1',
      '-subj',
      '/CN=127.0.0.1',
      '-addext',
      'subjectAltName=IP:127.0.0.1',
    ],
    { stdio: 'pipe' }
  );
});

afterAll(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe('daemon bind', () => {
  it('binds 127.0.0.1 by default, over plain HTTP', () => {
    expect(resolveServeBind({ mode: 'daemon' })).toEqual({ hostname: '127.0.0.1' });
  });

  it('refuses --host 0.0.0.0 without TLS, naming the way out', () => {
    expect(() => resolveServeBind({ mode: 'daemon', host: '0.0.0.0' })).toThrow(ValidationError);
    expect(() => resolveServeBind({ mode: 'daemon', host: '0.0.0.0' })).toThrow(/--tls-cert/);
    expect(() => resolveServeBind({ mode: 'daemon', host: '192.168.1.10' })).toThrow(
      ValidationError
    );
  });

  it('accepts other loopback spellings without TLS (control)', () => {
    for (const host of ['localhost', '127.0.0.2', '::1']) {
      expect(resolveServeBind({ mode: 'daemon', host }).hostname).toBe(host);
    }
    // A bracketed literal is unbracketed, since Node's listen cannot resolve '[::1]' (review 8dfddee9.1).
    expect(resolveServeBind({ mode: 'daemon', host: '[::1]' }).hostname).toBe('::1');
    expect(isLoopbackHost('0.0.0.0')).toBe(false);
    expect(isLoopbackHost('::')).toBe(false);
    expect(isLoopbackHost('128.0.0.1')).toBe(false);
  });

  it('refuses half a TLS pair and an unreadable file', () => {
    expect(() => resolveServeBind({ mode: 'daemon', host: '0.0.0.0', tlsCert: certPath })).toThrow(
      /--tls-cert and --tls-key go together/
    );
    expect(() =>
      resolveServeBind({
        mode: 'daemon',
        host: '0.0.0.0',
        tlsCert: join(dir, 'missing.pem'),
        tlsKey: keyPath,
      })
    ).toThrow(/missing\.pem/);
  });

  it('keeps the container default of 0.0.0.0 over HTTP', () => {
    expect(resolveServeBind({ mode: 'container' })).toEqual({ hostname: '0.0.0.0' });
  });

  it('serves HTTPS with a self-signed pair', async () => {
    const bind = resolveServeBind({
      mode: 'daemon',
      host: '127.0.0.1',
      tlsCert: certPath,
      tlsKey: keyPath,
    });
    expect(bind.tls).toBeDefined();
    const app = new Hono().get('/v1/health', (c) => c.json({ ok: true }));
    const server = serve({ fetch: app.fetch, port: 0, ...serveListenOptions(bind) });
    try {
      await new Promise<void>((resolve) => server.once('listening', () => resolve()));
      const { port } = server.address() as AddressInfo;
      const body = await new Promise<string>((resolve, reject) => {
        const req = request(
          { host: '127.0.0.1', port, path: '/v1/health', ca: readFileSync(certPath) },
          (res) => {
            let text = '';
            res.on('data', (chunk: Buffer) => {
              text += chunk.toString();
            });
            res.on('end', () => resolve(text));
          }
        );
        req.on('error', reject);
        req.end();
      });
      expect(JSON.parse(body)).toEqual({ ok: true });
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });
});
