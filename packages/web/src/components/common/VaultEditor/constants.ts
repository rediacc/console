import storageProviders from '@/data/storageProviders.json';
import vaultDefinitions from '@/data/vaults.json';
import type { StorageProvidersConfig, VaultDefinitionsConfig } from './types';

/**
 * Vault definitions configuration
 */
export const vaultDefinitionConfig = vaultDefinitions as unknown as VaultDefinitionsConfig;

/**
 * Storage provider configuration
 */
export const storageProviderConfig = storageProviders as unknown as StorageProvidersConfig;

/**
 * Machine basic field order
 */
export const MACHINE_BASIC_FIELD_ORDER = ['ip', 'user', 'datastore'] as const;

/**
 * Fields to keep when changing storage provider
 */
export const STORAGE_FIELDS_TO_KEEP = [
  'name',
  'provider',
  'description',
  'noVersioning',
  'parameters',
] as const;
