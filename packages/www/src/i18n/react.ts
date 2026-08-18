import { useMemo } from 'react';
import { resolveClientCatalogs } from './client-catalogs';
import { createTranslatorFrom, type TranslationCatalog } from './translator';
import type { Language } from './types';

/**
 * The catalogs every route pays for: `src/i18n/client/<locale>.json`, generated and
 * committed by `packages/www/scripts/generate-client-i18n.ts`.
 *
 * They hold only the keys reachable from the islands `BaseLayout` hydrates on every page,
 * about 219 leaves and 124 KB across all thirteen locales, against 9.28 MB for the full
 * set. Before this split, `useTranslation` reached `utils.ts` and its thirteen static
 * imports, Rollup hoisted every catalog into the shared vendor chunk, and an English
 * visitor downloaded Korean, Arabic, Russian and Japanese marketing copy to read the
 * homepage: 6,708,716 bytes in one asset, 89.5% of the page.
 *
 * Islands that are hydrated on ONE route (the install, downloads and partners forms) use
 * `react-route.ts` instead, so their strings ride their own chunk. Importing that module
 * from here would put them back on every route, which is the whole failure mode.
 *
 * `eager: true` is deliberate. All thirteen slices in one chunk is small enough that lazy
 * loading would buy little at the cost of making the translator asynchronous and changing
 * the API of every island.
 *
 * `client/` is a SIBLING of `translations/`, never a child. Three gates derive the site's
 * locale set by listing `src/i18n/translations/*.json` (check-translation-completeness.ts,
 * check-i18n-placeholders.ts, check_i18n_value_types.py), and extra files inside that
 * directory would corrupt every one of them.
 */
const clientTranslations = resolveClientCatalogs(
  import.meta.glob<TranslationCatalog>('./client/*.json', { eager: true, import: 'default' }),
  'client'
);

/**
 * React hook for using translations in React components
 * Uses useMemo to ensure stable references and prevent hydration mismatches
 */
export function useTranslation(lang: Language = 'en') {
  return useMemo(() => createTranslatorFrom(clientTranslations, lang), [lang]);
}
