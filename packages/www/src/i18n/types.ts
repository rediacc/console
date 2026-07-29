import type { SiteLocale } from '@rediacc/locales';
import type enTranslations from './translations/en.json';

export type Translations = typeof enTranslations;

/**
 * Utility type to get nested property type from a dot-notation path
 */
export type PathValue<T, P extends string> = P extends `${infer K}.${infer R}`
  ? K extends keyof T
    ? PathValue<T[K], R>
    : unknown
  : P extends keyof T
    ? T[P]
    : unknown;

// PRESENTATION ORDER, and the one locale array that is legitimately not SITE_LOCALES.
// Sorted A-Z by native display name (see getLanguageName in language-utils.ts).
// Latin scripts first (alphabetical), then non-Latin grouped by Unicode order.
//
// The membership is the invariant; the order is data. `_displayOrderIsComplete` below
// proves at COMPILE TIME that this covers exactly the site's locale set, so dropping or
// inventing a locale here is a build error rather than a menu that quietly loses an entry.
// Do not reorder it to match SITE_LOCALES — this order is what the language menu shows.
export const LANGUAGES = [
  'de', // Deutsch
  'et', // Eesti
  'en', // English
  'es', // Español
  'fr', // Français
  'it', // Italiano
  'pt', // Português
  'tr', // Türkçe
  'ar', // العربية
  'ru', // Русский
  'zh', // 中文
  'ja', // 日本語
  'ko', // 한국어
] as const;

/**
 * A locale this site ships. Sourced from `@rediacc/locales` so there is ONE definition of
 * the set; this file only decides the order they are displayed in.
 */
export type Language = SiteLocale;

// (No LOCALE_DISPLAY_ORDER alias: knip correctly flags an unused duplicate export, and
// the name `LANGUAGES` is load-bearing across 37 call sites. The comment above carries the
// meaning instead.)

// Compile-time proof that the display order is a complete permutation of the site's
// locales — mutual assignability, so it fails if LANGUAGES omits one OR invents one.
// Zero runtime cost: it is a type-level assertion, not a check that runs.
type _MutuallyAssignable<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
const _displayOrderIsComplete: _MutuallyAssignable<(typeof LANGUAGES)[number], SiteLocale> = true;
void _displayOrderIsComplete;

export type InterpolationParams = Record<string, string | number>;
