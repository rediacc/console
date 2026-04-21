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

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(
  __dirname,
  '../packages/cli/scripts/command-tree.json'
);

const FREEFORM_ARG_COMMAND_PATHS = new Set([
  'agent schema',
  'agent exec',
  'mcp capabilities',
  'mcp schema',
  'mcp exec',
  'run',
]);

const DEFAULT_EXEMPT_PREFIXES = [
  'rdc auth',
  'rdc audit',
  'rdc bridge',
  'rdc organization',
  'rdc permission',
  'rdc protocol',
  'rdc queue',
  'rdc region',
  'rdc repository',
  'rdc team',
  'rdc user',
  'rdc ceph',
];

const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const buildCommandRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=[<{\\["'a-zA-Z0-9])`
  );
};

const buildPlaceholderOnlyRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  return new RegExp(
    `(?:^|[\\s\`($:'"])(?:rdc\\s+)${segments}\\s+(?=<[a-zA-Z_][\\w-]*>|\\{\\{[a-zA-Z_]\\w*\\}\\})`
  );
};

let cachedLeafPaths = null;
let cachedAllPaths = null;

const loadPathsFromTree = () => {
  if (cachedLeafPaths && cachedAllPaths) {
    return { leaves: cachedLeafPaths, all: cachedAllPaths };
  }
  const raw = fs.readFileSync(COMMAND_TREE_PATH, 'utf-8');
  const tree = JSON.parse(raw);
  const leaves = new Set();
  const all = new Set();
  const walk = (node, parts) => {
    if (parts.length > 0) {
      const commandPath = parts.join(' ');
      if (!FREEFORM_ARG_COMMAND_PATHS.has(commandPath)) {
        all.add(commandPath);
        const isLeaf = (node.subcommands ?? []).length === 0;
        if (isLeaf && (node.arguments ?? []).length === 0) {
          leaves.add(commandPath);
        }
      }
    }
    for (const sub of node.subcommands ?? []) walk(sub, [...parts, sub.name]);
  };
  walk(tree, []);
  cachedLeafPaths = leaves;
  cachedAllPaths = all;
  return { leaves, all };
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

    const { leaves, all } = loadPathsFromTree();
    const leafEntries = [...leaves].sort((a, b) => b.length - a.length).map((p) => ({
      path: p,
      regex: buildCommandRegex(p),
    }));
    const allEntries = [...all]
      .sort((a, b) => b.length - a.length)
      .map((p) => ({ path: p, regex: buildPlaceholderOnlyRegex(p) }));

    if (leafEntries.length === 0 && allEntries.length === 0) return {};

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
        for (const entry of allEntries) tryReport(entry);
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
