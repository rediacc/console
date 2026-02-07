import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_LOCALE_DIR = path.join(ROOT_DIR, 'packages/web/src/i18n/locales/en');

let cachedResources = null;
let cachedLocaleDir = null;

const loadResources = (localeDir) => {
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
      // If JSON is malformed, treat as missing.
      resources.set(namespace, null);
    }
  });

  return resources;
};

const getResources = (localeDir) => {
  if (!cachedResources || cachedLocaleDir !== localeDir) {
    cachedResources = loadResources(localeDir);
    cachedLocaleDir = localeDir;
  }
  return cachedResources;
};

const getStringValue = (node) => {
  if (!node) return null;
  if (node.type === 'Literal' && typeof node.value === 'string') {
    return node.value;
  }
  if (node.type === 'TemplateLiteral' && node.expressions.length === 0) {
    return node.quasis[0]?.value?.cooked ?? null;
  }
  return null;
};

const extractNamespaces = (node) => {
  if (!node) return null;
  if (node.type === 'Literal' && typeof node.value === 'string') {
    return [node.value];
  }
  if (node.type === 'ArrayExpression') {
    const namespaces = node.elements
      .map((el) => (el ? getStringValue(el) : null))
      .filter((value) => typeof value === 'string');
    return namespaces.length > 0 ? namespaces : null;
  }
  return null;
};

const extractNamespacesFromOptions = (node) => {
  if (!node || node.type !== 'ObjectExpression') return null;
  for (const prop of node.properties) {
    if (prop.type !== 'Property') continue;
    const keyName =
      prop.key.type === 'Identifier' ? prop.key.name : prop.key.value;
    if (keyName !== 'ns') continue;
    return extractNamespaces(prop.value);
  }
  return null;
};

const hasDefaultValue = (node) => {
  if (!node || node.type !== 'ObjectExpression') return false;
  return node.properties.some((prop) => {
    if (prop.type !== 'Property') return false;
    const keyName =
      prop.key.type === 'Identifier' ? prop.key.name : prop.key.value;
    return keyName === 'defaultValue';
  });
};

const splitKey = (key) => {
  const colonIndex = key.indexOf(':');
  if (colonIndex === -1) {
    return { namespace: null, path: key };
  }
  return {
    namespace: key.slice(0, colonIndex),
    path: key.slice(colonIndex + 1),
  };
};

