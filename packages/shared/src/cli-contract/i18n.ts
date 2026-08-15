/**
 * Lazy per-language string bundles for the CLI contract.
 *
 * Each bundle is the flattened `commands.*` and `options.*` namespaces of that
 * locale's cli.json — exactly the keys a ContractCommand/ContractOption points
 * at via `descriptionKey`.
 *
 * The loaders are a static map of dynamic imports so a bundler can code-split
 * every language into its own chunk: a web console that renders English never
 * downloads the other twelve. (This is deliberately unlike @rediacc/shared/i18n,
 * which imports all locales statically for synchronous CLI access.)
 */
import type { ContractStrings } from './types.js';

export type ContractLanguage =
  | 'ar'
  | 'de'
  | 'en'
  | 'es'
  | 'et'
  | 'fr'
  | 'it'
  | 'ja'
  | 'ko'
  | 'pt'
  | 'ru'
  | 'tr'
  | 'zh';

/**
 * Explicitly typed: without the annotation TypeScript tries to serialise the
 * literal type of all thirteen bundles (1469 keys each) and gives up (TS7056).
 * Widening to ContractStrings at the boundary is also what consumers want.
 */
type BundleLoader = () => Promise<{ default: ContractStrings }>;

const LOADERS: Record<ContractLanguage, BundleLoader> = {
  ar: () => import('./data/i18n/ar.json'),
  de: () => import('./data/i18n/de.json'),
  en: () => import('./data/i18n/en.json'),
  es: () => import('./data/i18n/es.json'),
  et: () => import('./data/i18n/et.json'),
  fr: () => import('./data/i18n/fr.json'),
  it: () => import('./data/i18n/it.json'),
  ja: () => import('./data/i18n/ja.json'),
  ko: () => import('./data/i18n/ko.json'),
  pt: () => import('./data/i18n/pt.json'),
  ru: () => import('./data/i18n/ru.json'),
  tr: () => import('./data/i18n/tr.json'),
  zh: () => import('./data/i18n/zh.json'),
};

export const CONTRACT_LANGUAGES = Object.keys(LOADERS).sort() as ContractLanguage[];

export function isContractLanguage(lang: string): lang is ContractLanguage {
  return lang in LOADERS;
}

/**
 * Load one language's strings. Falls back to English for an unknown language,
 * so a caller can pass a raw locale header without guarding it first.
 */
export async function loadContractStrings(lang: string): Promise<ContractStrings> {
  const load = isContractLanguage(lang) ? LOADERS[lang] : LOADERS.en;
  const mod = await load();
  return mod.default;
}

/**
 * Resolve a descriptionKey against a loaded bundle.
 *
 * Falls back to the entry's English `label` when the key is missing from the
 * bundle or is null (a few factory-generated descriptions have no static key),
 * so the UI always has something to render.
 */
export function translate(
  strings: ContractStrings,
  descriptionKey: string | null,
  label: string
): string {
  if (!descriptionKey) return label;
  return strings[descriptionKey] ?? label;
}
