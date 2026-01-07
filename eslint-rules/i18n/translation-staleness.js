/**
 * ESLint rule to detect stale translations by comparing English values against stored hashes.
 *
 * This rule automatically calculates CRC32 hashes of English translation values at lint time
 * and compares them with stored hashes in .translation-hashes.json.
 *
 * If English values have changed since the last hash generation, the rule reports an error,
 * indicating that translations need to be updated.
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * Calculate CRC32 hash of a string (IEEE polynomial)
 * Returns 8-character lowercase hex string
 */
const crc32Table = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c;
  }
  return table;
})();

const crc32 = (str) => {
  let crc = 0xffffffff;
  for (let i = 0; i < str.length; i++) {
    const byte = str.charCodeAt(i) & 0xff;
    crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return ((crc ^ 0xffffffff) >>> 0).toString(16).padStart(8, '0');
};

/**
 * Flatten a JSON object to get all leaf key-value pairs
 */
const flattenKeyValues = (obj, prefix = '') => {
  const result = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flattenKeyValues(value, fullPath));
    } else if (typeof value === 'string') {
      result[fullPath] = value;
    }
  }

  return result;
};

/**
 * Load hash manifest file
 */
const loadHashManifest = (hashFilePath) => {
  try {
    if (!fs.existsSync(hashFilePath)) {
      return null;
    }
    const content = JSON.parse(fs.readFileSync(hashFilePath, 'utf-8'));
    return content.hashes || {};
  } catch {
    return null;
  }
};

/**
 * Recursively extract key-value pairs from AST
 */
const extractKeyValuesFromAst = (node, prefix = '') => {
  const result = {};

  if (!node || node.type !== 'Object') return result;

  for (const member of node.body?.members || []) {
    if (member.type !== 'Member') continue;

    const key = member.name?.type === 'String'
      ? member.name.value
      : member.name?.name;

    if (!key) continue;

    const fullPath = prefix ? `${prefix}.${key}` : key;
    const value = member.value;

    if (!value) continue;

    if (value.type === 'Object') {
      Object.assign(result, extractKeyValuesFromAst(value, fullPath));
    } else if (value.type === 'String') {
      result[fullPath] = {
        value: value.value,
        node: value,
      };
    }
  }

  return result;
};

/** @type {import('eslint').Rule.RuleModule} */
export const translationStaleness = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Detect stale translations by comparing English values against stored hashes',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          hashFileName: {
            type: 'string',
            default: '.translation-hashes.json',
            description: 'Name of the hash manifest file',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      staleTranslation: 'Translation outdated: "{{key}}". English value changed (stored: {{storedHash}}, current: {{currentHash}}). Update translations and run: npm run i18n:update-hashes',
      missingHashFile: 'Hash manifest file not found: {{path}}. Run: npm run i18n:generate-hashes',
      newKey: 'New translation key: "{{key}}" (hash: {{currentHash}}). Run: npm run i18n:update-hashes',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const hashFileName = options.hashFileName || '.translation-hashes.json';

    // Get current file info
    const filename = context.filename || context.getFilename();
    const fileDir = path.dirname(filename);
    const currentLang = path.basename(fileDir);

    // Only run on English files
    if (currentLang !== 'en') {
      return {};
    }

    // Determine hash file location (in the locales root, not in en/)
    const localesRoot = path.dirname(fileDir);
    const hashFilePath = path.join(localesRoot, hashFileName);

    return {
      Document(node) {
        if (node.body?.type !== 'Object') return;

        // Load stored hashes
        const storedHashes = loadHashManifest(hashFilePath);

        if (storedHashes === null) {
          // Hash file doesn't exist - report but don't block
          context.report({
            node,
            messageId: 'missingHashFile',
            data: { path: hashFilePath },
          });
          return;
        }

        // Extract key-values from current file AST
        const keyValues = extractKeyValuesFromAst(node.body);

        // Get the namespace from filename (e.g., 'common' from 'common.json')
        const namespace = path.basename(filename, '.json');

        // Compare each key's current hash with stored hash
        for (const [key, { value, node: valueNode }] of Object.entries(keyValues)) {
          // For web package, keys in hashes are prefixed with namespace
          // For CLI package, they're flat (single file)
          // Check both formats for compatibility
          const fullKey = namespace !== 'cli' ? `${namespace}.${key}` : key;
          const currentHash = crc32(value);

          // Try full key first, then bare key
          let storedHash = storedHashes[fullKey] || storedHashes[key];

          if (storedHash === undefined) {
            // New key that doesn't exist in hash manifest
            context.report({
              node: valueNode,
              messageId: 'newKey',
              data: {
                key: fullKey,
                currentHash,
              },
            });
          } else if (storedHash !== currentHash) {
            // Hash mismatch - English value changed
            context.report({
              node: valueNode,
              messageId: 'staleTranslation',
              data: {
                key: fullKey,
                storedHash,
                currentHash,
              },
            });
          }
        }
      },
    };
  },
};

export default translationStaleness;
