/**
 * `refreshRepoLicenseIdentity` and a licence issued by another account server.
 *
 * `subscription refresh --repo <ref>` always reissued, so a config pointed at another server wrote its blob over the
 * repo's licence with a lower sequence and renet refused the repo as `sequence_regression` (the 2026-11-11 hostinger
 * incident, the sibling of the batch path). The real function runs; only the executor, the account server and the
 * subscription state are faked.
 */

import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../../remote/sftp/index.js';
import type { MachineConfig } from '../../../types/index.js';

const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';
const MACHINE_ID = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
const FOREIGN_URL = 'https://eu.example.invalid/account/api/v1/licenses/renew';
const SAME_URL = `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/api/v1/licenses/renew`;

const { mockExecute } = vi.hoisted(() => ({ mockExecute: vi.fn() }));
const mockAccountServerFetch = vi.fn();

vi.mock('../../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
vi.mock('node:fs/promises', () => ({ readFile: vi.fn().mockResolvedValue('client-001\n') }));
vi.mock('../subscription-auth.js', () => ({
  getSubscriptionServerUrl: () => WK_ACCOUNT_DEFAULT_ORIGIN,
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    serverUrl: WK_ACCOUNT_DEFAULT_ORIGIN,
    token: { token: 'rdt_test' },
  }),
}));
vi.mock('../account-client.js', () => ({
  accountServerFetch: (...args: unknown[]) => mockAccountServerFetch(...args),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: { listRepositories: vi.fn().mockResolvedValue([]) },
}));
vi.mock('../../telemetry/telemetry.js', () => ({
  telemetryService: { setUserContext: vi.fn(), trackError: vi.fn() },
}));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) => `${key} ${JSON.stringify(vars ?? {})}`,
}));

const { refreshRepoLicenseIdentity } = await import('../license.js');

const machine: MachineConfig = { ip: '127.0.0.1', user: 'root', port: 22 };

function fakeMachine(currentRenewalUrl: string | undefined): SFTPClient {
  mockExecute.mockImplementation((opts: { commandKind: { name: string } }) =>
    Promise.resolve({
      success: true,
      exitCode: 0,
      stdout:
        opts.commandKind.name === 'license-scan'
          ? JSON.stringify([
              {
                repositoryGuid: REPO_GUID,
                luksUuid: 'luks-1',
                requestedSizeGb: 2,
                ...(currentRenewalUrl !== undefined && { currentRenewalUrl }),
              },
            ])
          : '[]',
    })
  );
  return {
    exec: vi.fn((c: string) => Promise.resolve(c.includes('machine-id') ? `${MACHINE_ID}\n` : '')),
    execStreaming: vi.fn().mockResolvedValue(0),
    connect: vi.fn(),
    close: vi.fn(),
  } as unknown as SFTPClient;
}

function run(sftp: SFTPClient, adoptOrigin?: boolean): Promise<boolean> {
  return refreshRepoLicenseIdentity(
    'test-machine',
    machine,
    'key',
    { repositoryGuid: REPO_GUID, kind: 'grand', ...(adoptOrigin && { adoptOrigin }) },
    '/usr/bin/renet',
    sftp
  );
}

const names = () =>
  mockExecute.mock.calls.map((c) => (c[0] as { commandKind: { name: string } }).commandKind.name);

describe('refreshRepoLicenseIdentity and the licence origin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccountServerFetch.mockResolvedValue({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });
  });

  it('refuses a foreign-origin licence: no account request, no licence write, one scan', async () => {
    await expect(run(fakeMachine(FOREIGN_URL))).rejects.toThrow(
      'errors.license.foreignOriginSkipped'
    );
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
    expect(names()).not.toContain('license-write');
    expect(names().filter((n) => n === 'license-scan')).toHaveLength(1);
  });

  it('adoptOrigin reissues a foreign-origin licence from one scan and writes it', async () => {
    await expect(run(fakeMachine(FOREIGN_URL), true)).resolves.toBe(true);
    expect(mockAccountServerFetch).toHaveBeenCalledTimes(1);
    const body = (mockAccountServerFetch.mock.calls[0] as [string, { body: object }])[1].body;
    expect(body).not.toHaveProperty('adoptOrigin');
    expect(names()).toContain('license-write');
    expect(names().filter((n) => n === 'license-scan')).toHaveLength(1);
  });

  it('a same-origin licence still reissues without the flag', async () => {
    await expect(run(fakeMachine(SAME_URL))).resolves.toBe(true);
    expect(mockAccountServerFetch).toHaveBeenCalledTimes(1);
    expect(names()).toContain('license-write');
  });

  it('a licence with no renewalUrl names no origin and still reissues', async () => {
    await expect(run(fakeMachine(undefined))).resolves.toBe(true);
    expect(mockAccountServerFetch).toHaveBeenCalledTimes(1);
  });
});
