/**
 * ESLint rule: enforce BLOCKER-quality reasons on conditional `test.skip` /
 * `it.skip` calls.
 *
 * This matches only the CONDITIONAL-skip form:
 *   test.skip(cond, 'reason');   // cond is NOT a string literal
 *   it.skip(cond, 'reason');
 *
 * It does NOT target the declaration form `test.skip('test name', fn)` where
 * the first arg is a string literal (test title) — that's a separate lint
 * concern covered by no-restricted-syntax in eslint.config.js for unit
 * tests where .skip() is banned outright.
 *
 * Contract (must stay in sync with scripts/lib/blocker-validator.ts):
 *   - Reason length >= 30 chars after trim + trailing-punctuation strip
 *   - Reason must not match any phrase in LOW_EFFORT_BLOCKER_PATTERNS
 *   - Bare 0-arg and 1-arg-with-boolean form is rejected (no reason at all)
 */

// Kept in sync with scripts/lib/blocker-validator.ts and .ci/scripts/lib/blocker-validator.sh.
// If you touch this list, update ALL THREE — the shared validator, the bash
// validator, and this ESLint rule.
const LOW_EFFORT_BLOCKER_PATTERNS = [
  // npm-audit ack-tier
  'no fix', 'no fix available', 'no fix yet', 'no upstream fix', 'no fix published',
  'no patch', 'no patch yet', 'no patch available',
  'none', 'n/a', 'na', 'empty', '-',
  // scheduling ack-tier
  'tbd', 'wip', 'fixme', 'todo', 'later', 'fix later', 'will fix', 'pending',
  'skip', 'skipping', 'skipped', 'ignore', 'ignoring', 'ignored',
  'unknown', 'unknown reason', 'idk', 'dunno', 'whatever',
  // review-gate-style acks
  'ok', 'okay', 'ack', 'acknowledged', 'noted', 'done', 'fixed', 'applied',
  'addressed', 'updated', 'changed', 'understood',
  // explicit escape-hatch attempts
  'escape', 'escape hatch', 'suppressed', 'suppress', 'bypass', 'override',
  'upstream issue', 'transitive', 'dev dep', 'dev only',
];
const BLOCKER_MIN_LENGTH = 30;

function normalize(reason) {
  return String(reason).toLowerCase().trim().replace(/[.!?,;:]+$/, '');
}

/** @type {import('eslint').Rule.RuleModule} */
export const testSkipBlocker = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Require BLOCKER-quality reasons on conditional test.skip(cond, reason) calls',
      recommended: true,
    },
    messages: {
      bareSkip:
        'Bare {{fn}}.skip() is not allowed. Use the conditional form with a BLOCKER-quality reason: {{fn}}.skip(cond, "reason explaining >=30 chars, no banned phrases").',
      missingReason:
        '{{fn}}.skip(cond) without a reason is not allowed. Add a BLOCKER-quality reason string as the second argument.',
      nonLiteralReason:
        '{{fn}}.skip(cond, reason) must pass a STRING LITERAL reason so the BLOCKER gate can validate it at lint time.',
      tooShort:
        '{{fn}}.skip reason is too short ({{len}} chars, minimum {{min}}). Explain WHO is blocked, WHY the test can\'t run here, and WHEN it would.',
      bannedPhrase:
        '{{fn}}.skip reason "{{normalized}}" matches the banned-phrase list — write a specific reason naming the env var, binary, or infra gap.',
    },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        // Match (test|it).skip( ... )
        if (
          node.callee.type !== 'MemberExpression' ||
          node.callee.property.type !== 'Identifier' ||
          node.callee.property.name !== 'skip' ||
          node.callee.object.type !== 'Identifier' ||
          (node.callee.object.name !== 'test' && node.callee.object.name !== 'it')
        ) {
          return;
        }
        const fn = node.callee.object.name;
        const args = node.arguments;

        // 0-arg: test.skip() — bare form, banned.
        if (args.length === 0) {
          context.report({ node, messageId: 'bareSkip', data: { fn } });
          return;
        }

        // 1-arg form. If the single arg is a string LITERAL, this is the
        // declaration form `test.skip('name', …)` (playwright/vitest allow
        // declaring-as-skipped) — and the existing `no-restricted-syntax`
        // config elsewhere handles unit-test cases. Let it pass here.
        if (args.length === 1) {
          const only = args[0];
          if (only.type === 'Literal' && typeof only.value === 'string') {
            return; // declaration form
          }
          // Otherwise (identifier / boolean / call): conditional skip with no reason.
          context.report({ node, messageId: 'missingReason', data: { fn } });
          return;
        }

        // 2-arg form. If args[0] is a string literal AND args[1] is a function,
        // this is the declaration form `test.skip('name', fn)`.
        if (args.length >= 2) {
          const first = args[0];
          const second = args[1];
          const firstIsString =
            first.type === 'Literal' && typeof first.value === 'string';
          const secondIsFn =
            second.type === 'ArrowFunctionExpression' ||
            second.type === 'FunctionExpression';
          if (firstIsString && secondIsFn) {
            return; // declaration form
          }

          // Otherwise: conditional skip. The reason argument must be a
          // string literal or a template literal whose static parts pass
          // the BLOCKER quality gate.
          let reasonString;
          if (second.type === 'Literal' && typeof second.value === 'string') {
            reasonString = second.value;
          } else if (second.type === 'TemplateLiteral') {
            // Concatenate the static quasi parts only; dynamic expressions
            // are replaced with a single space so a banned-phrase match
            // can't slip through a multi-interpolation expression.
            reasonString = second.quasis.map((q) => q.value.cooked).join(' ');
          } else {
            context.report({
              node,
              messageId: 'nonLiteralReason',
              data: { fn },
            });
            return;
          }

          const normalized = normalize(reasonString);
          if (LOW_EFFORT_BLOCKER_PATTERNS.includes(normalized)) {
            context.report({
              node,
              messageId: 'bannedPhrase',
              data: { fn, normalized },
            });
            return;
          }
          if (normalized.length < BLOCKER_MIN_LENGTH) {
            context.report({
              node,
              messageId: 'tooShort',
              data: { fn, len: String(normalized.length), min: String(BLOCKER_MIN_LENGTH) },
            });
            return;
          }
        }
      },
    };
  },
};
