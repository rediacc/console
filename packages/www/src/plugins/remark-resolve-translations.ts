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

import type { Root, Strong, Text } from 'mdast';
import { visit } from 'unist-util-visit';

import {
  DEFAULT_LANGUAGE,
  extractLanguageFromContent,
  hasTranslationKeys,
  replaceTranslationKeys,
} from './translation-keys.mjs';

interface RemarkFile {
  data: Record<string, unknown>;
  // VFile.value is `string | Uint8Array` in newer @types/vfile. We only ever
  // read string content, but the type must accept both for assignability.
  value?: string | Uint8Array;
  path?: string;
}

/**
 * The resolution itself lives in `./translation-keys.mjs` so that
 * `scripts/generate-search-index.js` can use the SAME implementation. It could not import
 * this file: the generator runs as plain `node` from `astro.config.mjs`. When the two were
 * separate, the rendered page resolved every placeholder and the search index resolved
 * none, and each locale's index shipped 2,122 raw `{{t:...}}` strings to readers.
 *
 * This module keeps only the remark-specific half: finding the document's language, and
 * walking the mdast nodes that can carry a placeholder.
 */

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
    // Method 3: From file path (e.g., /docs/tr/architecture.md)
    else if (file.path) {
      const pathMatch = /\/docs\/([a-z]{2})\//.exec(file.path);
      if (pathMatch) {
        language = pathMatch[1];
      }
    }

    // Visit all text nodes and replace translation keys
    visit(tree, 'text', (node: Text) => {
      if (hasTranslationKeys(node.value)) {
        node.value = replaceTranslationKeys(node.value, language, file.path);
      }
    });

    // Also check inline code nodes (for cases like `{{t:key}}`)
    visit(tree, 'inlineCode', (node: { value: string }) => {
      if (hasTranslationKeys(node.value)) {
        node.value = replaceTranslationKeys(node.value, language, file.path);
      }
    });

    // Also check strong/emphasis nodes (for cases like **{{t:key}}**)
    visit(tree, 'strong', (node: Strong) => {
      for (const child of node.children) {
        if (child.type === 'text' && hasTranslationKeys(child.value)) {
          child.value = replaceTranslationKeys(child.value, language, file.path);
        }
      }
    });
  };
}
