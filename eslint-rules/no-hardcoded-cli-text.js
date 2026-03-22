/**
 * ESLint rule to disallow hardcoded text in CLI code.
 * Enforces use of t() translation function for user-facing strings.
 */

// Patterns that should be ignored (technical strings, not user-facing)
const IGNORE_PATTERNS = [
  // URLs and protocols
  /^[a-z][a-z0-9+.-]*:\/\//i,
  // File paths starting with / or ./
  /^\.?\/[a-zA-Z0-9_/-]+$/,
  // Pure numbers, punctuation, whitespace
  /^[-\s\d.,:;!?/()[\]{}<>%*+|_`~@#$^&=]+$/,
  // Single characters
  /^.$/,
  // Empty or whitespace only
  /^\s*$/,
  // CLI flags (e.g., --flag, -f)
  /^-{1,2}[a-zA-Z][\w-]*$/,
  // Environment variable names
  /^[A-Z][A-Z0-9_]+$/,
  // Technical identifiers (camelCase or snake_case without spaces)
  /^[a-z][a-zA-Z0-9_]*$/,
  // Format strings without text (e.g., %s, %d)
  /^[%{}[\]]+$/,
  // JSON-like structures
  /^\s*[{[\]]/,
  // Date/time format patterns
  /^[YMDHhmsaAzZT\-/:.\s]+$/,
  // Output format options
  /^(table|json|yaml|csv)$/i,
  // HTTP methods
  /^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$/,
];

// Check if a string should be ignored
const shouldIgnore = (text) => {
  if (!text || typeof text !== 'string') return true;
  const trimmed = text.trim();
  if (!trimmed) return true;
  // Must contain at least one letter to be user-facing
  if (!/[a-zA-Z]/.test(trimmed)) return true;
  return IGNORE_PATTERNS.some((pattern) => pattern.test(trimmed));
};

// Get string value from AST node
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

// Check if a call expression is a t() translation call
const isTranslationCall = (node) => {
  if (node.type !== 'CallExpression') return false;
  const callee = node.callee;
  // Direct t() call
  if (callee.type === 'Identifier' && callee.name === 't') return true;
  // i18n.t() call
  if (
    callee.type === 'MemberExpression' &&
    callee.property.type === 'Identifier' &&
    callee.property.name === 't'
  ) {
    return true;
  }
  return false;
};

/** @type {import('eslint').Rule.RuleModule} */
export const noHardcodedCliText = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow hardcoded text in CLI code; prefer t() translations',
      recommended: true,
    },
    schema: [],
    messages: {
      hardcodedText:
        'Hardcoded text "{{text}}" should use t() translation function.',
      hardcodedDescription:
        'Command description should use t() translation function.',
      hardcodedOption:
        'Option description should use t() translation function.',
      hardcodedSpinner:
        'Spinner text should use t() translation function.',
      hardcodedPrompt:
        'Prompt message should use t() translation function.',
      hardcodedError:
        'Error message should use t() translation function.',
      hardcodedOutput:
        'Output message should use t() translation function.',
      hardcodedHelpText:
        'Help text "{{text}}" in addHelpText() should use t() translation function.',
    },
  },

  create(context) {
    return {
      CallExpression(node) {
        const callee = node.callee;

        // Skip t() calls themselves
        if (isTranslationCall(node)) return;

        // Check outputService.success/error/warn/info('...')
        if (
          callee.type === 'MemberExpression' &&
          callee.object.type === 'Identifier' &&
          callee.object.name === 'outputService' &&
          callee.property.type === 'Identifier' &&
          ['success', 'error', 'warn', 'info'].includes(callee.property.name)
        ) {
          const arg = node.arguments[0];
          // Skip if arg is a t() call
          if (arg && isTranslationCall(arg)) return;
          const value = getStringValue(arg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: arg,
              messageId: 'hardcodedOutput',
              data: { text: value.slice(0, 50) },
            });
          }
        }

        // Check withSpinner('...', fn) - first argument is message
        if (
          callee.type === 'Identifier' &&
          callee.name === 'withSpinner'
        ) {
          const arg = node.arguments[0];
          if (arg && isTranslationCall(arg)) return;
          const value = getStringValue(arg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: arg,
              messageId: 'hardcodedSpinner',
              data: { text: value.slice(0, 50) },
            });
          }
        }

        // Check askText/askPassword/askConfirm('...')
        if (
          callee.type === 'Identifier' &&
          ['askText', 'askPassword', 'askConfirm'].includes(callee.name)
        ) {
          const arg = node.arguments[0];
          if (arg && isTranslationCall(arg)) return;
          const value = getStringValue(arg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: arg,
              messageId: 'hardcodedPrompt',
              data: { text: value.slice(0, 50) },
            });
          }
        }

        // Check .description('...') - Commander command description
        if (
          callee.type === 'MemberExpression' &&
          callee.property.type === 'Identifier' &&
          callee.property.name === 'description'
        ) {
          const arg = node.arguments[0];
          if (arg && isTranslationCall(arg)) return;
          const value = getStringValue(arg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: arg,
              messageId: 'hardcodedDescription',
              data: { text: value.slice(0, 50) },
            });
          }
        }

        // Check .addHelpText('after', `...`) - template literal quasis
        if (
          callee.type === 'MemberExpression' &&
          callee.property.type === 'Identifier' &&
          callee.property.name === 'addHelpText'
        ) {
          const contentArg = node.arguments[1];
          if (contentArg && contentArg.type === 'TemplateLiteral') {
            for (const quasi of contentArg.quasis) {
              const raw = quasi.value.cooked ?? '';
              // Split into lines; check each line for user-facing text
              for (const line of raw.split('\n')) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                // For command example lines ($ rdc ...), check for hardcoded
                // descriptions trailing after 2+ spaces (e.g., "$ rdc foo  Description here")
                if (/^\$\s+/.test(trimmed)) {
                  const descMatch = trimmed.match(/\s{2,}([A-Z][a-zA-Z].*)$/);
                  if (descMatch) {
                    const desc = descMatch[1].trim();
                    if (desc && /[a-zA-Z]{2,}/.test(desc) && !shouldIgnore(desc)) {
                      context.report({
                        node: quasi,
                        messageId: 'hardcodedHelpText',
                        data: { text: desc.slice(0, 50) },
                      });
                    }
                  }
                  continue;
                }

                // Flag any other user-facing text (including labels like "Examples:")
                if (/[a-zA-Z]{2,}/.test(trimmed) && !shouldIgnore(trimmed)) {
                  context.report({
                    node: quasi,
                    messageId: 'hardcodedHelpText',
                    data: { text: trimmed.slice(0, 50) },
                  });
                }
              }
            }
          } else if (contentArg) {
            // Plain string literal in addHelpText — should use template with t()
            const value = getStringValue(contentArg);
            if (value && !shouldIgnore(value)) {
              context.report({
                node: contentArg,
                messageId: 'hardcodedHelpText',
                data: { text: value.slice(0, 50) },
              });
            }
          }
        }

        // Check .option('-x, --flag <value>', '...') - second arg is description
        // Check .requiredOption() similarly
        if (
          callee.type === 'MemberExpression' &&
          callee.property.type === 'Identifier' &&
          ['option', 'requiredOption'].includes(callee.property.name)
        ) {
          // Description is the second argument
          const descArg = node.arguments[1];
          if (descArg && isTranslationCall(descArg)) return;
          const value = getStringValue(descArg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: descArg,
              messageId: 'hardcodedOption',
              data: { text: value.slice(0, 50) },
            });
          }
        }
      },

      // Check throw new ValidationError('...')
      ThrowStatement(node) {
        if (
          node.argument &&
          node.argument.type === 'NewExpression' &&
          node.argument.callee.type === 'Identifier' &&
          node.argument.callee.name === 'ValidationError'
        ) {
          const arg = node.argument.arguments[0];
          if (arg && isTranslationCall(arg)) return;
          const value = getStringValue(arg);
          if (value && !shouldIgnore(value)) {
            context.report({
              node: arg,
              messageId: 'hardcodedError',
              data: { text: value.slice(0, 50) },
            });
          }
        }
      },
    };
  },
};
