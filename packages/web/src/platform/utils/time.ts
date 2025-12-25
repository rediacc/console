/**
 * Core utility functions for handling time and timezone conversions
 * These utilities are framework-agnostic and can be used in both React and CLI
 */

/**
 * Format a timestamp without timezone conversion - displays the time as-is
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
  const match = timestamp.match(/(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})/);

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
      const msMatch = timestamp.match(/\.\d{3}/);
      const ms = msMatch ? msMatch[0] : '';
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}${ms}`;
    }
    default:
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  }
}

/**
 * Format duration in full text format for display
 * @param seconds - Duration in seconds
 * @returns Formatted duration string with full words (e.g., "2 minutes", "45 seconds")
 */
export function formatDurationFull(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} second${seconds !== 1 ? 's' : ''}`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
}
