import { STALE_TASK_CONSTANTS } from '@rediacc/shared/queue';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { normalizeToBoolean, normalizeToNumber, normalizeToString } from '@/platform';

/**
 * Determines if a task is in a terminal state (completed, cancelled, or permanently failed).
 * Terminal states are states from which a task will not transition to another state.
 */
export const isTaskInTerminalState = (
  queueDetails: GetTeamQueueItems_ResultSet1 | Record<string, unknown>
): boolean => {
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const retryCount = normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount');
  const permanentlyFailed = normalizeToBoolean(
    queueDetails,
    'permanentlyFailed',
    'PermanentlyFailed'
  );
  const lastFailureReason = normalizeToString(
    queueDetails,
    'lastFailureReason',
    'LastFailureReason'
  );

  // Check if task is in a terminal state
  if (status === 'COMPLETED' || status === 'CANCELLED') {
    return true;
  }

  if (
    status === 'FAILED' &&
    (permanentlyFailed || retryCount >= STALE_TASK_CONSTANTS.MAX_RETRY_COUNT)
  ) {
    return true;
  }

  if (
    status === 'PENDING' &&
    retryCount >= STALE_TASK_CONSTANTS.MAX_RETRY_COUNT &&
    lastFailureReason
  ) {
    return true;
  }

  return false;
};
