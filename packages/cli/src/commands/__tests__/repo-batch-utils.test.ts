import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInfo, mockGetWithVaultStatus, mockGetMachineContainers } = vi.hoisted(() => ({
  mockInfo: vi.fn(),
  mockGetWithVaultStatus: vi.fn(),
  mockGetMachineContainers: vi.fn(),
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    info: mockInfo,
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../../providers/index.js', () => ({
  getStateProvider: vi.fn().mockResolvedValue({
    isCloud: false,
    machines: {
      getWithVaultStatus: mockGetWithVaultStatus,
    },
  }),
}));

vi.mock('@rediacc/shared/services/machine', () => ({
  getMachineContainers: mockGetMachineContainers,
}));

import { printResolvedServiceUrls, printServiceUrlPattern } from '../repo-batch-utils.js';

describe('printServiceUrlPattern', () => {
  beforeEach(() => {
    mockInfo.mockClear();
  });

  it('builds {service}.<repo>.<machineDomain> for a grand repo', () => {
    printServiceUrlPattern('mail', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mail.hostinger.example.com');
    expect(printed).not.toContain(':aldaniz');
    expect(printed.split('https://')[1] ?? '').not.toContain(':');
  });

  it('flattens fork composite key into {service}-fork-<tag>.<parent>.<machineDomain>', () => {
    printServiceUrlPattern('demo-stackoverflow:aldaniz2', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain(
      'https://{service}-fork-aldaniz2.demo-stackoverflow.hostinger.example.com'
    );
    expect(printed.split('https://')[1] ?? '').not.toContain(':');
  });
});

describe('printResolvedServiceUrls', () => {
  beforeEach(() => {
    mockInfo.mockClear();
    mockGetWithVaultStatus.mockClear();
    mockGetMachineContainers.mockClear();
  });

  it('prints concrete URLs when container query returns matches', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([
      {
        id: 'abc1',
        name: 'mautic-mautic-1',
        image: 'mautic:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'mautic',
        labels: {
          'rediacc.repo_name': 'mautic',
          'rediacc.service_name': 'mautic-app',
          'rediacc.service_port': '8080',
        },
      },
      {
        id: 'abc2',
        name: 'mautic-db-1',
        image: 'mysql:8',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'mautic',
        labels: {
          'rediacc.repo_name': 'mautic',
          'rediacc.service_name': 'mautic-app',
          'rediacc.service_port': '3306',
        },
      },
    ]);

    await printResolvedServiceUrls('mautic', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledWith(
      'Exposed: https://mautic-app.mautic.hostinger.example.com'
    );
    expect(mockInfo).toHaveBeenCalledTimes(2);
  });

  it('emits fork-tag host shape for forked repos', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([
      {
        id: 'fork1',
        name: 'mautic-fork-bugrepro-mautic-1',
        image: 'mautic:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'mautic',
        labels: {
          'rediacc.repo_name': 'mautic:bugrepro',
          'rediacc.service_name': 'mautic-app',
          'rediacc.service_port': '8080',
          'rediacc.is_fork': 'true',
          'rediacc.fork_tag': 'bugrepro',
        },
      },
    ]);

    await printResolvedServiceUrls('mautic:bugrepro', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledWith(
      'Exposed: https://mautic-app-fork-bugrepro.mautic.hostinger.example.com'
    );
    expect(mockInfo).toHaveBeenCalledTimes(1);
  });

  it('falls back to template when query throws', async () => {
    mockGetWithVaultStatus.mockRejectedValueOnce(new Error('SSH timeout'));

    await printResolvedServiceUrls('mautic', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mautic.hostinger.example.com');
  });

  it('falls back when no containers match the repo', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([]);

    await printResolvedServiceUrls('mautic', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mautic.hostinger.example.com');
  });

  it('emits custom Traefik domains from container labels (no service_port)', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([
      {
        id: 'nc1',
        name: 'nextcloud-app',
        image: 'nextcloud:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'nextcloud',
        labels: {
          'rediacc.repo_name': 'nextcloud',
          'traefik.http.routers.nc.rule': 'Host(`cloud.rediacc.io`)',
        },
      },
      {
        id: 'nc2',
        name: 'nextcloud-collabora',
        image: 'collabora:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'nextcloud',
        labels: {
          'rediacc.repo_name': 'nextcloud',
          'traefik.http.routers.collabora.rule': 'Host(`office.rediacc.io`)',
        },
      },
    ]);

    await printResolvedServiceUrls('nextcloud', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://cloud.rediacc.io  (custom)');
    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://office.rediacc.io  (custom)');
    expect(mockInfo).toHaveBeenCalledTimes(2);
  });

  it('mixes auto-route and custom-domain lines when both are present', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([
      {
        id: 'm1',
        name: 'app',
        image: 'app:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'mixed',
        labels: {
          'rediacc.repo_name': 'mixed',
          'rediacc.service_name': 'app',
          'rediacc.service_port': '8080',
          'traefik.http.routers.app.rule': 'Host(`mixed.example.com`) || Host(`alt.example.com`)',
        },
      },
    ]);

    await printResolvedServiceUrls('mixed', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://app.mixed.hostinger.example.com');
    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://mixed.example.com  (custom)');
    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://alt.example.com  (custom)');
    expect(mockInfo).toHaveBeenCalledTimes(3);
  });

  it('honors rediacc.domain label as explicit declaration', async () => {
    mockGetWithVaultStatus.mockResolvedValueOnce({ machineName: 'hostinger', vaultStatus: '{}' });
    mockGetMachineContainers.mockReturnValueOnce([
      {
        id: 'd1',
        name: 'foo',
        image: 'foo:latest',
        command: '',
        created: '',
        status: 'running',
        state: 'running',
        ports: '',
        port_mappings: [],
        repository: 'foo',
        labels: {
          'rediacc.repo_name': 'foo',
          'rediacc.domain': 'a.example.com, b.example.com',
        },
      },
    ]);

    await printResolvedServiceUrls('foo', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://a.example.com  (custom)');
    expect(mockInfo).toHaveBeenCalledWith('Exposed: https://b.example.com  (custom)');
    expect(mockInfo).toHaveBeenCalledTimes(2);
  });
});
