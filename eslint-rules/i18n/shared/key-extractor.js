/**
 * Key Extractor Utility
 *
 * Scans TypeScript/JavaScript source files to extract translation keys used in t() calls.
 * Used by no-unused-keys rule to detect unused translations.
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * Cache for extracted keys, KEYED BY SOURCE DIRECTORY.
 *
 * It was a single unkeyed slot plus one timestamp until 2026-09-06, which meant
 * the second caller within the TTL got the FIRST caller's key set no matter
 * which directory it asked about. That is not hypothetical here: this repository
 * has three unrelated locale trees (packages/cli, private/account/web,
 * private/account), require-path-option.js exists precisely because no rule can
 * guess which one a config block means, and eslint.config.js is free to
 * configure no-unused-keys once per tree. Two blocks in one eslint run would
 * have made the second tree report against the first tree's usage, which shows
 * up as unused-key findings that are simply wrong, or as silence that is worse.
 *
 * The bug was latent only because the rule is currently 'off' everywhere. It was
 * found by writing the rule's first RuleTester spec: two fixtures in one process
 * returned identical results.
 */
const extractedKeysCache = new Map();
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

// Directories that never hold first-party source
const SKIPPED_DIRS = new Set(['node_modules', 'dist', '.git']);
const SOURCE_FILE_RE = /\.(ts|tsx|js|jsx)$/;

/**
 * Accumulate one directory entry: recurse into directories, collect source files.
 */
const collectSourceEntry = (entry, dir, files) => {
  const fullPath = path.join(dir, entry.name);

  if (entry.isDirectory()) {
    if (!SKIPPED_DIRS.has(entry.name)) {
      findSourceFiles(fullPath, files);
    }
    return;
  }

  if (entry.isFile() && SOURCE_FILE_RE.test(entry.name)) {
    files.push(fullPath);
  }
};

/**
 * Recursively find all TypeScript/JavaScript files in a directory
 */
const findSourceFiles = (dir, files = []) => {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    // Directory read error - skip
    return files;
  }

  for (const entry of entries) {
    collectSourceEntry(entry, dir, files);
  }

  return files;
};

/**
 * Extract all translation keys used in source files
 * Returns a Map of namespace -> Set of keys
 */
const recordUsedKey = (usedKeys, fullKey) => {
  // Parse namespace:key format
  let namespace = 'common';
  let key = fullKey;

  const colonIndex = fullKey.indexOf(':');
  if (colonIndex !== -1) {
    namespace = fullKey.slice(0, colonIndex);
    key = fullKey.slice(colonIndex + 1);
  }

  if (!usedKeys.has(namespace)) {
    usedKeys.set(namespace, new Set());
  }
  usedKeys.get(namespace).add(key);
};

export const extractUsedKeys = (sourceDir) => {
  // Check cache
  const now = Date.now();
  const cached = extractedKeysCache.get(sourceDir);
  if (cached && now - cached.timestamp < CACHE_TTL) {
    return cached.keys;
  }

  const usedKeys = new Map(); // namespace -> Set of keys
  const sourceFiles = findSourceFiles(sourceDir);

  for (const filePath of sourceFiles) {
    const fileKeys = extractKeysFromFile(filePath);

    for (const fullKey of fileKeys) {
      recordUsedKey(usedKeys, fullKey);
    }
  }

  // Update cache
  extractedKeysCache.set(sourceDir, { keys: usedKeys, timestamp: now });

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
    if (key.startsWith(`${usedKey}.`) || usedKey.startsWith(`${key}.`)) {
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
 * Clear the cache (useful for testing).
 *
 * Pass a directory to drop only that entry; pass nothing to drop all of them.
 */
export const clearKeyExtractorCache = (sourceDir) => {
  if (sourceDir === undefined) {
    extractedKeysCache.clear();
    return;
  }
  extractedKeysCache.delete(sourceDir);
};

export default {
  extractUsedKeys,
  isKeyUsed,
  getUsedKeysForNamespace,
  clearKeyExtractorCache,
};
