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

/**
 * Error severity levels for parsing queue errors
 */
export type ErrorSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO' | 'UNKNOWN'

/**
 * Parsed error information from queue output
 */
export interface ParsedError {
  severity: ErrorSeverity
  message: string
  fullLine: string
}

/**
 * Extract first error line from command output
 * Searches for lines with severity prefixes: CRITICAL:, ERROR:, WARNING:, INFO:
 *
 * @param output - Command output string to parse
 * @returns ParsedError object with severity and message, or null if no error found
 *
 * @example
 * const output = "Some output\nERROR: Repository not found\nMore output"
 * const error = extractFirstError(output)
 * // Returns: { severity: 'ERROR', message: 'Repository not found', fullLine: 'ERROR: Repository not found' }
 */
export function extractFirstError(output: string | null | undefined): ParsedError | null {
  if (!output) return null

  // Split into lines and search for first line with severity prefix
  const lines = output.split('\n')
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/

  for (const line of lines) {
    const trimmedLine = line.trim()
    const match = trimmedLine.match(severityPattern)

    if (match) {
      const [, severity, message] = match
      return {
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine
      }
    }
  }

  // If no severity prefix found, look for lines containing "error" or "failed" (case-insensitive)
  for (const line of lines) {
    const trimmedLine = line.trim()
    const lowerLine = trimmedLine.toLowerCase()

    if (lowerLine.includes('error') || lowerLine.includes('failed')) {
      return {
        severity: 'UNKNOWN',
        message: trimmedLine,
        fullLine: trimmedLine
      }
    }
  }

  return null
}

/**
 * Extract all severity-prefixed lines from command output
 * Searches for ALL lines with severity prefixes: CRITICAL:, ERROR:, WARNING:, INFO:
 *
 * @param output - Command output string to parse
 * @returns Array of ParsedError objects, empty array if none found
 *
 * @example
 * const output = "Some output\nERROR: Repository not found\nWARNING: Disk space low\nMore output"
 * const errors = extractAllErrors(output)
 * // Returns: [
 * //   { severity: 'ERROR', message: 'Repository not found', fullLine: 'ERROR: Repository not found' },
 * //   { severity: 'WARNING', message: 'Disk space low', fullLine: 'WARNING: Disk space low' }
 * // ]
 */
export function extractAllErrors(output: string | null | undefined): ParsedError[] {
  if (!output) return []

  const errors: ParsedError[] = []
  const lines = output.split('\n')
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/

  for (const line of lines) {
    const trimmedLine = line.trim()
    const match = trimmedLine.match(severityPattern)

    if (match) {
      const [, severity, message] = match
      errors.push({
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine
      })
    }
  }

  return errors
}

/**
 * Get color for error severity level
 * @param severity - Error severity level
 * @returns Ant Design color string
 */
export function getSeverityColor(severity: ErrorSeverity): string {
  switch (severity) {
    case 'CRITICAL':
      return 'red'
    case 'ERROR':
      return 'error'
    case 'WARNING':
      return 'warning'
    case 'INFO':
      return 'blue'
    case 'UNKNOWN':
      return 'default'
    default:
      return 'default'
  }
}

/**
 * Parsed error result with all errors and prioritization
 */
export interface ParsedErrorResult {
  /** All errors found in the text */
  allErrors: ParsedError[]
  /** The highest severity error (for display priority) */
  primaryError: ParsedError | null
}

/**
 * Parse failure reason text to extract all severity-prefixed errors
 * This is the consolidated parsing logic used across the application
 *
 * @param failureReason - Text containing error messages (e.g., from lastFailureReason)
 * @returns ParsedErrorResult with all errors and the primary (highest severity) error
 *
 * @example
 * const text = "ERROR: Repository not found\nWARNING: Disk space low"
 * const result = parseFailureReason(text)
 * // Returns:
 * // {
 * //   allErrors: [
 * //     { severity: 'ERROR', message: 'Repository not found', ... },
 * //     { severity: 'WARNING', message: 'Disk space low', ... }
 * //   ],
 * //   primaryError: { severity: 'ERROR', message: 'Repository not found', ... }
 * // }
 */
export function parseFailureReason(failureReason: string | null | undefined): ParsedErrorResult {
  if (!failureReason) {
    return { allErrors: [], primaryError: null }
  }

  const errors: ParsedError[] = []
  const lines = failureReason.split('\n')
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/

  // Extract all severity-prefixed lines
  for (const line of lines) {
    const trimmedLine = line.trim()
    const match = trimmedLine.match(severityPattern)

    if (match) {
      const [, severity, message] = match
      errors.push({
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine
      })
    }
  }

  // If no severity-prefixed errors found, treat entire message as single unknown error
  if (errors.length === 0 && failureReason.trim()) {
    errors.push({
      severity: 'UNKNOWN',
      message: failureReason.trim(),
      fullLine: failureReason.trim()
    })
  }

  // Find the highest severity error (CRITICAL > ERROR > WARNING > INFO > UNKNOWN)
  const primaryError = errors.length > 0 ? errors.reduce((highest, current) => {
    const severityOrder: Record<ErrorSeverity, number> = {
      CRITICAL: 0,
      ERROR: 1,
      WARNING: 2,
      INFO: 3,
      UNKNOWN: 4
    }
    const highestOrder = severityOrder[highest.severity]
    const currentOrder = severityOrder[current.severity]
    return currentOrder < highestOrder ? current : highest
  }) : null

  return { allErrors: errors, primaryError }
}
