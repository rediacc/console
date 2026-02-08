/**
 * ESLint rule to enforce minimum translation coverage across languages.
 * Reports if any language falls below the specified coverage threshold.
 */

import fs from 'node:fs';
import path from 'node:path';

// Cache for locale coverage data
let coverageCache = new Map();

/**
 * Get all supported language directories
 */
const getLanguageDirectories = (localesDir) => {
  try {
    const entries = fs.readdirSync(localesDir, { withFileTypes: true });
    return entries
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
  } catch {
    return [];
  }
};

/**
 * Flatten a JSON object to count all leaf keys
 */
const countKeys = (obj, prefix = '') => {
  let count = 0;

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      count += countKeys(value, fullPath);
    } else {
      count += 1;
    }
  }

  return count;
};

/**
 * Load and count keys from a locale file
 */
const getKeyCount = (filePath) => {
  const cacheKey = `count:${filePath}`;
  if (coverageCache.has(cacheKey)) {
    return coverageCache.get(cacheKey);
  }

  try {
    const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const count = countKeys(content);
    coverageCache.set(cacheKey, count);
    return count;
  } catch {
    return 0;
  }
};

/**
 * Calculate coverage for all languages
 */
const calculateCoverage = (localesDir, namespace, sourceLanguage) => {
  const languages = getLanguageDirectories(localesDir);
  const coverage = {};

  // Get source language count
  const sourcePath = path.join(localesDir, sourceLanguage, `${namespace}.json`);
  const sourceCount = getKeyCount(sourcePath);

  if (sourceCount === 0) {
    return { sourceCount: 0, languages: {} };
  }

  for (const lang of languages) {
    if (lang === sourceLanguage) continue;

    const langPath = path.join(localesDir, lang, `${namespace}.json`);
    if (!fs.existsSync(langPath)) {
      coverage[lang] = { count: 0, total: sourceCount, percentage: 0 };
      continue;
    }

    const langCount = getKeyCount(langPath);
    // Coverage is capped at 100% (extra keys don't increase coverage)
    const percentage = Math.min(100, Math.round((langCount / sourceCount) * 100));

    coverage[lang] = {
      count: langCount,
      total: sourceCount,
      percentage,
    };
  }

  return { sourceCount, languages: coverage };
};

/** @type {import('eslint').Rule.RuleModule} */
export const translationCoverage = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Enforce minimum translation coverage across all languages',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          localesDir: {
            type: 'string',
            description: 'Path to the locales directory',
          },
          sourceLanguage: {
            type: 'string',
            default: 'en',
            description: 'Source language (100% coverage baseline)',
          },
          minimumCoverage: {
            type: 'number',
            default: 80,
            minimum: 0,
            maximum: 100,
            description: 'Minimum required coverage percentage',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      lowCoverage: '{{language}} translation coverage is {{percentage}}% ({{count}}/{{total}} keys). Minimum required: {{minimum}}%.',
      missingFile: '{{language}} is missing translation file for namespace "{{namespace}}".',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localesDir = options.localesDir || 'packages/web/src/i18n/locales';
    const sourceLanguage = options.sourceLanguage || 'en';
    const minimumCoverage = options.minimumCoverage ?? 80;

    // Resolve paths
    const projectRoot = process.cwd();
    const absoluteLocalesDir = path.isAbsolute(localesDir)
      ? localesDir
      : path.join(projectRoot, localesDir);

    // Get current file info
    const filename = context.filename;
    const namespace = path.basename(filename, '.json');
    const currentLang = path.basename(path.dirname(filename));

    // Only run on source language files (English)
    if (currentLang !== sourceLanguage) {
      return {};
    }

    return {
      Document(node) {
        if (node.body?.type !== 'Object') return;

        const { sourceCount, languages } = calculateCoverage(
          absoluteLocalesDir,
          namespace,
          sourceLanguage
        );

        if (sourceCount === 0) {
          return; // Empty source file
        }

        for (const [lang, data] of Object.entries(languages)) {
          if (data.count === 0 && data.total > 0) {
            // Missing translation file
            context.report({
              node,
              messageId: 'missingFile',
              data: {
                language: lang,
                namespace,
              },
            });
          } else if (data.percentage < minimumCoverage) {
            // Low coverage
            context.report({
              node,
              messageId: 'lowCoverage',
              data: {
                language: lang,
                percentage: data.percentage,
                count: data.count,
                total: data.total,
                minimum: minimumCoverage,
              },
            });
          }
        }
      },
    };
  },
};

export default translationCoverage;
