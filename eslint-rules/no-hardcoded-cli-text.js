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

const OUTPUT_METHODS = ['success', 'error', 'warn', 'info'];
const PROMPT_FNS = ['askText', 'askPassword', 'askConfirm'];
const OPTION_METHODS = ['option', 'requiredOption'];

/** outputService.success/error/warn/info('...') */
const isOutputServiceCall = (callee) =>
  callee.type === 'MemberExpression' &&
  callee.object.type === 'Identifier' &&
  callee.object.name === 'outputService' &&
  callee.property.type === 'Identifier' &&
  OUTPUT_METHODS.includes(callee.property.name);

/** A method call `x.<name>(...)` for one of `names`. */
const isMethodCall = (callee, names) =>
  callee.type === 'MemberExpression' &&
  callee.property.type === 'Identifier' &&
  names.includes(callee.property.name);

/** A bare call `<name>(...)` for one of `names`. */
const isPlainCall = (callee, names) =>
  callee.type === 'Identifier' && names.includes(callee.name);

/**
 * Call shapes whose Nth argument is a user-facing string. addHelpText is NOT
 * here: its content needs a line-by-line walk, handled separately.
 */
const ARGUMENT_CHECKS = [
  { matches: (callee) => isOutputServiceCall(callee), argIndex: 0, messageId: 'hardcodedOutput' },
  { matches: (callee) => isPlainCall(callee, ['withSpinner']), argIndex: 0, messageId: 'hardcodedSpinner' },
  { matches: (callee) => isPlainCall(callee, PROMPT_FNS), argIndex: 0, messageId: 'hardcodedPrompt' },
  { matches: (callee) => isMethodCall(callee, ['description']), argIndex: 0, messageId: 'hardcodedDescription' },
  { matches: (callee) => isMethodCall(callee, OPTION_METHODS), argIndex: 1, messageId: 'hardcodedOption' },
];

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
    /**
     * Report `arg` when it carries a hardcoded user-facing string.
     * Returns true when the whole visitor should stop, which is the case the
     * inline `return`s used to encode: the argument is already a t() call.
     */
    const checkArgument = (arg, messageId) => {
      // Skip if arg is a t() call
      if (arg && isTranslationCall(arg)) return true;

      const value = getStringValue(arg);
      if (value && !shouldIgnore(value)) {
        context.report({
          node: arg,
          messageId,
          data: { text: value.slice(0, 50) },
        });
      }
      return false;
    };

    /** One line of an addHelpText template literal. */
    const checkHelpTextLine = (quasi, line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      // For command example lines ($ rdc ...), check for hardcoded
      // descriptions trailing after 2+ spaces (e.g., "$ rdc foo  Description here")
      if (/^\$\s+/.test(trimmed)) {
        const descMatch = trimmed.match(/\s{2,}([A-Z][a-zA-Z].*)$/);
        const desc = descMatch ? descMatch[1].trim() : '';
        if (desc && /[a-zA-Z]{2,}/.test(desc) && !shouldIgnore(desc)) {
          context.report({
            node: quasi,
            messageId: 'hardcodedHelpText',
            data: { text: desc.slice(0, 50) },
          });
        }
        return;
      }

      // Flag any other user-facing text (including labels like "Examples:")
      if (/[a-zA-Z]{2,}/.test(trimmed) && !shouldIgnore(trimmed)) {
        context.report({
          node: quasi,
          messageId: 'hardcodedHelpText',
          data: { text: trimmed.slice(0, 50) },
        });
      }
    };

    /** .addHelpText('after', `...`) - template literal quasis, or a plain string. */
    const checkHelpText = (contentArg) => {
      if (!contentArg) return;

      if (contentArg.type === 'TemplateLiteral') {
        for (const quasi of contentArg.quasis) {
          // Split into lines; check each line for user-facing text
          for (const line of (quasi.value.cooked ?? '').split('\n')) {
            checkHelpTextLine(quasi, line);
          }
        }
        return;
      }

      // Plain string literal in addHelpText — should use template with t()
      const value = getStringValue(contentArg);
      if (value && !shouldIgnore(value)) {
        context.report({
          node: contentArg,
          messageId: 'hardcodedHelpText',
          data: { text: value.slice(0, 50) },
        });
      }
    };

    return {
      CallExpression(node) {
        const callee = node.callee;

        // Skip t() calls themselves
        if (isTranslationCall(node)) return;

        for (const check of ARGUMENT_CHECKS) {
          if (!check.matches(callee)) continue;
          if (checkArgument(node.arguments[check.argIndex], check.messageId)) return;
        }

        if (isMethodCall(callee, ['addHelpText'])) {
          checkHelpText(node.arguments[1]);
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
          checkArgument(node.argument.arguments[0], 'hardcodedError');
        }
      },
    };
  },
};
