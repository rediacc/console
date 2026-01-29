/**
 * Application-wide constants
 */

/**
 * Primary contact email for Rediacc
 * Used across the website for forms, structured data, and contact information
 */
export const CONTACT_EMAIL = 'contact@rediacc.com';

/**
 * Primary site URL
 * Used as fallback for RSS feeds and other canonical URL references
 */
export const SITE_URL = 'https://www.rediacc.com';

/**
 * External Links
 * Centralized configuration for important external URLs
 */
export const EXTERNAL_LINKS = {
  /**
   * Schedule Consultation - Outlook Booking Page
   * Used for high-intent CTAs (pricing, solutions, sales contact)
   * Update this URL when changing scheduling platforms
   */
  SCHEDULE_CONSULTATION: 'https://cloud.rediacc.io/apps/calendar/appointment/kqpjP6qdYT63',
} as const;

/**
 * Get the console URL
 * Always returns '/console' to ensure consistent behavior across all environments
 * and to avoid language prefix interference (e.g., /en/console)
 */
export function getConsoleUrl(_origin?: string): string {
  return '/console';
}
