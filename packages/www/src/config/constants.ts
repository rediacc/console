/**
 * Application-wide constants
 */
import { PROTOCOL_DEFAULTS } from '@rediacc/shared/config/defaults';
import {
  WK_CLOUD_ORIGIN,
  WK_CONTACT_EMAIL,
  WK_GH_REPO,
} from '@rediacc/shared/config/well-known.generated';

/**
 * Primary contact email for Rediacc
 * Used across the website for forms, structured data, and contact information
 */
export const CONTACT_EMAIL = WK_CONTACT_EMAIL;

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
export const GITHUB_REPO = WK_GH_REPO;

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
  SCHEDULE_CONSULTATION: `${WK_CLOUD_ORIGIN}/apps/calendar/appointment/kqpjP6qdYT63`,
} as const;

/**
 * Local path to the account portal SPA.
 * On marketing hosts this path is intercepted by BaseLayout and opens the
 * region picker; on portal/on-prem hosts it navigates directly.
 */
export const ACCOUNT_PATH = '/account/';
