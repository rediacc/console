/**
 * ESLint rule to ban positional CLI syntax in user-facing locale strings
 * for commands that actually require named options.
 *
 * Catches documentation that teaches the wrong syntax. Fresh agents reliably try
 * the form shown in help text first, so a string like `rdc machine status <name>`
 * — when the real command requires `--name <name>` — burns one failed command per
 * session.
 *
 * The denylist AUTO-DERIVES from command-tree.json (every leaf with zero
 * positional arguments), so this rule follows the tree rather than asserting a
 * doctrine about it. That is why it survived P4's inversion to positional refs
 * while `custom/no-positional-arguments` — which banned positionals outright on
 * the Commander side — had to be deleted: a command that now takes `<repo-ref>`
 * simply stops being in the derived denylist.
 *
 * See issue #446.
 *
 * Config shape (either-or):
 *
 *   // Explicit form (retained for pinning specific commands with custom msg):
 *   {
 *     commands: [
 *       { path: 'repo fork', requiredOptions: ['--parent'] },
 *     ],
 *     exemptCommandPrefixes: ['rdc audit', 'rdc team', ...]
 *   }
 *
 *   // Auto-derive from packages/cli/scripts/command-tree.json (preferred):
 *   {
 *     autoDerive: true,
 *     exemptCommandPrefixes: ['rdc audit', ...],
 *   }
 *
 * In autoDerive mode the rule reads command-tree.json at init time and flags
 * any text that matches `rdc <leaf-command-path> <non-flag>` for every leaf
 * command whose arguments array is empty. This keeps the denylist in sync
 * with the Commander source automatically.
 *
 * The detector logic is duplicated here from scripts/lib/positional-cli-detector.ts
 * because ESLint rules are plain JS (no tsx) and must stay self-contained.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FREEFORM_ARG_COMMAND_PATHS as SHARED_FREEFORM } from '../lib/cli-exempt-lists.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(
  __dirname,
  '../../packages/cli/scripts/command-tree.json'
);

const FREEFORM_ARG_COMMAND_PATHS = new Set(SHARED_FREEFORM);

const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Build a detection regex for a command path. Matches when the command path
 * is immediately followed by a non-flag token (placeholder, interpolation,
 * literal). Does NOT match when `--flag` follows, or when the line ends
 * immediately after the path.
 */
/** Match any non-flag token after the command path. Used for leaf commands. */
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

/** Match only placeholder/interpolation next token. Used for ALL commands
 *  (a placeholder is never a valid subcommand name, so even parent paths
 *  should reject this form). */
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
        // `rdc repo up <repo-ref>` is the syntax we want the help text to teach.
        // The parent set used to be every path, which flagged that correct form.
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
export const noPositionalCliSyntax = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow positional CLI syntax in locale strings for commands that require named options.',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          autoDerive: {
            type: 'boolean',
            description:
              'Derive the zero-positional command set automatically from packages/cli/scripts/command-tree.json.',
          },
          commands: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                path: { type: 'string' },
                requiredOptions: {
                  type: 'array',
                  items: { type: 'string' },
                },
              },
              required: ['path', 'requiredOptions'],
              additionalProperties: false,
            },
          },
          exemptCommandPrefixes: {
            type: 'array',
            items: { type: 'string' },
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      positionalSyntaxExplicit:
        'Locale string "{{key}}" teaches positional syntax for `{{path}}`, but this command requires {{requiredOptions}}. Rewrite the example to use the named form (e.g., `{{path}} {{firstOption}} <name>`). See issue #446. See docs/i18n/CONVENTIONS.md.',
      positionalSyntaxDerived:
        'Locale string "{{key}}" teaches positional syntax for `{{path}}`. This command accepts zero positional arguments — use named options instead (e.g., `{{path}} --name <value>`). See issue #446. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const autoDerive = Boolean(options.autoDerive);
    const exemptCommandPrefixes = options.exemptCommandPrefixes || [];

    const explicitCommands = (options.commands || []).map((c) => ({
      path: c.path,
      regex: buildCommandRegex(c.path),
      requiredOptions: c.requiredOptions,
      source: 'explicit',
    }));

    let derivedCommands = [];
    if (autoDerive) {
      const { leaves, parents } = loadPathsFromTree();
      // Leaf-command pass: reject ANY non-flag next token. Sorted
      // longest-first so the most specific leaf wins on dedup.
      const sortedLeaves = [...leaves].sort((a, b) => b.length - a.length);
      for (const p of sortedLeaves) {
        derivedCommands.push({
          path: p,
          regex: buildCommandRegex(p),
          requiredOptions: [],
          source: 'derived',
        });
      }
      // Parent pass: reject a placeholder/interpolation next token. A parent
      // expects a SUBCOMMAND there, and a placeholder can never name one.
      // Sorted longest-first so the most specific path wins.
      const sortedParents = [...parents].sort((a, b) => b.length - a.length);
      for (const p of sortedParents) {
        derivedCommands.push({
          path: p,
          regex: buildPlaceholderOnlyRegex(p),
          requiredOptions: [],
          source: 'derived',
        });
      }
    }

    const allCommands = [...explicitCommands, ...derivedCommands];
    if (allCommands.length === 0) return {};

    const isExempt = (value) => {
      const trimmed = value.trimStart();
      return exemptCommandPrefixes.some((prefix) => trimmed.startsWith(prefix));
    };

    const checkObject = (node, prefix = '') => {
      if (!node || node.type !== 'Object') return;
      const members = node.members || [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key =
          member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (!key) continue;

        const fullPath = prefix ? `${prefix}.${key}` : key;
        const value = member.value;

        if (value?.type === 'Object') {
          checkObject(value, fullPath);
        } else if (value?.type === 'String') {
          const strValue = value.value;
          const lines = strValue.split(/\r?\n/);
          for (const line of lines) {
            if (isExempt(line.trimStart())) continue;
            // Dedupe per-line per-rdc-position so a longer match wins.
            const reported = new Set();
            for (const command of allCommands) {
              const m = command.regex.exec(line);
              if (!m) continue;
              const rdcIndex = line.indexOf('rdc ', m.index);
              // Skip Commander usage placeholders like `[options]`,
              // `[command...]` — these aren't teaching positional syntax.
              const trailing = line.slice(rdcIndex);
              const afterPath = trailing.slice(`rdc ${command.path} `.length);
              if (
                /^\[options\](?!\w)/.test(afterPath) ||
                /^\[command\.\.\.\](?!\w)/.test(afterPath) ||
                /^\[command\](?!\w)/.test(afterPath) ||
                /^\[komut\.\.\.\](?!\w)/.test(afterPath) ||
                /^\[seçenekler\](?!\w)/.test(afterPath)
              ) {
                continue;
              }
              const posKey = `${rdcIndex}`;
              if (reported.has(posKey)) continue;
              reported.add(posKey);
              if (command.source === 'explicit') {
                context.report({
                  node: value,
                  messageId: 'positionalSyntaxExplicit',
                  data: {
                    key: fullPath,
                    path: command.path,
                    requiredOptions: command.requiredOptions.join(', '),
                    firstOption: command.requiredOptions[0],
                  },
                });
              } else {
                context.report({
                  node: value,
                  messageId: 'positionalSyntaxDerived',
                  data: {
                    key: fullPath,
                    path: command.path,
                  },
                });
              }
            }
          }
        }
      }
    };

    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          checkObject(node.body);
        }
      },
    };
  },
};

export default noPositionalCliSyntax;
