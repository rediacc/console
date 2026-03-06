import { describe, expect, it } from 'vitest';
import type { ExistingResourceData } from '../../types';
import { parseVaultData } from '../parseVaultData';

describe('parseVaultData', () => {
  it('returns empty object when vaultContent is undefined', () => {
    const result = parseVaultData('machine', undefined);
    expect(result).toEqual({});
  });

  it('returns empty object when vaultContent is empty', () => {
    const existingData: ExistingResourceData = { vaultContent: '' };
    const result = parseVaultData('machine', existingData);
    expect(result).toEqual({});
  });

  it('returns parsed vault data for non-repository resources', () => {
    const existingData: ExistingResourceData = {
      vaultContent: JSON.stringify({ key: 'value', nested: { data: 123 } }),
    };
    const result = parseVaultData('machine', existingData);
    expect(result).toEqual({ key: 'value', nested: { data: 123 } });
  });

  it('returns vault data when credential is at root level for repository', () => {
    const existingData: ExistingResourceData = {
      vaultContent: JSON.stringify({ credential: 'my-secret-credential-1234567890' }),
    };
    const result = parseVaultData('repository', existingData);
    expect(result).toEqual({ credential: 'my-secret-credential-1234567890' });
  });

  it('extracts credential from nested repositoryVault', () => {
    const existingData: ExistingResourceData = {
      vaultContent: JSON.stringify({
        repositoryVault: JSON.stringify({ credential: 'nested-credential-1234567890' }),
      }),
    };
    const result = parseVaultData('repository', existingData);
    expect(result).toEqual({ credential: 'nested-credential-1234567890' });
  });

  it('extracts credential from 32-char string field', () => {
    const existingData: ExistingResourceData = {
      vaultContent: JSON.stringify({
        someField: 'abcdefghijklmnopqrstuvwxyz123456',
      }),
    };
    const result = parseVaultData('repository', existingData);
    expect(result).toEqual({ credential: 'abcdefghijklmnopqrstuvwxyz123456' });
  });

  it('returns empty object for invalid JSON', () => {
    const existingData: ExistingResourceData = { vaultContent: 'invalid-json{' };
    const result = parseVaultData('machine', existingData);
    expect(result).toEqual({});
  });

  it('returns original vault data if no credential pattern found for repository', () => {
    const existingData: ExistingResourceData = {
      vaultContent: JSON.stringify({ otherField: 'value' }),
    };
    const result = parseVaultData('repository', existingData);
    expect(result).toEqual({ otherField: 'value' });
  });
});
