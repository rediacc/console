/**
 * Queue action service
 * Platform-agnostic service for executing queue actions
 */

import type { QueueRequestContext } from '../../queue-vault';

/**
 * Parameters for queue action execution
 */
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
  repositoryGuid?: string;
  vaultContent?: string;
  repositoryNetworkId?: number;
  repositoryNetworkMode?: string;
  repositoryTag?: string;
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

/**
 * Result of a queue action execution
 */
export interface QueueActionResult {
  success: boolean;
  taskId?: string;
  error?: string;
  isQueued?: boolean;
}

/**
 * Dependencies required by QueueActionService
 * These must be injected by the platform (web or CLI)
 */
export interface QueueActionDependencies {
  /** Build queue vault from context */
  buildQueueVault(context: QueueRequestContext): Promise<string>;
  /** Create queue item in the system */
  createQueueItem(data: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    queueVault: string;
    priority: number;
  }): Promise<{ taskId?: string; isQueued?: boolean }>;
}

/**
 * Platform-agnostic queue action service
 * Handles vault assembly and queue item creation for any function
 */
export class QueueActionService {
  constructor(private readonly deps: QueueActionDependencies) {}

  /**
   * Execute a queue action
   * @param params - Action parameters
   * @param teamVault - Team vault content
   * @returns Result of the action execution
   */
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
      repositoryGuid: params.repositoryGuid,
      repositoryVault: params.vaultContent,
      repositoryNetworkId: params.repositoryNetworkId,
      repositoryNetworkMode: params.repositoryNetworkMode,
      repositoryTag: params.repositoryTag,
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
