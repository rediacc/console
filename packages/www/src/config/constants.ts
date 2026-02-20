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
 * Legal company details for mandatory website disclosures in Estonia.
 */
export const COMPANY_LEGAL_NAME = 'Rediacc OÜ';
export const COMPANY_REGISTRY_CODE = '17363830';
export const COMPANY_REGISTER_NAME = 'Estonian Commercial Register (Äriregister)';
export const COMPANY_VAT_NUMBER = 'EE102920091';
export const COMPANY_REGISTERED_ADDRESS =
  'Tartu mnt 67/1-13b, 10115 Tallinn, Harju county, Estonia';

/**
 * GitHub repository path for fetching releases
 */
export const GITHUB_REPO = 'rediacc/console';

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
 * Stripe integration configuration
 * Populated via Vite env vars at build time:
 * - PR previews: sandbox keys + per-PR www worker
 * - Production: live keys + www.rediacc.com
 * ACCOUNT_SERVER_URL is same-origin: www worker proxies /account/api/* to account-server
 */
export const STRIPE_CONFIG = {
  PUBLISHABLE_KEY: import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY ?? '',
  ACCOUNT_SERVER_URL: '/account',
} as const;

/**
 * Get the console URL
 * Always returns '/console' to ensure consistent behavior across all environments
 * and to avoid language prefix interference (e.g., /en/console)
 */
export function getConsoleUrl(_origin?: string): string {
  return '/console';
}
