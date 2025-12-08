import { useCallback } from 'react';
import { useCreateQueueItem } from '@/api/queries/queue';
import { useTeams } from '@/api/queries/teams';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import type { Machine } from '@/types';
import type { GetCompanyTeams_ResultSet1 } from '@rediacc/shared/types';
import { type QueueItemCompletionResult, waitForQueueItemCompletion } from './helloService';

export interface PingFunctionParams {
  teamName: string;
  machineName: string;
  bridgeName: string;
  priority?: number;
  description?: string;
  addedVia?: string;
  machineVault?: string;
  teamVault?: string;
  vaultContent?: string;
}

export interface PingFunctionResult {
  taskId?: string;
  success: boolean;
  error?: string;
}

type QueueItemMutation =
  | Pick<ReturnType<typeof useCreateQueueItem>, 'mutateAsync' | 'isPending'>
  | Pick<ReturnType<typeof useManagedQueueItem>, 'mutateAsync' | 'isPending'>;

type BuildQueueVaultFn = ReturnType<typeof useQueueVaultBuilder>['buildQueueVault'];

interface QueueCreationResponse {
  taskId?: string;
  isQueued?: boolean;
}

const isQueueCreationResponse = (value: unknown): value is QueueCreationResponse => {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Partial<QueueCreationResponse>;
  const hasValidTaskId = candidate.taskId === undefined || typeof candidate.taskId === 'string';
  const hasValidQueued =
    candidate.isQueued === undefined || typeof candidate.isQueued === 'boolean';
  return hasValidTaskId && hasValidQueued;
};

const normalizeQueueCreationResponse = (value: unknown): QueueCreationResponse => {
  return isQueueCreationResponse(value) ? value : {};
};

/**
 * Custom hook that provides a standardized way to call the ping function
 * This encapsulates the logic for building the queue vault and creating queue items
 */
export function usePingFunction(options?: { useManaged?: boolean }) {
  const { buildQueueVault } = useQueueVaultBuilder();
  // Always call both hooks unconditionally
  const managedMutation = useManagedQueueItem();
  const regularMutation = useCreateQueueItem();
  const createQueueItemMutation: QueueItemMutation = options?.useManaged
    ? managedMutation
    : regularMutation;
  const { data: teams } = useTeams();

  const executePing = useCallback(
    async (params: PingFunctionParams): Promise<PingFunctionResult> => {
      try {
        const teamVault = getTeamVault(params, teams);
        const queueVault = await buildPingQueueVault(params, teamVault, buildQueueVault);
        const response = await createPingQueueItem(params, queueVault, createQueueItemMutation);

        return {
          taskId: response?.taskId,
          success: !!response?.taskId || !!response?.isQueued,
        };
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Failed to execute ping function';
        return {
          success: false,
          error: message,
        };
      }
    },
    [buildQueueVault, createQueueItemMutation, teams]
  );

  const executePingForMachine = useCallback(
    async (
      machine: Machine,
      options?: {
        priority?: number;
        description?: string;
        addedVia?: string;
      }
    ): Promise<PingFunctionResult> => {
      return executePing({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        priority: options?.priority,
        description: options?.description,
        addedVia: options?.addedVia,
        machineVault: machine.vaultContent || '{}',
      });
    },
    [executePing]
  );

  const executePingAndWait = useCallback(
    async (
      params: PingFunctionParams,
      timeout?: number
    ): Promise<{
      taskId?: string;
      success: boolean;
      error?: string;
      completionResult?: QueueItemCompletionResult;
    }> => {
      const result = await executePing(params);

      if (!result.success || !result.taskId) {
        return result;
      }

      const completionResult = await waitForQueueItemCompletion(result.taskId, timeout);

      return {
        ...result,
        completionResult,
        success: completionResult.success,
        error: completionResult.success ? undefined : completionResult.message,
      };
    },
    [executePing]
  );

  const executePingForMachineAndWait = useCallback(
    async (
      machine: Machine,
      options?: {
        priority?: number;
        description?: string;
        addedVia?: string;
        timeout?: number;
      }
    ): Promise<{
      taskId?: string;
      success: boolean;
      error?: string;
      completionResult?: QueueItemCompletionResult;
    }> => {
      return executePingAndWait(
        {
          teamName: machine.teamName,
          machineName: machine.machineName,
          bridgeName: machine.bridgeName,
          priority: options?.priority,
          description: options?.description,
          addedVia: options?.addedVia,
          machineVault: machine.vaultContent || '{}',
        },
        options?.timeout
      );
    },
    [executePingAndWait]
  );

  return {
    executePing,
    executePingForMachine,
    executePingAndWait,
    executePingForMachineAndWait,
    waitForQueueItemCompletion,
    isLoading: createQueueItemMutation.isPending,
  };
}

// Helper functions
function getTeamVault(
  params: PingFunctionParams,
  teams: GetCompanyTeams_ResultSet1[] | undefined
): string {
  if (params.teamVault && params.teamVault !== '{}') {
    return params.teamVault;
  }

  const teamData = teams?.find((team) => team.teamName === params.teamName);
  return teamData?.vaultContent || '{}';
}

async function buildPingQueueVault(
  params: PingFunctionParams,
  teamVault: string,
  buildQueueVault: BuildQueueVaultFn
): Promise<string> {
  const DEFAULT_PRIORITY = 4;
  const DEFAULT_ADDED_VIA = 'ping-service';
  const DEFAULT_VAULT = '{}';

  return buildQueueVault({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    functionName: 'ping',
    params: {},
    priority: params.priority || DEFAULT_PRIORITY,
    addedVia: params.addedVia || DEFAULT_ADDED_VIA,
    machineVault: params.machineVault || DEFAULT_VAULT,
    teamVault: teamVault,
    repositoryVault: params.vaultContent || DEFAULT_VAULT,
  });
}

async function createPingQueueItem(
  params: PingFunctionParams,
  queueVault: string,
  createQueueItemMutation: QueueItemMutation
): Promise<QueueCreationResponse> {
  const DEFAULT_PRIORITY = 4;

  const response = await createQueueItemMutation.mutateAsync({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    queueVault,
    priority: params.priority || DEFAULT_PRIORITY,
  });

  return normalizeQueueCreationResponse(response);
}
