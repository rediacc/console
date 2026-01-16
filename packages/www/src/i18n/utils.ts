import arTranslations from './translations/ar.json';
import deTranslations from './translations/de.json';
import enTranslations from './translations/en.json';
import esTranslations from './translations/es.json';
import frTranslations from './translations/fr.json';
import jaTranslations from './translations/ja.json';
import ruTranslations from './translations/ru.json';
import trTranslations from './translations/tr.json';
import zhTranslations from './translations/zh.json';
import type { Language, InterpolationParams, Translations, PathValue } from './types';

const translations = {
  en: enTranslations,
  de: deTranslations,
  es: esTranslations,
  fr: frTranslations,
  ja: jaTranslations,
  ar: arTranslations,
  ru: ruTranslations,
  tr: trTranslations,
  zh: zhTranslations,
};

/**
 * Get a nested value from an object using a dot-notation path
 */
function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, key) => {
    if (current && typeof current === 'object' && key in current) {
      return (current as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

/**
 * Replace interpolation placeholders in a string with actual values
 * Example: "Hello {{name}}" with { name: "World" } => "Hello World"
 */
function interpolate(text: string, params?: InterpolationParams): string {
  if (!params) return text;

  return Object.entries(params).reduce((result, [key, value]) => {
    return result.replace(new RegExp(`{{${key}}}`, 'g'), String(value));
  }, text);
}

/**
 * Get translation by key with optional interpolation
 * @param lang - Language code
 * @param key - Translation key in dot notation (e.g., "hero.title")
 * @param params - Optional parameters for interpolation
 * @returns Translated string or the key if translation not found
 */
export function getTranslation(lang: Language, key: string, params?: InterpolationParams): string {
  const translation = getNestedValue(translations[lang], key);

  if (translation === undefined) {
    console.warn(`Translation key not found: ${key}`);
    return key;
  }

  if (typeof translation === 'string') {
    return interpolate(translation, params);
  }

  console.warn(`Translation key "${key}" does not point to a string value`);
  return key;
}

/**
 * Get an array of translations
 * @param lang - Language code
 * @param key - Translation key pointing to an array
 * @returns Array of strings or empty array if not found
 */
export function getTranslationArray(lang: Language, key: string): string[] {
  const translation = getNestedValue(translations[lang], key);

  if (!Array.isArray(translation)) {
    console.warn(`Translation key "${key}" does not point to an array`);
    return [];
  }

  return translation;
}

/**
 * Get an object of translations
 * @param lang - Language code
 * @param key - Translation key pointing to an object
 * @returns Object with translations or empty object if not found
 */
export function getTranslationObject(lang: Language, key: string): Record<string, unknown> {
  const translation = getNestedValue(translations[lang], key);

  if (typeof translation !== 'object' || translation === null) {
    console.warn(`Translation key "${key}" does not point to an object`);
    return {};
  }

  return translation as Record<string, unknown>;
}

/**
 * Create a translation function bound to a specific language
 * Useful for Astro pages and server-side code
 */
export function createTranslator(lang: Language = 'en') {
  return {
    t: (key: string, params?: InterpolationParams) => getTranslation(lang, key, params),
    ta: (key: string) => getTranslationArray(lang, key),
    to: <P extends string>(key: P): PathValue<Translations, P> =>
      getNestedValue(translations[lang], key) as PathValue<Translations, P>,
  };
}
