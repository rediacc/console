/**
 * ESLint rule to detect unused translation keys in locale JSON files.
 * Scans source files for t() calls and reports keys that are never used.
 */

import path from 'node:path';
import { extractUsedKeys } from './shared/key-extractor.js';

/** @type {import('eslint').Rule.RuleModule} */
export const noUnusedKeys = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow unused translation keys in locale files',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          sourceDir: {
            type: 'string',
            description: 'Path to source directory to scan for t() calls',
          },
          ignorePatterns: {
            type: 'array',
            items: { type: 'string' },
            description: 'Key patterns to ignore (regex strings)',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      unusedKey: 'Translation key "{{key}}" is not used in any source file.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const sourceDir = options.sourceDir || 'packages/web/src';
    const ignorePatterns = (options.ignorePatterns || []).map((p) => new RegExp(p));

    // Resolve paths
    const projectRoot = process.cwd();
    const absoluteSourceDir = path.isAbsolute(sourceDir)
      ? sourceDir
      : path.join(projectRoot, sourceDir);

    // Get namespace from filename
    const filename = context.filename || context.getFilename();
    const namespace = path.basename(filename, '.json');

    // Extract all used keys from source files
    const usedKeysMap = extractUsedKeys(absoluteSourceDir);
    const usedKeys = usedKeysMap.get(namespace) || new Set();

    /**
     * Check if a key matches any ignore pattern
     */
    const isIgnored = (key) => {
      return ignorePatterns.some((pattern) => pattern.test(key));
    };

    /**
     * Check if a key or any of its parent paths are used
     */
    const isKeyOrParentUsed = (key) => {
      // Check exact match
      if (usedKeys.has(key)) {
        return true;
      }

      // Check if this is a parent of a used key
      for (const usedKey of usedKeys) {
        if (usedKey.startsWith(key + '.')) {
          return true;
        }
      }

      // Check if any parent path is used (means the whole object is accessed)
      const parts = key.split('.');
      for (let i = 1; i < parts.length; i++) {
        const parentPath = parts.slice(0, i).join('.');
        if (usedKeys.has(parentPath)) {
          return true;
        }
      }

      return false;
    };

    /**
     * Flatten keys from a JSON object node
     */
    const flattenKeys = (node, prefix = '') => {
      const keys = [];

      if (!node || node.type !== 'Object') return keys;

      const members = node.body?.members || [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key = member.name?.type === 'String'
          ? member.name.value
          : member.name?.name;

        if (!key) continue;

        const fullPath = prefix ? `${prefix}.${key}` : key;

        if (member.value?.type === 'Object') {
          // Recursively check nested objects
          keys.push(...flattenKeys(member.value, fullPath));
        } else {
          // Leaf value - this is a translation key
          keys.push({ key: fullPath, node: member.name });
        }
      }

      return keys;
    };

    return {
      Document(node) {
        if (node.body?.type !== 'Object') return;

        const allKeys = flattenKeys(node.body);

        for (const { key, node: keyNode } of allKeys) {
          // Skip ignored patterns
          if (isIgnored(key)) {
            continue;
          }

          // Check if key is used
          if (!isKeyOrParentUsed(key)) {
            context.report({
              node: keyNode,
              messageId: 'unusedKey',
              data: { key },
            });
          }
        }
      },
    };
  },
};

export default noUnusedKeys;
