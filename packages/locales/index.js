/**
 * The site's locale set. ONE declaration, consumed by everything.
 *
 * Before this package there were 31 copies of this list in the console tree alone, in five
 * different orderings, plus more in the submodules and the gitignored Python repos. They
 * drifted: `eslint.config.js` carried 8, two media gates carried 10, `VIDEO_LANGS` carried
 * 11, and nothing could tell a deliberate subset from a stale copy.
 *
 * Plain ESM with a hand-written `.d.ts`, and NO build step, on purpose. The consumers
 * include `eslint.config.js` (runs before any build), eleven `node`-run `.js` scripts, an
 * Astro/Vite app, `tsx` scripts, two Cloudflare workers and the CLI bundle. Anything that
 * resolved through a `dist/` — `packages/shared` does — would need a build before eslint
 * could load it. A bare specifier into a workspace package resolves for all of them via
 * Node's upward `node_modules` walk, with no ordering constraint at all.
 *
 * Adding a locale here is deliberately a multi-file change: `Record<Language, string>` in
 * `packages/www/src/i18n/language-utils.ts` and friends will stop compiling until every
 * map is filled in. That is the point. A locale that is "supported" but has no strings is
 * how this repo shipped Italian, Korean and Portuguese narration spoken in English.
 */

/**
 * All 13 site locales.
 *
 * ORDER: this is the ordering 15 of the 16 declarations it replaces already used, kept
 * deliberately rather than sorted. Nothing found so far depends on the order, but "found
 * nothing" is weaker evidence than "changed nothing", and several consumers iterate this
 * list to WRITE files and to build production edge routes. Alphabetical would have been
 * prettier at the cost of making the consolidation and a behaviour change indistinguishable
 * in the same diff. For a human-facing order, use LOCALE_DISPLAY_ORDER in
 * packages/www/src/i18n/types.ts, which is a presentation fact and is gated to stay a
 * permutation of this list.
 */
export const SITE_LOCALES = [
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

/** The source language. Content is authored here and translated outward. */
export const DEFAULT_LOCALE = 'en';

/**
 * Everything except the source language. DERIVED, never re-declared — four scripts used to
 * hand-maintain their own copy of this.
 *
 * Consumers that exclude `en` do so STRUCTURALLY, not for coverage: it is the translation
 * source, the freshness baseline, and the file that scaffolding must never overwrite. Using
 * SITE_LOCALES where this belongs would make the transcript scaffolder replace authored
 * English with `TODO:` stubs and make the translator spend model calls translating English
 * into English over its own source.
 */
export const NON_ENGLISH_LOCALES = SITE_LOCALES.filter((l) => l !== DEFAULT_LOCALE);

/**
 * Is this a locale we ship? Use for UNTRUSTED input — `$LANG`, a `--lang` flag, a URL
 * segment — where falling back to English is the correct, friendly behaviour.
 */
export function isSiteLocale(value) {
  return SITE_LOCALES.includes(value);
}

/**
 * Assert a locale, THROWING if unknown. Use where the value is an internal invariant: a
 * manifest key, a directory name, a pipeline argument.
 *
 * The distinction from isSiteLocale is load-bearing, not stylistic. Silently defaulting an
 * internal value to English is exactly the `map.get(code, "English")` shape that shipped
 * wrong-language audio here and survived four commits, because a wrong-language clip has a
 * plausible duration and a zero exit code. Silently defaulting UNTRUSTED input is correct
 * and must not be replaced with a throw, or a foreign `$LANG` crashes the CLI.
 */
export function assertSiteLocale(value, context = 'locale') {
  if (!isSiteLocale(value)) {
    throw new Error(
      `${context}: ${JSON.stringify(value)} is not a site locale. ` +
        `Known: ${SITE_LOCALES.join(', ')}. If this is a new locale, add it to ` +
        `packages/locales/index.js (and index.d.ts) rather than special-casing it here.`
    );
  }
  return value;
}

/**
 * Declare a DELIBERATE subset of the site locales, and fail loudly on a typo.
 *
 * Subsets are real: "locales whose media is published to R2" is a fact about a bucket, not
 * about the site, so it belongs at its own call site rather than in this file. What this
 * gives it is a checked relationship — an unknown code throws at module load instead of
 * quietly never matching anything.
 *
 * @param {string} name  what the subset means, used in the error
 * @param {readonly string[]} codes
 */
export function subset(name, codes) {
  for (const code of codes) {
    if (!isSiteLocale(code)) {
      throw new Error(
        `locale subset "${name}" contains ${JSON.stringify(code)}, which is not a site ` +
          `locale. Known: ${SITE_LOCALES.join(', ')}.`
      );
    }
  }
  return Object.freeze([...codes]);
}

/** Codes in SITE_LOCALES that a subset omits. For diagnostics and gate messages. */
export function missingFrom(codes) {
  return SITE_LOCALES.filter((l) => !codes.includes(l));
}
