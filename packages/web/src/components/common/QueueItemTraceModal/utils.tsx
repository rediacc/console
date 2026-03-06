import type { GetTeamQueueItems_ResultSet1, QueueTraceLog } from '@rediacc/shared/types';
import dayjs from 'dayjs';
import { formatTimestampAsIs, normalizeToNumber, normalizeToString } from '@/platform';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  RetweetOutlined,
  RocketOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@/utils/optimizedIcons';
import type { PriorityInfo, SimplifiedStatus, TaskStalenessLevel } from './types';

// Helper function to extract timestamp from trace logs for specific action
export const getTimelineTimestamp = (
  traceLogs: QueueTraceLog[],
  action: string,
  fallbackAction?: string
): string | null => {
  if (traceLogs.length === 0) return null;

  // Try primary action first
  let log = traceLogs.find((log) => normalizeToString(log, 'action', 'Action') === action);

  // If not found and fallback provided, try fallback action
  if (!log && fallbackAction) {
    log = traceLogs.find((log) => normalizeToString(log, 'action', 'Action') === fallbackAction);
  }

  if (log) {
    const timestamp = normalizeToString(log, 'timestamp', 'Timestamp');
    return timestamp ? formatTimestampAsIs(timestamp, 'time') : null;
  }

  return null;
};

// Helper function to get simplified status
export const getSimplifiedStatus = (
  queueDetails: GetTeamQueueItems_ResultSet1 | null
): SimplifiedStatus => {
  if (!queueDetails) return { status: 'unknown', color: 'neutral', icon: null };
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const retryCount = normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount');
  const lastFailureReason = normalizeToString(
    queueDetails,
    'lastFailureReason',
    'LastFailureReason'
  );

  // Check if this is a PENDING status after retry (it was failed and is being retried)
  if (status === 'PENDING' && retryCount > 0 && lastFailureReason) {
    // If we've reached max retries (2), show as failed instead of retrying
    if (retryCount >= 2) {
      return { status: 'Failed (Max Retries)', color: 'error', icon: <CloseCircleOutlined /> };
    }
    return { status: 'Retrying', color: 'warning', icon: <RetweetOutlined spin /> };
  }

  switch (status) {
    case 'COMPLETED':
      return { status: 'Completed', color: 'success', icon: <CheckCircleOutlined /> };
    case 'FAILED':
      return { status: 'Failed', color: 'error', icon: <CloseCircleOutlined /> };
    case 'CANCELLED':
      return { status: 'Cancelled', color: 'error', icon: <CloseCircleOutlined /> };
    case 'CANCELLING':
      return { status: 'Cancelling', color: 'warning', icon: <SyncOutlined spin /> };
    case 'PROCESSING':
      return { status: 'Processing', color: 'primary', icon: <SyncOutlined spin /> };
    case 'ASSIGNED':
      return { status: 'Assigned', color: 'primary', icon: <ClockCircleOutlined /> };
    default:
      return { status: status || 'Pending', color: 'neutral', icon: <ClockCircleOutlined /> };
  }
};

// Helper function to get task staleness level (progressive: none, early, stale, critical)
export const getTaskStaleness = (
  queueDetails: GetTeamQueueItems_ResultSet1 | null
): TaskStalenessLevel => {
  if (!queueDetails) return 'none';
  const lastAssigned =
    normalizeToString(queueDetails, 'lastAssigned', 'LastAssigned') ||
    normalizeToString(queueDetails, 'assignedTime', 'AssignedTime');
  const lastRetryAt = normalizeToString(queueDetails, 'lastRetryAt', 'LastRetryAt');
  const lastResponseAt = normalizeToString(queueDetails, 'lastResponseAt', 'LastResponseAt');
  const status = normalizeToString(queueDetails, 'status', 'Status');

  // Only check staleness for active processing tasks
  if (
    !lastAssigned ||
    status === 'COMPLETED' ||
    status === 'CANCELLED' ||
    status === 'CANCELLING' ||
    status === 'FAILED' ||
    status === 'PENDING'
  ) {
    return 'none';
  }

  // Find the most recent activity timestamp
  const timestamps = [lastAssigned, lastRetryAt, lastResponseAt].filter(Boolean);
  if (timestamps.length === 0) return 'none';

  // Use the most recent timestamp as the last activity time
  const lastActivityTime = timestamps.reduce((latest, current) => {
    return dayjs(current).isAfter(dayjs(latest)) ? current : latest;
  });

  const secondsSinceLastActivity = dayjs().diff(dayjs(lastActivityTime), 'second');

  // Progressive staleness levels
  if (secondsSinceLastActivity >= 120) return 'critical'; // 2+ minutes - strong cancellation recommendation
  if (secondsSinceLastActivity >= 90) return 'stale'; // 1.5+ minutes - stale with cancel option
  if (secondsSinceLastActivity >= 60) return 'early'; // 1+ minute - early warning
  return 'none';
};

// Legacy function for backward compatibility
export const isTaskStale = (queueDetails: GetTeamQueueItems_ResultSet1 | null): boolean => {
  const staleness = getTaskStaleness(queueDetails);
  return staleness === 'stale' || staleness === 'critical';
};

// Helper function to check if task is old pending (6+ hours)
export const isStalePending = (queueDetails: GetTeamQueueItems_ResultSet1 | null): boolean => {
  if (!queueDetails) return false;
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const healthStatus = normalizeToString(queueDetails, 'healthStatus', 'HealthStatus');
  const createdTime = normalizeToString(queueDetails, 'createdTime', 'CreatedTime');

  if (healthStatus === 'STALE_PENDING') return true;

  if (status !== 'PENDING' || !createdTime) return false;

  const hoursSinceCreated = dayjs().diff(dayjs(createdTime), 'hour');
  return hoursSinceCreated >= 6;
};

// Helper function to get priority color and icon
// Using grayscale system - only visual distinction through icons
export const getPriorityInfo = (priority: number | undefined): PriorityInfo => {
  if (!priority) return { color: 'neutral', icon: null, label: 'Normal' };

  switch (priority) {
    case 1:
      return { color: 'neutral', icon: <ThunderboltOutlined />, label: 'Highest' };
    case 2:
      return { color: 'neutral', icon: <RocketOutlined />, label: 'High' };
    case 3:
      return { color: 'neutral', icon: null, label: 'Normal' };
    case 4:
      return { color: 'neutral', icon: null, label: 'Low' };
    case 5:
      return { color: 'neutral', icon: null, label: 'Lowest' };
    default:
      return { color: 'neutral', icon: null, label: 'Normal' };
  }
};

// Get current step for Steps component (3 steps: Assigned, Processing, Completed)
export const getCurrentStep = (queueDetails: GetTeamQueueItems_ResultSet1 | null): number => {
  if (!queueDetails) return 0;
  const status = normalizeToString(queueDetails, 'status', 'Status');

  switch (status) {
    case 'COMPLETED':
      return 2;
    case 'FAILED':
    case 'CANCELLED':
      return -1;
    case 'CANCELLING':
      return 1; // Show as processing (with cancelling description)
    case 'PROCESSING':
      return 1;
    case 'ASSIGNED':
      return 0;
    default:
      return 0; // PENDING - will show as waiting for assignment
  }
};
