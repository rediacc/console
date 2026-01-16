/**
 * Language Cookie Utilities
 *
 * Shared cookie management for language selection across www.rediacc.com and console.rediacc.com
 */

export const LANGUAGE_COOKIE_NAME = 'rediacc_lang';

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
 * Get language from cookie
 */
export function getLanguageCookie(): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === LANGUAGE_COOKIE_NAME) {
      return decodeURIComponent(value);
    }
  }
  return null;
}

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

/**
 * Delete language cookie
 */
export function deleteLanguageCookie(): void {
  if (typeof document === 'undefined') {
    return;
  }

  // Set expiry to past date to delete
  setLanguageCookie('', { maxAge: -1 });
}

/**
 * Check if a language code is valid
 */
export function isValidLanguage(lang: string): boolean {
  const validLanguages = ['en', 'es', 'fr', 'de', 'zh', 'ja', 'ar', 'tr', 'ru'];
  return validLanguages.includes(lang);
}
