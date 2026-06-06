/**
 * ESLint rule: ban references to CLI `--flags` that are not registered options
 * of ANY rdc command, in user-facing locale strings.
 *
 * Motivation (issue #489): `rdc repo up --help` told users to pass `--mount`, but
 * no such option exists (the real flag is `--mount-only`), so `rdc repo up --mount`
 * fails with `error: unknown option '--mount'`. The help prose actively guided users
 * — and agents that parse help text — toward a flag the parser rejects.
 *
 * Complements `no-positional-cli-syntax` (which catches positional examples for
 * commands that require named options). That rule deliberately treats `--flag` as
 * the *correct* named form and skips it, so a non-existent `--flag` slips through.
 * This rule fills that gap.
 *
 * ## Detection model (deliberately context-free)
 *
 * A per-command "is this flag valid for THIS command" check was prototyped and
 * rejected: single-word command names (`repo`, `machine`, `config`, `agent`, ...)
 * collide with ordinary prose nouns, so the "current command" context leaks and
 * real flags get mis-attributed — ~45 reports, almost all false positives.
 *
 * Every genuine bug is instead a flag that exists on NO command at all. So the rule
 * reports a `--token` only when it is absent from the union of every command's
 * registered options (plus globals, plus the positive form of `--no-X` negatable
 * booleans). This needs no command context, so the collision problem disappears and
 * the false-positive rate drops to zero on the `en` source locale.
 *
 * ## Scope: `en` source locale only (wired in eslint.config.js)
 *
 * Flags are language-invariant. Running across translated locales surfaces
 * translation-only false positives (e.g. Estonian agglutinates grammatical case
 * endings onto flag names: `--current-ita`, `--force-ist`). Prefix-trimming to
 * absorb those is unsafe (it would mask real bugs like `--snapshot-name`, since
 * `--snapshot` exists on another command). `translation-coverage` /
 * `cross-language-consistency` already guard that translations mirror `en`.
 *
 * The valid-flag set is derived from `packages/cli/scripts/command-tree.json`
 * (the same source of truth `no-positional-cli-syntax` uses via autoDerive).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TREE_PATH = path.resolve(
  __dirname,
  '../../packages/cli/scripts/command-tree.json'
);

// Root/global options the program registers (these are filtered out of per-command
// nodes in command-tree.json, so they must be added explicitly) plus Commander
// built-ins. Mirrors GLOBAL_OPTION_LONGS in packages/cli/scripts/export-command-tree.ts.
const GLOBAL_FLAGS = ['--output', '--context', '--lang', '--version', '--help', '--help-all'];

const LONG_FLAG_RE = /--[a-z][a-z0-9-]*/g;
const LEADING_TOKEN_CHARS = /^[('"`[]+/;
const TRAILING_TOKEN_CHARS = /[)'"`\].,;:!?]+$/;

let cachedFlags = null;

/** Build the set of every valid long flag across all commands + globals.
 *  Exported so the cross-locale consistency rule can reuse the same source of
 *  truth to tell mangled flag tokens from real ones. */
export const loadValidFlags = () => {
  if (cachedFlags) return cachedFlags;
  const tree = JSON.parse(fs.readFileSync(COMMAND_TREE_PATH, 'utf-8'));
  const flags = new Set(GLOBAL_FLAGS);
  for (const o of tree.options ?? []) {
    for (const f of o.flags.match(LONG_FLAG_RE) ?? []) flags.add(f);
  }
  const walk = (node) => {
    for (const o of node.options ?? []) {
      for (const f of o.flags.match(LONG_FLAG_RE) ?? []) flags.add(f);
    }
    for (const sub of node.subcommands ?? []) walk(sub);
  };
  walk(tree);
  // Commander negatable booleans: a registered `--no-foo` makes `--foo` a valid
  // reference too (e.g. "Implies --infra" when `--no-infra` is the option).
  for (const f of [...flags]) {
    const m = f.match(/^--no-(.+)$/);
    if (m) flags.add('--' + m[1]);
  }
  cachedFlags = flags;
  return flags;
};

/** @type {import('eslint').Rule.RuleModule} */
export const noUndefinedCliFlags = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow references to CLI --flags that are not registered options of any rdc command.',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          exemptFlags: {
            type: 'array',
            items: { type: 'string' },
            description:
              'Flags to treat as valid even though they are not in command-tree.json (e.g. external-tool flags shown in examples).',
          },
          exemptKeyPrefixes: {
            type: 'array',
            items: { type: 'string' },
            description:
              'Locale key prefixes to skip entirely (e.g. cloud/legacy command groups).',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      undefinedFlag:
        'Locale string "{{key}}" references CLI flag `{{flag}}`, which is not a registered option of any rdc command. `rdc … {{flag}}` fails with "unknown option \'{{flag}}\'". Fix the flag name or remove the reference. See issue #489. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const exemptFlags = new Set(options.exemptFlags || []);
    const exemptKeyPrefixes = options.exemptKeyPrefixes || [];
    const validFlags = loadValidFlags();

    const isExemptKey = (key) =>
      exemptKeyPrefixes.some((prefix) => key.startsWith(prefix));

    /** Extract the leading `--flag` from a whitespace-delimited token, after
     *  stripping surrounding markdown/quote/punctuation characters. */
    const flagOf = (token) => {
      const cleaned = token
        .replace(LEADING_TOKEN_CHARS, '')
        .replace(TRAILING_TOKEN_CHARS, '');
      const m = cleaned.match(/^(--[a-z][a-z0-9-]*)/);
      return m ? m[1] : null;
    };

    const checkObject = (node, prefix = '') => {
      if (!node || node.type !== 'Object') return;
      for (const member of node.members || []) {
        if (member.type !== 'Member') continue;
        const key =
          member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (!key) continue;
        const fullPath = prefix ? `${prefix}.${key}` : key;
        const value = member.value;

        if (value?.type === 'Object') {
          checkObject(value, fullPath);
        } else if (value?.type === 'String') {
          if (isExemptKey(fullPath)) continue;
          const reported = new Set();
          for (const token of value.value.split(/\s+/)) {
            const flag = flagOf(token);
            if (!flag) continue;
            if (validFlags.has(flag) || exemptFlags.has(flag)) continue;
            if (reported.has(flag)) continue;
            reported.add(flag);
            context.report({
              node: value,
              messageId: 'undefinedFlag',
              data: { key: fullPath, flag },
            });
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

export default noUndefinedCliFlags;
