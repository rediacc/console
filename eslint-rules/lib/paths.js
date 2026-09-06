/**
 * The ONE place `eslint-rules/` answers "where is the repository".
 *
 * WHY THIS EXISTS. Before this module, six files in this tree resolved a root
 * by hand, in four different idioms, at three different depths:
 *
 *   no-positional-cli-syntax-source.js  __dirname + '../packages/cli/...'
 *   i18n/no-positional-cli-syntax.js    __dirname + '../../packages/cli/...'
 *   i18n/no-undefined-cli-flags.js      __dirname + '../../packages/cli/...'
 *   translation-helpers.js              fileURLToPath(import.meta.url) + '..'
 *   i18n/no-untranslated-tutorial-transcript-values.js   process.cwd()
 *   i18n/shared/require-path-option.js  process.cwd() as a default parameter
 *
 * Three of those spell the SAME file, packages/cli/scripts/command-tree.json,
 * with two different depth strings, because two of the rules sit one directory
 * deeper than the third. A rule that moves between `eslint-rules/` and
 * `eslint-rules/i18n/` therefore silently resolves a path that does not exist,
 * and a rule that reads nothing reports nothing: it looks exactly like a clean
 * tree. That failure mode is the reason check_lint_rule_liveness.py exists, and
 * a hand-counted `..` is the cheapest way to reintroduce it.
 *
 * TWO ROOTS, NOT ONE, AND THE DISTINCTION IS THE POINT.
 *
 *   REPO_ROOT   Where this source file lives. Correct for data the RULE owns
 *               and ships with, such as the CLI command tree. Independent of
 *               how or from where eslint was invoked.
 *
 *   lintRoot()  Where eslint was invoked (`context.cwd`, falling back to the
 *               process cwd). Correct for a relative path a HUMAN wrote in
 *               eslint.config.js, because that path was written relative to the
 *               place the config is run from.
 *
 * Conflating the two is a real defect and not a style question: a rule that
 * resolves its own bundled data through the lint cwd breaks the moment eslint
 * runs with `--cwd` or from a package subdirectory, and a rule that resolves a
 * config-supplied option through REPO_ROOT ignores the option's stated meaning.
 * Two named exports make the choice explicit at every call site.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** Absolute path of `eslint-rules/lib/`. */
const HERE = path.dirname(fileURLToPath(import.meta.url));

/** Absolute path of `eslint-rules/`. */
export const RULES_DIR = path.resolve(HERE, '..');

/** Absolute path of the repository root. */
export const REPO_ROOT = path.resolve(RULES_DIR, '..');

/**
 * A path under the repository root, anchored on this file rather than on cwd.
 *
 * @param {...string} segments Path segments relative to the repository root.
 * @returns {string} Absolute path.
 */
export const repoPath = (...segments) => path.resolve(REPO_ROOT, ...segments);

/**
 * The generated CLI command tree. Three rules read it (no-positional-cli-syntax,
 * no-positional-cli-syntax-source, no-undefined-cli-flags) and each used to
 * spell the depth itself.
 */
export const COMMAND_TREE_PATH = repoPath('packages', 'cli', 'scripts', 'command-tree.json');

/**
 * The directory a config-supplied relative option is resolved against.
 *
 * `context.cwd` is eslint's own notion of the working directory and is the
 * value the config author was writing against. `process.cwd()` is only the
 * fallback for an eslint old enough not to expose it, and for a RuleTester
 * harness that constructs no cwd of its own.
 *
 * @param {{ cwd?: string }} context The rule context.
 * @returns {string} Absolute directory path.
 */
export const lintRoot = (context) => context?.cwd ?? process.cwd();
