import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockInfo,
  mockFetchMachineStatus,
  mockGetMachineContainers,
  mockGetLocalMachine,
  mockGetCurrent,
  mockEnsureRepoDnsRecords,
  mockIsCertCacheStale,
  mockDownloadCertCache,
} = vi.hoisted(() => ({
  mockInfo: vi.fn(),
  mockFetchMachineStatus: vi.fn(),
  mockGetMachineContainers: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetCurrent: vi.fn(),
  mockEnsureRepoDnsRecords: vi.fn(),
  mockIsCertCacheStale: vi.fn(),
  mockDownloadCertCache: vi.fn(),
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    info: mockInfo,
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

// Lease-aware machine-status path used by printResolvedServiceUrls
vi.mock('../../services/machine-status.js', () => ({
  fetchMachineStatus: mockFetchMachineStatus,
}));

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getLocalMachine: mockGetLocalMachine,
    getLocalConfig: vi.fn().mockResolvedValue({}),
    getCurrent: mockGetCurrent,
  },
}));

vi.mock('../../services/infra-provision.js', () => ({
  ensureRepoDnsRecords: mockEnsureRepoDnsRecords,
}));

vi.mock('../../services/cert-cache.js', () => ({
  isCertCacheStale: mockIsCertCacheStale,
  downloadCertCache: mockDownloadCertCache,
}));

vi.mock('@rediacc/shared/services/machine', () => ({
  getMachineContainers: mockGetMachineContainers,
}));

import {
  postRepoUpTasks,
  printResolvedServiceUrls,
  printServiceUrlPattern,
} from '../repo-batch-utils.js';

const LIST_RESULT = { repositories: [], containers: [] };

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
    mockFetchMachineStatus.mockClear();
    mockGetMachineContainers.mockClear();
  });

  it('prints concrete URLs when container query returns matches', async () => {
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
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
    // Lease-aware status fetch: only the containers section is requested
    expect(mockFetchMachineStatus).toHaveBeenCalledExactlyOnceWith('hostinger', {
      sections: ['containers'],
    });
  });

  it('emits fork-tag host shape for forked repos', async () => {
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
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
    mockFetchMachineStatus.mockRejectedValueOnce(new Error('SSH timeout'));

    await printResolvedServiceUrls('mautic', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mautic.hostinger.example.com');
  });

  it('falls back when no containers match the repo', async () => {
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
    mockGetMachineContainers.mockReturnValueOnce([]);

    await printResolvedServiceUrls('mautic', 'hostinger', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mautic.hostinger.example.com');
  });

  it('emits custom Traefik domains from container labels (no service_port)', async () => {
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
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
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
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
    mockFetchMachineStatus.mockResolvedValueOnce(LIST_RESULT);
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

describe('postRepoUpTasks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetLocalMachine.mockResolvedValue({ infra: { baseDomain: 'rdc.dev' } });
    mockGetCurrent.mockResolvedValue({});
    mockIsCertCacheStale.mockReturnValue(false);
    mockEnsureRepoDnsRecords.mockResolvedValue(undefined);
    mockFetchMachineStatus.mockResolvedValue(LIST_RESULT);
    mockGetMachineContainers.mockReturnValue([]);
  });

  it('uses a pre-started dns promise (no second ensureDns) and records parallel steps', async () => {
    const steps: { name: string; duration_ms: number; detail?: string }[] = [];

    await postRepoUpTasks('app:tag', 'm1', {
      dnsPromise: Promise.resolve('rdc.dev'),
      steps,
    });

    // Caller fired DNS early — postRepoUpTasks must not re-run it
    expect(mockEnsureRepoDnsRecords).not.toHaveBeenCalled();
    // cert sync ran in parallel; service URLs ran last
    expect(steps.map((s) => s.name)).toEqual(['cert_sync', 'service_urls']);
    expect(steps[0].detail).toBe('∥');
    expect(steps[1].detail).toBeUndefined();
    expect(mockFetchMachineStatus).toHaveBeenCalledExactlyOnceWith('m1', {
      sections: ['containers'],
    });
    expect(mockInfo).toHaveBeenCalledWith(expect.stringContaining('m1.rdc.dev'));
  });

  it('starts its own DNS step when no promise is provided (DNS ∥ cert sync, then URLs)', async () => {
    const steps: { name: string; duration_ms: number; detail?: string }[] = [];
    mockIsCertCacheStale.mockReturnValue(true);
    mockDownloadCertCache.mockResolvedValue({ certCount: 2, compressedSize: 10 });

    await postRepoUpTasks('app', 'm1', { steps });

    expect(mockEnsureRepoDnsRecords).toHaveBeenCalledTimes(1);
    const names = steps.map((s) => s.name);
    expect(names).toContain('dns');
    expect(names).toContain('cert_sync');
    expect(names.at(-1)).toBe('service_urls');
    expect(steps.find((s) => s.name === 'dns')?.detail).toBe('∥');
    // Stale cache triggers the download over the shared-connection path
    expect(mockDownloadCertCache).toHaveBeenCalledWith('m1', { silent: true }, undefined);
  });

  it('skips service URLs (but still cert-syncs) when no baseDomain is configured', async () => {
    const steps: { name: string; duration_ms: number; detail?: string }[] = [];
    mockGetLocalMachine.mockResolvedValue({});

    await postRepoUpTasks('app', 'm1', { steps });

    expect(steps.map((s) => s.name).sort()).toEqual(['cert_sync', 'dns']);
    expect(mockFetchMachineStatus).not.toHaveBeenCalled();
    expect(mockInfo).not.toHaveBeenCalled();
  });
});
