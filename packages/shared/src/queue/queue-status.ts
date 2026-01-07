import type { QueueHealthStatus, QueueStatus } from '../types';

/**
 * Status configuration for display
 */
export interface StatusConfig {
  label?: string;
}

/**
 * Status configuration map for queue health statuses
 */
export const QUEUE_STATUS_CONFIG: Record<QueueHealthStatus, StatusConfig> = {
  PENDING: {},
  ACTIVE: {},
  STALE: {},
  STALE_PENDING: {},
  CANCELLING: {},
  COMPLETED: {},
  FAILED: {},
  CANCELLED: {},
  UNKNOWN: {},
};

/**
 * Priority configuration
 */
export interface PriorityConfig {
  timeout?: string;
  label: string;
  color: string;
}

/**
 * Priority configuration map (1-5 scale)
 */
export const PRIORITY_CONFIG: Partial<Record<number, PriorityConfig>> = {
  1: { timeout: '33s', label: 'Highest', color: 'red' },
  2: { timeout: 'Tier timeout', label: 'High', color: 'orange' },
  3: { timeout: 'Tier timeout', label: 'Normal', color: 'blue' },
  4: { timeout: 'Tier timeout', label: 'Low', color: 'gray' },
  5: { timeout: 'Tier timeout', label: 'Lowest', color: 'default' },
};

/**
 * Get priority label for display
 */
export function getPriorityLabel(priority: number): string {
  return PRIORITY_CONFIG[priority]?.label ?? 'Unknown';
}

/**
 * Get priority color for styling
 */
export function getPriorityColor(priority: number): string {
  return PRIORITY_CONFIG[priority]?.color ?? 'default';
}

/**
 * Stale task detection constants
 */
export const STALE_TASK_CONSTANTS = {
  /** Check interval in milliseconds (5 seconds) */
  CHECK_INTERVAL_MS: 5000,
  /** Threshold for considering a task stale (24 hours) */
  STALE_TASK_THRESHOLD_MS: 24 * 60 * 60 * 1000,
  /** Minutes without progress to consider processing task stale */
  STALE_PROCESSING_MINUTES: 5,
  /** Maximum retry attempts */
  MAX_RETRY_COUNT: 3,
};

/**
 * Terminal statuses that indicate a task has finished
 */
export const TERMINAL_STATUSES: QueueStatus[] = ['COMPLETED', 'CANCELLED', 'FAILED'] as const;

/**
 * Active statuses that indicate a task is still running
 */
export const ACTIVE_STATUSES: QueueStatus[] = ['PENDING', 'ASSIGNED', 'PROCESSING'] as const;

/**
 * Permanent failure message patterns
 */
export const PERMANENT_FAILURE_MESSAGES = [
  'Bridge reported failure',
  'Task permanently failed',
  'Fatal error',
] as const;

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.includes(status as QueueStatus);
}

export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.includes(status as QueueStatus);
}

export function isPermanentFailure(failureReason: string | undefined | null): boolean {
  if (!failureReason) return false;
  return PERMANENT_FAILURE_MESSAGES.some((msg) => failureReason.includes(msg));
}

export function getStatusConfig(status: QueueHealthStatus): StatusConfig {
  return QUEUE_STATUS_CONFIG[status];
}

const DEFAULT_PRIORITY_CONFIG: PriorityConfig = {
  timeout: 'Tier timeout',
  label: 'Normal',
  color: 'blue',
};

export function getPriorityConfig(priority: number): PriorityConfig {
  return PRIORITY_CONFIG[priority] ?? DEFAULT_PRIORITY_CONFIG;
}

export function isRetryEligible(retryCount: number, lastFailureReason?: string): boolean {
  if (retryCount >= STALE_TASK_CONSTANTS.MAX_RETRY_COUNT) {
    return false;
  }

  if (isPermanentFailure(lastFailureReason)) {
    return false;
  }

  return true;
}

export function isStaleTask(minutesSinceAssigned: number): boolean {
  return minutesSinceAssigned > STALE_TASK_CONSTANTS.STALE_PROCESSING_MINUTES;
}

export function filterActiveItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter((item) => !TERMINAL_STATUSES.includes(item.healthStatus as QueueStatus));
}

export function filterCompletedItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter((item) => item.healthStatus === 'COMPLETED');
}

export function filterFailedItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter((item) => item.healthStatus === 'FAILED');
}

export function filterCancelledItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter((item) => item.healthStatus === 'CANCELLED');
}

export type { QueueHealthStatus, QueueStatus } from '../types';
