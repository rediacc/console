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
import type { Root, Strong, Text } from 'mdast';
import { visit } from 'unist-util-visit';

interface RemarkFile {
  data: Record<string, unknown>;
  value?: string;
  path?: string;
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Path to web locales (relative to this plugin at packages/www/src/plugins/)
const WEB_LOCALES_PATH = path.resolve(__dirname, '../../../web/src/i18n/locales');

// Path to CLI locales (for resolving CLI translation keys)
const CLI_LOCALES_PATH = path.resolve(__dirname, '../../../cli/src/i18n/locales');

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

  // Try web locales first, then CLI locales
  const paths = [
    path.join(WEB_LOCALES_PATH, lang, `${namespace}.json`),
    path.join(CLI_LOCALES_PATH, lang, `${namespace}.json`),
  ];

  for (const filePath of paths) {
    if (fs.existsSync(filePath)) {
      try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const translations = JSON.parse(content) as Record<string, unknown>;
        translationCache.set(cacheKey, translations);
        return translations;
      } catch {
        console.error(`Failed to load translation file: ${filePath}`);
      }
    }
  }

  return null;
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

  return function transformer(tree: Root, file: RemarkFile) {
    // Extract language from file content (frontmatter)
    let language = defaultLang;

    // Try multiple methods to get the language
    // Method 1: From file.data.astro.frontmatter (Astro content collections)
    const astroData = file.data.astro as { frontmatter?: { language?: string } } | undefined;
    if (astroData?.frontmatter?.language) {
      language = astroData.frontmatter.language;
    }
    // Method 2: From raw file content (fallback)
    else if (file.value && typeof file.value === 'string') {
      language = extractLanguageFromContent(file.value);
    }
    // Method 3: From file path (e.g., /docs/tr/web-application.md)
    else if (file.path) {
      const pathMatch = /\/docs\/([a-z]{2})\//.exec(file.path);
      if (pathMatch) {
        language = pathMatch[1];
      }
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

    // Also check strong/emphasis nodes (for cases like **{{t:key}}**)
    visit(tree, 'strong', (node: Strong) => {
      for (const child of node.children) {
        if (child.type === 'text' && TRANSLATION_KEY_PATTERN.test(child.value)) {
          TRANSLATION_KEY_PATTERN.lastIndex = 0;
          child.value = replaceTranslationKeys(child.value, language, file.path);
        }
      }
    });
  };
}
