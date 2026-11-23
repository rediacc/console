/**
 * The renet step of a mutating verb (`repo fork`, `repo up`, ...) names what it did. It printed
 * "Renet provisioned" whenever the verb MAY replace renet, including when the machine already ran
 * this build and nothing was replaced (hostinger, 2026-11-23: a fork run reported a provision and
 * the machine kept the released renet).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  acquire: vi.fn(),
  info: vi.fn(),
}));

vi.mock('../../renet/renet-execution.js', () => ({
  acquireRemoteRenet: h.acquire,
  verifyMachineSetup: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../renet/renet-upload-decision.js', () => ({ renetMayUpload: () => true }));
vi.mock('../../core/output.js', () => ({ outputService: { info: h.info } }));
vi.mock('../../../utils/spinner.js', () => ({ startSpinner: () => null, stopSpinner: vi.fn() }));
vi.mock('../license-recovery.js', () => ({
  ensureRepoLicenseForProvisioning: vi.fn().mockResolvedValue(undefined),
  ensureRepoLicenseForRestore: vi.fn().mockResolvedValue(undefined),
  maybeRefreshRepoLicenses: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../backup/backup-store-universe.js', () => ({
  assertBackupStoreUniverse: vi.fn().mockResolvedValue(undefined),
}));

const { provisionAndVerify, renetStepKey } = await import('../local-executor-provision.js');

async function run(uploaded: boolean): Promise<string[]> {
  h.acquire.mockResolvedValue({ remotePath: '/r/renet', uploaded, drift: null });
  await provisionAndVerify(
    { renetPath: 'renet' } as never,
    { ip: '10.0.0.1' } as never,
    'key',
    { functionName: 'repository_fork', machineName: 'm1', params: {} } as never,
    {} as never,
    [],
    false
  );
  return h.info.mock.calls.map((c) => String(c[0]));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('renet step message', () => {
  it('maps an uploaded result to "updated" and an unchanged one to "unchanged"', () => {
    expect(renetStepKey({ uploaded: true })).toBe('timing.step.renetUpdated');
    expect(renetStepKey({ uploaded: false })).toBe('timing.step.renetUnchanged');
  });

  it('says "updated" when the binary was replaced', async () => {
    const lines = await run(true);
    expect(lines.some((l) => /^Renet updated \(/.test(l))).toBe(true);
    expect(lines.some((l) => /provisioned/i.test(l))).toBe(false);
  });

  it('does not claim a provision when the machine already ran this build', async () => {
    const lines = await run(false);
    expect(lines.some((l) => /^Renet unchanged/.test(l))).toBe(true);
    expect(lines.some((l) => /provisioned|updated/i.test(l))).toBe(false);
  });
});
