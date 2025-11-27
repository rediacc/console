/**
 * Queue formatting utilities for CLI display
 * These use the same logic as the web console but adapted for terminal output
 */

import chalk from 'chalk'
import { parseFailureReason } from './errorParser.js'

/**
 * Format age in minutes to human-readable string
 * Same logic as web console's formatAge function
 *
 * @param minutes - Age in minutes
 * @returns Formatted string like "2h 30m" or "1d 5h"
 *
 * @example
 * formatAge(150) // "2h 30m"
 * formatAge(45) // "45m"
 * formatAge(2000) // "1d 9h"
 */
export function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
  return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`
}

/**
 * Get chalk color function for queue status
 * Maps queue health status to appropriate colors
 *
 * @param status - Queue status (PENDING, COMPLETED, FAILED, etc.)
 * @returns Chalk color function
 */
export function getStatusColor(status: string): (text: string) => string {
  const statusUpper = status.toUpperCase()

  switch (statusUpper) {
    case 'COMPLETED':
      return chalk.green
    case 'FAILED':
      return chalk.red
    case 'CANCELLED':
      return chalk.red
    case 'PROCESSING':
    case 'ASSIGNED':
    case 'ACTIVE':
      return chalk.blue
    case 'CANCELLING':
    case 'STALE':
    case 'STALE_PENDING':
      return chalk.yellow
    case 'PENDING':
      return chalk.gray
    default:
      return chalk.white
  }
}

/**
 * Format status with color for CLI display
 *
 * @param status - Queue status string
 * @returns Colored status string
 */
export function formatStatus(status: string | undefined): string {
  if (!status) return chalk.gray('UNKNOWN')

  const colorFn = getStatusColor(status)
  return colorFn(status)
}

/**
 * Format priority with color and label
 * Same priority levels as web console (1=highest, 5=lowest)
 *
 * @param priority - Priority number (1-5)
 * @returns Colored priority string with label
 *
 * @example
 * formatPriority(1) // Red "P1 (Highest)"
 * formatPriority(3) // Blue "P3 (Normal)"
 */
export function formatPriority(priority: number | undefined): string {
  if (!priority) return chalk.gray('-')

  const priorityMap: Record<number, { color: (text: string) => string; label: string }> = {
    1: { color: chalk.red.bold, label: 'P1 (Highest)' },
    2: { color: chalk.yellow, label: 'P2 (High)' },
    3: { color: chalk.blue, label: 'P3 (Normal)' },
    4: { color: chalk.cyan, label: 'P4 (Low)' },
    5: { color: chalk.gray, label: 'P5 (Lowest)' }
  }

  const config = priorityMap[priority] || priorityMap[3]
  return config.color(config.label)
}

/**
 * Get chalk color function for error severity
 *
 * @param severity - Error severity level
 * @returns Chalk color function
 */
export function getSeverityColor(severity: string): (text: string) => string {
  switch (severity) {
    case 'CRITICAL':
      return chalk.red.bold
    case 'ERROR':
      return chalk.red
    case 'WARNING':
      return chalk.yellow
    case 'INFO':
      return chalk.blue
    case 'UNKNOWN':
    default:
      return chalk.gray
  }
}

/**
 * Format error message with severity badge
 * Parses lastFailureReason and highlights severity levels
 *
 * @param failureReason - Raw failure reason text
 * @param showAll - Whether to show all errors or just primary (default: false)
 * @returns Formatted error string with colored severity badges
 *
 * @example
 * formatError("ERROR: Repository not found")
 * // Returns: [ERROR] Repository not found (in red)
 *
 * formatError("ERROR: Repo not found\nWARNING: Disk space low")
 * // Returns: [ERROR] Repo not found (+1 more)
 *
 * formatError("ERROR: Repo not found\nWARNING: Disk space low", true)
 * // Returns: [ERROR] Repo not found\n[WARNING] Disk space low
 */
export function formatError(failureReason: string | undefined, showAll: boolean = false): string {
  if (!failureReason) return chalk.gray('No errors')

  const { primaryError, allErrors } = parseFailureReason(failureReason)

  if (!primaryError) {
    // No severity prefix found, return original message
    return failureReason
  }

  if (showAll && allErrors.length > 1) {
    // Show all errors
    return allErrors
      .map(error => {
        const colorFn = getSeverityColor(error.severity)
        const badge = `[${error.severity}]`
        return `${colorFn(badge)} ${error.message}`
      })
      .join('\n')
  }

  // Show primary error only
  const colorFn = getSeverityColor(primaryError.severity)
  const badge = `[${primaryError.severity}]`
  const message = primaryError.message

  if (allErrors.length > 1) {
    return `${colorFn(badge)} ${message} ${chalk.dim(`(+${allErrors.length - 1} more)`)}`
  }

  return `${colorFn(badge)} ${message}`
}

/**
 * Format retry count with color
 * Green for 0, yellow for 1, red for 2+
 *
 * @param retryCount - Number of retries
 * @returns Colored retry count string
 */
export function formatRetryCount(retryCount: number | undefined): string {
  if (retryCount === undefined || retryCount === null) return chalk.gray('-')

  if (retryCount === 0) return chalk.green(`${retryCount}/2`)
  if (retryCount === 1) return chalk.yellow(`${retryCount}/2`)
  return chalk.red.bold(`${retryCount}/2`)
}

/**
 * Format boolean value with colored checkmark/cross
 *
 * @param value - Boolean value
 * @returns Colored checkmark or cross
 */
export function formatBoolean(value: boolean | undefined): string {
  if (value === undefined || value === null) return chalk.gray('-')
  return value ? chalk.green('✓') : chalk.red('✗')
}
