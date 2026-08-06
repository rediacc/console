/**
 * ESLint rule to ban positional CLI syntax in TypeScript/TSX/Astro source
 * string literals and template literals.
 *
 * Complements `i18n/no-positional-cli-syntax` (which scans JSON locale files)
 * by catching:
 *   - `addHelpText('after', '…$ rdc machine query <name>…')` in Commander.js
 *     command definitions
 *   - Error message strings that embed `rdc …` examples
 *   - JSX children / Astro templates that render CLI examples
 *
 * The rule derives its denylist from packages/cli/scripts/command-tree.json
 * via the same leaf-only / zero-positional-args logic as the JSON rule.
 *
 * Detector logic is duplicated here (not imported) because ESLint rules are
 * plain JS and must stay self-contained.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  EXEMPT_COMMAND_PREFIXES as SHARED_EXEMPT_PREFIXES,
  FREEFORM_ARG_COMMAND_PATHS as SHARED_FREEFORM,
} from './lib/cli-exempt-lists.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(
  __dirname,
  '../packages/cli/scripts/command-tree.json'
);

const FREEFORM_ARG_COMMAND_PATHS = new Set(SHARED_FREEFORM);

const DEFAULT_EXEMPT_PREFIXES = SHARED_EXEMPT_PREFIXES;

const escapeRegex = (str) => str.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');

const buildCommandRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    // A prose word that ends the clause is not an argument. German splits separable
    // verbs ("fuehren Sie rdc config reconcile aus."), so the particle lands after the
    // command and used to read as a positional. Kept identical to the shared detector in
    // scripts/lib/positional-cli-detector.ts — an ESLint rule cannot import a .ts module,
    // which is why this regex exists twice; if you change one, change the other.
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?![\\p{L}]+[.,;:!?])(?=[<{\\["'a-zA-Z0-9])`,
    'u'
  );
};

const buildPlaceholderOnlyRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=<[a-zA-Z_][\\w-]*>|\\{\\{[a-zA-Z_]\\w*\\}\\})`
  );
};

let cachedLeafPaths = null;
let cachedParentPaths = null;

const loadPathsFromTree = () => {
  if (cachedLeafPaths && cachedParentPaths) {
    return { leaves: cachedLeafPaths, parents: cachedParentPaths };
  }
  const raw = fs.readFileSync(COMMAND_TREE_PATH, 'utf-8');
  const tree = JSON.parse(raw);
  const leaves = new Set();
  const parents = new Set();
  const walk = (node, parts) => {
    if (parts.length > 0) {
      const commandPath = parts.join(' ');
      if (!FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
        const isLeaf = (node.subcommands ?? []).length === 0;
        const takesPositional = (node.arguments ?? []).length > 0;
        // A command that takes a positional belongs in NEITHER pass: after P4
        // `rdc repo up <repo-ref>` is the syntax we want taught. This set used to
        // be every path, which flagged the correct form and claimed the command
        // "accepts zero positional arguments" — false, and it blocked the reshape.
        if (isLeaf && !takesPositional) leaves.add(commandPath);
        if (!isLeaf && !takesPositional) parents.add(commandPath);
      }
    }
    for (const sub of node.subcommands ?? []) walk(sub, [...parts, sub.name]);
  };
  walk(tree, []);
  cachedLeafPaths = leaves;
  cachedParentPaths = parents;
  return { leaves, parents };
};

/** @type {import('eslint').Rule.RuleModule} */
export const noPositionalCliSyntaxSource = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow positional CLI syntax in TypeScript/TSX/Astro source strings for commands that require named options.',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          exemptCommandPrefixes: {
            type: 'array',
            items: { type: 'string' },
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      positionalSyntax:
        'String teaches positional syntax for `{{path}}`, but this command accepts zero positional arguments. Rewrite to use named options (e.g., `{{path}} --name <value>`). See issue #446.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const exemptPrefixes = [
      ...DEFAULT_EXEMPT_PREFIXES,
      ...(options.exemptCommandPrefixes || []),
    ];

    const { leaves, parents } = loadPathsFromTree();
    const leafEntries = [...leaves].sort((a, b) => b.length - a.length).map((p) => ({
      path: p,
      regex: buildCommandRegex(p),
    }));
    const parentEntries = [...parents]
      .sort((a, b) => b.length - a.length)
      .map((p) => ({ path: p, regex: buildPlaceholderOnlyRegex(p) }));

    if (leafEntries.length === 0 && parentEntries.length === 0) return {};

    const checkStringValue = (node, strValue) => {
      if (typeof strValue !== 'string') return;
      if (!strValue.includes('rdc ')) return;

      const lines = strValue.split(/\r?\n/);
      const reported = new Set();
      for (const line of lines) {
        const trimmedStart = line.trimStart();
        if (exemptPrefixes.some((p) => trimmedStart.startsWith(p))) continue;
        const reportedPerLine = new Set();
        const tryReport = (entry) => {
          const m = entry.regex.exec(line);
          if (!m) return;
          const rdcIndex = line.indexOf('rdc ', m.index);
          const trailing = line.slice(rdcIndex);
          const afterPath = trailing.slice(`rdc ${entry.path} `.length);
          if (
            /^\[options\](?!\w)/.test(afterPath) ||
            /^\[command\.\.\.\](?!\w)/.test(afterPath) ||
            /^\[command\](?!\w)/.test(afterPath) ||
            /^\[komut\.\.\.\](?!\w)/.test(afterPath) ||
            /^\[seçenekler\](?!\w)/.test(afterPath)
          ) {
            return;
          }
          const posKey = `${rdcIndex}`;
          if (reportedPerLine.has(posKey)) return;
          reportedPerLine.add(posKey);
          const reportKey = `${entry.path}|${line.trim()}`;
          if (reported.has(reportKey)) return;
          reported.add(reportKey);
          context.report({
            node,
            messageId: 'positionalSyntax',
            data: { path: entry.path },
          });
        };
        for (const entry of leafEntries) tryReport(entry);
        for (const entry of parentEntries) tryReport(entry);
      }
    };

    return {
      Literal(node) {
        checkStringValue(node, node.value);
      },
      TemplateElement(node) {
        checkStringValue(node, node.value?.cooked ?? node.value?.raw);
      },
      JSXText(node) {
        checkStringValue(node, node.value);
      },
    };
  },
};

export default noPositionalCliSyntaxSource;
