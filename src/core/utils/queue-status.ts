/**
 * Core utilities for queue status handling
 * These utilities are framework-agnostic and can be used in both React and CLI
 */

/**
 * Queue health status types
 */
export type QueueHealthStatus =
  | 'PENDING'
  | 'ACTIVE'
  | 'STALE'
  | 'STALE_PENDING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'UNKNOWN'

/**
 * Queue status types (lower level)
 */
export type QueueStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'FAILED'

/**
 * Status configuration for display
 */
export interface StatusConfig {
  color: string
  label?: string
}

/**
 * Status configuration map for queue health statuses
 */
export const QUEUE_STATUS_CONFIG: Record<QueueHealthStatus, StatusConfig> = {
  'PENDING': { color: 'default' },
  'ACTIVE': { color: 'processing' },
  'STALE': { color: 'warning' },
  'STALE_PENDING': { color: 'orange' },
  'CANCELLING': { color: 'warning' },
  'COMPLETED': { color: 'success' },
  'FAILED': { color: 'error' },
  'CANCELLED': { color: 'error' },
  'UNKNOWN': { color: 'default' }
}

/**
 * Priority configuration
 */
export interface PriorityConfig {
  color: string
  timeout?: string
}

/**
 * Priority configuration map (1-5 scale)
 */
export const PRIORITY_CONFIG: Record<number, PriorityConfig> = {
  1: { color: 'red', timeout: '33s' },
  2: { color: 'orange', timeout: 'Tier timeout' },
  3: { color: 'gold', timeout: 'Tier timeout' },
  4: { color: 'blue', timeout: 'Tier timeout' },
  5: { color: 'green', timeout: 'Tier timeout' }
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
  MAX_RETRY_COUNT: 3
}

/**
 * Terminal statuses that indicate a task has finished
 */
export const TERMINAL_STATUSES: QueueStatus[] = ['COMPLETED', 'CANCELLED', 'FAILED']

/**
 * Active statuses that indicate a task is still running
 */
export const ACTIVE_STATUSES: QueueStatus[] = ['PENDING', 'ASSIGNED', 'PROCESSING']

/**
 * Permanent failure message patterns
 */
export const PERMANENT_FAILURE_MESSAGES = [
  'Bridge reported failure',
  'Task permanently failed',
  'Fatal error'
]

/**
 * Check if a status is a terminal status
 * @param status - Queue status to check
 * @returns True if the status is terminal
 */
export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.includes(status as QueueStatus)
}

/**
 * Check if a status is an active status
 * @param status - Queue status to check
 * @returns True if the status is active
 */
export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.includes(status as QueueStatus)
}

/**
 * Check if a failure reason indicates a permanent failure
 * @param failureReason - The failure reason string
 * @returns True if the failure is permanent
 */
export function isPermanentFailure(failureReason: string | undefined | null): boolean {
  if (!failureReason) return false

  return PERMANENT_FAILURE_MESSAGES.some(msg => failureReason.includes(msg))
}

/**
 * Get status configuration for a queue health status
 * @param status - Queue health status
 * @returns Status configuration
 */
export function getStatusConfig(status: QueueHealthStatus): StatusConfig {
  return QUEUE_STATUS_CONFIG[status] || QUEUE_STATUS_CONFIG.UNKNOWN
}

/**
 * Get priority configuration
 * @param priority - Priority level (1-5)
 * @returns Priority configuration
 */
export function getPriorityConfig(priority: number): PriorityConfig {
  return PRIORITY_CONFIG[priority] || PRIORITY_CONFIG[3]
}

/**
 * Check if a task should be retried based on retry count and failure reason
 * @param retryCount - Current retry count
 * @param lastFailureReason - Last failure reason
 * @returns True if the task can be retried
 */
export function isRetryEligible(retryCount: number, lastFailureReason?: string): boolean {
  // Don't retry if max retries reached
  if (retryCount >= STALE_TASK_CONSTANTS.MAX_RETRY_COUNT) {
    return false
  }

  // Don't retry permanent failures
  if (isPermanentFailure(lastFailureReason)) {
    return false
  }

  return true
}

/**
 * Check if a task is stale based on processing time
 * @param minutesSinceAssigned - Minutes since the task was assigned
 * @returns True if the task is stale
 */
export function isStaleTask(minutesSinceAssigned: number): boolean {
  return minutesSinceAssigned > STALE_TASK_CONSTANTS.STALE_PROCESSING_MINUTES
}

/**
 * Format age in minutes to human-readable string
 * @param minutes - Age in minutes
 * @returns Formatted age string (e.g., "2h 30m", "1d 5h")
 */
export function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
  return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`
}

/**
 * Filter active queue items (not terminal)
 * @param items - Array of queue items with healthStatus property
 * @returns Filtered array of active items
 */
export function filterActiveItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter(item => !TERMINAL_STATUSES.includes(item.healthStatus as QueueStatus))
}

/**
 * Filter completed queue items
 * @param items - Array of queue items with healthStatus property
 * @returns Filtered array of completed items
 */
export function filterCompletedItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter(item => item.healthStatus === 'COMPLETED')
}

/**
 * Filter failed queue items
 * @param items - Array of queue items with healthStatus property
 * @returns Filtered array of failed items
 */
export function filterFailedItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter(item => item.healthStatus === 'FAILED')
}

/**
 * Filter cancelled queue items
 * @param items - Array of queue items with healthStatus property
 * @returns Filtered array of cancelled items
 */
export function filterCancelledItems<T extends { healthStatus: string }>(items: T[]): T[] {
  return items.filter(item => item.healthStatus === 'CANCELLED')
}
