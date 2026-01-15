import { parseGetQueueItemTrace } from '@rediacc/shared/api';
import type { GetTeamQueueItems_ResultSet1, QueueTrace } from '@rediacc/shared/types';
import { typedApi } from '@/api/client';
import i18n from '@/i18n/config';

interface HelloResponseData {
  result?: string;
  [key: string]: unknown;
}

export interface QueueItemCompletionResult {
  success: boolean;
  message: string;
  status?: string;
  responseData?: HelloResponseData;
}

/**
 * Wait for a queue item to complete by polling its status
 * @param taskId The task ID to monitor
 * @param timeout Maximum time to wait in milliseconds (default: 30 seconds)
 * @returns Completion result with success status and message
 */
const DEFAULT_TIMEOUT = 30000;
const POLLING_INTERVAL = 1000;

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
    const response = await typedApi.GetQueueItemTrace({ taskId });
    const trace = parseGetQueueItemTrace(response as never);
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
    return createSuccessResult(i18n.t('shared:success.helloFunctionSuccess'), 'COMPLETED');
  }

  const vaultData = parseResponseVaultContent(responseVault.vaultContent);
  const resultMessage = typeof vaultData.result === 'string' ? vaultData.result : undefined;
  const isError = resultMessage?.includes('Error');

  return isError
    ? createErrorResult(
        resultMessage ?? i18n.t('shared:errors.helloFunctionError'),
        'COMPLETED',
        vaultData
      )
    : createSuccessResult(
        resultMessage ?? i18n.t('shared:success.helloFunctionSuccess'),
        'COMPLETED',
        vaultData
      );
}

function handleFailedStatus(
  queueDetails: GetTeamQueueItems_ResultSet1,
  status: string
): QueueItemCompletionResult {
  const failureReason = queueDetails.lastFailureReason ?? i18n.t('shared:errors.operationFailed');

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
