import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    listStorages: vi.fn(),
    listMachines: vi.fn(),
  },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (params) return `${key}:${JSON.stringify(params)}`;
    return key;
  },
}));

import { configService } from '../../services/config-resources.js';
import type { RdcConfig } from '../../types/index.js';
import {
  assertMachineExists,
  assertResourceName,
  assertStorageExists,
  BackupDestinationSchema,
  BackupScheduleSchema,
  CertEmailSchema,
  InfraConfigSchema,
  MachineConfigSchema,
  normalizeDomain,
  normalizeEmail,
  normalizeIp,
  normalizePath,
  parseConfig,
  RepositoryConfigSchema,
  resourceName,
  stringifyConfig,
} from '../config-schema.js';

const mockListStorages = vi.mocked(configService.listStorages);
const mockListMachines = vi.mocked(configService.listMachines);

describe('config-schema', () => {
  describe('resourceName', () => {
    it('accepts valid names', () => {
      expect(resourceName.safeParse('mail').success).toBe(true);
      expect(resourceName.safeParse('my-server-1').success).toBe(true);
      expect(resourceName.safeParse('a').success).toBe(true);
      expect(resourceName.safeParse('abc123').success).toBe(true);
    });

    it('rejects leading hyphen', () => {
      expect(resourceName.safeParse('-bad').success).toBe(false);
    });

    it('rejects trailing hyphen', () => {
      expect(resourceName.safeParse('bad-').success).toBe(false);
    });

    it('rejects uppercase', () => {
      expect(resourceName.safeParse('BAD').success).toBe(false);
    });

    it('rejects spaces', () => {
      expect(resourceName.safeParse('has space').success).toBe(false);
    });

    it('rejects empty string', () => {
      expect(resourceName.safeParse('').success).toBe(false);
    });

    it('rejects names over 63 characters', () => {
      expect(resourceName.safeParse('a'.repeat(64)).success).toBe(false);
    });

    it('accepts exactly 63 characters', () => {
      expect(resourceName.safeParse('a'.repeat(63)).success).toBe(true);
    });
  });

  describe('assertResourceName', () => {
    it('passes for valid names', () => {
      expect(() => assertResourceName('mail')).not.toThrow();
    });

    it('throws ValidationError for invalid names', () => {
      expect(() => assertResourceName('-bad')).toThrow('Invalid resource name');
      expect(() => assertResourceName('')).toThrow('Invalid resource name');
    });
  });

  describe('MachineConfigSchema', () => {
    it('accepts valid machine config', () => {
      const result = MachineConfigSchema.safeParse({
        ip: '10.0.0.1',
        user: 'root',
        port: 22,
        datastore: '/mnt/rediacc',
      });
      expect(result.success).toBe(true);
    });

    it('accepts hostname as IP', () => {
      const result = MachineConfigSchema.safeParse({
        ip: 'server.example.com',
        user: 'root',
      });
      expect(result.success).toBe(true);
    });

    it('accepts IPv6', () => {
      const result = MachineConfigSchema.safeParse({
        ip: '::1',
        user: 'root',
      });
      expect(result.success).toBe(true);
    });

    it('rejects empty IP', () => {
      expect(MachineConfigSchema.safeParse({ ip: '', user: 'root' }).success).toBe(false);
    });

    it('rejects empty user', () => {
      expect(MachineConfigSchema.safeParse({ ip: '10.0.0.1', user: '' }).success).toBe(false);
    });

    it('rejects port 0', () => {
      expect(MachineConfigSchema.safeParse({ ip: '10.0.0.1', user: 'root', port: 0 }).success).toBe(
        false
      );
    });

    it('rejects port 99999', () => {
      expect(
        MachineConfigSchema.safeParse({ ip: '10.0.0.1', user: 'root', port: 99999 }).success
      ).toBe(false);
    });

    it('rejects relative datastore path', () => {
      expect(
        MachineConfigSchema.safeParse({ ip: '10.0.0.1', user: 'root', datastore: 'relative/path' })
          .success
      ).toBe(false);
    });

    it('accepts config without optional fields', () => {
      expect(MachineConfigSchema.safeParse({ ip: '10.0.0.1', user: 'root' }).success).toBe(true);
    });
  });

  describe('RepositoryConfigSchema', () => {
    it('accepts valid UUID', () => {
      expect(
        RepositoryConfigSchema.safeParse({ repositoryGuid: '550e8400-e29b-41d4-a716-446655440000' })
          .success
      ).toBe(true);
    });

    it('rejects non-UUID GUID', () => {
      expect(RepositoryConfigSchema.safeParse({ repositoryGuid: 'not-a-uuid' }).success).toBe(
        false
      );
    });

    it('rejects empty GUID', () => {
      expect(RepositoryConfigSchema.safeParse({ repositoryGuid: '' }).success).toBe(false);
    });

    it('accepts full config with optional fields', () => {
      expect(
        RepositoryConfigSchema.safeParse({
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          tag: 'latest',
          credential: 'my-cred',
          networkId: 2816,
        }).success
      ).toBe(true);
    });
  });

  describe('InfraConfigSchema', () => {
    it('accepts valid IPv4', () => {
      expect(InfraConfigSchema.safeParse({ publicIPv4: '1.2.3.4' }).success).toBe(true);
    });

    it('rejects invalid IPv4', () => {
      expect(InfraConfigSchema.safeParse({ publicIPv4: 'not-an-ip' }).success).toBe(false);
    });

    it('rejects IPv6 in IPv4 field', () => {
      expect(InfraConfigSchema.safeParse({ publicIPv4: '::1' }).success).toBe(false);
    });

    it('accepts valid IPv6', () => {
      expect(InfraConfigSchema.safeParse({ publicIPv6: '2001:db8::1' }).success).toBe(true);
    });

    it('rejects IPv4 in IPv6 field', () => {
      expect(InfraConfigSchema.safeParse({ publicIPv6: '1.2.3.4' }).success).toBe(false);
    });

    it('accepts valid domain', () => {
      expect(InfraConfigSchema.safeParse({ baseDomain: 'example.com' }).success).toBe(true);
    });

    it('accepts subdomain', () => {
      expect(InfraConfigSchema.safeParse({ baseDomain: 'sub.example.com' }).success).toBe(true);
    });

    it('rejects domain without TLD', () => {
      expect(InfraConfigSchema.safeParse({ baseDomain: 'nodot' }).success).toBe(false);
    });

    it('accepts valid port list', () => {
      expect(InfraConfigSchema.safeParse({ tcpPorts: [80, 443, 8080] }).success).toBe(true);
    });

    it('rejects port 0 in list', () => {
      expect(InfraConfigSchema.safeParse({ tcpPorts: [0] }).success).toBe(false);
    });

    it('rejects port 70000 in list', () => {
      expect(InfraConfigSchema.safeParse({ tcpPorts: [70000] }).success).toBe(false);
    });

    it('accepts empty object', () => {
      expect(InfraConfigSchema.safeParse({}).success).toBe(true);
    });
  });

  describe('BackupDestinationSchema', () => {
    it('accepts valid destination with cron', () => {
      expect(
        BackupDestinationSchema.safeParse({
          storage: 'microsoft',
          schedule: '0 2 * * *',
          enabled: true,
        }).success
      ).toBe(true);
    });

    it('accepts destination without optional fields', () => {
      expect(BackupDestinationSchema.safeParse({ storage: 'microsoft' }).success).toBe(true);
    });

    it('rejects empty storage name', () => {
      expect(BackupDestinationSchema.safeParse({ storage: '' }).success).toBe(false);
    });

    it('accepts every-15-min cron', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '*/15 * * * *' }).success
      ).toBe(true);
    });

    it('accepts weekly Sunday cron', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '0 2 * * 0' }).success
      ).toBe(true);
    });

    it('rejects 6-field cron', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '0 0 2 * * *' }).success
      ).toBe(false);
    });

    it('rejects minute out of range', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '60 2 * * *' }).success
      ).toBe(false);
    });

    it('rejects hour out of range', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '0 25 * * *' }).success
      ).toBe(false);
    });

    it('rejects nonsense cron', () => {
      expect(BackupDestinationSchema.safeParse({ storage: 'test', schedule: 'bad' }).success).toBe(
        false
      );
    });

    it('accepts range cron expression', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '0 1-5 * * *' }).success
      ).toBe(true);
    });

    it('accepts comma-separated cron values', () => {
      expect(
        BackupDestinationSchema.safeParse({ storage: 'test', schedule: '0 2 * * 1,3,5' }).success
      ).toBe(true);
    });
  });

  describe('BackupScheduleSchema', () => {
    it('accepts valid cron', () => {
      expect(BackupScheduleSchema.safeParse({ schedule: '0 2 * * *' }).success).toBe(true);
    });

    it('rejects invalid cron', () => {
      expect(BackupScheduleSchema.safeParse({ schedule: 'bad' }).success).toBe(false);
    });

    it('accepts without schedule', () => {
      expect(BackupScheduleSchema.safeParse({ enabled: true }).success).toBe(true);
    });
  });

  describe('CertEmailSchema', () => {
    it('accepts valid email', () => {
      expect(CertEmailSchema.safeParse('user@example.com').success).toBe(true);
    });

    it('rejects invalid email', () => {
      expect(CertEmailSchema.safeParse('not-an-email').success).toBe(false);
    });
  });

  describe('parseConfig', () => {
    it('returns parsed data for valid input', () => {
      const result = parseConfig(
        MachineConfigSchema,
        { ip: '10.0.0.1', user: 'root', port: 22 },
        'machine config'
      );
      expect(result).toEqual({ ip: '10.0.0.1', user: 'root', port: 22 });
    });

    it('throws ValidationError for invalid input', () => {
      expect(() =>
        parseConfig(MachineConfigSchema, { ip: '', user: '' }, 'machine config')
      ).toThrow('Invalid machine config');
    });

    it('includes field path in error message', () => {
      try {
        parseConfig(MachineConfigSchema, { ip: '10.0.0.1', user: '', port: 99999 }, 'test');
        expect.fail('should have thrown');
      } catch (error) {
        const msg = (error as Error).message;
        expect(msg).toContain('user');
        expect(msg).toContain('port');
      }
    });
  });

  describe('assertStorageExists', () => {
    it('passes when storage exists', async () => {
      mockListStorages.mockResolvedValue([
        { name: 'microsoft', config: { provider: 's3', vaultContent: {} } },
        { name: 'r2-cloudflare', config: { provider: 's3', vaultContent: {} } },
      ]);
      await expect(assertStorageExists('microsoft')).resolves.not.toThrow();
    });

    it('throws when storage does not exist', async () => {
      mockListStorages.mockResolvedValue([
        { name: 'microsoft', config: { provider: 's3', vaultContent: {} } },
      ]);
      await expect(assertStorageExists('google')).rejects.toThrow('errors.config.storageNotFound');
    });

    it('includes available storages in error message', async () => {
      mockListStorages.mockResolvedValue([
        { name: 'microsoft', config: { provider: 's3', vaultContent: {} } },
        { name: 'r2', config: { provider: 's3', vaultContent: {} } },
      ]);
      await expect(assertStorageExists('google')).rejects.toThrow('microsoft, r2');
    });

    it('shows (none) when no storages configured', async () => {
      mockListStorages.mockResolvedValue([]);
      await expect(assertStorageExists('google')).rejects.toThrow('(none)');
    });
  });

  describe('assertMachineExists', () => {
    it('passes when machine exists', async () => {
      mockListMachines.mockResolvedValue([
        { name: 'hostinger', config: { ip: '1.2.3.4', user: 'root' } },
      ]);
      await expect(assertMachineExists('hostinger')).resolves.not.toThrow();
    });

    it('throws when machine does not exist', async () => {
      mockListMachines.mockResolvedValue([
        { name: 'hostinger', config: { ip: '1.2.3.4', user: 'root' } },
      ]);
      await expect(assertMachineExists('nonexistent')).rejects.toThrow(
        'errors.config.machineNotFound'
      );
    });

    it('includes available machines in error message', async () => {
      mockListMachines.mockResolvedValue([
        { name: 'hostinger', config: { ip: '1.2.3.4', user: 'root' } },
        { name: 'staging', config: { ip: '5.6.7.8', user: 'root' } },
      ]);
      await expect(assertMachineExists('prod')).rejects.toThrow('hostinger, staging');
    });
  });

  describe('input normalization', () => {
    it('normalizeIp trims whitespace', () => {
      expect(normalizeIp('  10.0.0.1  ')).toBe('10.0.0.1');
    });

    it('normalizeDomain trims and lowercases', () => {
      expect(normalizeDomain('  Example.COM  ')).toBe('example.com');
    });

    it('normalizeEmail trims and lowercases', () => {
      expect(normalizeEmail('  User@Example.COM  ')).toBe('user@example.com');
    });

    it('normalizePath trims and strips trailing slashes', () => {
      expect(normalizePath('/mnt/rediacc/')).toBe('/mnt/rediacc');
      expect(normalizePath('/mnt/rediacc////')).toBe('/mnt/rediacc');
      expect(normalizePath('  /mnt/data  ')).toBe('/mnt/data');
    });

    it('normalizePath preserves root slash', () => {
      expect(normalizePath('/')).toBe('/');
    });
  });

  describe('orderedReplacer / stringifyConfig', () => {
    it('puts metadata keys first in root config', () => {
      const config: RdcConfig = {
        machines: { test: { ip: '1.2.3.4', user: 'root' } },
        version: 1,
        id: 'test-id',
        ssh: { privateKeyPath: '/test' },
      };
      const json = stringifyConfig(config);
      const keys = Object.keys(JSON.parse(json));
      expect(keys[0]).toBe('id');
      expect(keys[1]).toBe('version');
    });

    it('sorts nested object keys alphabetically', () => {
      const config: RdcConfig = {
        id: 'test',
        version: 1,
        machines: {
          server: { user: 'root', ip: '1.2.3.4', port: 22 },
        },
      };
      const json = stringifyConfig(config);
      const parsed = JSON.parse(json);
      const machineKeys = Object.keys(parsed.machines.server);
      expect(machineKeys).toEqual(['ip', 'port', 'user']);
    });

    it('preserves arrays in order', () => {
      const config: RdcConfig = {
        id: 'test',
        version: 1,
        machines: {
          srv: { ip: '1.2.3.4', user: 'root', infra: { tcpPorts: [443, 80, 25] } },
        },
      };
      const json = stringifyConfig(config);
      const parsed = JSON.parse(json);
      expect(parsed.machines.srv.infra.tcpPorts).toEqual([443, 80, 25]);
    });

    it('strips undefined values', () => {
      const config: RdcConfig = { id: 'test', version: 1, team: undefined };
      const json = stringifyConfig(config);
      expect(json).not.toContain('team');
    });

    it('places ssh before machines before storages', () => {
      const config: RdcConfig = {
        id: 'test',
        version: 1,
        storages: {},
        machines: {},
        ssh: { privateKeyPath: '/test' },
      };
      const json = stringifyConfig(config);
      const keys = Object.keys(JSON.parse(json));
      const sshIdx = keys.indexOf('ssh');
      const machinesIdx = keys.indexOf('machines');
      const storagesIdx = keys.indexOf('storages');
      expect(sshIdx).toBeLessThan(machinesIdx);
      expect(machinesIdx).toBeLessThan(storagesIdx);
    });
  });
});
