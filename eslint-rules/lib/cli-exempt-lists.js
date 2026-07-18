/**
 * The exemption lists the positional-CLI-syntax checks share.
 *
 * ★ ONE DEFINITION, THREE CONSUMERS. These lists used to be hand-copied into
 * `scripts/lib/positional-cli-detector.ts`, `eslint-rules/no-positional-cli-syntax-source.js`
 * and `eslint-rules/i18n/no-positional-cli-syntax.js`, with the third copy also
 * pasted into `eslint.config.js`. The rule this repo learned the hard way: IF TWO
 * PLACES MUST AGREE AND NEITHER IMPORTS THE OTHER, THEY ALREADY DISAGREE — you just
 * have not looked yet. "Keep in sync with X" is a comment, and a comment cannot fail.
 *
 * Plain ESM JavaScript on purpose: ESLint rules are plain JS and cannot import a
 * `.ts` module, so the shared definition has to live somewhere both a rule and a
 * tsx script can reach. That constraint is what produced the copies; this file is
 * the answer to it.
 *
 * ★ Both lists were STALE when they were unified. Every entry named a command that
 * no longer exists. A blanket exemption for a command that is gone is not harmless:
 * it is a fail-open that arms itself the moment anyone reuses the name.
 */

/**
 * Commands whose positional argument is a FREEFORM string (a function name, a raw
 * command), not a resource name someone would positionalise by mistake. They are
 * held out of the zero-positional denylist.
 *
 * Pruned 2026-07-13: `agent schema` / `agent exec` (the `agent` noun was removed),
 * and `mcp capabilities` / `mcp schema` / `mcp exec` (the `mcp` noun is `mcp serve`
 * alone now). `run` remains: it is the Rediaccfile-function escape hatch, held out
 * of the generated tree entirely.
 */
export const FREEFORM_ARG_COMMAND_PATHS = ['run'];

/**
 * Line prefixes exempt from the positional checks.
 *
 * ★ EMPTY, and that is the correct value. It used to hold twelve entries —
 * `rdc auth`, `rdc audit`, `rdc bridge`, `rdc organization`, `rdc permission`,
 * `rdc protocol`, `rdc queue`, `rdc region`, `rdc repository`, `rdc team`,
 * `rdc user`, `rdc ceph` — described as "cloud-adapter and legacy groups that
 * legitimately use positional subcommands". EVERY ONE OF THEM WAS DELETED WITH THE
 * CLOUD ADAPTER. So the list exempted twelve commands that do not exist, in three
 * files, and would have silently exempted any of those names the day it came back.
 *
 * If a genuine exemption is ever needed, add it HERE, with the reason, and it takes
 * effect in all three consumers at once.
 */
export const EXEMPT_COMMAND_PREFIXES = [];
