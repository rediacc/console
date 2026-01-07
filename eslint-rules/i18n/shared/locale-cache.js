import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const DEFAULT_LOCALE_DIR = path.join(ROOT_DIR, 'packages/web/src/i18n/locales');

let cachedResources = new Map();
let cachedAllKeys = new Map();

/**
 * Load all JSON locale files from a directory
 * @param {string} localeDir - Path to locale directory (e.g., locales/en)
 * @returns {Map<string, object>} Map of namespace to parsed JSON
 */
export const loadLocaleResources = (localeDir) => {
  if (cachedResources.has(localeDir)) {
    return cachedResources.get(localeDir);
  }

  const resources = new Map();
  if (!fs.existsSync(localeDir)) {
    return resources;
  }

  const files = fs.readdirSync(localeDir);
  files.forEach((file) => {
    if (!file.endsWith('.json')) return;
    const namespace = path.basename(file, '.json');
    const filePath = path.join(localeDir, file);
    try {
      const contents = fs.readFileSync(filePath, 'utf8');
      resources.set(namespace, JSON.parse(contents));
    } catch {
      resources.set(namespace, null);
    }
  });

  cachedResources.set(localeDir, resources);
  return resources;
};

/**
 * Flatten nested object keys into dot-notation paths
 * @param {object} obj - The object to flatten
 * @param {string} prefix - Current key prefix
 * @returns {string[]} Array of flattened key paths
 */
export const flattenKeys = (obj, prefix = '') => {
  const keys = [];
  if (!obj || typeof obj !== 'object') return keys;

  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    const value = obj[key];
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...flattenKeys(value, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
};

/**
 * Get all flattened keys from all namespaces in a locale directory
 * @param {string} localeDir - Path to locale directory
 * @returns {Map<string, Set<string>>} Map of namespace to Set of flattened keys
 */
export const getAllLocaleKeys = (localeDir) => {
  if (cachedAllKeys.has(localeDir)) {
    return cachedAllKeys.get(localeDir);
  }

  const resources = loadLocaleResources(localeDir);
  const allKeys = new Map();

  for (const [namespace, data] of resources) {
    if (data) {
      allKeys.set(namespace, new Set(flattenKeys(data)));
    }
  }

  cachedAllKeys.set(localeDir, allKeys);
  return allKeys;
};

/**
 * Check if a key path exists in a resource object
 * @param {object} resource - The resource object
 * @param {string[]} segments - Key path segments
 * @returns {boolean} Whether the path exists
 */
export const hasPath = (resource, segments) => {
  if (!resource) return false;
  let current = resource;
  for (const segment of segments) {
    if (!Object.prototype.hasOwnProperty.call(current, segment)) {
      return false;
    }
    current = current[segment];
  }
  return true;
};

/**
 * Get value at a path in a resource object
 * @param {object} resource - The resource object
 * @param {string[]} segments - Key path segments
 * @returns {*} The value at the path or undefined
 */
export const getValueAtPath = (resource, segments) => {
  if (!resource) return undefined;
  let current = resource;
  for (const segment of segments) {
    if (!Object.prototype.hasOwnProperty.call(current, segment)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
};

/**
 * Get the root directory for the console project
 */
export const getRootDir = () => ROOT_DIR;

/**
 * Get the default locale directory
 */
export const getDefaultLocaleDir = () => DEFAULT_LOCALE_DIR;

/**
 * Get all supported language codes
 */
export const getSupportedLanguages = () => {
  const localesDir = DEFAULT_LOCALE_DIR;
  if (!fs.existsSync(localesDir)) return [];
  return fs.readdirSync(localesDir).filter((dir) => {
    const fullPath = path.join(localesDir, dir);
    return fs.statSync(fullPath).isDirectory();
  });
};

/**
 * Clear all caches (useful for testing or when files change)
 */
export const clearCache = () => {
  cachedResources.clear();
  cachedAllKeys.clear();
};
