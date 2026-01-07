/**
 * Key Extractor Utility
 *
 * Scans TypeScript/JavaScript source files to extract translation keys used in t() calls.
 * Used by no-unused-keys rule to detect unused translations.
 */

import fs from 'node:fs';
import path from 'node:path';

// Cache for extracted keys
let extractedKeysCache = null;
let cacheTimestamp = 0;
const CACHE_TTL = 30000; // 30 seconds cache TTL

/**
 * Simple regex-based extraction of t() call keys
 * Handles: t('key'), t("key"), t('namespace:key')
 */
const T_CALL_REGEX = /\bt\s*\(\s*(['"`])([^'"`]+)\1/g;

/**
 * Extract translation keys from a single file
 */
const extractKeysFromFile = (filePath) => {
  const keys = new Set();

  try {
    const content = fs.readFileSync(filePath, 'utf-8');

    // Extract keys from t() calls
    let match;
    while ((match = T_CALL_REGEX.exec(content)) !== null) {
      const key = match[2];
      // Skip template literals with expressions
      if (!key.includes('${')) {
        keys.add(key);
      }
    }
    // Reset regex lastIndex for next file
    T_CALL_REGEX.lastIndex = 0;
  } catch {
    // File read error - skip
  }

  return keys;
};

/**
 * Recursively find all TypeScript/JavaScript files in a directory
 */
const findSourceFiles = (dir, files = []) => {
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        // Skip node_modules and dist directories
        if (entry.name !== 'node_modules' && entry.name !== 'dist' && entry.name !== '.git') {
          findSourceFiles(fullPath, files);
        }
      } else if (entry.isFile()) {
        // Include .ts, .tsx, .js, .jsx files
        if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
          files.push(fullPath);
        }
      }
    }
  } catch {
    // Directory read error - skip
  }

  return files;
};

/**
 * Extract all translation keys used in source files
 * Returns a Map of namespace -> Set of keys
 */
export const extractUsedKeys = (sourceDir) => {
  // Check cache
  const now = Date.now();
  if (extractedKeysCache && (now - cacheTimestamp) < CACHE_TTL) {
    return extractedKeysCache;
  }

  const usedKeys = new Map(); // namespace -> Set of keys
  const sourceFiles = findSourceFiles(sourceDir);

  for (const filePath of sourceFiles) {
    const fileKeys = extractKeysFromFile(filePath);

    for (const fullKey of fileKeys) {
      // Parse namespace:key format
      let namespace = 'common';
      let key = fullKey;

      if (fullKey.includes(':')) {
        const colonIndex = fullKey.indexOf(':');
        namespace = fullKey.slice(0, colonIndex);
        key = fullKey.slice(colonIndex + 1);
      }

      if (!usedKeys.has(namespace)) {
        usedKeys.set(namespace, new Set());
      }
      usedKeys.get(namespace).add(key);
    }
  }

  // Update cache
  extractedKeysCache = usedKeys;
  cacheTimestamp = now;

  return usedKeys;
};

/**
 * Check if a specific key is used in the source files
 */
export const isKeyUsed = (sourceDir, namespace, key) => {
  const usedKeys = extractUsedKeys(sourceDir);
  const namespaceKeys = usedKeys.get(namespace);

  if (!namespaceKeys) {
    return false;
  }

  // Check exact match
  if (namespaceKeys.has(key)) {
    return true;
  }

  // Check if any used key is a prefix of this key (for nested objects)
  // e.g., if t('dashboard.widgets') is used, dashboard.widgets.title is considered used
  for (const usedKey of namespaceKeys) {
    if (key.startsWith(usedKey + '.') || usedKey.startsWith(key + '.')) {
      return true;
    }
  }

  return false;
};

/**
 * Get all used keys for a namespace
 */
export const getUsedKeysForNamespace = (sourceDir, namespace) => {
  const usedKeys = extractUsedKeys(sourceDir);
  return usedKeys.get(namespace) || new Set();
};

/**
 * Clear the cache (useful for testing)
 */
export const clearKeyExtractorCache = () => {
  extractedKeysCache = null;
  cacheTimestamp = 0;
};

export default {
  extractUsedKeys,
  isKeyUsed,
  getUsedKeysForNamespace,
  clearKeyExtractorCache,
};
