/** `registerNewRepo` omits a network ID of 0 from the config record: 0 is not a valid ID (review 3decc360.2). */

import type { RepositoryConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const addRepository = vi.fn((_name: string, _config: RepositoryConfig) => Promise.resolve());
let allocated = 0;

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn(() => Promise.resolve(undefined)),
    addRepository: (name: string, config: RepositoryConfig) => addRepository(name, config),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  targetFloor: vi.fn(() => Promise.resolve(0)),
  allocateNetworkIdWithFloor: vi.fn(() => Promise.resolve(allocated)),
}));

import { registerNewRepo } from '../repo-create-delete.js';

describe('registerNewRepo network ID', () => {
  beforeEach(() => {
    addRepository.mockClear();
  });

  it('omits a network ID of 0 from the record', async () => {
    allocated = 0;
    await registerNewRepo('shop', { machine: 'm1' }, {}, { machine: 'm1' });
    expect(addRepository.mock.calls[0][1]).not.toHaveProperty('networkId');
  });

  it('records a positive network ID', async () => {
    allocated = 2816;
    await registerNewRepo('shop', { machine: 'm1' }, {}, { machine: 'm1' });
    expect(addRepository.mock.calls[0][1]).toHaveProperty('networkId', 2816);
  });
});
