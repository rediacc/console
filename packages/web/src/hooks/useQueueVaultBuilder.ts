import { useCallback } from 'react';
import { typedApi } from '@/api/client';
import { type QueueRequestContext, queueService } from '@/services/queue';
import { parseGetOrganizationVault } from '@rediacc/shared/api';
import { parseVaultContentOrEmpty, type VaultContent } from '@rediacc/shared/queue-vault';

/**
 * Hook to build queue vault data with all required context
 * This combines vault data from various entities based on function requirements
 */
type QueueVaultBuilderParams = Omit<
  QueueRequestContext,
  'organizationVault' | 'organizationCredential'
> & {
  repositoryVault?: QueueRequestContext['repositoryVault'];
  destinationRepositoryVault?: QueueRequestContext['destinationRepositoryVault'];
  sourceRepositoryVault?: QueueRequestContext['sourceRepositoryVault'];
  allRepositoryCredentials?: Record<string, string>;
};

const parseOptionalVault = (vault: VaultContent | undefined) =>
  vault ? parseVaultContentOrEmpty(vault) : undefined;

export function useQueueVaultBuilder() {
  const buildQueueVault = useCallback(async (context: QueueVaultBuilderParams): Promise<string> => {
    const response = await typedApi.GetOrganizationVault({});
    const organizationVaultData = parseGetOrganizationVault(response as never);

    if (!organizationVaultData) {
      throw new Error('Failed to fetch organization vault data');
    }

    const {
      repositoryVault,
      destinationRepositoryVault,
      sourceRepositoryVault,
      allRepositoryCredentials,
      ...baseContext
    } = context;

    const parsedVaults = {
      teamVault: parseOptionalVault(baseContext.teamVault),
      machineVault: parseOptionalVault(baseContext.machineVault),
      repositoryVault: parseOptionalVault(repositoryVault),
      bridgeVault: parseOptionalVault(baseContext.bridgeVault),
      storageVault: parseOptionalVault(baseContext.storageVault),
      organizationVault: parseVaultContentOrEmpty(organizationVaultData.vaultContent),
      destinationMachineVault: parseOptionalVault(baseContext.destinationMachineVault),
      destinationStorageVault: parseOptionalVault(baseContext.destinationStorageVault),
      destinationRepositoryVault: parseOptionalVault(destinationRepositoryVault),
      sourceMachineVault: parseOptionalVault(baseContext.sourceMachineVault),
      sourceStorageVault: parseOptionalVault(baseContext.sourceStorageVault),
      sourceRepositoryVault: parseOptionalVault(sourceRepositoryVault),
    };

    const fullContext: QueueRequestContext = {
      ...baseContext,
      ...parsedVaults,
      organizationCredential: organizationVaultData.organizationCredential ?? undefined,
      allRepositoryCredentials,
    };

    return queueService.buildQueueVault(fullContext);
  }, []);

  return { buildQueueVault };
}
