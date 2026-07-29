/**
 * Hand-written to give TypeScript a literal tuple, which `resolveJsonModule` cannot do
 * (it widens to `string[]`). That literal type is what makes `SiteLocale` a union, and
 * `Record<SiteLocale, string>` an exhaustiveness check — the property that turns "someone
 * added a locale and forgot a translation map" from a runtime surprise into a build error.
 *
 * MUST stay in sync with index.js. `check:ci-locale-sources` compares them, so a drift
 * here is a gate failure rather than a silently wrong type.
 */

export declare const SITE_LOCALES: readonly [
  'en',
  'de',
  'es',
  'fr',
  'ja',
  'ar',
  'ru',
  'tr',
  'zh',
  'et',
  'ko',
  'pt',
  'it',
];

/** A locale this site ships. */
export type SiteLocale = (typeof SITE_LOCALES)[number];

export declare const DEFAULT_LOCALE: 'en';

/** Every site locale except the source language. Derived from SITE_LOCALES. */
export declare const NON_ENGLISH_LOCALES: readonly SiteLocale[];

/** Narrowing predicate for UNTRUSTED input, where an English fallback is correct. */
export declare function isSiteLocale(value: unknown): value is SiteLocale;

/** Throws on an unknown locale. For internal invariants, never for user input. */
export declare function assertSiteLocale(value: unknown, context?: string): SiteLocale;

/** Declare a deliberate subset; throws at module load on an unknown code. */
export declare function subset(name: string, codes: readonly SiteLocale[]): readonly SiteLocale[];

/** Codes in SITE_LOCALES that the given list omits. */
export declare function missingFrom(codes: readonly string[]): readonly SiteLocale[];
