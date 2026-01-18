/**
 * Remark plugin to resolve {{t:namespace.key}} patterns in markdown content.
 *
 * This plugin transforms inline translation key references to their resolved values
 * at build time, pulling translations from the web package's locale files.
 *
 * Example:
 *   Input:  Click the **{{t:organization.users.modals.createTitle}}** button
 *   Output: Click the **Create User** button (for English)
 *           Click the **Benutzer erstellen** button (for German)
 *
 * The language is extracted from the document's frontmatter `language` field.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { visit } from 'unist-util-visit';
import type { Root, Text } from 'mdast';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Path to web locales (relative to this plugin at packages/www/src/plugins/)
const WEB_LOCALES_PATH = path.resolve(__dirname, '../../../web/src/i18n/locales');

// Default language when not specified
const DEFAULT_LANGUAGE = 'en';

// Pattern to match {{t:namespace.key.path}}
const TRANSLATION_KEY_PATTERN = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

// Cache for loaded translation files
const translationCache = new Map<string, Record<string, unknown>>();

/**
 * Load a translation namespace file for a given language
 */
function loadTranslationFile(namespace: string, lang: string): Record<string, unknown> | null {
  const cacheKey = `${lang}/${namespace}`;

  if (translationCache.has(cacheKey)) {
    return translationCache.get(cacheKey) ?? null;
  }

  const filePath = path.join(WEB_LOCALES_PATH, lang, `${namespace}.json`);

  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    const translations = JSON.parse(content) as Record<string, unknown>;
    translationCache.set(cacheKey, translations);
    return translations;
  } catch {
    console.error(`Failed to load translation file: ${filePath}`);
    return null;
  }
}

/**
 * Resolve a nested key path in a translation object
 * e.g., "users.modals.createTitle" -> translations.users.modals.createTitle
 */
function resolveKeyPath(translations: Record<string, unknown>, keyPath: string): string | null {
  const keys = keyPath.split('.');
  let current: unknown = translations;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return null;
    }
    current = (current as Record<string, unknown>)[key];
  }

  if (typeof current === 'string') {
    return current;
  }

  return null;
}

/**
 * Get a translation value for a full key (namespace.keyPath)
 */
function getTranslation(namespace: string, keyPath: string, lang: string): string | null {
  const translations = loadTranslationFile(namespace, lang);
  if (!translations) {
    return null;
  }
  return resolveKeyPath(translations, keyPath);
}

/**
 * Extract language from frontmatter content
 */
function extractLanguageFromContent(content: string): string {
  // Match frontmatter block
  const frontmatterMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
  if (!frontmatterMatch) {
    return DEFAULT_LANGUAGE;
  }

  const frontmatter = frontmatterMatch[1];
  // Match language field
  const languageMatch = /^language:\s*['"]?([a-z]{2})['"]?\s*$/m.exec(frontmatter);
  if (languageMatch) {
    return languageMatch[1];
  }

  return DEFAULT_LANGUAGE;
}

/**
 * Replace all {{t:key}} patterns in a string with resolved translations
 */
function replaceTranslationKeys(text: string, lang: string, filePath?: string): string {
  return text.replace(TRANSLATION_KEY_PATTERN, (match, namespace, keyPath) => {
    const resolved = getTranslation(namespace, keyPath, lang);
    if (resolved === null) {
      const location = filePath ? ` in ${filePath}` : '';
      // Log warning but don't throw - allows build to continue
      console.warn(
        `[remark-resolve-translations] Translation key not found: ${namespace}.${keyPath} for language '${lang}'${location}`
      );
      // Return the original pattern so it's visible in output (helps debugging)
      return match;
    }
    return resolved;
  });
}

export interface RemarkResolveTranslationsOptions {
  /** Fallback language if not found in frontmatter */
  defaultLanguage?: string;
}

/**
 * Remark plugin that resolves {{t:namespace.key}} patterns in markdown content
 */
export function remarkResolveTranslations(options: RemarkResolveTranslationsOptions = {}) {
  const defaultLang = options.defaultLanguage ?? DEFAULT_LANGUAGE;

  return function transformer(tree: Root, file: { value?: string; path?: string }) {
    // Extract language from file content (frontmatter)
    let language = defaultLang;
    if (file.value && typeof file.value === 'string') {
      language = extractLanguageFromContent(file.value);
    }

    // Visit all text nodes and replace translation keys
    visit(tree, 'text', (node: Text) => {
      if (TRANSLATION_KEY_PATTERN.test(node.value)) {
        // Reset lastIndex since we're using the pattern in test and replace
        TRANSLATION_KEY_PATTERN.lastIndex = 0;
        node.value = replaceTranslationKeys(node.value, language, file.path);
      }
    });

    // Also check inline code nodes (for cases like `{{t:key}}`)
    visit(tree, 'inlineCode', (node: { value: string }) => {
      if (TRANSLATION_KEY_PATTERN.test(node.value)) {
        TRANSLATION_KEY_PATTERN.lastIndex = 0;
        node.value = replaceTranslationKeys(node.value, language, file.path);
      }
    });
  };
}
