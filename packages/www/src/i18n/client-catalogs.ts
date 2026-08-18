import { SITE_LOCALES } from '@rediacc/locales';
import type { TranslationCatalog } from './translator';
import type { Language } from './types';

/**
 * Turn an `import.meta.glob` result into a locale map, and HARD FAIL if the set does not
 * match `@rediacc/locales`.
 *
 * The glob call itself has to stay in the importing module, because Vite resolves the
 * pattern statically and a variable pattern silently matches nothing. What lives here is
 * the part worth having once: the assertion.
 *
 * It runs at module load, so a missing or extra `<dir>/<locale>.json` fails the Astro build
 * while it server-renders the first island, rather than shipping a locale that renders raw
 * translation keys. The expected set comes from SITE_LOCALES and never from the files on
 * disk: deriving it from the glob would let a deleted file define its own absence away,
 * which is how 379 German values sat in the Arabic, Japanese, Russian and Chinese catalogs
 * while every gate stayed green.
 */
export function resolveClientCatalogs(
  modules: Record<string, TranslationCatalog>,
  directory: string
): Record<Language, TranslationCatalog> {
  const prefix = `./${directory}/`;
  const suffix = '.json';

  const byLocale: Record<string, TranslationCatalog> = {};
  for (const [modulePath, catalog] of Object.entries(modules)) {
    byLocale[modulePath.slice(prefix.length, -suffix.length)] = catalog;
  }

  const found = Object.keys(byLocale).sort();
  const missing = SITE_LOCALES.filter((locale) => !(locale in byLocale));
  const unexpected = found.filter(
    (locale) => !(SITE_LOCALES as readonly string[]).includes(locale)
  );

  if (missing.length > 0 || unexpected.length > 0) {
    const missingPart = missing.length > 0 ? `Missing: ${missing.join(', ')}. ` : '';
    const unexpectedPart = unexpected.length > 0 ? `Unexpected: ${unexpected.join(', ')}. ` : '';
    const foundPart = found.length > 0 ? found.join(', ') : '(none)';
    throw new Error(
      `src/i18n/${directory}/ does not match @rediacc/locales. ${missingPart}${unexpectedPart}Found: ${foundPart}. Regenerate with: npm run i18n:generate-client -w @rediacc/www`
    );
  }

  return byLocale;
}
