import { generateKeyPairSync } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { DEFAULTS } from '@rediacc/shared/config';
import type { Client as SSHClient, ConnectConfig } from 'ssh2';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { seamedSftpClient } from '../../__tests__/sftp-client-seam.js';
import {
  defaultReadyTimeoutMs,
  EXECUTOR_READY_TIMEOUT_MS,
  type SFTPClient,
} from '../sftp/client.js';
import { SshConnectError } from '../sftp/connect-error.js';

const privateKey = generateKeyPairSync('rsa', { modulusLength: 2048 })
  .privateKey.export({ type: 'pkcs1', format: 'pem' })
  .toString();

/** A stand-in ssh2 client that records the connect config and fails the connect as unanswered TCP. */
function recordingClient(seen: ConnectConfig[]): () => SSHClient {
  return () => {
    const emitter = new EventEmitter() as EventEmitter & {
      connect: (config: ConnectConfig) => void;
      end: () => void;
    };
    emitter.connect = (config) => {
      seen.push(config);
      setImmediate(() =>
        emitter.emit(
          'error',
          Object.assign(new Error('Timed out while waiting for handshake'), {
            level: 'client-timeout',
          })
        )
      );
    };
    emitter.end = () => undefined;
    return emitter as unknown as SSHClient;
  };
}

/** An IPv4 literal with no configured IPv6, so the unreachable connect is not retried. */
const base = { host: '192.0.2.10', port: 22, username: 'u', privateKey };

async function failedConnect(client: SFTPClient): Promise<SshConnectError> {
  const error = await client.connect().then(
    () => undefined,
    (e: unknown) => e
  );
  expect(error).toBeInstanceOf(SshConnectError);
  return error as SshConnectError;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('defaultReadyTimeoutMs', () => {
  it('is the longer executor deadline when the container executor env is set', () => {
    expect(defaultReadyTimeoutMs({ REDIACC_EXECUTOR_ORG_ID: 'org-1' })).toBe(
      EXECUTOR_READY_TIMEOUT_MS
    );
  });

  it('keeps the interactive default without it, or with it blank', () => {
    expect(defaultReadyTimeoutMs({})).toBe(DEFAULTS.SSH.READY_TIMEOUT);
    expect(defaultReadyTimeoutMs({ REDIACC_EXECUTOR_ORG_ID: '  ' })).toBe(
      DEFAULTS.SSH.READY_TIMEOUT
    );
  });

  it('outlasts the fourth SYN retransmission at 15 s, and the interactive one does not', () => {
    expect(EXECUTOR_READY_TIMEOUT_MS).toBeGreaterThanOrEqual(20_000);
    expect(DEFAULTS.SSH.READY_TIMEOUT).toBe(10_000);
  });
});

describe('SFTPClient readyTimeout', () => {
  it('connects with the executor deadline inside a container executor', async () => {
    vi.stubEnv('REDIACC_EXECUTOR_ORG_ID', 'org-1');
    const seen: ConnectConfig[] = [];
    const error = await failedConnect(seamedSftpClient(base, recordingClient(seen)));
    expect(seen.map((c) => c.readyTimeout)).toEqual([EXECUTOR_READY_TIMEOUT_MS]);
    expect(error.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(error.timeoutMs).toBe(EXECUTOR_READY_TIMEOUT_MS);
    expect(error.message).toContain('within 25 s');
  });

  it('connects with the 10 s interactive deadline outside one (control)', async () => {
    vi.stubEnv('REDIACC_EXECUTOR_ORG_ID', '');
    const seen: ConnectConfig[] = [];
    const error = await failedConnect(seamedSftpClient(base, recordingClient(seen)));
    expect(seen.map((c) => c.readyTimeout)).toEqual([DEFAULTS.SSH.READY_TIMEOUT]);
    expect(error.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(error.message).toContain('within 10 s');
  });

  it('lets an explicit config timeout win inside a container executor', async () => {
    vi.stubEnv('REDIACC_EXECUTOR_ORG_ID', 'org-1');
    const seen: ConnectConfig[] = [];
    await failedConnect(seamedSftpClient({ ...base, timeout: 300 }, recordingClient(seen)));
    expect(seen.map((c) => c.readyTimeout)).toEqual([300]);
  });
});
