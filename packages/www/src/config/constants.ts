/**
 * Application-wide constants
 */
import { PROTOCOL_DEFAULTS } from '@rediacc/shared/config/defaults';

/**
 * Primary contact email for Rediacc
 * Used across the website for forms, structured data, and contact information
 */
export const CONTACT_EMAIL = 'contact@rediacc.com';

/**
 * Primary site URL
 * Used as fallback for RSS feeds and other canonical URL references
 */
export const SITE_URL = import.meta.env.PUBLIC_SITE_URL ?? PROTOCOL_DEFAULTS.SITE_URL;

/**
 * Legal company details for mandatory website disclosures in Estonia.
 */
export const COMPANY_LEGAL_NAME = 'Rediacc OÜ';
export const COMPANY_REGISTRY_CODE = '17363830';
export const COMPANY_REGISTER_NAME = 'Estonian Commercial Register (Äriregister)';
export const COMPANY_VAT_NUMBER = 'EE102920091';
export const COMPANY_REGISTERED_ADDRESS =
  'Harju maakond, Tallinn, Kesklinna linnaosa, Tartu mnt 67/1-13b, 10115, Estonia';

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
 * Default account origin for the primary region (EU).
 * The marketing site links and proxies target this origin.
 */
export const DEFAULT_ACCOUNT_ORIGIN = 'https://eu.rediacc.com';

/**
 * Local path to the account portal SPA.
 * On marketing hosts this path is intercepted by BaseLayout and opens the
 * region picker; on portal/on-prem hosts it navigates directly.
 */
export const ACCOUNT_PATH = '/account/';

/**
 * Get the account URL.
 * Returns the EU account portal URL. Users can switch regions from the portal.
 */
export function getAccountUrl(_origin?: string): string {
  return `${DEFAULT_ACCOUNT_ORIGIN}${ACCOUNT_PATH}`;
}
