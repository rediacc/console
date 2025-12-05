/**
 * Core utility functions for handling time and timezone conversions
 * These utilities are framework-agnostic and can be used in both React and CLI
 */

/**
 * Calculate relative time from a timestamp, assuming the timestamp is in UTC
 * @param timestamp - ISO 8601 timestamp string (assumed to be UTC if no timezone specified)
 * @returns Relative time string (e.g., "2 minutes ago", "1 hour ago")
 */
export function getRelativeTimeFromUTC(timestamp: string | null | undefined): string {
  if (!timestamp) return '-';

  // Parse the timestamp as-is without forcing timezone conversion
  const date: Date = new Date(timestamp);

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffSeconds < 60) {
    return 'just now';
  } else if (diffMinutes === 1) {
    return '1 minute ago';
  } else if (diffMinutes < 60) {
    return `${diffMinutes} minutes ago`;
  } else if (diffHours === 1) {
    return '1 hour ago';
  } else if (diffHours < 24) {
    return `${diffHours} hours ago`;
  } else if (diffDays === 1) {
    return '1 day ago';
  } else if (diffDays < 30) {
    return `${diffDays} days ago`;
  } else {
    // For older dates, show the actual date
    return date.toLocaleDateString();
  }
}

/**
 * Get localized relative time with i18n support
 * @param timestamp - ISO 8601 timestamp string
 * @param t - i18n translation function
 * @returns Localized relative time string
 */
export function getLocalizedRelativeTime(
  timestamp: string | null | undefined,
  t: (key: string, options?: Record<string, unknown>) => string
): string {
  if (!timestamp) return '-';

  // Parse the timestamp as-is without forcing timezone conversion
  const date: Date = new Date(timestamp);

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) {
    return t('machines:justNow');
  } else if (diffMinutes < 60) {
    return t('machines:minutesAgo', { count: diffMinutes });
  } else if (diffHours < 24) {
    return t('machines:hoursAgo', { count: diffHours });
  } else if (diffDays < 30) {
    return t('machines:daysAgo', { count: diffDays });
  } else {
    return date.toLocaleDateString();
  }
}

/**
 * Format a timestamp to local date/time string
 * @param timestamp - ISO 8601 timestamp string
 * @returns Formatted local date/time string
 */
export function formatTimestamp(timestamp: string | null | undefined): string {
  if (!timestamp) return '-';

  // Use the formatTimestampAsIs function to avoid timezone conversion
  return formatTimestampAsIs(timestamp, 'datetime');
}

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
 * Calculate duration between two timestamps
 * @param start - Start timestamp
 * @param end - End timestamp
 * @returns Duration in milliseconds
 */
export function calculateDuration(
  start: string | null | undefined,
  end: string | null | undefined
): number {
  if (!start || !end) return 0;

  const startDate = new Date(start);
  const endDate = new Date(end);

  return endDate.getTime() - startDate.getTime();
}

/**
 * Format duration in human-readable format
 * @param ms - Duration in milliseconds
 * @returns Formatted duration string (e.g., "2h 30m 15s")
 */
export function formatDuration(ms: number): string {
  if (ms <= 0) return '0s';

  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const parts: string[] = [];

  if (days > 0) parts.push(`${days}d`);
  if (hours % 24 > 0) parts.push(`${hours % 24}h`);
  if (minutes % 60 > 0) parts.push(`${minutes % 60}m`);
  if (seconds % 60 > 0 || parts.length === 0) parts.push(`${seconds % 60}s`);

  return parts.join(' ');
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
