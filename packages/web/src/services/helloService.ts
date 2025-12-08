import { useCallback } from 'react';
import { api } from '@/api/client';
import { useCreateQueueItem } from '@/api/queries/queue';
import { useTeams } from '@/api/queries/teams';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import type { Machine } from '@/types';
import type {
  QueueTrace,
  GetTeamQueueItems_ResultSet1,
  GetCompanyTeams_ResultSet1,
} from '@rediacc/shared/types';

export interface HelloFunctionParams {
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

export interface HelloFunctionResult {
  taskId?: string;
  success: boolean;
  error?: string;
}

export interface QueueItemCompletionResult {
  success: boolean;
  message: string;
  status?: string;
  responseData?: HelloResponseData;
}

type QueueItemMutation =
  | Pick<ReturnType<typeof useCreateQueueItem>, 'mutateAsync' | 'isPending'>
  | Pick<ReturnType<typeof useManagedQueueItem>, 'mutateAsync' | 'isPending'>;

type BuildQueueVaultFn = ReturnType<typeof useQueueVaultBuilder>['buildQueueVault'];

interface HelloResponseData {
  result?: string;
  [key: string]: unknown;
}

interface QueueCreationResponse {
  taskId?: string;
  isQueued?: boolean;
}

interface CreateQueueItemArgs {
  teamName: string;
  machineName: string;
  bridgeName: string;
  queueVault: string;
  priority?: number;
}

type CreateQueueItemExecutor = (args: CreateQueueItemArgs) => Promise<QueueCreationResponse>;

/**
 * Wait for a queue item to complete by polling its status
 * @param taskId The task ID to monitor
 * @param timeout Maximum time to wait in milliseconds (default: 30 seconds)
 * @returns Completion result with success status and message
 */
const DEFAULT_TIMEOUT = 30000;
const POLLING_INTERVAL = 1000;

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

const parseResponseVaultContent = (
  vaultContent: string | Record<string, unknown>
): HelloResponseData => {
  if (typeof vaultContent === 'string') {
    try {
      const parsed = JSON.parse(vaultContent);
      if (typeof parsed === 'object' && parsed !== null) {
        return parsed as HelloResponseData;
      }
      return { result: String(parsed) };
    } catch {
      return { result: vaultContent };
    }
  }

  return vaultContent as HelloResponseData;
};

export async function waitForQueueItemCompletion(
  taskId: string,
  timeout: number = DEFAULT_TIMEOUT
): Promise<QueueItemCompletionResult> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const pollResult = await pollQueueItemStatus(taskId);

    if (pollResult) {
      return pollResult;
    }

    // Wait before next poll
    await new Promise((resolve) => setTimeout(resolve, POLLING_INTERVAL));
  }

  return createTimeoutResult();
}

async function pollQueueItemStatus(taskId: string): Promise<QueueItemCompletionResult | null> {
  try {
    const trace = await api.queue.getTrace({ taskId });
    const queueDetails = trace.queueDetails;

    if (!queueDetails) {
      return null;
    }

    const status = queueDetails.status;

    switch (status) {
      case 'COMPLETED':
        return handleCompletedStatus(trace);
      case 'FAILED':
      case 'CANCELLED':
        return handleFailedStatus(queueDetails, status);
      default:
        return null;
    }
  } catch {
    // Continue polling on error
    return null;
  }
}

function handleCompletedStatus(trace: QueueTrace): QueueItemCompletionResult {
  const responseVault = trace.responseVaultContent;

  if (!responseVault?.vaultContent) {
    return createSuccessResult('Hello function completed successfully', 'COMPLETED');
  }

  const vaultData = parseResponseVaultContent(responseVault.vaultContent);
  const resultMessage = typeof vaultData.result === 'string' ? vaultData.result : undefined;
  const isError = resultMessage?.includes('Error');

  return isError
    ? createErrorResult(resultMessage ?? 'Hello function reported an error', 'COMPLETED', vaultData)
    : createSuccessResult(
        resultMessage || 'Hello function completed successfully',
        'COMPLETED',
        vaultData
      );
}

function handleFailedStatus(
  queueDetails: GetTeamQueueItems_ResultSet1,
  status: string
): QueueItemCompletionResult {
  const failureReason = queueDetails.lastFailureReason || 'Operation failed';

  return createErrorResult(failureReason, status);
}

function createSuccessResult(
  message: string,
  status: string,
  responseData?: HelloResponseData
): QueueItemCompletionResult {
  return { success: true, message, status, responseData };
}

