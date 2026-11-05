/**
 * REDIACC_NO_PROVISION=1 holds a machine's renet: a mutating verb runs the installed binary as-is.
 *
 * THE DEFECT THIS PINS (2026-11-05). acquireRemoteRenet('provision') uploaded the CLI's renet on every
 * mutating verb run outside an executor, and nothing could refuse it. A live runner working against
 * hostinger from a branch checkout would have replaced production renet (10e5913) with a build 82
 * commits ahead just by running `repo fork`. `rdc machine setup` is the explicit path and still uploads.
 *
 * Real: renet-execution's access decision. Fake: the provisioner (inspect and provision), the request
 * context, the SEA probe and output.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { inspectMock, provisionMock, warnMock } = vi.hoisted(() => ({
  inspectMock: vi.fn(() =>
    Promise.resolve({
      drift: 'hash',
      remotePath: '/usr/lib/rediacc/renet/0.0.0-dev/renet',
      remoteVersion: '0.0.0-dev',
      remoteHash: 'e442cea7d999aaaa',
      localVersion: '0.0.0-dev',
      localHash: 'c47803a0bbacbbbb',
    })
  ),
  provisionMock: vi.fn(() =>
    Promise.resolve({
      success: true,
      action: 'uploaded',
      arch: 'amd64',
      remotePath: '/usr/lib/rediacc/renet/0.0.0-dev/renet',
    })
  ),
  warnMock: vi.fn(),
}));

vi.mock('../renet-provisioner.js', () => ({
  renetProvisioner: { inspect: inspectMock, provision: provisionMock },
}));
vi.mock('../../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/request-context.js')>()),
  currentRequestContext: () => undefined,
}));
vi.mock('../../core/embedded-assets.js', () => ({ isSEA: () => true }));
vi.mock('../../core/output.js', () => ({
  outputService: { warn: warnMock, info: vi.fn(), debug: vi.fn(), error: vi.fn() },
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({ host: 'hostinger', username: 'root', privateKey: 'k' }),
  withSharedOrPooledSftp: (
    shared: unknown,
    _config: unknown,
    fn: (sftp: unknown) => Promise<unknown>
  ) => fn(shared),
}));

const { acquireRemoteRenet } = await import('../renet-execution.js');

const CONFIG = { renetPath: 'renet' };
const KEY = 'k';
let port = 22000;

function machine() {
  // A fresh port per case: the drift warning is printed once per host and process.
  port += 1;
  return { ip: '10.0.0.5', user: 'root', port };
}

describe('REDIACC_NO_PROVISION holds the machine renet', () => {
  beforeEach(() => {
    inspectMock.mockClear();
    provisionMock.mockClear();
    warnMock.mockClear();
  });
  afterEach(() => {
    delete process.env.REDIACC_NO_PROVISION;
  });

  it('CONTROL: without it, a mutating verb provisions', async () => {
    const got = await acquireRemoteRenet('provision', CONFIG, machine(), KEY, {
      machineName: 'hostinger',
    });
    expect(provisionMock).toHaveBeenCalledTimes(1);
    expect(inspectMock).not.toHaveBeenCalled();
    expect(got.uploaded).toBe(true);
  });

  it('with it set, a mutating verb runs the installed renet as-is and names the hold', async () => {
    process.env.REDIACC_NO_PROVISION = '1';
    const got = await acquireRemoteRenet('provision', CONFIG, machine(), KEY, {
      machineName: 'hostinger',
    });
    expect(provisionMock).not.toHaveBeenCalled();
    expect(inspectMock).toHaveBeenCalledTimes(1);
    expect(got).toMatchObject({
      uploaded: false,
      remotePath: '/usr/lib/rediacc/renet/0.0.0-dev/renet',
      drift: 'hash',
    });
    expect(warnMock).toHaveBeenCalledTimes(1);
    const warned = String(warnMock.mock.calls[0]?.[0]);
    expect(warned).toContain('REDIACC_NO_PROVISION=1 holds it');
    expect(warned).toContain('rdc machine setup hostinger');
  });

  it('with it set, `rdc machine setup` still provisions', async () => {
    process.env.REDIACC_NO_PROVISION = '1';
    const got = await acquireRemoteRenet('provision', CONFIG, machine(), KEY, {
      machineName: 'hostinger',
      explicitSetup: true,
    });
    expect(provisionMock).toHaveBeenCalledTimes(1);
    expect(inspectMock).not.toHaveBeenCalled();
    expect(got.uploaded).toBe(true);
  });

  it('a value other than 1 does not hold', async () => {
    process.env.REDIACC_NO_PROVISION = 'true';
    await acquireRemoteRenet('provision', CONFIG, machine(), KEY, { machineName: 'hostinger' });
    expect(provisionMock).toHaveBeenCalledTimes(1);
  });
});
