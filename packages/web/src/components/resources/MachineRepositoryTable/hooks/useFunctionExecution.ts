import type {
  DynamicQueueActionParams,
  QueueActionResult,
  TypedQueueActionParams,
} from '@/services/queue';
import { showMessage } from '@/utils/messages';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { QueueFunction } from '@rediacc/shared/types';
import type { Repository } from '../types';

// Re-export typed function data interfaces from handlers/types.ts
export type {
  BaseFunctionData,
  CustomFunctionData,
  CustomFunctionParams,
  ForkFunctionData,
  ForkFunctionParams,
  PullFunctionData,
  PullFunctionParams,
  PushFunctionData,
  PushFunctionParams,
} from '../handlers/types';

export interface FunctionExecutionContext {
  selectedRepository: Repository | null;
  teamRepositories: {
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    vaultContent?: string;
    grandGuid?: string;
    parentGuid?: string;
    repositoryNetworkId?: number;
    repositoryNetworkMode?: string;
  }[];
  machine: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    vaultContent?: string;
  };
  teamMachines: {
    machineName: string;
    vaultContent?: string;
  }[];
  teamStorages: {
    storageName: string;
    vaultContent?: string;
  }[];
  executeTyped: <F extends BridgeFunctionName>(
    functionName: F,
    params: Omit<TypedQueueActionParams<F>, 'functionName'>
  ) => Promise<QueueActionResult>;
  executeDynamic: (
    functionName: BridgeFunctionName,
    params: Omit<DynamicQueueActionParams, 'functionName'>
  ) => Promise<QueueActionResult>;
  createRepositoryCredential: (
    name: string,
    tag: string
  ) => Promise<{
    repositoryGuid: string;
    repositoryName: string;
    repositoryNetworkId?: number;
    repositoryNetworkMode?: string;
    repositoryTag: string;
  }>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  closeModal: () => void;
  t: TypedTFunction;
}

export interface FunctionData {
  function: QueueFunction;
  params: Record<string, unknown>;
  priority: number;
  description: string;
}

export const getGrandRepoVault = (
  repoData: {
    vaultContent?: string;
    grandGuid?: string;
    repositoryGuid: string;
  },
  teamRepositories: {
    repositoryGuid: string;
    vaultContent?: string;
  }[]
): string => {
  if (!repoData.grandGuid || !repoData.vaultContent) {
    return repoData.vaultContent ?? '{}';
  }

  const grandRepo = teamRepositories.find((r) => r.repositoryGuid === repoData.grandGuid);
  return grandRepo?.vaultContent ?? repoData.vaultContent;
};

export const getRequiredTag = (
  params: { tag?: string } | Record<string, unknown>,
  errorMsg: string,
  _t: TypedTFunction,
  closeModal: () => void
): string | null => {
  const tag = typeof params.tag === 'string' ? params.tag.trim() : '';
  if (!tag) {
    showMessage('error', errorMsg);
    closeModal();
    return null;
  }
  return tag;
};

export const showMultiTargetSummary = (
  taskIds: string[],
  total: number,
  keys: { success: string; partial: string; allFailed: string },
  t: TypedTFunction,
  onQueueItemCreated?: (taskId: string, machineName: string) => void,
  machineName?: string
) => {
  if (taskIds.length === total) {
    showMessage('success', t(keys.success, { count: taskIds.length }));
  } else if (taskIds.length > 0) {
    showMessage('warning', t(keys.partial, { success: taskIds.length, total }));
  } else {
    showMessage('error', t(keys.allFailed));
  }
  if (onQueueItemCreated && taskIds[0] && machineName) {
    onQueueItemCreated(taskIds[0], machineName);
  }
};
