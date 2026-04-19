/**
 * ESLint rule to ban positional CLI syntax in user-facing locale strings
 * for commands that actually require named options.
 *
 * Complements `custom/no-positional-arguments` (which enforces named options
 * on the Commander API side) by catching documentation that teaches the wrong
 * syntax. Fresh agents reliably try the form shown in help text first, so a
 * string like `rdc repo fork <parent>` — when the real command requires
 * `--parent <parent>` — burns one failed command per session.
 *
 * See issue #446.
 *
 * Config shape:
 *
 *   {
 *     commands: [
 *       { path: 'repo fork',     requiredOptions: ['--parent'] },
 *       { path: 'repo takeover', requiredOptions: ['--target'] },
 *     ],
 *     exemptCommandPrefixes: ['rdc audit', 'rdc team', ...]
 *   }
 *
 * For each command, the rule auto-builds a regex that matches the command
 * path immediately followed by a placeholder `<...>` or handlebars `{{...}}`
 * — the two forms that unambiguously teach positional syntax. Correct
 * documentation (`repo fork --parent <name>`) has `--` after the command and
 * never matches.
 */

const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Build a detection regex for a command path. The path segments are separated
 * by any whitespace, with an optional `rdc` prefix.
 */
const buildCommandRegex = (commandPath) => {
  const segments = commandPath.trim().split(/\s+/).map(escapeRegex).join('\\s+');
  // (?:^|\s) — command starts at a word boundary
  // (?:rdc\s+)? — optional 'rdc' prefix (workflow diagrams often drop it)
  // <segments>\s+ — the command path followed by whitespace
  // (?:<|\{\{) — a placeholder '<name>' or interpolation '{{name}}' (the
  // forms that teach positional syntax). When --parent/--flag is used, '-'
  // follows instead and never matches.
  return new RegExp(`(?:^|\\s)(?:rdc\\s+)?${segments}\\s+(?:<|\\{\\{)`);
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
          commands: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                path: {
                  type: 'string',
                  description:
                    'Space-separated command path, e.g. "repo fork" or "machine vault set".',
                },
                requiredOptions: {
                  type: 'array',
                  items: { type: 'string' },
                  description:
                    'The --flag names this command requires (shown in the error message).',
                },
              },
              required: ['path', 'requiredOptions'],
              additionalProperties: false,
            },
          },
          exemptCommandPrefixes: {
            type: 'array',
            items: { type: 'string' },
            description:
              'Values whose trimmed start matches any of these strings are skipped (for legacy/cloud-adapter commands that use positional subcommands legitimately).',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      positionalSyntax:
        'Locale string "{{key}}" teaches positional syntax for `{{path}}`, but this command requires {{requiredOptions}}. Rewrite the example to use the named form (e.g., `{{path}} {{firstOption}} <name>`). See issue #446.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const commands = (options.commands || []).map((c) => ({
      path: c.path,
      regex: buildCommandRegex(c.path),
      requiredOptions: c.requiredOptions,
    }));
    const exemptCommandPrefixes = options.exemptCommandPrefixes || [];

    if (commands.length === 0) return {};

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
          if (isExempt(strValue)) continue;

          for (const command of commands) {
            if (command.regex.test(strValue)) {
              context.report({
                node: value,
                messageId: 'positionalSyntax',
                data: {
                  key: fullPath,
                  path: command.path,
                  requiredOptions: command.requiredOptions.join(', '),
                  firstOption: command.requiredOptions[0],
                },
              });
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
