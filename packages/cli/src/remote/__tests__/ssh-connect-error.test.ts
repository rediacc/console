import { generateKeyPairSync } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { createServer, type Server } from 'node:net';
import type { Client as SSHClient } from 'ssh2';
import { afterEach, describe, expect, it } from 'vitest';
import { EXIT_CODES } from '../../types/index.js';
import { SFTPClient } from '../sftp/client.js';
import {
  classifySshConnectFailure,
  SshConnectError,
  type SshConnectFailureInput,
  type SshConnectFailureKind,
} from '../sftp/connect-error.js';

const privateKey = generateKeyPairSync('rsa', { modulusLength: 2048 })
  .privateKey.export({ type: 'pkcs1', format: 'pem' })
  .toString();

/** A stand-in for the ssh2 client: emits what the test scripts when connect() is called. */
function plantedClient(script: (emitter: EventEmitter) => void): () => SSHClient {
  return () => {
    const emitter = new EventEmitter() as EventEmitter & { connect: () => void; end: () => void };
    emitter.connect = () => setImmediate(() => script(emitter));
    emitter.end = () => undefined;
    return emitter as unknown as SSHClient;
  };
}

const timeoutError = () =>
  Object.assign(new Error('Timed out while waiting for handshake'), { level: 'client-timeout' });

async function connectError(client: SFTPClient): Promise<SshConnectError> {
  const error = await client.connect().then(
    () => undefined,
    (e: unknown) => e
  );
  expect(error).toBeInstanceOf(SshConnectError);
  return error as SshConnectError;
}

const base = { host: '192.0.2.10', port: 22, username: 'u', privateKey, timeout: 300 };

describe('classifySshConnectFailure', () => {
  const cases: [SshConnectFailureInput, SshConnectFailureKind][] = [
    [{ level: 'client-timeout', tcpConnected: false }, 'unreachable'],
    [{ level: 'client-timeout', tcpConnected: true }, 'handshake-timeout'],
    [{ level: 'client-socket', code: 'ETIMEDOUT', tcpConnected: false }, 'unreachable'],
    [{ level: 'client-socket', code: 'ECONNREFUSED', tcpConnected: false }, 'refused'],
    [{ level: 'client-socket', code: 'ENOTFOUND', tcpConnected: false }, 'other'],
    [{ level: 'client-authentication', tcpConnected: true }, 'auth'],
    [{ level: 'protocol', tcpConnected: true }, 'other'],
    [{ tcpConnected: false }, 'other'],
  ];
  it.each(cases)('%j -> %s', (input, kind) => {
    expect(classifySshConnectFailure(input)).toBe(kind);
  });
});

describe('SshConnectError', () => {
  const make = (kind: SshConnectFailureKind) =>
    new SshConnectError({ kind, host: 'h', port: 22, timeoutMs: 10000, cause: 'boom' });

  it('carries the code, exit code and retryability per kind', () => {
    expect(make('unreachable')).toMatchObject({
      errorCode: 'EGRESS_UNREACHABLE',
      exitCode: EXIT_CODES.NETWORK_ERROR,
      retryable: true,
    });
    expect(make('refused')).toMatchObject({
      errorCode: 'SSH_REFUSED',
      exitCode: 6,
      retryable: true,
    });
    expect(make('handshake-timeout')).toMatchObject({
      errorCode: 'SSH_HANDSHAKE_TIMEOUT',
      exitCode: 6,
      retryable: true,
    });
    expect(make('auth')).toMatchObject({
      errorCode: 'SSH_AUTH_FAILED',
      exitCode: 1,
      retryable: false,
    });
    const other = make('other');
    expect(other.errorCode).toBeUndefined();
    expect(other.exitCode).toBe(1);
    expect(other.message).toBe('SSH connection error: boom');
  });

  it('names the cause of an unreachable target', () => {
    const msg = make('unreachable').message;
    expect(msg).toContain('h:22 never answered the TCP connection attempt within 10 s');
    expect(msg).toContain('a firewall may be dropping the traffic');
    expect(make('unreachable').name).toBe('SshConnectError');
  });
});

describe('SFTPClient.connect classification', () => {
  const servers: Server[] = [];
  afterEach(() => {
    for (const s of servers.splice(0)) s.close();
  });

  it('a timeout with no connect event is unreachable', async () => {
    const client = new SFTPClient(
      base,
      plantedClient((e) => e.emit('error', timeoutError()))
    );
    const error = await connectError(client);
    expect(error.kind).toBe('unreachable');
    expect(error.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(error.message).toContain('192.0.2.10:22');
  });

  it('a timeout after the connect event is a handshake timeout', async () => {
    const client = new SFTPClient(
      base,
      plantedClient((e) => {
        e.emit('connect');
        e.emit('error', timeoutError());
      })
    );
    expect((await connectError(client)).kind).toBe('handshake-timeout');
  });

  it('a real connect to a closed loopback port is refused', async () => {
    const probe = createServer();
    await new Promise<void>((r) => probe.listen(0, '127.0.0.1', r));
    const port = (probe.address() as { port: number }).port;
    await new Promise<void>((r) => probe.close(() => r()));
    const error = await connectError(new SFTPClient({ ...base, host: '127.0.0.1', port }));
    expect(error.kind).toBe('refused');
    expect(error.errorCode).toBe('SSH_REFUSED');
  });

  it('a real listener that never sends a banner is a handshake timeout', async () => {
    const server = createServer(() => undefined);
    servers.push(server);
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
    const port = (server.address() as { port: number }).port;
    const error = await connectError(new SFTPClient({ ...base, host: '127.0.0.1', port }));
    expect(error.kind).toBe('handshake-timeout');
    expect(error.errorCode).toBe('SSH_HANDSHAKE_TIMEOUT');
  });
});
