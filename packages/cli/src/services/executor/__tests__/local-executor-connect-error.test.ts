/**
 * A named SSH connect failure reaches the executor envelope with its code, exit
 * code and guidance, instead of flattening to an anonymous exit 1.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { acquireFor, stdoutChunks } = vi.hoisted(() => ({
  acquireFor: vi.fn(),
  stdoutChunks: [] as string[],
}));

vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: { acquireFor },
  withSharedOrPooledSftp: vi.fn(),
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn(() =>
      Promise.resolve({
        sshPrivateKey: 'PRIVATE_KEY',
        sshPublicKey: 'PUBLIC_KEY',
        ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
      })
    ),
    getLocalMachine: vi.fn(() =>
      Promise.resolve({ ip: '192.0.2.10', user: 'root', port: 22, knownHosts: 'kh' })
    ),
    getRepository: vi.fn(() => Promise.resolve(undefined)),
    getRepositoryKey: vi.fn(() => Promise.resolve(undefined)),
    listStorages: vi.fn(() => Promise.resolve([])),
    listRepositories: vi.fn(() => Promise.resolve([])),
  },
}));

vi.mock('../../renet/renet-execution.js', () => ({
  buildLocalVault: vi.fn(() => '{}'),
  acquireRemoteRenet: vi.fn(),
  readSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  readOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  verifyMachineSetup: vi.fn(),
}));

vi.mock('../license-recovery.js', () => ({
  ensureRepoLicenseForProvisioning: vi.fn(),
  ensureRepoLicenseForRestore: vi.fn(),
  maybeRefreshRepoIdentity: vi.fn(),
  maybeRefreshRepoLicenses: vi.fn(),
  needsLicenseRecovery: vi.fn(() => false),
  refreshRepoIdentityFor: vi.fn(),
  resolveLicenseFailure: vi.fn(),
}));
vi.mock('../../telemetry/telemetry.js', () => ({
  isTelemetryDisabled: () => true,
  telemetryService: { trackError: vi.fn(), shutdown: vi.fn().mockResolvedValue(undefined) },
}));
vi.mock('../../telemetry/otlp-credentials.js', () => ({ fetchOtlpCredentials: vi.fn() }));
vi.mock('../../core/audit.js', () => ({ auditService: { recordOperation: vi.fn() } }));

const { localExecutorService } = await import('../local-executor.js');
const { SshConnectError } = await import('../../../remote/sftp/connect-error.js');
const { handleError, setOutputFormat } = await import('../../../utils/errors.js');

vi.spyOn(process, 'exit').mockImplementation(() => {
  throw new Error('process.exit called');
});
vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
  stdoutChunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
  return true;
});

const connectError = (kind: 'unreachable' | 'refused') =>
  new SshConnectError({ kind, host: '192.0.2.10', port: 22, timeoutMs: 10000, cause: 'x' });

function run() {
  return localExecutorService.execute({
    functionName: 'machine_status',
    machineName: 'blackhole',
    params: {},
    captureOutput: true,
    quietSpinners: true,
  });
}

beforeEach(() => {
  acquireFor.mockReset();
  stdoutChunks.length = 0;
});

describe('LocalExecutorService.execute with a failed SSH connect', () => {
  it('answers exit 6 and EGRESS_UNREACHABLE naming host and port', async () => {
    acquireFor.mockRejectedValue(connectError('unreachable'));
    const result = await run();
    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(6);
    expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(result.error).toContain('192.0.2.10:22');
    expect(result.errorGuidance).toBeTruthy();
  });

  it('carries the unanswered address as connectTarget, for the egress report', async () => {
    acquireFor.mockRejectedValue(
      new SshConnectError({
        kind: 'unreachable',
        host: '203.0.113.9',
        port: 2222,
        timeoutMs: 10000,
        cause: 'x',
      })
    );
    const result = await run();
    expect(result.connectTarget).toEqual({ host: '203.0.113.9', port: 2222 });
  });

  it('answers SSH_REFUSED for a refused connect, with no connectTarget', async () => {
    acquireFor.mockRejectedValue(connectError('refused'));
    const result = await run();
    expect(result).toMatchObject({ exitCode: 6, errorCode: 'SSH_REFUSED' });
    expect(result).not.toHaveProperty('connectTarget');
  });

  it('keeps exit 1, no code and no connectTarget for a plain Error', async () => {
    acquireFor.mockRejectedValue(new Error('disk on fire'));
    const result = await run();
    expect(result.exitCode).toBe(1);
    expect(result.errorCode).toBeUndefined();
    expect(result.error).toBe('disk on fire');
    expect(result).not.toHaveProperty('connectTarget');
  });
});

describe('normalizeError for a raw SshConnectError', () => {
  it('maps to NETWORK_ERROR, exit 6, retryable', () => {
    setOutputFormat('json');
    expect(() => handleError(connectError('unreachable'))).toThrow(/process\.exit/);
    const envelope = JSON.parse(stdoutChunks.join('')).errors[0];
    expect(envelope.code).toBe('NETWORK_ERROR');
    expect(envelope.retryable).toBe(true);
    expect(envelope.message).toContain('192.0.2.10:22');
    expect(process.exit).toHaveBeenCalledWith(6);
  });
});
