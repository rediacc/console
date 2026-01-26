import type { Language } from './types';

export const SUPPORTED_LANGUAGES: Language[] = [
  'en',
  'de',
  'es',
  'fr',
  'ja',
  'ar',
  'ru',
  'tr',
  'zh',
] as const;
export const DEFAULT_LANGUAGE: Language = 'en';

/**
 * Extract language from URL path
 * e.g., "/en/blog/post" => "en"
 * e.g., "/es/docs/ref" => "es"
 */
export function getLanguageFromPath(pathname: string): Language {
  const regex = /^\/([a-z]{2})(?:\/|$)/;
  const match = regex.exec(pathname);
  const lang = match?.[1] as Language | undefined;
  return isSupportedLanguage(lang) ? lang : DEFAULT_LANGUAGE;
}

/**
 * Check if a language is supported
 */
function isSupportedLanguage(lang: string | undefined): lang is Language {
  return lang !== undefined && SUPPORTED_LANGUAGES.includes(lang as Language);
}

/**
 * Remove language prefix from path
 * e.g., "/en/blog/post" => "/blog/post"
 * e.g., "/es/blog/post" => "/blog/post"
 */
export function getPathWithoutLanguage(pathname: string): string {
  const regex = /^\/([a-z]{2})(.*)$/;
  const match = regex.exec(pathname);
  if (match) {
    return match[2] || '/';
  }
  return pathname;
}

/**
 * Get language name for display
 */
export function getLanguageName(lang: Language): string {
  const names: Record<Language, string> = {
    en: 'English',
    de: 'Deutsch',
    es: 'Español',
    fr: 'Français',
    ja: '日本語',
    ar: 'العربية',
    ru: 'Русский',
    tr: 'Türkçe',
    zh: '中文',
  };
  return names[lang];
}

/**
 * Get language flag emoji (optional but nice)
 */
export function getLanguageFlag(lang: Language): string {
  const flags: Record<Language, string> = {
    en: '🇬🇧',
    de: '🇩🇪',
    es: '🇪🇸',
    fr: '🇫🇷',
    ja: '🇯🇵',
    ar: '🇸🇦',
    ru: '🇷🇺',
    tr: '🇹🇷',
    zh: '🇨🇳',
  };
  return flags[lang];
}

/**
 * Generate static paths for language-prefixed pages (used in Astro getStaticPaths)
 */
export function getLanguagePaths() {
  return SUPPORTED_LANGUAGES.map((lang) => ({
    params: { lang },
    props: { lang },
  }));
}

/**
 * Get locale string for Open Graph and hreflang
 */
export function getLocale(lang: Language): string {
  const locales: Record<Language, string> = {
    en: 'en_US', de: 'de_DE', es: 'es_ES', fr: 'fr_FR', ja: 'ja_JP',
    ar: 'ar_SA', ru: 'ru_RU', tr: 'tr_TR', zh: 'zh_CN',
  };
  return locales[lang];
}
