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

export const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'] as const;
export type Language = (typeof LANGUAGES)[number];

export type InterpolationParams = Record<string, string | number>;
