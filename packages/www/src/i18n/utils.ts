import arTranslations from './translations/ar.json';
import deTranslations from './translations/de.json';
import enTranslations from './translations/en.json';
import esTranslations from './translations/es.json';
import etTranslations from './translations/et.json';
import frTranslations from './translations/fr.json';
import itTranslations from './translations/it.json';
import jaTranslations from './translations/ja.json';
import koTranslations from './translations/ko.json';
import ptTranslations from './translations/pt.json';
import ruTranslations from './translations/ru.json';
import trTranslations from './translations/tr.json';
import zhTranslations from './translations/zh.json';
import { createTranslatorFrom, type TranslationCatalog } from './translator';
import type { Language } from './types';

/**
 * The FULL thirteen catalogs, for server-side callers only.
 *
 * These thirteen static imports are load-bearing beyond loading data: they are the reason
 * deleting `src/i18n/translations/<locale>.json` is a build error rather than a silent
 * shipping of English. Three i18n gates (completeness, placeholders, value-types) cannot
 * see a missing FILE at all, so do not replace them with a glob or a dynamic import.
 *
 * Nothing that reaches a React island may import this module. The client path is
 * `react.ts`, which reads the generated slices in `src/i18n/client/`. Importing this from
 * an island puts all thirteen catalogs into the shared vendor chunk that every page loads,
 * which cost 6.7 MB of JavaScript on every route until 2026-08.
 */
const translations: Record<Language, TranslationCatalog> = {
  en: enTranslations,
  de: deTranslations,
  es: esTranslations,
  fr: frTranslations,
  ja: jaTranslations,
  ar: arTranslations,
  ru: ruTranslations,
  tr: trTranslations,
  zh: zhTranslations,
  et: etTranslations,
  it: itTranslations,
  ko: koTranslations,
  pt: ptTranslations,
};

/**
 * Create a translation function bound to a specific language
 * Useful for Astro pages and server-side code
 */
export function createTranslator(lang: Language = 'en') {
  return createTranslatorFrom(translations, lang);
}
