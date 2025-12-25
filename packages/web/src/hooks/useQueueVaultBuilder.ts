import { useCallback } from 'react';
import { api } from '@/api/client';
import { type QueueRequestContext, queueService } from '@/services/queue';

/**
 * Hook to build queue vault data with all required context
 * This combines vault data from various entities based on function requirements
 */
type QueueVaultBuilderParams = Omit<QueueRequestContext, 'companyVault' | 'companyCredential'> & {
  repositoryVault?: QueueRequestContext['repositoryVault'];
  destinationRepositoryVault?: QueueRequestContext['destinationRepositoryVault'];
  sourceRepositoryVault?: QueueRequestContext['sourceRepositoryVault'];
  allRepositoryCredentials?: Record<string, string>;
};

const parseVaultContent = (vault?: QueueRequestContext['teamVault']): Record<string, unknown> => {
  if (!vault || vault === '-') {
    return {};
  }

  if (typeof vault === 'string') {
    try {
      return JSON.parse(vault);
    } catch {
      return {};
    }
  }

  return vault;
};

export function useQueueVaultBuilder() {
  const buildQueueVault = useCallback(async (context: QueueVaultBuilderParams): Promise<string> => {
    // Fetch company vault directly from API to ensure we have the latest data
    const companyVaultData = await api.company.getVault();

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
        | 'companyVault'
        | 'destinationMachineVault'
        | 'destinationStorageVault'
        | 'destinationRepositoryVault'
        | 'sourceMachineVault'
        | 'sourceStorageVault'
        | 'sourceRepositoryVault'
      >
    > = {
      teamVault: baseContext.teamVault ? parseVaultContent(baseContext.teamVault) : undefined,
      machineVault: baseContext.machineVault
        ? parseVaultContent(baseContext.machineVault)
        : undefined,
      repositoryVault: repositoryVault ? parseVaultContent(repositoryVault) : undefined,
      bridgeVault: baseContext.bridgeVault ? parseVaultContent(baseContext.bridgeVault) : undefined,
      storageVault: baseContext.storageVault
        ? parseVaultContent(baseContext.storageVault)
        : undefined,
      companyVault: parseVaultContent(companyVaultData.vault),
      destinationMachineVault: baseContext.destinationMachineVault
        ? parseVaultContent(baseContext.destinationMachineVault)
        : undefined,
      destinationStorageVault: baseContext.destinationStorageVault
        ? parseVaultContent(baseContext.destinationStorageVault)
        : undefined,
      destinationRepositoryVault: destinationRepositoryVault
        ? parseVaultContent(destinationRepositoryVault)
        : undefined,
      sourceMachineVault: baseContext.sourceMachineVault
        ? parseVaultContent(baseContext.sourceMachineVault)
        : undefined,
      sourceStorageVault: baseContext.sourceStorageVault
        ? parseVaultContent(baseContext.sourceStorageVault)
        : undefined,
      sourceRepositoryVault: sourceRepositoryVault
        ? parseVaultContent(sourceRepositoryVault)
        : undefined,
    };

    // Build complete context with vault data
    const fullContext: QueueRequestContext = {
      ...baseContext,
      ...parsedVaults,
      companyCredential: companyVaultData.companyCredential ?? undefined,
      allRepositoryCredentials,
    };

    // Use the service to build the vault
    return queueService.buildQueueVault(fullContext);
  }, []);

  return { buildQueueVault };
}
