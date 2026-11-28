import { describe, expect, it, vi } from 'vitest';
import { REMOTE_INSTALL_PATH, REMOTE_RENET_PATH } from '../../renet/renet-provisioner.js';
import { preDeployProvisioning } from '../backup-schedule.js';

const VERSIONED_SLOT = '/usr/lib/rediacc/renet/v9.9.9/renet';
const mocks = vi.hoisted(() => ({
  acquire: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock('../../renet/renet-execution.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../renet/renet-execution.js')>()),
  acquireRemoteRenet: mocks.acquire,
}));
vi.mock('../../account/license.js', () => ({ refreshRepoLicensesBatch: mocks.refresh }));
vi.mock('../../../utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/platform.js')>()),
  isDevBuild: () => false,
}));

/**
 * Scheduled backup units must exec the stable `current` renet, never a versioned slot: a versioned
 * ExecStart= kept running the replaced binary after an upgrade (2026-11-23, hostinger stale_binary
 * refused two live proofs). The dry run returns the path the units are rendered with.
 */
describe('preDeployProvisioning unit path', () => {
  it('renders units with the stable current path, not the versioned install slot', async () => {
    const path = await preDeployProvisioning('m1', {} as never, {} as never, '', {
      dryRun: true,
    } as never);
    expect(path).toBe(REMOTE_RENET_PATH);
    expect(path).not.toBe(REMOTE_INSTALL_PATH);
  });

  it('control: the two constants differ, so the assertion above can fail', () => {
    expect(REMOTE_RENET_PATH).not.toBe(REMOTE_INSTALL_PATH);
  });

  it('real deploy: units name the stable path while the license refresh runs on the acquired slot', async () => {
    mocks.acquire.mockResolvedValue({ remotePath: VERSIONED_SLOT });
    mocks.refresh.mockResolvedValue({
      scanned: 0,
      valid: 0,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
    });
    const path = await preDeployProvisioning(
      'm1',
      {} as never,
      { ip: '10.0.0.1' } as never,
      'key',
      { dryRun: false } as never
    );
    expect(path).toBe(REMOTE_RENET_PATH);
    expect(path).not.toBe(VERSIONED_SLOT);
    // Control: the mocked acquire did hand back the versioned slot, and the refresh used it.
    expect(mocks.refresh).toHaveBeenCalledWith('m1', { ip: '10.0.0.1' }, 'key', VERSIONED_SLOT);
  });
});
