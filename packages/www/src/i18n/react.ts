import { useEffect, useMemo, useSyncExternalStore } from 'react';
import english from './client/en.json';
import { resolveClientCatalogs } from './client-catalogs';
import { getLanguageFromPath } from './language-utils';
import { createCatalogStore } from './react/catalog-store';
import { createTranslatorFrom, type TranslationCatalog } from './translator';
import type { Language } from './types';

/**
 * The catalogs every route draws on: `src/i18n/client/<locale>.json`, generated and
 * committed by `packages/www/scripts/generate-client-i18n.ts`.
 *
 * They hold only the keys reachable from the islands `BaseLayout` hydrates on every page,
 * about 219 leaves and 10-16 KB per locale, against 9.28 MB for the full set. Before the
 * client split, `useTranslation` reached `utils.ts` and its thirteen static imports, and an
 * English visitor downloaded Korean, Arabic, Russian and Japanese marketing copy to read the
 * homepage: 6,708,716 bytes in one asset, 89.5% of the page.
 *
 * ONE LOCALE PER PAGE, NOT THIRTEEN. The slices were once one eager glob, a 142,457 B chunk
 * that pushed the homepage to 516,318 B against the 500,000 B budget of
 * check:ci-client-bundle-budget while every visitor read exactly one of them. Now English is
 * the only static import and every other locale is a member of the keyed map below, so a
 * page fetches its own slice and nothing else. The gate charges such a map at its largest
 * member, which is the honest cost of a choice a visitor makes once.
 *
 * WHY ENGLISH STAYS STATIC. `useLanguage` server-renders 'en' on every locale and hands
 * React the same 'en' as its hydration snapshot, so the islands built on it hydrate in
 * English on /de/ and /ar/ too and only then switch. Hydrating them against anything but
 * the English slice would be a mismatch. Once the islands server-render their real locale
 * (agent/plans/PLAN-ssr-nav-locale.md), English can join the map.
 *
 * THE MAP'S KEYS MUST STAY BARE LANGUAGE TAGS, every value a bare `() => import(...)`.
 * That is the shape the gate recognises as one choice (`localeAlternatives`); a glob's
 * `./client/ar.json` keys, or a non-import entry in the middle, read as separate imports
 * and are charged in full.
 *
 * Islands that are hydrated on ONE route (the install, downloads and partners forms) use
 * `react-route.ts` instead, so their strings ride their own chunk. Importing that module
 * from here would put them back on every route, which is the whole failure mode.
 *
 * `client/` is a SIBLING of `translations/`, never a child. Three gates derive the site's
 * locale set by listing `src/i18n/translations/*.json` (check-translation-completeness.ts,
 * check-i18n-placeholders.ts, check_i18n_value_types.py), and extra files inside that
 * directory would corrupt every one of them.
 */
const catalogs = createCatalogStore(english, {
  ar: () => import('./client/ar.json'),
  de: () => import('./client/de.json'),
  es: () => import('./client/es.json'),
  et: () => import('./client/et.json'),
  fr: () => import('./client/fr.json'),
  it: () => import('./client/it.json'),
  ja: () => import('./client/ja.json'),
  ko: () => import('./client/ko.json'),
  pt: () => import('./client/pt.json'),
  ru: () => import('./client/ru.json'),
  tr: () => import('./client/tr.json'),
  zh: () => import('./client/zh.json'),
});

/*
 * Loaded BEFORE any island renders, through top-level await: every island that translates
 * imports this module, so none evaluates, and none hydrates, until its page's slice is in
 * hand. That is what keeps first paint free of raw keys and of a hydration mismatch. A
 * language switch is a full navigation (no page renders `<ClientRouter />`, see
 * BaseLayout), so the next page evaluates this again for its own locale.
 *
 * The server holds every slice, because one build renders all thirteen locales, and checks
 * the set against `@rediacc/locales` so a missing or extra slice still fails the build.
 */
if (typeof window === 'undefined') {
  await catalogs.loadAll();
  resolveClientCatalogs(
    Object.fromEntries(
      Object.entries(catalogs.all()).map(([lang, catalog]) => [`./client/${lang}.json`, catalog])
    ),
    'client'
  );
} else {
  await catalogs.load(getLanguageFromPath(window.location.pathname));
}

/**
 * React hook for using translations in React components.
 *
 * The page's own locale and English are always in hand (see above), so on every first
 * render, server or hydration, the translator reads the requested catalog synchronously.
 * Any other locale, such as a `lang` prop that names a different language, renders English
 * for the one frame it takes to fetch, then re-renders through the store subscription.
 */
export function useTranslation(lang: Language = 'en') {
  const catalog = useSyncExternalStore(
    catalogs.subscribe,
    () => catalogs.get(lang),
    () => catalogs.get(lang)
  );

  useEffect(() => {
    if (!catalog) void catalogs.load(lang);
  }, [catalog, lang]);

  return useMemo(
    () =>
      createTranslatorFrom(
        { [lang]: catalog ?? english } as Record<Language, TranslationCatalog>,
        lang
      ),
    [catalog, lang]
  );
}
