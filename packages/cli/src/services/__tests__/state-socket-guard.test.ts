import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PLAN-config-networkid-discovery T7 control "state.ts socket guard removed": a repo record with no network id must yield a vault with no socket path, and the connection builder must refuse it instead of aiming at `net-undefined`.

const mockGetRepository = vi.hoisted(() => vi.fn());

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn().mockResolvedValue({
      machines: {
        srv: { ip: '1.2.3.4', user: 'root', knownHosts: 'kh', datastore: WK_DATASTORE_PATH },
      },
      ssh: { privateKeyPath: '/k' },
      sshPrivateKey: 'FAKE_PRIVATE_KEY',
    }),
    getCurrent: vi.fn().mockResolvedValue({}),
    getRepository: mockGetRepository,
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../renet/renet-execution.js', () => ({
  readSSHKey: vi.fn().mockResolvedValue('FAKE_PRIVATE_KEY'),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string) => key,
}));

const { LocalStateProvider } = await import('../state.js');
const { getSSHConnectionDetails } = await import('../machine/ssh-connection.js');

describe('state.ts docker socket guard', () => {
  beforeEach(() => {
    mockGetRepository.mockReset();
  });

  it('a record without a network id gets no socket path and never the text "undefined"', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-1' });
    const vaults = await new LocalStateProvider().vaults.getConnectionVaults('team', 'srv', 'app');
    expect(vaults.machineVault.dockerSocket).toBeUndefined();
    expect(vaults.machineVault.dockerHost).toBeUndefined();
    expect(JSON.stringify(vaults)).not.toContain('undefined');
  });

  it('a record with a network id carries the real socket', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-1', networkId: 2880 });
    const vaults = await new LocalStateProvider().vaults.getConnectionVaults('team', 'srv', 'app');
    expect(vaults.machineVault.dockerSocket).toMatch(/net-2880\/docker-2880\.sock$/);
    expect(JSON.stringify(vaults)).not.toContain('undefined');
  });

  it('the connection builder refuses a repo without a network id', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-1' });
    await expect(getSSHConnectionDetails('team', 'srv', 'app')).rejects.toThrow(
      /errors\.ssh\.noNetworkId/
    );
  });
});
