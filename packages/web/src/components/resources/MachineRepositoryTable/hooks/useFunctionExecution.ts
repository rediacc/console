import { type TFunction } from 'i18next';
import type { QueueFunction } from '@/api/queries/queue';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';

export interface FunctionExecutionContext {
  selectedRepository: Repository | null;
  teamRepositories: Array<{
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    vaultContent?: string;
    grandGuid?: string;
    parentGuid?: string;
    repositoryNetworkId?: string;
    repositoryNetworkMode?: string;
  }>;
  machine: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    vaultContent?: string;
  };
  teamMachines: Array<{
    machineName: string;
    vaultContent?: string;
  }>;
  teamStorages: Array<{
    storageName: string;
    vaultContent?: string;
  }>;
  executeAction: (params: unknown) => Promise<{
    success: boolean;
    taskId?: string;
    isQueued?: boolean;
    error?: string;
  }>;
  createRepositoryCredential: (name: string, tag: string) => Promise<{
    repositoryGuid: string;
    repositoryName: string;
    repositoryNetworkId?: string;
    repositoryNetworkMode?: string;
    repositoryTag: string;
  }>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  closeModal: () => void;
  t: TFunction;
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
  teamRepositories: Array<{
    repositoryGuid: string;
    vaultContent?: string;
  }>
): string => {
  if (!repoData.grandGuid || !repoData.vaultContent) {
    return repoData.vaultContent || '{}';
  }

  const grandRepo = teamRepositories.find((r) => r.repositoryGuid === repoData.grandGuid);
  return grandRepo?.vaultContent || repoData.vaultContent;
};

export const getRequiredTag = (
  params: Record<string, unknown>,
  errorMsg: string,
  _t: TFunction,
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
  t: TFunction,
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
