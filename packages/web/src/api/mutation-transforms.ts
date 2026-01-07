/**
 * Mutation transformation helpers for type-safe API mutations.
 * These functions are used by generated hooks to transform semantic input types
 * into API-compatible parameter formats.
 *
 * Generated hooks import and use these transforms automatically based on
 * configuration in hooks.config.json.
 */

import { minifyJSON } from '@/platform/utils/json';
import { hashPassword as cryptoHashPassword } from '@/utils/auth';

/**
 * Hash a password using the standard hashing algorithm.
 * Used for: CreateNewUser, UpdateUserPassword, etc.
 */
export async function hashPassword(password: string): Promise<string> {
  return cryptoHashPassword(password);
}

/**
 * Generate a 6-digit activation code.
 * Used for: CreateNewUser
 */
export function generateActivationCode(): string {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

/**
 * Ensure vault content is valid JSON, defaulting to empty object.
 * Used for: Create operations (CreateTeam, CreateMachine, etc.)
 */
export function ensureVaultContent(vaultContent?: string): string {
  return vaultContent ?? '{}';
}

/**
 * Minify and validate vault JSON content.
 * Used for: Update operations (UpdateTeamVault, UpdateMachineVault, etc.)
 */
export function minifyVaultContent(vaultContent: string): string {
  return minifyJSON(vaultContent);
}

/**
 * Type definitions for semantic mutation inputs.
 * These provide developer-friendly field names that map to API parameters.
 */

// User mutations
export interface CreateUserInput {
  email: string;
  password: string;
}

// Team mutations
export interface CreateTeamInput {
  teamName: string;
  vaultContent?: string;
}

// Machine mutations
export interface CreateMachineInput {
  teamName: string;
  machineName: string;
  bridgeName: string;
  vaultContent?: string;
}

// Repository mutations
export interface CreateRepositoryInput {
  teamName: string;
  repositoryName: string;
  repositoryTag?: string;
  parentRepositoryName?: string;
  repositoryGuid?: string;
  networkMode?: string;
  vaultContent?: string;
}

// Storage mutations
export interface CreateStorageInput {
  teamName: string;
  storageName: string;
  vaultContent?: string;
}

// Region mutations
export interface CreateRegionInput {
  regionName: string;
  vaultContent?: string;
}

// Bridge mutations
export interface CreateBridgeInput {
  regionName: string;
  bridgeName: string;
  vaultContent?: string;
}

// Ceph mutations
export interface CreateCephClusterInput {
  clusterName: string;
  vaultContent?: string;
}
