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
];
export const DEFAULT_LANGUAGE: Language = 'en';

/**
 * Extract language from URL path
 * e.g., "/en/blog/post" => "en"
 * e.g., "/es/docs/ref" => "es"
 */
export function getLanguageFromPath(pathname: string): Language {
  const match = pathname.match(/^\/([a-z]{2})(?:\/|$)/);
  const lang = match?.[1] as Language | undefined;
  return isSupportedLanguage(lang) ? lang : DEFAULT_LANGUAGE;
}

/**
 * Check if a language is supported
 */
export function isSupportedLanguage(lang: string | undefined): lang is Language {
  return lang !== undefined && SUPPORTED_LANGUAGES.includes(lang as Language);
}

/**
 * Get all available translations for a given slug
 * Useful for building language switchers
 */
export function getAvailableTranslations(
  slug: string,
  allPosts: CollectionEntry[],
  collection: 'blog' | 'docs'
): { lang: Language; url: string }[] {
  const baseSlug = slug.split('/').pop() ?? slug;
  const translations = allPosts
    .filter((post) => post.slug === baseSlug && post.collection === collection)
    .map((post) => ({
      lang: post.data.language ?? DEFAULT_LANGUAGE,
      url: `/${post.data.language ?? DEFAULT_LANGUAGE}/${collection}/${post.slug}`,
    }));

  // If no translations found, return empty array
  return translations.length > 0 ? translations : [];
}

/**
 * Generate localized URL for a path
 * e.g., generateLocalizedPath("/blog/post", "es") => "/es/blog/post"
 */
export function generateLocalizedPath(path: string, lang: Language): string {
  if (lang === DEFAULT_LANGUAGE && !path.startsWith('/')) {
    return `/${lang}${path}`;
  }
  if (lang !== DEFAULT_LANGUAGE) {
    return `/${lang}${path}`;
  }
  return path;
}

/**
 * Remove language prefix from path
 * e.g., "/en/blog/post" => "/blog/post"
 * e.g., "/es/blog/post" => "/blog/post"
 */
export function getPathWithoutLanguage(pathname: string): string {
  const match = pathname.match(/^\/([a-z]{2})(.*)$/);
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
