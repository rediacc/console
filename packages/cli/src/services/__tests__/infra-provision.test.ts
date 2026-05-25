import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InfraConfig } from '../../types/index.js';

const { mockEnsureRecord } = vi.hoisted(() => ({
  mockEnsureRecord: vi.fn().mockResolvedValue('unchanged' as const),
}));

vi.mock('../cloudflare-dns.js', () => ({
  CloudflareDnsClient: class MockCloudflareDnsClient {
    ensureRecord = mockEnsureRecord;
  },
}));

vi.mock('../output.js', () => ({
  outputService: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../config-resources.js', () => ({
  configService: {
    updateConfigFields: vi.fn(),
    applyDefaults: vi.fn().mockResolvedValue({ team: undefined }),
  },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

import { buildInfraPayload, ensureRepoDnsRecords } from '../infra-provision.js';

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
