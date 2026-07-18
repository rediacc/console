import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InfraConfig } from '../../types/index.js';

const { mockEnsureRecord, mockSearchRecordsBySuffix, mockDeleteRecord } = vi.hoisted(() => ({
  mockEnsureRecord: vi.fn().mockResolvedValue('unchanged' as const),
  mockSearchRecordsBySuffix: vi.fn().mockResolvedValue([]),
  mockDeleteRecord: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../provision/cloudflare-dns.js', () => ({
  CloudflareDnsClient: class MockCloudflareDnsClient {
    ensureRecord = mockEnsureRecord;
    searchRecordsBySuffix = mockSearchRecordsBySuffix;
    deleteRecord = mockDeleteRecord;
  },
}));

vi.mock('../core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    updateConfigFields: vi.fn(),
    applyDefaults: vi.fn().mockResolvedValue({ team: undefined }),
  },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

import {
  buildInfraPayload,
  ensureClusterDnsRecords,
  ensureRepoDnsRecords,
  removeClusterDnsRecords,
} from '../provision/infra-provision.js';

const baseInfra: InfraConfig = {
  baseDomain: 'rediacc.io',
  publicIPv4: '72.61.137.225',
  publicIPv6: '2a02:4780:c:e9b5::1',
  tcpPorts: [],
  udpPorts: [],
};

const dnsConfig = { cfDnsApiToken: 'cf_token', cfDnsZoneId: 'zone_abc' };

describe('ensureRepoDnsRecords wildcard hostname', () => {
  beforeEach(() => {
    mockEnsureRecord.mockClear();
  });

  it('uses the repo name directly when repoName is a grand (no colon)', async () => {
    await ensureRepoDnsRecords('hostinger', 'mail', baseInfra, dnsConfig);

    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'A',
      '*.mail.hostinger.rediacc.io',
      '72.61.137.225'
    );
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'AAAA',
      '*.mail.hostinger.rediacc.io',
      '2a02:4780:c:e9b5::1'
    );
  });

  it('strips :tag from a fork composite repoName before building the wildcard', async () => {
    await ensureRepoDnsRecords('hostinger', 'demo-stackoverflow:aldaniz2', baseInfra, dnsConfig);

    const calledNames = mockEnsureRecord.mock.calls.map((args) => args[2] as string);
    for (const name of calledNames) {
      expect(name).not.toContain(':');
    }
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'A',
      '*.demo-stackoverflow.hostinger.rediacc.io',
      '72.61.137.225'
    );
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'AAAA',
      '*.demo-stackoverflow.hostinger.rediacc.io',
      '2a02:4780:c:e9b5::1'
    );
  });

  it('is a no-op when cfDnsApiToken is missing', async () => {
    await ensureRepoDnsRecords('hostinger', 'demo-stackoverflow:aldaniz2', baseInfra, {});
    expect(mockEnsureRecord).not.toHaveBeenCalled();
  });

  it('is a no-op for .local base domains', async () => {
    await ensureRepoDnsRecords(
      'hostinger',
      'demo-stackoverflow:aldaniz2',
      { ...baseInfra, baseDomain: 'lan.local' },
      dnsConfig
    );
    expect(mockEnsureRecord).not.toHaveBeenCalled();
  });
});

describe('ensureClusterDnsRecords wildcard hostname', () => {
  beforeEach(() => {
    mockEnsureRecord.mockClear();
  });

  it('creates the cluster base + wildcard A/AAAA records', async () => {
    await ensureClusterDnsRecords('hostinger', 'prod', baseInfra, dnsConfig);

    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'A',
      'prod.hostinger.rediacc.io',
      '72.61.137.225'
    );
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'A',
      '*.prod.hostinger.rediacc.io',
      '72.61.137.225'
    );
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'AAAA',
      'prod.hostinger.rediacc.io',
      '2a02:4780:c:e9b5::1'
    );
    expect(mockEnsureRecord).toHaveBeenCalledWith(
      'zone_abc',
      'AAAA',
      '*.prod.hostinger.rediacc.io',
      '2a02:4780:c:e9b5::1'
    );
  });

  it('omits AAAA records when there is no IPv6', async () => {
    await ensureClusterDnsRecords(
      'hostinger',
      'prod',
      { ...baseInfra, publicIPv6: undefined },
      dnsConfig
    );
    const types = mockEnsureRecord.mock.calls.map((args) => args[1] as string);
    expect(types).toEqual(['A', 'A']);
  });

  it('is a no-op when cfDnsApiToken is missing', async () => {
    await ensureClusterDnsRecords('hostinger', 'prod', baseInfra, {});
    expect(mockEnsureRecord).not.toHaveBeenCalled();
  });

  it('is a no-op for .local base domains', async () => {
    await ensureClusterDnsRecords(
      'hostinger',
      'prod',
      { ...baseInfra, baseDomain: 'lan.local' },
      dnsConfig
    );
    expect(mockEnsureRecord).not.toHaveBeenCalled();
  });
});

describe('removeClusterDnsRecords', () => {
  beforeEach(() => {
    mockSearchRecordsBySuffix.mockClear();
    mockDeleteRecord.mockClear();
  });

  it('deletes every record under the cluster suffix and returns the count', async () => {
    mockSearchRecordsBySuffix.mockResolvedValueOnce([
      { id: 'r1', type: 'A', name: 'prod.hostinger.rediacc.io' },
      { id: 'r2', type: 'A', name: '*.prod.hostinger.rediacc.io' },
    ]);

    const deleted = await removeClusterDnsRecords('hostinger', 'prod', baseInfra, dnsConfig);

    expect(mockSearchRecordsBySuffix).toHaveBeenCalledWith('zone_abc', 'prod.hostinger.rediacc.io');
    expect(mockDeleteRecord).toHaveBeenCalledWith('zone_abc', 'r1');
    expect(mockDeleteRecord).toHaveBeenCalledWith('zone_abc', 'r2');
    expect(deleted).toBe(2);
  });

  it('is a no-op when cfDnsApiToken is missing', async () => {
    const deleted = await removeClusterDnsRecords('hostinger', 'prod', baseInfra, {});
    expect(deleted).toBe(0);
    expect(mockSearchRecordsBySuffix).not.toHaveBeenCalled();
  });
});

describe('buildInfraPayload team_name field', () => {
  it('includes team_name in the infra config JSON when team is set', () => {
    const json = buildInfraPayload('my-machine', baseInfra, {
      cfDnsApiToken: 'token',
      certEmail: 'admin@example.com',
      team: 'alpha',
    });
    const parsed = JSON.parse(json) as Record<string, unknown>;
    expect(parsed.team_name).toBe('alpha');
    expect(parsed.machine_name).toBe('my-machine');
  });

  it('emits team_name as empty string when no team is configured', () => {
    const json = buildInfraPayload('my-machine', baseInfra, {
      cfDnsApiToken: 'token',
    });
    const parsed = JSON.parse(json) as Record<string, unknown>;
    expect(parsed.team_name).toBe('');
  });

  it('emits team_name as empty string when team is explicitly undefined', () => {
    const json = buildInfraPayload('my-machine', baseInfra, {
      team: undefined,
    });
    const parsed = JSON.parse(json) as Record<string, unknown>;
    expect(parsed.team_name).toBe('');
  });
});
