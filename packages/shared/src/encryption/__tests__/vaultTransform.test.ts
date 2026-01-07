import { describe, expect, it } from 'vitest';
import { hasVaultFields, isVaultField, transformVaultFields } from '../vaultTransform.js';

describe('vaultTransform', () => {
  describe('isVaultField', () => {
    it('should return true for fields containing "vault" (case insensitive)', () => {
      expect(isVaultField('machineVault')).toBe(true);
      expect(isVaultField('teamVault')).toBe(true);
      expect(isVaultField('queueVault')).toBe(true);
      expect(isVaultField('organizationVault')).toBe(true);
      expect(isVaultField('vault')).toBe(true);
      expect(isVaultField('VAULT')).toBe(true);
      expect(isVaultField('myVaultData')).toBe(true);
    });

    it('should return false for fields not containing "vault"', () => {
      expect(isVaultField('name')).toBe(false);
      expect(isVaultField('machineName')).toBe(false);
      expect(isVaultField('status')).toBe(false);
      expect(isVaultField('id')).toBe(false);
      expect(isVaultField('password')).toBe(false);
      expect(isVaultField('')).toBe(false);
    });
  });

  describe('hasVaultFields', () => {
    it('should return true for objects with vault fields', () => {
      expect(hasVaultFields({ machineVault: {} })).toBe(true);
      expect(hasVaultFields({ name: 'test', teamVault: {} })).toBe(true);
    });

    it('should return true for nested objects with vault fields', () => {
      expect(hasVaultFields({ data: { machineVault: {} } })).toBe(true);
      expect(hasVaultFields({ items: [{ queueVault: {} }] })).toBe(true);
    });

    it('should return false for objects without vault fields', () => {
      expect(hasVaultFields({ name: 'test', status: 'active' })).toBe(false);
      expect(hasVaultFields({ data: { id: 1 } })).toBe(false);
    });

    it('should return false for null/undefined', () => {
      expect(hasVaultFields(null)).toBe(false);
      expect(hasVaultFields(undefined)).toBe(false);
    });

    it('should return false for primitives', () => {
      expect(hasVaultFields('string')).toBe(false);
      expect(hasVaultFields(123)).toBe(false);
      expect(hasVaultFields(true)).toBe(false);
    });

    it('should return true for arrays containing vault fields', () => {
      expect(hasVaultFields([{ machineVault: {} }])).toBe(true);
      expect(hasVaultFields([{ name: 'a' }, { queueVault: {} }])).toBe(true);
    });

    it('should return false for arrays without vault fields', () => {
      expect(hasVaultFields([{ name: 'a' }, { name: 'b' }])).toBe(false);
      expect(hasVaultFields([1, 2, 3])).toBe(false);
    });
  });

  describe('transformVaultFields', () => {
    const mockTransformer = (value: string): Promise<string> => {
      return Promise.resolve(`TRANSFORMED:${value}`);
    };

    it('should transform vault field values', async () => {
      const input = { machineVault: 'secret-data', name: 'test' };
      const result = await transformVaultFields(input, mockTransformer);

      expect(result.machineVault).toBe('TRANSFORMED:secret-data');
      expect(result.name).toBe('test');
    });

    it('should not transform non-vault fields', async () => {
      const input = { password: 'secret', name: 'test' };
      const result = await transformVaultFields(input, mockTransformer);

      expect(result.password).toBe('secret');
      expect(result.name).toBe('test');
    });

    it('should transform nested vault fields', async () => {
      const input = {
        machine: {
          machineVault: 'machine-secret',
        },
        name: 'test',
      };
      const result = await transformVaultFields(input, mockTransformer);

      expect(result.machine.machineVault).toBe('TRANSFORMED:machine-secret');
      expect(result.name).toBe('test');
    });

    it('should transform vault fields in arrays', async () => {
      const input = {
        items: [{ queueVault: 'item1' }, { queueVault: 'item2' }],
      };
      const result = await transformVaultFields(input, mockTransformer);

      expect(result.items[0].queueVault).toBe('TRANSFORMED:item1');
      expect(result.items[1].queueVault).toBe('TRANSFORMED:item2');
    });

    it('should handle empty vault field values', async () => {
      const input = { machineVault: '', name: 'test' };
      const result = await transformVaultFields(input, mockTransformer);

      // Empty strings should not be transformed
      expect(result.machineVault).toBe('');
    });

    it('should handle null values', async () => {
      const result = await transformVaultFields(null, mockTransformer);
      expect(result).toBe(null);
    });

    it('should handle primitive values', async () => {
      const result = await transformVaultFields('string', mockTransformer);
      expect(result).toBe('string');
    });

    it('should handle arrays at root level', async () => {
      const input = [{ machineVault: 'data1' }, { machineVault: 'data2' }];
      const result = await transformVaultFields(input, mockTransformer);

      expect(result[0].machineVault).toBe('TRANSFORMED:data1');
      expect(result[1].machineVault).toBe('TRANSFORMED:data2');
    });

    it('should preserve non-string vault field values', async () => {
      const input = {
        machineVault: { nested: 'object' } as unknown as string,
        name: 'test',
      };
      const result = await transformVaultFields(input, mockTransformer);

      // Non-string vault values should be recursively processed
      expect(result.machineVault).toEqual({ nested: 'object' });
    });
  });
});
