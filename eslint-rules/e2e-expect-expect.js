/**
 * custom/e2e-expect-expect -- host port of `eslint-plugin-playwright`'s
 * `expect-expect` rule, configured exactly as `eslint.config/tests.js:36-47`
 * does (`assertFunctionPatterns`), with the three stub-file exemptions at
 * `eslint.config/tests.js:77-88` carried over as `ignores` in
 * `scripts/data/source-rules.ts` instead of a config override.
 *
 * WHY A PORT, NOT A DIRECT DEPENDENCY. `eslint-plugin-playwright` is an ESLint
 * plugin: its rule reads `context.sourceCode.getScope(node).references` to
 * resolve import aliases, which `scripts/lib/rule-host.ts`'s scope shim does
 * not build (see that module's own header: it tracks declarations, not
 * references). Reimplementing needs only the part of the real rule this repo's
 * config actually exercises -- Playwright's bare `test(...)` (this repo aliases
 * nothing; vitest's `it`/`describe` are invisible to the REAL plugin too,
 * because `it` never resolves to `"test"` without a configured
 * `settings.playwright.globalAliases`, which this repo's config never sets --
 * verified by reading `eslint-plugin-playwright`'s own `resolveToPlaywrightFn`).
 *
 * ALGORITHM. For every `test(name, fn)` / `test.only(...)` / `test.skip(...)` /
 * `test.fixme(...)` / `test.fail(...)` call whose LAST argument is a function,
 * that function's own subtree (which includes any nested `test.step(...)`
 * callback -- a step's assertion counts for its parent test, exactly as the
 * real rule's ancestor-walk does) is searched for one qualifying call:
 *
 *   - any call chain rooted at the identifier `expect` (`expect(x)`,
 *     `expect(x).toBe(y)`, `expect.soft(x)...`, `expect(x).not.toBe(y)`, …) --
 *     this over-accepts a bare `expect(x)` with no matcher chained, which the
 *     real rule's stricter chain parser does not, but that call throws at
 *     runtime in real Playwright ("expect(...) requires a matcher") and does
 *     not occur in this tree, so the difference is never observable here; or
 *   - any call whose own name, or member name for `a.b.c(...)`, matches one of
 *     `assertFunctionPatterns` (checked against the RIGHTMOST identifier, the
 *     same position the real rule's `dig()` helper checks).
 *
 * A test with no such call anywhere in its body is reported once, on the test
 * call's own callee -- the same node the real rule reports on.
 */

import { visitorKeys as jsVisitorKeys } from 'oxc-parser';

const KEYS = /** @type {Record<string, string[]>} */ (/** @type {unknown} */ (jsVisitorKeys));

/** Walks `node` and every descendant reachable through `KEYS`, calling `visit` on each. Ignores `.parent`, exactly like `no-unused-underscore-var.js`'s own `walk`, for the same reason: it is a backlink the host sets before any rule runs, not a child to descend into. */
function walk(node, visit) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return;
  visit(node);
  for (const key of KEYS[node.type] ?? []) {
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value) walk(child, visit);
    } else if (value && typeof value.type === 'string') {
      walk(value, visit);
    }
  }
}

function isFunctionNode(node) {
  return !!node && (node.type === 'ArrowFunctionExpression' || node.type === 'FunctionExpression');
}

const TEST_MEMBER_SUFFIXES = new Set(['only', 'skip', 'fixme', 'fail']);

/** `test(name, fn)`, `test(name, options, fn)`, or one of `test.{only,skip,fixme,fail}` with the same shape. Deliberately excludes `test.step` (a step's assertions belong to its PARENT test, which is why searching the parent's whole subtree already finds them) and `test.describe`/`test.use`/`test.slow`/the hooks (none of these are graded on carrying an assertion). */
function isTestCall(node) {
  if (node.type !== 'CallExpression') return false;
  const args = node.arguments ?? [];
  if (args.length < 2 || !isFunctionNode(args[args.length - 1])) return false;
  const callee = node.callee;
  if (callee.type === 'Identifier' && callee.name === 'test') return true;
  return (
    callee.type === 'MemberExpression' &&
    callee.object?.type === 'Identifier' &&
    callee.object.name === 'test' &&
    callee.property?.type === 'Identifier' &&
    TEST_MEMBER_SUFFIXES.has(callee.property.name)
  );
}

/** The leftmost identifier of a call/member chain: `expect` for `expect(x).not.toBe(y)`, `test` for `test.step(...)`. */
function chainRootName(node) {
  if (!node) return null;
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') return chainRootName(node.object);
  if (node.type === 'CallExpression') return chainRootName(node.callee);
  return null;
}

/** The rightmost identifier of a call/member chain: `toBe` for `expect(x).toBe(y)`, `verifyLogin` for a bare `verifyLogin(page)`. This is the position `assertFunctionPatterns` matches against, mirroring the real rule's `dig()`. */
function lastMemberName(node) {
  if (!node) return null;
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression') return lastMemberName(node.property);
  if (node.type === 'CallExpression') return lastMemberName(node.callee);
  return null;
}

function isAssertionCall(node, patterns) {
  if (node.type !== 'CallExpression') return false;
  if (chainRootName(node.callee) === 'expect') return true;
  const name = lastMemberName(node.callee);
  return typeof name === 'string' && patterns.some((pattern) => pattern.test(name));
}

/** @type {import('../scripts/lib/rule-host.ts').RuleModule} */
export const e2eExpectExpect = {
  meta: {
    messages: {
      noAssertions:
        'Test has no assertions. Add an expect(...) call, or one matching assertFunctionPatterns ({{patterns}}).',
    },
    schema: [
      {
        type: 'object',
        properties: {
          assertFunctionPatterns: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = context.options[0] ?? {};
    const patterns = (options.assertFunctionPatterns ?? []).map((source) => new RegExp(source));

    return {
      Program(program) {
        walk(program, (node) => {
          if (!isTestCall(node)) return;
          const body = node.arguments[node.arguments.length - 1];
          let hasAssertion = false;
          walk(body, (inner) => {
            if (!hasAssertion && isAssertionCall(inner, patterns)) hasAssertion = true;
          });
          if (!hasAssertion) {
            context.report({
              node: node.callee,
              messageId: 'noAssertions',
              data: { patterns: patterns.map((p) => p.source).join(', ') },
            });
          }
        });
      },
    };
  },
};

export default e2eExpectExpect;
