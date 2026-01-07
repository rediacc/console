/**
 * Queue action service
 * Platform-agnostic service for executing queue actions
 */

import type { QueueRequestContext } from '../../queue-vault';
import type {
  BridgeFunctionName,
  FunctionParamsMap,
} from '../../queue-vault/data/functions.generated';

/**
 * Base parameters for queue action execution (without function-specific fields).
 * This is the foundation for both TypedQueueActionParams and DynamicQueueActionParams.
 */
export interface QueueActionBaseParams {
  teamName: string;
  machineName: string;
  bridgeName: string;
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
  /** User's preferred language for task output (en, de, es, fr, ja, ar, ru, tr, zh) */
  language?: string;
}

/**
 * Type-safe queue action params with compile-time parameter validation.
 * Use this for type-safe function calls where params are validated against
 * the function's expected parameter interface.
 *
 * @example
 * const params: TypedQueueActionParams<'backup_create'> = {
 *   functionName: 'backup_create',
 *   params: { dest: 'backup.tar', storages: ['s3'] }, // Type-checked!
 *   teamName: 'Production',
 *   machineName: 'server-01',
 *   // ... other required fields
 * };
 */
export type TypedQueueActionParams<F extends BridgeFunctionName> = QueueActionBaseParams & {
  functionName: F;
  params: FunctionParamsMap[F];
};

/**
 * Union of all typed queue action params.
 * Useful for exhaustive matching and type guards.
 */
export type AnyTypedQueueActionParams = {
  [F in BridgeFunctionName]: TypedQueueActionParams<F>;
}[BridgeFunctionName];

/**
 * Dynamic queue action params with validated function name but untyped params.
 * Use when function name is determined at runtime but comes from a trusted source.
 *
 * @example
 * const params: DynamicQueueActionParams = {
 *   functionName: functionData.function.name as BridgeFunctionName,
 *   params: functionData.params,
 *   teamName: 'Production',
 *   // ... other required fields
 * };
 */
export type DynamicQueueActionParams = QueueActionBaseParams & {
  functionName: BridgeFunctionName;
  params: Record<string, unknown>;
};

/**
 * Type guard to check if params are for a specific function.
 * Narrows the type to TypedQueueActionParams<F> when true.
 *
 * @example
 * if (isTypedQueueAction(params, 'backup_create')) {
 *   // params.params is now BackupCreateParams
 *   console.log(params.params.storages);
 * }
 */
export function isTypedQueueAction<F extends BridgeFunctionName>(
  params: DynamicQueueActionParams | TypedQueueActionParams<BridgeFunctionName>,
  functionName: F
): params is TypedQueueActionParams<F> {
  return params.functionName === functionName;
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
   * @param params - Action parameters (typed or dynamic)
   * @param teamVault - Team vault content
   * @returns Result of the action execution
   */
  async execute(params: DynamicQueueActionParams, teamVault: string): Promise<QueueActionResult> {
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
      language: params.language,
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
      taskId: response.taskId,
      isQueued: response.isQueued,
    };
  }
}
