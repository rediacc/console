/**
 * Custom i18next Cookie Detector
 *
 * Manages language preference in a shared cookie across www.rediacc.com and console.rediacc.com
 */

import type { CustomDetector } from 'i18next-browser-languagedetector';

const COOKIE_NAME = 'rediacc_lang';
const COOKIE_DOMAIN = '.rediacc.com';
const COOKIE_MAX_AGE = 31536000; // 1 year in seconds

/**
 * Get language from cookie
 */
function getCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [cookieName, value] = cookie.trim().split('=');
    if (cookieName === name) {
      return decodeURIComponent(value);
    }
  }
  return null;
}

/**
 * Set cookie with proper domain configuration for cross-subdomain access
 */
function setCookie(name: string, value: string): void {
  if (typeof document === 'undefined') {
    return;
  }

  // Determine if we're in local development
  const isLocalhost =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1' ||
      window.location.hostname.startsWith('192.168.') ||
      window.location.hostname.startsWith('10.') ||
      window.location.hostname.endsWith('.local'));

  let cookieString = `${name}=${encodeURIComponent(value)}`;
  cookieString += `; path=/`;
  cookieString += `; max-age=${COOKIE_MAX_AGE}`;
  cookieString += `; samesite=Lax`;

  // Only set domain for production (not localhost)
  if (!isLocalhost) {
    cookieString += `; domain=${COOKIE_DOMAIN}`;
  }

  // Only set secure flag on HTTPS
  if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
    cookieString += `; secure`;
  }

  document.cookie = cookieString;
}

/**
 * Custom i18next detector for cookie-based language storage
 */
export const cookieDetector: CustomDetector = {
  name: 'cookieDetector',

  lookup(): string | undefined {
    const value = getCookie(COOKIE_NAME);
    return value ?? undefined;
  },

  cacheUserLanguage(lng: string): void {
    setCookie(COOKIE_NAME, lng);
  },
};
