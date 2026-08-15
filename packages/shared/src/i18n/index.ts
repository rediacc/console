/**
 * Shared i18n utilities for CLI and Web.
 *
 * Usage in CLI (sync):
 *   import { getSharedTranslations } from '@rediacc/shared/i18n';
 *   const translations = getSharedTranslations('en');
 *
 * Usage in Web (async):
 *   import { loadSharedTranslationsAsync } from '@rediacc/shared/i18n';
 *   const translations = await loadSharedTranslationsAsync('en');
 */

// Import all translations statically for sync loading
// These are bundled at build time
import ar from './locales/ar/common.json' with { type: 'json' };
import de from './locales/de/common.json' with { type: 'json' };
import en from './locales/en/common.json' with { type: 'json' };
import es from './locales/es/common.json' with { type: 'json' };
import et from './locales/et/common.json' with { type: 'json' };
import fr from './locales/fr/common.json' with { type: 'json' };
import it from './locales/it/common.json' with { type: 'json' };
import ja from './locales/ja/common.json' with { type: 'json' };
import ko from './locales/ko/common.json' with { type: 'json' };
import pt from './locales/pt/common.json' with { type: 'json' };
import ru from './locales/ru/common.json' with { type: 'json' };
import tr from './locales/tr/common.json' with { type: 'json' };
import zh from './locales/zh/common.json' with { type: 'json' };
import type { SharedCommonTranslations, SupportedLanguage } from './types.js';

// Re-export types
export * from './types.js';

/**
 * Static translations map for sync loading (CLI).
 */
const translationsMap: Record<SupportedLanguage, SharedCommonTranslations> = {
  en,
  de,
  es,
  fr,
  ja,
  ar,
  ru,
  tr,
  zh,
  et,
  ko,
  pt,
  it,
};

/**
 * Get shared translations synchronously (for CLI).
 * This uses statically imported translations for fast sync access.
 *
 * @param lang - Language code (defaults to 'en')
 * @returns The shared translations object
 */
export function getSharedTranslations(lang: SupportedLanguage = 'en'): SharedCommonTranslations {
  return translationsMap[lang];
}

/**
 * Load shared translations asynchronously (for Web).
 * This can be used with i18next backends for lazy loading.
 *
 * @param lang - Language code (defaults to 'en')
 * @returns Promise resolving to the shared translations object
 */
export function loadSharedTranslationsAsync(
  lang: SupportedLanguage = 'en'
): Promise<SharedCommonTranslations> {
  // For now, return the static translations.
  // In the future, this could be modified to use dynamic imports
  // for better code splitting in web bundles.
  return Promise.resolve(translationsMap[lang]);
}

/**
 * Get all available translations (for bundling).
 * @returns Record of all language translations
 */
export function getAllTranslations(): Record<SupportedLanguage, SharedCommonTranslations> {
  return translationsMap;
}

/**
 * Namespace for the shared translations.
 * Use this when registering with i18next.
 */
export const SHARED_NAMESPACE = 'shared';
