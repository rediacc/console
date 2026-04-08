/**
 * ESLint rule to catch unawaited Drizzle ORM query terminators.
 *
 * Background: the shared `Database` type in `private/account/src/db/index.ts`
 * is now `DrizzleD1Database` (the production runtime), which means every
 * `.run()`, `.get()`, and `.all()` call returns a Promise. The rule fires
 * whenever one of these terminators is invoked on a chained member
 * expression (i.e., a Drizzle query builder) without an `await`.
 *
 * Note: `.values()` is intentionally NOT a terminator here. In Drizzle it's
 * the setter on inserts (`db.insert(t).values({...})`) that returns a
 * builder, not a Promise.
 *
 * This is a defence-in-depth backstop. The TypeScript type fix already
 * catches the bug at compile time when callers read properties on the
 * unawaited result, but the lint rule still fires for cases where the
 * Promise is silently dropped (e.g., `db.update(...).where(...).run();`
 * called for side-effect with no return value used). It also fires when
 * users circumvent the type system with `as any` or similar casts.
 *
 * The rule is scoped to `private/account/src/**` via the eslint.config.js
 * `files:` glob — that's the only place where the Drizzle Database type
 * applies. The repo's other packages (CLI, web, www) don't talk to drizzle.
 *
 * To minimize false positives on unrelated `.get()` calls (Map, URLSearchParams,
 * etc.), the rule walks the receiver chain back from the terminator and only
 * fires if at least one Drizzle query-builder method (`select`, `insert`,
 * `update`, `delete`, `from`, `where`, `orderBy`, etc.) is present in the
 * chain.
 *
 * @example
 * // Bad — silent failure on D1, the row is never inserted
 * db.insert(table).values({...}).run();
 *
 * // Bad — `row` is a Promise, not the row
 * const row = db.select().from(table).where(eq(table.id, id)).get();
 *
 * // Good
 * await dbRun(db.insert(table).values({...}));
 * const row = await db.select().from(table).where(eq(table.id, id)).get();
 *
 * // Also good — async function returning the Promise directly
 * async function findById(id) {
 *   return db.select().from(table).where(eq(table.id, id)).get();
 * }
 */

const TERMINATORS = new Set(['run', 'get', 'all']);

// Drizzle query-builder methods. If we find any of these in the receiver
// chain of a terminator call, we treat that terminator as a Drizzle call.
// This avoids false positives on Map.get(), URLSearchParams.get(), etc.
const DRIZZLE_BUILDER_METHODS = new Set([
  'select',
  'insert',
  'update',
  'delete',
  'from',
  'where',
  'orderBy',
  'limit',
  'offset',
  'groupBy',
  'having',
  'innerJoin',
  'leftJoin',
  'rightJoin',
  'fullJoin',
  'onConflictDoNothing',
  'onConflictDoUpdate',
  'returning',
  'set',
]);

/**
 * Walk back from a CallExpression `.run()` / `.get()` / `.all()` / `.values()`
 * and check whether any earlier link in the chain is a Drizzle builder method.
 * Returns true if the chain looks like a Drizzle query.
 */
function chainContainsDrizzleBuilder(callee) {
  let current = callee.object;
  while (current) {
    if (current.type === 'CallExpression' && current.callee.type === 'MemberExpression') {
      const methodName = current.callee.property?.name;
      if (typeof methodName === 'string' && DRIZZLE_BUILDER_METHODS.has(methodName)) {
        return true;
      }
      current = current.callee.object;
      continue;
    }
    if (current.type === 'MemberExpression') {
      current = current.object;
      continue;
    }
    break;
  }
  return false;
}

/**
 * Determine if the parent of a node makes the value safely awaited or
 * propagated to a caller that will await it. We accept:
 *   - `await chain.run()`
 *   - `return chain.run();` inside an async function
 *   - `chain.run().then(...)` / `.catch(...)` / `.finally(...)`
 *   - `Promise.all([chain.get(), ...])` / `Promise.race([...])` / `Promise.allSettled([...])`
 *   - The argument of an awaited call: `await Promise.all([chain.run(), ...])`
 */
function isSafelyConsumed(node, ancestors) {
  const parent = ancestors[ancestors.length - 1];
  if (!parent) return false;

  // await chain.run()
  if (parent.type === 'AwaitExpression') return true;

  // chain.run().then(...) / .catch(...) / .finally(...)
  if (
    parent.type === 'MemberExpression' &&
    parent.object === node &&
    parent.property?.type === 'Identifier' &&
    (parent.property.name === 'then' ||
      parent.property.name === 'catch' ||
      parent.property.name === 'finally')
  ) {
    return true;
  }

  // return chain.run() — assume the enclosing function is async (and will
  // be linted by the no-floating-promises chain at the caller). If the
  // enclosing function is NOT async, the Promise still floats — but that's
  // a separate bug class that no-floating-promises catches generically.
  if (parent.type === 'ReturnStatement' || parent.type === 'ArrowFunctionExpression') {
    return true;
  }

  // Argument to Promise.all / Promise.race / Promise.allSettled / Promise.any
  // We walk up to find the nearest CallExpression and check the callee.
  if (parent.type === 'ArrayExpression') {
    // Look for the enclosing call: ArrayExpression -> CallExpression(args)
    const grand = ancestors[ancestors.length - 2];
    if (
      grand?.type === 'CallExpression' &&
      grand.callee.type === 'MemberExpression' &&
      grand.callee.object?.type === 'Identifier' &&
      grand.callee.object.name === 'Promise' &&
      grand.callee.property?.type === 'Identifier' &&
      ['all', 'race', 'allSettled', 'any'].includes(grand.callee.property.name)
    ) {
      return true;
    }
  }

  // Direct argument: `void chain.run()` (intentional fire-and-forget)
  if (parent.type === 'UnaryExpression' && parent.operator === 'void') {
    return true;
  }

  // Used in a binary/logical expression like `chain.run() || somethingElse`
  // — likely intentional. Defer to no-floating-promises if available.
  // (Don't flag here — too speculative.)

  return false;
}

/** @type {import('eslint').Rule.RuleModule} */
export const noUnawaitedDrizzleTerminator = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow unawaited .run/.get/.all/.values calls on Drizzle query chains. The shared Database type is async (D1) at runtime — silently dropping these promises causes production data loss.',
      recommended: true,
    },
    schema: [],
    messages: {
      missingAwait:
        "Unawaited Drizzle .{{method}}() call. The Database type is async at runtime (D1) — wrap with `await` (or use the dbRun helper for .run()) to avoid silent data loss in production.",
    },
  },

  create(context) {
    return {
      CallExpression(node) {
        // Must be `.something()` on a chain.
        if (node.callee.type !== 'MemberExpression') return;
        if (node.callee.property?.type !== 'Identifier') return;

        const method = node.callee.property.name;
        if (!TERMINATORS.has(method)) return;

        // The receiver must itself be a CallExpression (a chained query builder).
        // Bare `foo.get()` where foo is just an identifier is not flagged.
        if (node.callee.object?.type !== 'CallExpression') return;

        // Must look like a Drizzle chain — at least one builder method present.
        if (!chainContainsDrizzleBuilder(node.callee)) return;

        // Walk up the AST to find this node's ancestors so we can check how
        // it's consumed. ESLint provides getAncestors() but we need the
        // immediate parent first; use the rule's source code traversal.
        const ancestors = context.sourceCode.getAncestors(node);

        if (isSafelyConsumed(node, ancestors)) return;

        context.report({
          node,
          messageId: 'missingAwait',
          data: { method },
        });
      },
    };
  },
};

export default noUnawaitedDrizzleTerminator;
