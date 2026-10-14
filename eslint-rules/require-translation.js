import { resolveRequiredDirOption } from './i18n/shared/require-path-option.js';
import {
  ROOT_DIR,
  getResources,
  getStringValue,
  hasPath,
  isNotTranslationKey,
  splitKey,
} from './translation-helpers.js';

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
  if (node?.type !== 'ObjectExpression') return null;
  for (const prop of node.properties) {
    if (prop.type !== 'Property') continue;
    const keyName = prop.key.type === 'Identifier' ? prop.key.name : prop.key.value;
    if (keyName !== 'ns') continue;
    return extractNamespaces(prop.value);
  }
  return null;
};

const hasDefaultValue = (node) => {
  if (node?.type !== 'ObjectExpression') return false;
  return node.properties.some((prop) => {
    if (prop.type !== 'Property') return false;
    const keyName = prop.key.type === 'Identifier' ? prop.key.name : prop.key.value;
    return keyName === 'defaultValue';
  });
};

function recordBinding(context, tBindings, name, namespaces, node) {
  if (!name || !namespaces) return;
  const scope = context.sourceCode.getScope(node);
  const scopeRange = scope?.block?.range ?? node.range;
  tBindings.push({
    name,
    namespaces,
    scopeRange,
  });
}

function findNamespacesForIdentifier(tBindings, name, node) {
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
    (a, b) => a.scopeRange[1] - a.scopeRange[0] - (b.scopeRange[1] - b.scopeRange[0])
  );
  return candidates[0].namespaces;
}

/**
 * Namespaces to look the key up in: the one written into the key itself,
 * else the one passed in t()'s options, else the one the `t` binding was
 * created with. null when none of the three answers.
 */
function resolveNamespaces(tBindings, node, namespace, optionArg) {
  if (namespace) return [namespace];

  const nsFromOptions = extractNamespacesFromOptions(optionArg);
  if (nsFromOptions) return nsFromOptions;

  if (node.callee.type === 'Identifier') {
    return findNamespacesForIdentifier(tBindings, node.callee.name, node);
  }
  return null;
}

/** The `useTranslation()` call a declarator initialiser wraps (directly, or through `.t`), else null. */
function translationHookCallOf(init) {
  let callNode = null;
  if (init.type === 'CallExpression') {
    callNode = init;
  } else if (
    init.type === 'MemberExpression' &&
    init.property?.type === 'Identifier' &&
    init.property.name === 't' &&
    init.object.type === 'CallExpression'
  ) {
    callNode = init.object;
  }

  if (callNode?.callee.type !== 'Identifier') return null;
  if (callNode.callee.name !== 'useTranslation') return null;
  return callNode;
}

/** The local name a destructured `t` property is bound to, else null. */
function destructuredTName(prop) {
  if (prop.type !== 'Property') return null;
  if (prop.key.type !== 'Identifier' || prop.key.name !== 't') return null;

  if (prop.value.type === 'Identifier') return prop.value.name;
  if (prop.value.type === 'AssignmentPattern' && prop.value.left.type === 'Identifier') {
    return prop.value.left.name;
  }
  return null;
}

function recordTranslationBindings(env, node) {
  if (!node.init) return;

  const callNode = translationHookCallOf(node.init);
  if (!callNode) return;

  const { context, tBindings } = env;
  const namespaces = extractNamespaces(callNode.arguments[0]);

  if (node.id.type === 'ObjectPattern') {
    for (const prop of node.id.properties) {
      const name = destructuredTName(prop);
      if (name !== null) recordBinding(context, tBindings, name, namespaces, node);
    }
  }

  if (node.id.type === 'Identifier' && node.init.type === 'MemberExpression') {
    recordBinding(context, tBindings, node.id.name, namespaces, node);
  }
}

/** True when the call's callee is a `t`: the plain identifier `t`, or a binding recorded from useTranslation(). */
function hasTranslationCallee(tBindings, node) {
  // ONLY A `t` IS A TRANSLATION CALL: a binding made by useTranslation() (the portal), or an identifier named `t` (the CLI imports one from its i18n module and prefixes every key `cli:`). A string with a colon reads as `ns:key`, and a key naming its own namespace used to skip the callee check entirely, so `cn('h-11 md:text-lg')` was reported as a missing key `text-lg` in a namespace `h-11` (ConfigRemote.tsx, 2026-09-26). The first fix accepted only the useTranslation() binding and silenced every CLI key; the lint-rule liveness gate caught it.
  if (node.callee.type !== 'Identifier') return false;
  return (
    node.callee.name === 't' ||
    findNamespacesForIdentifier(tBindings, node.callee.name, node) !== null
  );
}

function checkTranslationCall(env, node) {
  const { context, tBindings, resources, ignoreDefaultValue } = env;
  if (!hasTranslationCallee(tBindings, node)) return;
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

  const namespaces = resolveNamespaces(tBindings, node, namespace, optionArg);
  if (!namespaces || namespaces.length === 0) return;

  const segments = keyPath.split('.').filter(Boolean);
  if (segments.length === 0) return;

  const exists = namespaces.some((ns) => hasPath(resources.get(ns), segments));
  if (!exists) {
    context.report({
      node: keyNode,
      messageId: 'missingKey',
      data: { key: keyValue },
    });
  }
}

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
    const localeDir = resolveRequiredDirOption(
      'custom/require-translation',
      'localeDir',
      options.localeDir,
      ROOT_DIR
    );
    const ignoreDefaultValue = options.ignoreDefaultValue === true;
    const resources = getResources(localeDir);

    const tBindings = [];

    const env = { context, tBindings, resources, ignoreDefaultValue };

    return {
      VariableDeclarator(node) {
        recordTranslationBindings(env, node);
      },

      CallExpression(node) {
        checkTranslationCall(env, node);
      },
    };
  },
};