// Patterns that are clearly not translation keys
const isNotTranslationKey = (key) => {
  // Shared namespace keys - validated in packages/shared/src/i18n/locales/
  if (key.startsWith('shared:')) return true;
  // Node.js built-in module specifiers (e.g., node:fs, node:path, node:sea)
  if (key.startsWith('node:')) return true;
  // Commander event names (e.g., command:*)
  if (key === 'command:*') return true;
  // URLs (http, https, or any protocol like rediacc://)
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(key)) return true;
  // Date/time format patterns (e.g., HH:mm:ss, YYYY-MM-DD, YYYY-MM-DDTHH:mm:ss)
  if (/^[YMDHhmsaAzZT\-/:.\s]+$/.test(key)) return true;
  // ISO 8601 date strings (e.g., 2023-01-01T00:00:00Z)
  if (/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?Z?$/.test(key)) return true;
  // JSON arrays or objects
  if (/^\s*[\[{]/.test(key)) return true;
  // Log-style prefixed messages (e.g., "[API Connection] DEBUG...")
  if (/^\[.+\]\s/.test(key)) return true;
  // Pure numbers or punctuation
  if (/^[\d\s.,;:!?-]+$/.test(key)) return true;
  // Commander option flags (e.g., --extra-machine <name:ip:user>)
  if (/^-/.test(key)) return true;
  return false;
};

const hasPath = (resource, segments) => {
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

/** @type {import('eslint').Rule.RuleModule} */
export const requireTranslation = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Require translation keys to exist in en locale files',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          localeDir: { type: 'string' },
          ignoreDefaultValue: { type: 'boolean' },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      missingKey: 'Missing translation key "{{key}}" in en locale files.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localeDir = options.localeDir
      ? path.resolve(ROOT_DIR, options.localeDir)
      : DEFAULT_LOCALE_DIR;
    const ignoreDefaultValue = options.ignoreDefaultValue === true;
    const resources = getResources(localeDir);

    const tBindings = [];

    const recordBinding = (name, namespaces, node) => {
      if (!name || !namespaces) return;
      const scope = context.sourceCode.getScope(node);
      const scopeRange = scope?.block?.range ?? node.range;
      tBindings.push({
        name,
        namespaces,
        scopeRange,
      });
    };

    const findNamespacesForIdentifier = (name, node) => {
      const position = node.range?.[0] ?? 0;
      const candidates = tBindings.filter(
        (binding) =>
          binding.name === name &&
          binding.scopeRange &&
          position >= binding.scopeRange[0] &&
          position <= binding.scopeRange[1]
      );
      if (candidates.length === 0) return null;
      // Prefer the smallest scope to handle shadowing.
      candidates.sort(
        (a, b) =>
          a.scopeRange[1] - a.scopeRange[0] - (b.scopeRange[1] - b.scopeRange[0])
      );
      return candidates[0].namespaces;
    };

    const reportMissingKey = (node, key) => {
      context.report({
        node,
        messageId: 'missingKey',
        data: { key },
      });
    };

    return {
      VariableDeclarator(node) {
        if (!node.init) return;

        let callNode = null;
        if (node.init.type === 'CallExpression') {
          callNode = node.init;
        } else if (
          node.init.type === 'MemberExpression' &&
          node.init.property?.type === 'Identifier' &&
          node.init.property.name === 't' &&
          node.init.object.type === 'CallExpression'
        ) {
          callNode = node.init.object;
        }

        if (!callNode || callNode.callee.type !== 'Identifier') return;
        if (callNode.callee.name !== 'useTranslation') return;

        const namespaces = extractNamespaces(callNode.arguments[0]);

        if (node.id.type === 'ObjectPattern') {
          node.id.properties.forEach((prop) => {
            if (prop.type !== 'Property') return;
            if (prop.key.type !== 'Identifier' || prop.key.name !== 't') return;

            if (prop.value.type === 'Identifier') {
              recordBinding(prop.value.name, namespaces, node);
            } else if (
              prop.value.type === 'AssignmentPattern' &&
              prop.value.left.type === 'Identifier'
            ) {
              recordBinding(prop.value.left.name, namespaces, node);
            }
          });
        }

        if (node.id.type === 'Identifier' && node.init.type === 'MemberExpression') {
          recordBinding(node.id.name, namespaces, node);
        }
      },

      CallExpression(node) {
        const keyNode = node.arguments?.[0];
        const keyValue = getStringValue(keyNode);
        if (!keyValue) return;

        // Skip values that are clearly not translation keys
        if (isNotTranslationKey(keyValue)) return;

        const { namespace, path: keyPath } = splitKey(keyValue);
        const optionArg = node.arguments?.[1];

        if (ignoreDefaultValue && hasDefaultValue(optionArg)) {
          return;
        }

        let namespaces = null;

        if (namespace) {
          namespaces = [namespace];
        } else {
          const nsFromOptions = extractNamespacesFromOptions(optionArg);
          if (nsFromOptions) {
            namespaces = nsFromOptions;
          }
        }

        if (!namespaces) {
          if (node.callee.type === 'Identifier') {
            namespaces = findNamespacesForIdentifier(node.callee.name, node);
          }
        }

        if (!namespaces || namespaces.length === 0) return;

        const segments = keyPath.split('.').filter(Boolean);
        if (segments.length === 0) return;

        const exists = namespaces.some((ns) =>
          hasPath(resources.get(ns), segments)
        );
        if (!exists) {
          reportMissingKey(keyNode, keyValue);
        }
      },
    };
  },
};
