import type { Language } from './types';

interface CollectionEntry {
  slug: string;
  collection: string;
  data: {
    language?: Language;
  };
}

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
