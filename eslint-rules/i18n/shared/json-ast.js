/**
 * Shared helpers for walking @eslint/json ASTs.
 *
 * Locale files parse as Document -> Object -> Member[], where a Member's name
 * is a String node in JSON and an Identifier node in JSONC/JSON5. Every locale
 * rule needs the same three moves, and each one used to inline them.
 *
 * ---------------------------------------------------------------------------
 * THE `body` TRAP -- why this module exists at all
 * ---------------------------------------------------------------------------
 * Only the Document node carries `body`. An Object node carries `members`
 * DIRECTLY. Probed against @eslint/json:
 *
 *   Document keys [ 'type', 'body', 'loc', 'tokens', 'range' ]
 *   body.type Object   keys: [ 'type', 'members', 'loc', 'range' ]
 *   members isArray: true | o.body: undefined
 *
 * A rule that reaches for `node.body?.members` on an Object therefore walks an
 * empty list and CANNOT report anything, ever. Five rules did exactly that and
 * were inert for it -- sorted-keys, no-empty-translations,
 * key-naming-convention, no-unused-keys, translation-staleness -- while nine
 * siblings used the correct access. They are all routed through
 * `objectMembers` now, and no rule spells the walk inline any more, so the
 * broken spelling has nowhere left to live. Keep it that way: a new locale
 * rule reaches for this helper, never for `.members` (and never for `.body`).
 */

/** A member's key as a plain string, or undefined when it has none. */
export const memberKey = (member) =>
  member.name?.type === 'String' ? member.name.value : member.name?.name;

/** The members of an Object node; [] for a missing node or any other type. */
export const objectMembers = (node) =>
  node?.type === 'Object' ? node.members || [] : [];

/** Dot-join a key onto its parent path ("" parent yields the bare key). */
export const joinPath = (path, key) => (path ? `${path}.${key}` : key);
