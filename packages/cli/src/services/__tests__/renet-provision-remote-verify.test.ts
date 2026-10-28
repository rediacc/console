/**
 * A persisted provision entry (written by an earlier process or another config)
 * must not outvote the remote slot: a mutating `provision()` confirms the slot
 * with one exec, and drops the entry when the slot was replaced or moved.
 */
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getFresh, drop, record } = vi.hoisted(() => ({
  getFresh: vi.fn(),
  drop: vi.fn(() => Promise.resolve()),
  record: vi.fn(() => Promise.resolve()),
}));

vi.mock('../renet/provision-state.js', () => ({
  getFreshProvisionEntry: getFresh,
  recordProvisionVerified: record,
  dropProvisionEntry: drop,
  isSetupVerifiedFresh: vi.fn(() => Promise.resolve(false)),
  recordSetupVerified: vi.fn(() => Promise.resolve()),
  RENET_PROVISION_STATE_TTL_MS: 60 * 60 * 1000,
}));

const config = { host: 'ops-vm', username: 'u', privateKey: 'k' };

function sftpAnswering(output: string | Error) {
  const exec = vi.fn((_command: string) =>
    output instanceof Error ? Promise.reject(output) : Promise.resolve(output)
  );
  return { exec, close: vi.fn() };
}

function probeOutput(slotHash: string | null, currentHash: string | null): string {
  const slot = slotHash ? `SLOT_HASH ${slotHash}\nSLOT_VERSION 0.0.0\n` : 'SLOT_ABSENT\n';
  const cur = currentHash
    ? `CURRENT_HASH ${currentHash}\nCURRENT_VERSION 0.0.0\n`
    : 'CURRENT_ABSENT\n';
  return slot + cur;
}

async function freshProvisioner() {
  vi.resetModules();
  const mod = await import('../renet/renet-provisioner.js');
  mod.renetProvisioner.clearCache();
  return mod.renetProvisioner;
}

describe('provision() with a persisted entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getFresh.mockResolvedValue({ version: 'x', hash: 'H', arch: 'amd64', verifiedAt: Date.now() });
  });

  it('trusts the entry when the remote slot and current still hold the recorded hash', async () => {
    const p = await freshProvisioner();
    const sftp = sftpAnswering(probeOutput('H', 'H'));
    const result = await p.provision(
      config,
      { localBinaryPath: '/nonexistent/renet' },
      sftp as never
    );
    expect(result.action).toBe('verified');
    expect(sftp.exec).toHaveBeenCalledTimes(1);
    expect(drop).not.toHaveBeenCalled();
    // Proven once: a second call in this process does not probe again.
    await p.provision(config, { localBinaryPath: '/nonexistent/renet' }, sftp as never);
    expect(sftp.exec).toHaveBeenCalledTimes(1);
  });

  it('drops the entry and takes the full path when another config replaced the slot', async () => {
    const p = await freshProvisioner();
    const sftp = sftpAnswering(probeOutput('OTHER', 'OTHER'));
    const result = await p.provision(
      config,
      { localBinaryPath: '/nonexistent/renet' },
      sftp as never
    );
    expect(result.action).not.toBe('verified');
    expect(drop).toHaveBeenCalledWith('ops-vm:22');
  });

  it('drops the entry when the slot is gone', async () => {
    const p = await freshProvisioner();
    const sftp = sftpAnswering(probeOutput(null, 'H'));
    const result = await p.provision(
      config,
      { localBinaryPath: '/nonexistent/renet' },
      sftp as never
    );
    expect(result.action).not.toBe('verified');
    expect(drop).toHaveBeenCalledWith('ops-vm:22');
  });

  it('does not trust the entry when the probe cannot run', async () => {
    const p = await freshProvisioner();
    const sftp = sftpAnswering(new Error('connection reset'));
    const result = await p.provision(
      config,
      { localBinaryPath: '/nonexistent/renet' },
      sftp as never
    );
    expect(result.action).not.toBe('verified');
  });

  it('forgetHost drops memory and disk so a 127 on the renet path re-provisions', async () => {
    const p = await freshProvisioner();
    const sftp = sftpAnswering(probeOutput('H', 'H'));
    await p.provision(config, { localBinaryPath: '/nonexistent/renet' }, sftp as never);
    await p.forgetHost(config);
    expect(drop).toHaveBeenCalledWith('ops-vm:22');
    const result = await p.provision(
      config,
      { localBinaryPath: '/nonexistent/renet' },
      sftp as never
    );
    // Persisted entry is consulted again and re-probed (2nd exec).
    expect(sftp.exec.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(result.success).toBe(true);
  });

  it('rejects the upload, naming REDIACC_ALLOW_DOWNGRADE, when a newer renet replaced the slot', async () => {
    const p = await freshProvisioner();
    const dir = mkdtempSync(join(tmpdir(), 'rdc-prov-'));
    const bin = join(dir, 'renet');
    writeFileSync(bin, 'local-renet-bytes');
    const exec = vi.fn((command: string) => {
      if (command.includes('SLOT_HASH')) return Promise.resolve(probeOutput('NEWER', 'NEWER'));
      return Promise.resolve('NEWER\nrenet version 99.0.0\n');
    });
    const result = await p.provision(config, { localBinaryPath: bin }, {
      exec,
      close: vi.fn(),
    } as never);
    expect(result.success).toBe(false);
    expect(result.action).toBe('version_rejected');
    expect(result.error).toMatch(/REDIACC_ALLOW_DOWNGRADE/);
  });
});
