/**
 * Language detection and normalization utilities.
 * Extracted from ContextServiceBase to keep file under max-lines.
 */

const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'] as const;

export function normalizeLanguage(lang: string): string {
  const base = lang.split('-')[0].split('_')[0].toLowerCase();
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(base) ? base : 'en';
}

export function detectSystemLanguage(): string {
  const sysLang = process.env.LANG ?? process.env.LC_ALL ?? '';
  return normalizeLanguage(sysLang);
}

export function isLanguageSupported(lang: string): boolean {
  const base = lang.split('-')[0].split('_')[0].toLowerCase();
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(base);
}

export function getSupportedLanguages(): string[] {
  return [...SUPPORTED_LANGUAGES];
}
