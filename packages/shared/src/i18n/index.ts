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
import ar from './locales/ar/common.json';
import de from './locales/de/common.json';
import en from './locales/en/common.json';
import es from './locales/es/common.json';
import fr from './locales/fr/common.json';
import ja from './locales/ja/common.json';
import ru from './locales/ru/common.json';
import tr from './locales/tr/common.json';
import zh from './locales/zh/common.json';
import type { SharedCommonTranslations, SupportedLanguage } from './types';

// Re-export types
export * from './types';

/**
 * Static translations map for sync loading (CLI).
 */
const translationsMap: Record<SupportedLanguage, SharedCommonTranslations> = {
  en: en as SharedCommonTranslations,
  de: de as SharedCommonTranslations,
  es: es as SharedCommonTranslations,
  fr: fr as SharedCommonTranslations,
  ja: ja as SharedCommonTranslations,
  ar: ar as SharedCommonTranslations,
  ru: ru as SharedCommonTranslations,
  tr: tr as SharedCommonTranslations,
  zh: zh as SharedCommonTranslations,
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
