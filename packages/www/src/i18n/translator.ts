import type { InterpolationParams, Language, PathValue, Translations } from './types';

/**
 * The translation lookup, with the catalogs left as a parameter.
 *
 * This module deliberately imports NO locale JSON. Two callers need the same lookup over
 * two different catalog sets:
 *
 *   utils.ts  the full thirteen catalogs (9.28 MB on disk), for the 55 `.astro` consumers
 *             and every other server-side caller.
 *   react.ts  the generated client slices in `src/i18n/client/` (about 224 KB for all
 *             thirteen), for the eighteen hydrated React islands.
 *
 * Keeping the logic here is what makes that split free of duplication. If react.ts imported
 * anything from utils.ts, Rollup would follow the thirteen static JSON imports into the
 * shared vendor chunk that every page loads, which is the 6.7 MB regression this file
 * exists to prevent.
 */

/** A parsed locale catalog. Deliberately loose: the client slices are a subset of the full ones. */
export type TranslationCatalog = Record<string, unknown>;

/**
 * Get a nested value from an object using a dot-notation path
 */
function getNestedValue(obj: TranslationCatalog, path: string): unknown {
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
    return result.replaceAll(new RegExp(`{{${key}}}`, 'g'), String(value));
  }, text);
}

/**
 * Get translation by key with optional interpolation or fallback string.
 *
 * Second argument can be either an interpolation params object
 * (e.g. `t('greeting', { name: 'world' })`) or a literal fallback string used
 * when the translation key is missing (e.g. `t('newKey', 'Default text')`).
 */
function getTranslation(
  catalog: TranslationCatalog,
  key: string,
  paramsOrFallback?: InterpolationParams | string
): string {
  const translation = getNestedValue(catalog, key);

  if (translation === undefined) {
    if (typeof paramsOrFallback === 'string') return paramsOrFallback;
    console.warn(`Translation key not found: ${key}`);
    return key;
  }

  if (typeof translation === 'string') {
    const params = typeof paramsOrFallback === 'object' ? paramsOrFallback : undefined;
    return interpolate(translation, params);
  }

  console.warn(`Translation key "${key}" does not point to a string value`);
  return key;
}

/**
 * Get an array of translations
 */
function getTranslationArray(catalog: TranslationCatalog, key: string): string[] {
  const translation = getNestedValue(catalog, key);

  if (!Array.isArray(translation)) {
    console.warn(`Translation key "${key}" does not point to an array`);
    return [];
  }

  return translation;
}

/**
 * Bind `t` / `ta` / `to` to one catalog set and one language.
 *
 * `to()` keeps its return type off the FULL English catalog (`Translations`) even when the
 * catalogs passed in are the client slices. That is on purpose: the slices are a subset of
 * the same shape, so the types stay honest about structure, and every existing call site
 * keeps compiling unchanged.
 */
export function createTranslatorFrom(
  catalogs: Readonly<Record<Language, TranslationCatalog>>,
  lang: Language
) {
  const catalog = catalogs[lang];
  return {
    t: (key: string, paramsOrFallback?: InterpolationParams | string) =>
      getTranslation(catalog, key, paramsOrFallback),
    ta: (key: string) => getTranslationArray(catalog, key),
    to: <P extends string>(key: P): PathValue<Translations, P> =>
      getNestedValue(catalog, key) as PathValue<Translations, P>,
  };
}
