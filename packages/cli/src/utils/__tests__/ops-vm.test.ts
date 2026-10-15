import { VM_NETWORK } from '@rediacc/shared/config';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn(() => Promise.resolve(null)) },
}));

import { isOpsVmAddress, isOpsVmMachine, isOpsVmPlacement } from '../ops-vm.js';

describe('isOpsVmAddress', () => {
  it('reads the fleet network from the shared bridge constant', () => {
    expect(VM_NETWORK.BRIDGE_IP).toBe('192.168.111.1');
    expect(isOpsVmAddress(VM_NETWORK.BRIDGE_IP)).toBe(true);
    for (const ip of VM_NETWORK.WORKER_IPS) expect(isOpsVmAddress(ip)).toBe(true);
  });

  it('accepts every host of the ops /24', () => {
    for (const ip of ['192.168.111.0', '192.168.111.11', '192.168.111.255']) {
      expect(isOpsVmAddress(ip), ip).toBe(true);
    }
  });

  it('refuses addresses just outside the range', () => {
    for (const ip of ['192.168.110.11', '192.168.112.11', '192.168.11.11', '192.169.111.11']) {
      expect(isOpsVmAddress(ip), ip).toBe(false);
    }
  });

  it('refuses malformed and look-alike addresses', () => {
    for (const ip of [
      '192.168.111.256',
      '192.168.111.011',
      '192.168.111.',
      '192.168.111',
      '192.168.111.11.example.com',
      'ops-worker',
      '::ffff:192.168.111.11',
      ' 192.168.111.11',
      '',
    ]) {
      expect(isOpsVmAddress(ip), JSON.stringify(ip)).toBe(false);
    }
  });

  it('refuses everything when there is no active config', async () => {
    await expect(isOpsVmMachine('ops-worker')).resolves.toBe(false);
    await expect(isOpsVmMachine(undefined)).resolves.toBe(false);
    await expect(isOpsVmPlacement({ machine: 'ops-worker' })).resolves.toBe(false);
    await expect(isOpsVmPlacement({ datastore: 'ops-pool' })).resolves.toBe(false);
    await expect(isOpsVmPlacement(undefined)).resolves.toBe(false);
  });
});
