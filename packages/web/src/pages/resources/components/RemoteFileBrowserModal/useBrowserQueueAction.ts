import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { waitForQueueItemCompletion } from '@/services/helloService';
import { FileListParserFactory } from './parserFactory';
import type { AdditionalVaultData, RemoteFile } from './types';

interface ExecuteListParams {
  selectedSource: string;
  currentPath: string;
  teamName: string;
  machineName: string;
  bridgeName: string;
  additionalVaultData: AdditionalVaultData;
  mapGuidToRepository: (guid: string) => {
    displayName: string;
    repositoryName?: string;
    repositoryTag?: string;
    isUnmapped: boolean;
  };
}

export function useBrowserQueueAction() {
  const { buildQueueVault } = useQueueVaultBuilder();
  const { mutateAsync: createQueueItem } = useManagedQueueItem();

  const executeList = async (params: ExecuteListParams): Promise<RemoteFile[]> => {
    const {
      selectedSource,
      currentPath,
      teamName,
      machineName,
      bridgeName,
      additionalVaultData,
      mapGuidToRepository,
    } = params;

    const vault = await buildQueueVault({
      teamName,
      machineName,
      bridgeName,
      functionName: 'list',
      params: {
        from: selectedSource,
        path: currentPath || '',
        format: 'json',
      },
      priority: 4,
      addedVia: 'file-browser',
      ...additionalVaultData,
    });

    const result = await createQueueItem({
      teamName,
      machineName,
      bridgeName,
      queueVault: vault,
      priority: 4,
    });

    const taskId = result.taskId || result.queueId;
    if (!taskId) {
      throw new Error('Failed to create queue item - no taskId returned');
    }

    if (result.isQueued) {
      throw new Error('QUEUED');
    }

    const completionResult = await waitForQueueItemCompletion(taskId, 30000);
    if (!completionResult.success) {
      throw new Error(completionResult.message || 'List operation failed');
    }

    return parseListResponse(completionResult.responseData, currentPath, mapGuidToRepository);
  };

  return { executeList };
}

function parseListResponse(
  responseData: { result?: string } | undefined,
  currentPath: string,
  mapGuidToRepository: (guid: string) => {
    displayName: string;
    repositoryName?: string;
    repositoryTag?: string;
    isUnmapped: boolean;
  }
): RemoteFile[] {
  const commandResult = responseData?.result;

  if (!commandResult && !responseData) {
    console.warn('Remote file browser received no response data');
    return [];
  }

  let dataToProcess = '';

  if (typeof commandResult === 'string') {
    try {
      const parsed = JSON.parse(commandResult);
      dataToProcess = parsed.command_output || '';
    } catch {
      dataToProcess = commandResult;
    }
  }

  if (typeof dataToProcess === 'string' && dataToProcess) {
    const parser = new FileListParserFactory(currentPath, mapGuidToRepository);
    return parser.parse(dataToProcess);
  }

  return [];
}
