import i18n from 'i18next';
// Import all locale files directly - they get bundled by esbuild
import { getAllTranslations, SHARED_NAMESPACE } from '@rediacc/shared/i18n';
import arCli from './locales/ar/cli.json' with { type: 'json' };
import deCli from './locales/de/cli.json' with { type: 'json' };
import enCli from './locales/en/cli.json' with { type: 'json' };
import esCli from './locales/es/cli.json' with { type: 'json' };
import frCli from './locales/fr/cli.json' with { type: 'json' };
import jaCli from './locales/ja/cli.json' with { type: 'json' };
import ruCli from './locales/ru/cli.json' with { type: 'json' };
import trCli from './locales/tr/cli.json' with { type: 'json' };
import zhCli from './locales/zh/cli.json' with { type: 'json' };

// Import shared translations from @rediacc/shared

export const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

// Get all shared translations
const sharedTranslations = getAllTranslations();

const resources = {
  en: { cli: enCli, [SHARED_NAMESPACE]: sharedTranslations.en },
  de: { cli: deCli, [SHARED_NAMESPACE]: sharedTranslations.de },
  es: { cli: esCli, [SHARED_NAMESPACE]: sharedTranslations.es },
  fr: { cli: frCli, [SHARED_NAMESPACE]: sharedTranslations.fr },
  ja: { cli: jaCli, [SHARED_NAMESPACE]: sharedTranslations.ja },
  ar: { cli: arCli, [SHARED_NAMESPACE]: sharedTranslations.ar },
  ru: { cli: ruCli, [SHARED_NAMESPACE]: sharedTranslations.ru },
  tr: { cli: trCli, [SHARED_NAMESPACE]: sharedTranslations.tr },
  zh: { cli: zhCli, [SHARED_NAMESPACE]: sharedTranslations.zh },
};

// Initialize i18n synchronously with English at module load time.
// This ensures t() works for command definitions.
// Language can be changed later via changeLanguage().
void i18n.init({
  lng: 'en',
  fallbackLng: 'en',
  ns: ['cli', SHARED_NAMESPACE],
  defaultNS: 'cli',
  resources,
  interpolation: {
    escapeValue: false, // Not needed for CLI output
  },
  initImmediate: false, // Synchronous initialization
});

/**
 * Initialize i18next with the specified language.
 * Safe to call multiple times - subsequent calls will change the language.
 */
export async function initI18n(language = 'en'): Promise<void> {
  const normalizedLang = normalizeLanguage(language);
  if (i18n.language !== normalizedLang) {
    await i18n.changeLanguage(normalizedLang);
  }
}

/**
 * Normalize a language code to a supported language.
 * Handles variants like 'en-US' -> 'en', 'zh-CN' -> 'zh'.
 */
function normalizeLanguage(lang: string): SupportedLanguage {
  const base = lang.split('-')[0].split('_')[0].toLowerCase();
  return SUPPORTED_LANGUAGES.includes(base as SupportedLanguage)
    ? (base as SupportedLanguage)
    : 'en';
}

/**
 * Translation function - use this throughout the CLI.
 */
export const t = i18n.t.bind(i18n);

/**
 * Change the current language.
 */
export const changeLanguage = async (lang: string): Promise<void> => {
  const normalizedLang = normalizeLanguage(lang);
  await i18n.changeLanguage(normalizedLang);
};