function createErrorResult(
  message: string,
  status: string,
  responseData?: HelloResponseData
): QueueItemCompletionResult {
  return { success: false, message, status, responseData };
}

function createTimeoutResult(): QueueItemCompletionResult {
  return createErrorResult('Operation timeout - no response received', 'TIMEOUT');
}

/**
 * Custom hook that provides a standardized way to call the hello function
 * This encapsulates the logic for building the queue vault and creating queue items
 */
export function useHelloFunction(options?: { useManaged?: boolean }) {
  const { buildQueueVault } = useQueueVaultBuilder();
  // Always call both hooks unconditionally
  const managedMutation = useManagedQueueItem();
  const regularMutation = useCreateQueueItem();
  const createQueueItemMutation: QueueItemMutation = options?.useManaged
    ? managedMutation
    : regularMutation;
  const { data: teams } = useTeams();

  const executeHello = useCallback(
    async (params: HelloFunctionParams): Promise<HelloFunctionResult> => {
      try {
        const teamVault = getTeamVault(params, teams);
        const queueVault = await buildHelloQueueVault(params, teamVault, buildQueueVault);
        const response = await createHelloQueueItem(params, queueVault, createQueueItemMutation);

        return {
          taskId: response?.taskId,
          success: !!response?.taskId || !!response?.isQueued,
        };
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Failed to execute hello function';
        return {
          success: false,
          error: message,
        };
      }
    },
    [buildQueueVault, createQueueItemMutation, teams]
  );

  const executeHelloForMachine = useCallback(
    async (
      machine: Machine,
      options?: {
        priority?: number;
        description?: string;
        addedVia?: string;
      }
    ): Promise<HelloFunctionResult> => {
      return executeHello({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        priority: options?.priority,
        description: options?.description,
        addedVia: options?.addedVia,
        machineVault: machine.vaultContent || '{}',
      });
    },
    [executeHello]
  );

  const executeHelloAndWait = useCallback(
    async (
      params: HelloFunctionParams,
      timeout?: number
    ): Promise<{
      taskId?: string;
      success: boolean;
      error?: string;
      completionResult?: QueueItemCompletionResult;
    }> => {
      const result = await executeHello(params);

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
    [executeHello]
  );

  const executeHelloForMachineAndWait = useCallback(
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
      return executeHelloAndWait(
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
    [executeHelloAndWait]
  );

  return {
    executeHello,
    executeHelloForMachine,
    executeHelloAndWait,
    executeHelloForMachineAndWait,
    waitForQueueItemCompletion,
    isLoading: createQueueItemMutation.isPending,
  };
}

// Helper functions
function getTeamVault(
  params: HelloFunctionParams,
  teams: GetCompanyTeams_ResultSet1[] | undefined
): string {
  if (params.teamVault && params.teamVault !== '{}') {
    return params.teamVault;
  }

  const teamData = teams?.find((team) => team.teamName === params.teamName);
  return teamData?.vaultContent || '{}';
}

async function buildHelloQueueVault(
  params: HelloFunctionParams,
  teamVault: string,
  buildQueueVault: BuildQueueVaultFn
): Promise<string> {
  const DEFAULT_PRIORITY = 4;
  const DEFAULT_ADDED_VIA = 'hello-service';
  const DEFAULT_VAULT = '{}';

  return buildQueueVault({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    functionName: 'hello',
    params: {},
    priority: params.priority || DEFAULT_PRIORITY,
    addedVia: params.addedVia || DEFAULT_ADDED_VIA,
    machineVault: params.machineVault || DEFAULT_VAULT,
    teamVault: teamVault,
    repositoryVault: params.vaultContent || DEFAULT_VAULT,
  });
}

async function createHelloQueueItem(
  params: HelloFunctionParams,
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

/**
 * Service class for hello function operations (if class-based approach is preferred)
 */
export class HelloService {
  static async executeHello(
    params: HelloFunctionParams,
    buildQueueVault: BuildQueueVaultFn,
    createQueueItem: CreateQueueItemExecutor
  ): Promise<HelloFunctionResult> {
    try {
      const teamVault = params.teamVault || '{}';
      const queueVault = await buildHelloQueueVault(params, teamVault, buildQueueVault);

      const response = await createQueueItem({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        queueVault,
        priority: params.priority || 4,
      });

      return {
        taskId: response?.taskId,
        success: !!response?.taskId,
      };
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to execute hello function';
      return {
        success: false,
        error: message,
      };
    }
  }

  static waitForQueueItemCompletion = waitForQueueItemCompletion;
}
