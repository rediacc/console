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
type TranslationCatalog = Record<string, unknown>;
export type { TranslationCatalog };

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
  paramsOrFallback: InterpolationParams | string | undefined,
  miss: MissHandler,
  strict: boolean
): string {
  const translation = getNestedValue(catalog, key);

  if (translation === undefined) {
    // Under `strict` the fallback is refused too: it is English text shown in every locale, the same defect as the key itself. Outside strict a fallback stays silent, as it always was: the caller named the text on purpose.
    if (typeof paramsOrFallback === 'string' && !strict) return paramsOrFallback;
    miss(`Translation key not found: ${key}`);
    return typeof paramsOrFallback === 'string' ? paramsOrFallback : key;
  }

  if (typeof translation === 'string') {
    const params = typeof paramsOrFallback === 'object' ? paramsOrFallback : undefined;
    return interpolate(translation, params);
  }

  miss(`Translation key "${key}" does not point to a string value`);
  return key;
}

/**
 * Get an array of translations
 */
function getTranslationArray(
  catalog: TranslationCatalog,
  key: string,
  miss: MissHandler
): string[] {
  const translation = getNestedValue(catalog, key);

  if (!Array.isArray(translation)) {
    miss(`Translation key "${key}" does not point to an array`);
    return [];
  }

  return translation;
}

type MissHandler = (message: string) => void;

/**
 * Whether a miss FAILS instead of warning: true while Astro prerenders a production build.
 *
 * WHY. `t()` answers a miss by returning the key, so a missing key ships as visible text.
 * https://www.rediacc.com/en/pricing showed `pages.pricing.plans.free.name` in all 13
 * locales (2026-11-17): the card builds the key from `plan.id`, the shared PLAN_ORDER
 * gained FREE, and no source-reading gate can follow a `${...}` key. The build printed
 * "Translation key not found" 39 times and exited 0. A throw during prerender turns every
 * such key, however it was built, into a failed build that names it.
 *
 * Dev (`astro dev`) and the browser keep the warning: a dev server should render a page
 * mid-edit, and a hydrated island must never crash for a reader. Vite replaces
 * `import.meta.env.SSR` with `false` in the client bundle, so the throw is not shipped.
 * `import.meta.env` is absent when tsx runs this module outside Vite, which reads as
 * not strict.
 */
function strictByDefault(): boolean {
  const env = import.meta.env as { PROD?: boolean; SSR?: boolean } | undefined;
  return Boolean(env?.PROD && env?.SSR);
}

function missHandler(lang: Language, strict: boolean): MissHandler {
  return strict
    ? (message) => {
        throw new Error(
          `[i18n] ${message} (lang '${lang}'). Add it to en.json and the 12 locales.`
        );
      }
    : (message) => console.warn(message);
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
  lang: Language,
  { strict = strictByDefault() }: { strict?: boolean } = {}
) {
  const catalog = catalogs[lang];
  const miss = missHandler(lang, strict);
  return {
    t: (key: string, paramsOrFallback?: InterpolationParams | string) =>
      getTranslation(catalog, key, paramsOrFallback, miss, strict),
    ta: (key: string) => getTranslationArray(catalog, key, miss),
    to: <P extends string>(key: P): PathValue<Translations, P> =>
      getNestedValue(catalog, key) as PathValue<Translations, P>,
  };
}
