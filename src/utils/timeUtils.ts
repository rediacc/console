/**
 * Utility functions for handling time and timezone conversions
 */

/**
 * Calculate relative time from a timestamp, assuming the timestamp is in UTC
 * @param timestamp - ISO 8601 timestamp string (assumed to be UTC if no timezone specified)
 * @returns Relative time string (e.g., "2 minutes ago", "1 hour ago")
 */
export function getRelativeTimeFromUTC(timestamp: string | null | undefined): string {
  if (!timestamp) return '-';
  
  // Parse the timestamp and ensure it's treated as UTC if no timezone is specified
  let date: Date;
  if (timestamp.endsWith('Z') || timestamp.includes('+') || timestamp.includes('-')) {
    // Timestamp already has timezone information
    date = new Date(timestamp);
  } else {
    // Assume UTC if no timezone specified
    date = new Date(timestamp + 'Z');
  }
  
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
  t: (key: string, options?: any) => string
): string {
  if (!timestamp) return '-';
  
  // Parse the timestamp and ensure it's treated as UTC if no timezone is specified
  let date: Date;
  if (timestamp.endsWith('Z') || timestamp.includes('+') || timestamp.includes('-')) {
    // Timestamp already has timezone information
    date = new Date(timestamp);
  } else {
    // Assume UTC if no timezone specified
    date = new Date(timestamp + 'Z');
  }
  
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
  
  // Parse the timestamp and ensure it's treated as UTC if no timezone is specified
  let date: Date;
  if (timestamp.endsWith('Z') || timestamp.includes('+') || timestamp.includes('-')) {
    // Timestamp already has timezone information
    date = new Date(timestamp);
  } else {
    // Assume UTC if no timezone specified
    date = new Date(timestamp + 'Z');
  }
  
  return date.toLocaleString();
}