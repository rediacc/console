import { describe, expect, it } from 'vitest';
import { REMOTE_INSTALL_PATH, REMOTE_RENET_PATH } from '../../renet/renet-provisioner.js';
import { preDeployProvisioning } from '../backup-schedule.js';

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
});
