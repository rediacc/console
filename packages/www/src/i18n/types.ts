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

// Sorted A-Z by native display name (see getLanguageName in language-utils.ts).
// Latin scripts first (alphabetical), then non-Latin grouped by Unicode order.
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
export type Language = (typeof LANGUAGES)[number];

export type InterpolationParams = Record<string, string | number>;
