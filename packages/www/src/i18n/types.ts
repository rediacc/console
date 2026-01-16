import type enTranslations from './translations/en.json';
import type esTranslations from './translations/es.json';

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

export type Language = 'en' | 'de' | 'es' | 'fr' | 'ja' | 'ar' | 'ru' | 'tr' | 'zh';

export type TranslationKey = string;

export type InterpolationParams = Record<string, string | number>;

export type LanguageTranslations = {
  en: typeof enTranslations;
  de: typeof enTranslations; // Same structure as en
  es: typeof esTranslations;
  fr: typeof enTranslations; // Same structure as en
  ja: typeof enTranslations; // Same structure as en
  ar: typeof enTranslations; // Same structure as en
  ru: typeof enTranslations; // Same structure as en
  tr: typeof enTranslations; // Same structure as en
  zh: typeof enTranslations; // Same structure as en
};
