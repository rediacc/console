/**
 * Language Cookie Utilities
 *
 * Shared cookie management for language selection across www.rediacc.com
 */

const LANGUAGE_COOKIE_NAME = 'rediacc_lang';

export interface LanguageCookieOptions {
  domain?: string;
  path?: string;
  maxAge?: number;
  secure?: boolean;
  sameSite?: 'Strict' | 'Lax' | 'None';
}

const DEFAULT_OPTIONS: LanguageCookieOptions = {
  domain: '.rediacc.com',
  path: '/',
  maxAge: 31536000, // 1 year in seconds
  secure: true,
  sameSite: 'Lax',
};

/**
 * Set language cookie
 */
export function setLanguageCookie(language: string, options: LanguageCookieOptions = {}): void {
  if (typeof document === 'undefined') {
    return;
  }

  const opts = { ...DEFAULT_OPTIONS, ...options };

  // For local development, don't set domain (allows localhost)
  const isLocalhost =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

  let cookieString = `${LANGUAGE_COOKIE_NAME}=${encodeURIComponent(language)}`;

  if (opts.path) {
    cookieString += `; path=${opts.path}`;
  }

  if (opts.domain && !isLocalhost) {
    cookieString += `; domain=${opts.domain}`;
  }

  if (opts.maxAge) {
    cookieString += `; max-age=${opts.maxAge}`;
  }

  if (opts.secure && window.location.protocol === 'https:') {
    cookieString += '; secure';
  }

  if (opts.sameSite) {
    cookieString += `; samesite=${opts.sameSite}`;
  }

  document.cookie = cookieString;
}
