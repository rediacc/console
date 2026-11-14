import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it, vi } from 'vitest';

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockGetLocalConfig = vi.hoisted(() => vi.fn());
const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockListRepositories = vi.hoisted(() => vi.fn());

// Mock configService used by LocalStateProvider
vi.mock('../config/config-resources.js', () => ({
  configService: {
    listMachines: vi.fn().mockResolvedValue([]),
    addMachine: vi.fn().mockResolvedValue(undefined),
    removeMachine: vi.fn().mockResolvedValue(undefined),
    getLocalConfig: mockGetLocalConfig.mockResolvedValue({
      machines: {},
      ssh: { privateKeyPath: '' },
      renetPath: '/usr/bin/renet',
    }),
    getCurrent: mockGetCurrent.mockResolvedValue({}),
    getRepository: mockGetRepository,
    listRepositories: mockListRepositories,
  },
}));

vi.mock('../renet/renet-execution.js', () => ({
  readSSHKey: vi.fn().mockResolvedValue('FAKE_PRIVATE_KEY'),
}));

const { LocalStateProvider } = await import('../state.js');

describe('LocalStateProvider', () => {
  describe('vaults.getConnectionVaults — per-repo secrets', () => {
    function setupMachineWithRepo(repoConfig: Record<string, unknown>) {
      mockGetLocalConfig.mockResolvedValue({
        machines: {
          srv: { ip: '1.2.3.4', user: 'root', knownHosts: 'kh', datastore: WK_DATASTORE_PATH },
        },
        ssh: { privateKeyPath: '/k' },
        renetPath: '/usr/bin/renet',
      });
      mockGetRepository.mockResolvedValue(repoConfig);
      mockGetCurrent.mockResolvedValue({});
    }

    it('partitions env-mode and file-mode secrets correctly', async () => {
      setupMachineWithRepo({
        repositoryGuid: '00000000-0000-0000-0000-000000000001',
        networkId: 1024,
        secrets: {
          STRIPE: { mode: 'env', value: 'sk_live_x' },
          DKIM: { mode: 'file', value: '-----BEGIN KEY-----\nABC\n' },
          DB_URL: { mode: 'env', value: 'postgres://user:pass@h/d' },
        },
      });

      const provider = new LocalStateProvider();
      const result = await provider.vaults.getConnectionVaults('team', 'srv', 'app:dev');

      expect(result.repositoryVault?.environment).toEqual({
        REDIACC_SECRET_STRIPE: 'sk_live_x',
        REDIACC_SECRET_DB_URL: 'postgres://user:pass@h/d',
      });
      expect(result.repositoryVault?.secretFiles).toEqual([
        { name: 'DKIM', value: '-----BEGIN KEY-----\nABC\n' },
      ]);
    });

    it('repo without secrets → empty environment + empty secretFiles', async () => {
      setupMachineWithRepo({
        repositoryGuid: '00000000-0000-0000-0000-000000000001',
        networkId: 1024,
      });

      const provider = new LocalStateProvider();
      const result = await provider.vaults.getConnectionVaults('team', 'srv', 'app:dev');
      expect(result.repositoryVault?.environment).toEqual({});
      expect(result.repositoryVault?.secretFiles).toEqual([]);
    });

    it('machine-only vault (no repository) does not include env/file secrets', async () => {
      mockGetLocalConfig.mockResolvedValue({
        machines: {
          srv: { ip: '1.2.3.4', user: 'root', knownHosts: 'kh', datastore: WK_DATASTORE_PATH },
        },
        ssh: { privateKeyPath: '/k' },
        renetPath: '/usr/bin/renet',
      });
      mockGetCurrent.mockResolvedValue({});

      const provider = new LocalStateProvider();
      const result = await provider.vaults.getConnectionVaults('team', 'srv');
      expect(result.repositoryVault).toBeUndefined();
    });
  });
});
