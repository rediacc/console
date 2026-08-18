import { useMemo } from 'react';
import { resolveClientCatalogs } from './client-catalogs';
import { createTranslatorFrom, type TranslationCatalog } from './translator';
import type { Language } from './types';

/**
 * Translations for islands that hydrate on ONE route: `src/i18n/client-route/<locale>.json`.
 *
 * Three components qualify today, and between them they wanted 58,578 bytes across the
 * thirteen locales:
 *
 *   InstallMethods            /[lang]/install     pages.install, hero.install.tabs
 *   DownloadsList             /[lang]/downloads   pages.downloads, and the shared platform filter label
 *   PartnerApplicationForm    /[lang]/partners    pages.partners.form
 *
 * This module exists so those bytes ride the chunks of the components that import it,
 * instead of the vendor chunk BaseLayout loads on all 1,814 pages. Nothing that runs on
 * every route may import it, and `react.ts` in particular must not: one import from there
 * puts the whole route bundle back on the homepage.
 *
 * Same API as `useTranslation`, different catalog. A component moves between the two by
 * changing which hook it calls, and `generate-client-i18n.ts` decides which bundle to check
 * it against by reading that call, so the split cannot silently drift.
 */
const routeTranslations = resolveClientCatalogs(
  import.meta.glob<TranslationCatalog>('./client-route/*.json', {
    eager: true,
    import: 'default',
  }),
  'client-route'
);

export function useRouteTranslation(lang: Language = 'en') {
  return useMemo(() => createTranslatorFrom(routeTranslations, lang), [lang]);
}
