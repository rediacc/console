/**
 * Application-wide constants
 */
import { PROTOCOL_DEFAULTS } from '@rediacc/shared/config/defaults';
import {
  WK_CLOUD_ORIGIN,
  WK_CONTACT_EMAIL,
  WK_GH_REPO,
} from '@rediacc/shared/config/well-known.generated';
import { LEGAL_ENTITY } from '@rediacc/shared/legal/entity.generated';

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
 * The registered address for mandatory website disclosures in Estonia, with the country named in English.
 * Every other legal company detail is read straight from `LEGAL_ENTITY` (@rediacc/shared/legal/entity.generated),
 * which `./run.sh legal-entity sync` projects from the vault.
 */
export const COMPANY_REGISTERED_ADDRESS = `${LEGAL_ENTITY.registeredAddress}, ${
  new Intl.DisplayNames(['en'], { type: 'region' }).of(LEGAL_ENTITY.countryCode) ??
  LEGAL_ENTITY.countryCode
}`;

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
