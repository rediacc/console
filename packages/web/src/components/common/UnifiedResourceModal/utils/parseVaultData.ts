import type { ExistingResourceData, ResourceType } from '../types';

const tryExtractCredentialFromNested = (
  vaultData: Record<string, unknown>
): Record<string, unknown> | null => {
  if (!vaultData.repositoryVault) {
    return null;
  }

  try {
    const innerVault =
      typeof vaultData.repositoryVault === 'string'
        ? JSON.parse(vaultData.repositoryVault)
        : vaultData.repositoryVault;

    if (innerVault && typeof innerVault === 'object' && 'credential' in innerVault) {
      return { credential: (innerVault as Record<string, unknown>).credential };
    }
  } catch (e) {
    console.error('[parseVaultData] Failed to parse nested vault:', e);
  }

  return null;
};

const tryExtractCredentialFromFields = (
  vaultData: Record<string, unknown>
): Record<string, unknown> | null => {
  for (const [, value] of Object.entries(vaultData)) {
    if (
      typeof value === 'string' &&
      value.length === 32 &&
      /^[A-Za-z0-9!@#$%^&*()_+{}|:<>,.?/]+$/.test(value)
    ) {
      return { credential: value };
    }
  }
  return null;
};

const parseRepositoryVault = (vaultData: Record<string, unknown>): Record<string, unknown> => {
  // Already has credential at root level
  if (vaultData.credential) {
    return vaultData;
  }

  // Try to extract from nested repositoryVault
  const nestedResult = tryExtractCredentialFromNested(vaultData);
  if (nestedResult) {
    return nestedResult;
  }

  // Try to find 32-character string that might be the credential
  const fieldResult = tryExtractCredentialFromFields(vaultData);
  if (fieldResult) {
    return fieldResult;
  }

  return vaultData;
};

export const parseVaultData = (
  resourceType: ResourceType,
  existingData?: ExistingResourceData
): Record<string, unknown> => {
  if (!existingData?.vaultContent) {
    return {};
  }

  try {
    const parsed = JSON.parse(existingData.vaultContent);

    if (resourceType === 'repository') {
      return parseRepositoryVault(parsed);
    }

    return parsed;
  } catch (e) {
    console.error('[parseVaultData] Failed to parse vault content:', e);
    return {};
  }
};
