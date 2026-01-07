import { useCallback } from 'react';
import { typedApi } from '@/api/client';
import { type QueueRequestContext, queueService } from '@/services/queue';
import { parseGetOrganizationVault } from '@rediacc/shared/api';
import { parseVaultContentOrEmpty } from '@rediacc/shared/queue-vault';

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

export function useQueueVaultBuilder() {
  const buildQueueVault = useCallback(async (context: QueueVaultBuilderParams): Promise<string> => {
    // Fetch organization vault directly from API to ensure we have the latest data
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

    const parsedVaults: Partial<
      Pick<
        QueueRequestContext,
        | 'teamVault'
        | 'machineVault'
        | 'repositoryVault'
        | 'bridgeVault'
        | 'storageVault'
        | 'organizationVault'
        | 'destinationMachineVault'
        | 'destinationStorageVault'
        | 'destinationRepositoryVault'
        | 'sourceMachineVault'
        | 'sourceStorageVault'
        | 'sourceRepositoryVault'
      >
    > = {
      teamVault: baseContext.teamVault
        ? parseVaultContentOrEmpty(baseContext.teamVault)
        : undefined,
      machineVault: baseContext.machineVault
        ? parseVaultContentOrEmpty(baseContext.machineVault)
        : undefined,
      repositoryVault: repositoryVault ? parseVaultContentOrEmpty(repositoryVault) : undefined,
      bridgeVault: baseContext.bridgeVault
        ? parseVaultContentOrEmpty(baseContext.bridgeVault)
        : undefined,
      storageVault: baseContext.storageVault
        ? parseVaultContentOrEmpty(baseContext.storageVault)
        : undefined,
      organizationVault: parseVaultContentOrEmpty(organizationVaultData.vaultContent),
      destinationMachineVault: baseContext.destinationMachineVault
        ? parseVaultContentOrEmpty(baseContext.destinationMachineVault)
        : undefined,
      destinationStorageVault: baseContext.destinationStorageVault
        ? parseVaultContentOrEmpty(baseContext.destinationStorageVault)
        : undefined,
      destinationRepositoryVault: destinationRepositoryVault
        ? parseVaultContentOrEmpty(destinationRepositoryVault)
        : undefined,
      sourceMachineVault: baseContext.sourceMachineVault
        ? parseVaultContentOrEmpty(baseContext.sourceMachineVault)
        : undefined,
      sourceStorageVault: baseContext.sourceStorageVault
        ? parseVaultContentOrEmpty(baseContext.sourceStorageVault)
        : undefined,
      sourceRepositoryVault: sourceRepositoryVault
        ? parseVaultContentOrEmpty(sourceRepositoryVault)
        : undefined,
    };

    // Build complete context with vault data
    const fullContext: QueueRequestContext = {
      ...baseContext,
      ...parsedVaults,
      organizationCredential: organizationVaultData.organizationCredential ?? undefined,
      allRepositoryCredentials,
    };

    // Use the service to build the vault
    return queueService.buildQueueVault(fullContext);
  }, []);

  return { buildQueueVault };
}
