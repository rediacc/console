/**
 * Shared types and low-level parsing helpers used by both parsing.ts and parsing-health.ts.
 * Kept in a separate file to avoid circular imports between those two modules.
 */

import { isListResult, type ListResult } from '../../queue-vault/data/list-types.generated';

export type { ListResult };

/**
 * Machine information with vault status.
 * Uses generic to allow any machine type that has the required properties.
 * Note: machineName is nullable to match generated API types.
 */
export type MachineWithVaultStatus = {
  machineName: string | null;
  vaultStatus?: string | null;
};

/**
 * Check if vault data appears to be encrypted (base64, not JSON)
 */
export function isEncryptedVaultData(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length < 40 || trimmed.startsWith('{')) {
    return false;
  }
  try {
    JSON.parse(trimmed);
    return false;
  } catch {
    return /^[A-Za-z0-9+/]+=*$/.test(trimmed);
  }
}

/**
 * Parse vault status and return the full ListResult data.
 * Returns null if parsing fails or data is encrypted.
 */
export function parseListResult(vaultStatusJson: string | undefined | null): ListResult | null {
  if (!vaultStatusJson) {
    return null;
  }

  if (isEncryptedVaultData(vaultStatusJson)) {
    return null;
  }

  const trimmed = vaultStatusJson.trim();
  if (!trimmed.startsWith('{')) {
    return null;
  }

  try {
    const data = JSON.parse(vaultStatusJson);
    if (isListResult(data)) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}
