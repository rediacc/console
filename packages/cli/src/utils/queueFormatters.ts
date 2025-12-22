/**
 * Queue formatting utilities for CLI display
 * These use the same logic as the web console but adapted for terminal output
 */

import chalk from 'chalk';
import type { ErrorSeverity } from '@rediacc/shared/error-parser';
import {
  formatError as formatErrorShared,
  formatErrors,
  getSeverityLevel,
  parseFailureReason,
} from '@rediacc/shared/error-parser';
import { STALE_TASK_CONSTANTS } from '@rediacc/shared/queue';

// Re-export formatAge for backwards compatibility
export { formatAge } from '@rediacc/shared/formatters';

/**
 * Get chalk color function for queue status
 * Maps queue health status to appropriate colors
 *
 * @param status - Queue status (PENDING, COMPLETED, FAILED, etc.)
 * @returns Chalk color function
 */
export function getStatusColor(status: string): (text: string) => string {
  const statusUpper = status.toUpperCase();

  switch (statusUpper) {
    case 'COMPLETED':
      return chalk.green;
    case 'FAILED':
      return chalk.red;
    case 'CANCELLED':
      return chalk.red;
    case 'PROCESSING':
    case 'ASSIGNED':
    case 'ACTIVE':
      return chalk.blue;
    case 'CANCELLING':
    case 'STALE':
    case 'STALE_PENDING':
      return chalk.yellow;
    case 'PENDING':
      return chalk.gray;
    default:
      return chalk.white;
  }
}

/**
 * Format status with color for CLI display
 *
 * @param status - Queue status string
 * @returns Colored status string
 */
export function formatStatus(status: string | undefined): string {
  if (!status) return chalk.gray('UNKNOWN');

  const colorFn = getStatusColor(status);
  return colorFn(status);
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
  if (!priority) return chalk.gray('-');

  const priorityMap: Record<number, { color: (text: string) => string; label: string }> = {
    1: { color: chalk.red.bold, label: 'P1 (Highest)' },
    2: { color: chalk.yellow, label: 'P2 (High)' },
    3: { color: chalk.blue, label: 'P3 (Normal)' },
    4: { color: chalk.cyan, label: 'P4 (Low)' },
    5: { color: chalk.gray, label: 'P5 (Lowest)' },
  };

  const config = priorityMap[priority] || priorityMap[3];
  return config.color(config.label);
}

/**
 * Chalk color adapter function for error formatting
 * Maps generic severity levels to chalk colors
 *
 * @param text - Text to color
 * @param level - Generic level string ('critical', 'error', 'warning', 'info', 'default')
 * @returns Colored text
 */
function chalkColorFn(text: string, level: string): string {
  const colorMap: Record<string, string> = {
    critical: chalk.red.bold(text),
    error: chalk.red(text),
    warning: chalk.yellow(text),
    info: chalk.blue(text),
    default: chalk.gray(text),
  };
  return colorMap[level] || chalk.gray(text);
}

/**
 * Get chalk color function for error severity
 * Uses shared getSeverityLevel for consistency
 *
 * @param severity - Error severity level
 * @returns Chalk color function
 */
export function getSeverityColor(severity: ErrorSeverity): (text: string) => string {
  const level = getSeverityLevel(severity);
  const colorMap: Record<string, (text: string) => string> = {
    critical: chalk.red.bold,
    error: chalk.red,
    warning: chalk.yellow,
    info: chalk.blue,
    default: chalk.gray,
  };
  return colorMap[level] || chalk.gray;
}

/**
 * Format error message with severity badge
 * Uses shared error parsing and formatting logic with chalk colors
 *
 * @param failureReason - Raw failure reason text
 * @param showAll - Whether to show all errors or just primary (default: false)
 * @returns Formatted error string with colored severity badges
 *
 * @example
 * formatError("ERROR: Repository not found")
 * // Returns: [ERROR] Repository not found (in red)
 *
 * formatError("ERROR: Repository not found\nWARNING: Disk space low")
 * // Returns: [ERROR] Repository not found (+1 more)
 *
 * formatError("ERROR: Repository not found\nWARNING: Disk space low", true)
 * // Returns: [ERROR] Repository not found\n[WARNING] Disk space low
 */
export function formatError(failureReason: string | undefined, showAll: boolean = false): string {
  if (!failureReason) return chalk.gray('No errors');

  const result = parseFailureReason(failureReason);

  if (!result.primaryError) {
    // No severity prefix found, return original message
    return failureReason;
  }

  if (showAll && result.allErrors.length > 1) {
    // Use shared formatErrors with chalk color function
    return formatErrors(result, { showAll: true, colorFn: chalkColorFn });
  }

  // Show primary error only with count indicator
  const formatted = formatErrorShared(result.primaryError, chalkColorFn);

  if (result.allErrors.length > 1) {
    return `${formatted} ${chalk.dim(`(+${result.allErrors.length - 1} more)`)}`;
  }

  return formatted;
}

/**
 * Format retry count with color
 * Green for 0, yellow for 1-2, red for 3+
 *
 * @param retryCount - Number of retries
 * @returns Colored retry count string
 */
export function formatRetryCount(retryCount: number | undefined): string {
  if (retryCount === undefined || retryCount === null) return chalk.gray('-');

  if (retryCount === 0) return chalk.green(`${retryCount}/${STALE_TASK_CONSTANTS.MAX_RETRY_COUNT}`);
  if (retryCount < STALE_TASK_CONSTANTS.MAX_RETRY_COUNT - 1)
    return chalk.yellow(`${retryCount}/${STALE_TASK_CONSTANTS.MAX_RETRY_COUNT}`);
  return chalk.red.bold(`${retryCount}/${STALE_TASK_CONSTANTS.MAX_RETRY_COUNT}`);
}

/**
 * Format boolean value with colored checkmark/cross
 *
 * @param value - Boolean value
 * @returns Colored checkmark or cross
 */
export function formatBoolean(value: boolean | undefined): string {
  if (value === undefined || value === null) return chalk.gray('-');
  return value ? chalk.green('✓') : chalk.red('✗');
}
