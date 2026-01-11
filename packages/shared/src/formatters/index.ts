/**
 * Shared formatting utilities for Rediacc Console
 * Platform-agnostic functions that work in both web and CLI environments
 */

/**
 * Format age in minutes to human-readable string
 *
 * @param minutes - Age in minutes
 * @returns Formatted age string (e.g., "2h 30m", "1d 5h")
 *
 * @example
 * formatAge(45)      // Returns: "45m"
 * formatAge(150)     // Returns: "2h 30m"
 * formatAge(1500)    // Returns: "1d 1h"
 */
export function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}

/**
 * Format a property key to human-readable header text
 * Converts camelCase/snake_case to Title Case
 *
 * @param key - Property key string
 * @returns Formatted header string
 *
 * @example
 * formatPropertyName('taskId')      // Returns: "Task Id"
 * formatPropertyName('createdAt')   // Returns: "Created At"
 * formatPropertyName('user_name')   // Returns: "User Name"
 */
export function formatPropertyName(key: string): string {
  return key
    .replaceAll(/([A-Z])/g, ' $1')
    .replaceAll('_', ' ')
    .replace(/^\s+/, '')
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Format a timestamp without timezone conversion - displays the time as-is
 *
 * @param timestamp - ISO 8601 timestamp string
 * @param format - 'time' for HH:mm:ss, 'datetime' for YYYY-MM-DD HH:mm:ss, 'full' for complete datetime
 * @returns Formatted timestamp string without timezone conversion
 */
export function formatTimestampAsIs(
  timestamp: string | null | undefined,
  format: 'time' | 'datetime' | 'full' = 'datetime'
): string {
  if (!timestamp) return '-';

  // Extract date/time components directly from the ISO string
  // Expected formats: "2024-01-15T14:30:45.123Z" or "2024-01-15T14:30:45" or "2024-01-15 14:30:45"

  // For timestamps in "YYYY-MM-DD HH:mm:ss.fff" or "YYYY-MM-DD HH:mm:ss" format
  const match = /(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})/.exec(timestamp);

  if (!match) {
    // If the format doesn't match, return the original timestamp
    return timestamp;
  }

  const [, year, month, day, hours, minutes, seconds] = match;

  switch (format) {
    case 'time':
      return `${hours}:${minutes}:${seconds}`;
    case 'datetime':
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    case 'full': {
      // Include milliseconds if present
      const msMatch = /\.\d{3}/.exec(timestamp);
      const ms = msMatch ? msMatch[0] : '';
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}${ms}`;
    }
    default:
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  }
}

/**
 * Format duration in full text format for display
 *
 * @param seconds - Duration in seconds
 * @returns Formatted duration string with full words (e.g., "2 minutes", "45 seconds")
 */
export function formatDurationFull(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} second${seconds === 1 ? '' : 's'}`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}

/**
 * Format a value for display (handles null, undefined, objects)
 *
 * @param value - Value to format
 * @returns String representation of the value
 */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}
