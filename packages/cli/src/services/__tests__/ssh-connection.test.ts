import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetConnectionVaults = vi.fn();

vi.mock('../../providers/index.js', () => ({
  getStateProvider: vi.fn(() => ({
    vaults: {
      getConnectionVaults: mockGetConnectionVaults,
    },
  })),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (params) {
      let result = key;
      for (const [k, v] of Object.entries(params)) {
        result += ` ${k}=${v}`;
      }
      return result;
    }
    return key;
  },
}));

import { getSSHConnectionDetails } from '../ssh-connection.js';

const baseMachineVault = {
  ip: '10.0.0.1',
  port: 22,
  known_hosts: 'ssh-ed25519 AAAA...',
  datastore: '/mnt/rediacc',
  universalUser: 'rediacc',
};

const baseTeamVault = {
  SSH_PRIVATE_KEY: '-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----',
};

const baseRepoVault = {
  path: '/home/my-app',
  networkId: 'abc123',
  networkMode: 'bridge',
  tag: 'latest',
  workingDirectory: '/mnt/rediacc/mounts/guid-1234',
};

describe('getSSHConnectionDetails', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns machine-only connection details when no repository specified', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: baseMachineVault,
      teamVault: baseTeamVault,
    });

    const result = await getSSHConnectionDetails('team1', 'server-1');

    expect(result.host).toBe('10.0.0.1');
    expect(result.port).toBe(22);
    expect(result.user).toBe('rediacc');
    expect(result.datastore).toBe('/mnt/rediacc');
    expect(result.universalUser).toBe('rediacc');
    expect(result.environment).toEqual({
      REDIACC_TEAM: 'team1',
      REDIACC_MACHINE: 'server-1',
      REDIACC_DATASTORE: '/mnt/rediacc',
      REDIACC_DATASTORE_USER: 'rediacc',
      UNIVERSAL_USER_NAME: 'rediacc',
    });
    expect(result.workingDirectory).toBe('/mnt/rediacc');
    expect(result.repositoryPath).toBeUndefined();
    expect(result.networkId).toBeUndefined();
  });

  it('returns full repository connection details', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: baseMachineVault,
      teamVault: baseTeamVault,
      repositoryVault: baseRepoVault,
    });

    const result = await getSSHConnectionDetails('team1', 'server-1', 'my-app');

    expect(result.host).toBe('10.0.0.1');
    expect(result.datastore).toBe('/mnt/rediacc');
    expect(result.universalUser).toBe('rediacc');
    expect(result.repositoryPath).toBe('/home/my-app');
    expect(result.networkId).toBe('abc123');
    expect(result.workingDirectory).toBe('/mnt/rediacc/mounts/guid-1234');
    expect(result.environment).toMatchObject({
      REDIACC_TEAM: 'team1',
      REDIACC_MACHINE: 'server-1',
      REDIACC_REPOSITORY: 'my-app',
      DOCKER_SOCKET: '/var/run/rediacc/docker-abc123.sock',
      DOCKER_HOST: 'unix:///var/run/rediacc/docker-abc123.sock',
      REPOSITORY_NETWORK_ID: 'abc123',
      REPOSITORY_PATH: '/home/my-app',
    });
  });

  it('uses sshUser from vault when available', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: { ...baseMachineVault, user: 'admin' },
      teamVault: baseTeamVault,
    });

    const result = await getSSHConnectionDetails('team1', 'server-1');
    expect(result.user).toBe('admin');
  });

  it('throws when machine has no IP address', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: { ...baseMachineVault, ip: undefined, host: undefined },
      teamVault: baseTeamVault,
    });

    await expect(getSSHConnectionDetails('team1', 'server-1')).rejects.toThrow(
      'errors.ssh.noIpAddress'
    );
  });

  it('throws when team has no SSH private key', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: baseMachineVault,
      teamVault: {},
    });

    await expect(getSSHConnectionDetails('team1', 'server-1')).rejects.toThrow(
      'errors.ssh.noPrivateKey'
    );
  });

  it('throws when machine has no known hosts', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: { ...baseMachineVault, known_hosts: '' },
      teamVault: baseTeamVault,
    });

    await expect(getSSHConnectionDetails('team1', 'server-1')).rejects.toThrow(
      'errors.ssh.noHostKey'
    );
  });

  it('falls back to host field when ip is not set', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: { ...baseMachineVault, ip: undefined, host: 'server.example.com' },
      teamVault: baseTeamVault,
    });

    const result = await getSSHConnectionDetails('team1', 'server-1');
    expect(result.host).toBe('server.example.com');
  });

  it('handles missing repositoryVault gracefully', async () => {
    mockGetConnectionVaults.mockResolvedValue({
      machineVault: baseMachineVault,
      teamVault: baseTeamVault,
      repositoryVault: undefined,
    });

    const result = await getSSHConnectionDetails('team1', 'server-1', 'my-app');
    expect(result.repositoryPath).toBe('/home/my-app');
    expect(result.environment?.REDIACC_REPOSITORY).toBe('my-app');
  });
});
