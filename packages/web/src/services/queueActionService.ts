import type { QueueRequestContext } from '@/core/types';

export interface QueueActionParams {
  teamName: string;
  machineName: string;
  bridgeName: string;
  functionName: string;
  params: Record<string, unknown>;
  priority: number;
  description?: string;
  addedVia: string;
  machineVault: string;
  repoGuid?: string;
  vaultContent?: string;
  repoNetworkId?: number;
  repoNetworkMode?: string;
  repoTag?: string;
  storageName?: string;
  storageVault?: string;
  sourceMachineVault?: string;
  sourceStorageVault?: string;
  sourceVaultContent?: string;
  destinationMachineVault?: string;
  destinationStorageVault?: string;
  destinationVaultContent?: string;
  teamVault?: string;
}

export interface QueueActionResult {
  success: boolean;
  taskId?: string;
  error?: string;
  isQueued?: boolean;
}

interface QueueActionDependencies {
  buildQueueVault(context: QueueRequestContext): Promise<string>;
  createQueueItem(data: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    queueVault: string;
    priority: number;
  }): Promise<{ taskId?: string; isQueued?: boolean }>;
}

export class QueueActionService {
  constructor(private readonly deps: QueueActionDependencies) {}

  async execute(params: QueueActionParams, teamVault: string): Promise<QueueActionResult> {
    const queueVault = await this.deps.buildQueueVault({
      teamName: params.teamName,
      machineName: params.machineName,
      bridgeName: params.bridgeName,
      functionName: params.functionName,
      params: params.params,
      priority: params.priority,
      addedVia: params.addedVia,
      teamVault,
      machineVault: params.machineVault,
      repositoryGuid: params.repoGuid,
      repositoryVault: params.vaultContent,
      repositoryNetworkId: params.repoNetworkId,
      repositoryNetworkMode: params.repoNetworkMode,
      repositoryTag: params.repoTag,
      storageName: params.storageName,
      storageVault: params.storageVault,
      sourceMachineVault: params.sourceMachineVault,
      sourceStorageVault: params.sourceStorageVault,
      sourceRepositoryVault: params.sourceVaultContent,
      destinationMachineVault: params.destinationMachineVault,
      destinationStorageVault: params.destinationStorageVault,
      destinationRepositoryVault: params.destinationVaultContent,
    });

    const response = await this.deps.createQueueItem({
      teamName: params.teamName,
      machineName: params.machineName,
      bridgeName: params.bridgeName,
      queueVault,
      priority: params.priority,
    });

    return {
      success: true,
      taskId: response?.taskId,
      isQueued: response?.isQueued,
    };
  }
}
