/**
 * The ONE place `scripts/` answers "where is the repository".
 *
 * THE MEASUREMENT THAT MOTIVATES IT, taken 2026-09-06 over `git ls-files scripts`
 * (164 TypeScript files). Around ninety files declare a repository root by hand,
 * under NINE different constant names:
 *
 *   ROOT, REPO, REPO_ROOT, CONSOLE_ROOT, ROOT_DIR, repoRoot, root, HERE, SCRIPT_DIR
 *
 * in FOUR different idioms:
 *
 *   path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
 *   const __dirname = path.dirname(fileURLToPath(import.meta.url)); path.join(__dirname, '..')
 *   join(fileURLToPath(new URL('.', import.meta.url)), '..')
 *   process.cwd(), or `process.env.SOME_ROOT ?? process.cwd()`
 *
 * at two different DEPTHS, because `scripts/lib/*.ts` and `scripts/ci-runner/*.ts`
 * need `'..', '..'` while `scripts/*.ts` needs `'..'`. That difference is the
 * whole hazard: a file moved one directory keeps a `..` count that now points at
 * `scripts/` instead of the repository, every path built from it misses, and a
 * gate that reads nothing reports nothing.
 *
 * WHY THE FOURTH IDIOM IS A DEFECT AND NOT A STYLE, and this is the part worth
 * reading. `check-gate-cwd-independence.ts` states the rule plainly: "no gate
 * derives a path from process.cwd()". Its regex only matches cwd() as the FIRST
 * ARGUMENT of path.resolve/join, so a bare
 *
 *   const ROOT = process.env.SECRET_SCOPE_ROOT ?? process.cwd();
 *
 * sails past it, and every path the gate builds afterwards is nonetheless
 * derived from the working directory. Measured on 2026-09-06 the gate reported
 * "240 gate script(s), all anchored on their own location" while four gates were
 * doing exactly that: check-e2e-skip-hygiene.ts:37, check-player-css-scope.ts:37,
 * check-secret-scope.ts:73, check-tracked-credentials.ts:77.
 *
 * `envRoot()` below is the drop-in for that shape. It keeps the environment
 * override those four gates use to point at a fixture tree, and replaces the
 * cwd fallback with the file-anchored root, so the override stays and the
 * accident goes.
 *
 * ANCHORING BY MARKER, NOT BY DEPTH. This module is itself a file that a later
 * phase may move, so counting `..` here would reproduce the bug it exists to
 * remove one level up. It walks parents instead, looking for the directory that
 * holds BOTH `package.json` and `.ci`. Only the repository root has both:
 * `packages/*` and `private/*` each carry a package.json and no `.ci`.
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * Walk up from a starting directory to the repository root.
 *
 * Exported for the selftest, which proves the walk is what finds the root
 * rather than a constant that happens to agree with it today.
 *
 * @param from Directory to start from.
 * @returns The repository root.
 * @throws If no ancestor carries both markers, which means this file has been
 *   copied out of the repository and silently guessing would be worse.
 */
export function findRepoRoot(from: string): string {
  let dir = path.resolve(from);
  for (;;) {
    if (fs.existsSync(path.join(dir, 'package.json')) && fs.existsSync(path.join(dir, '.ci'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      // The vacuity guard, and it is a real refusal rather than the word.
      // Falling back to cwd, or to `from`, or to `/` would hand every caller a
      // root that is confidently wrong, and a gate anchored on a wrong root
      // reads an empty corpus and prints a tick. Throwing is the only answer
      // that cannot be mistaken for success.
      throw new Error(
        `repo-root: VACUOUS anchor. Walked to the filesystem root from ${from} without ` +
          'finding a directory holding both package.json and .ci, so there is no repository ' +
          'root to return. Refusing rather than guessing: a wrong root makes every corpus ' +
          'scan built on it come back empty, which is indistinguishable from a clean tree.'
      );
    }
    dir = parent;
  }
}

/** Absolute path of the repository root. */
export const REPO_ROOT = findRepoRoot(import.meta.dirname);

/**
 * An absolute path under the repository root.
 *
 * @param segments Path segments relative to the repository root.
 */
export const repoPath = (...segments: string[]): string => path.resolve(REPO_ROOT, ...segments);

/**
 * A repository-relative path, for messages a human has to act on.
 *
 * Every gate that prints an absolute path makes its own output un-pasteable
 * into a `git` command, so this is not cosmetic.
 *
 * @param absolute An absolute path.
 */
export const rel = (absolute: string): string => path.relative(REPO_ROOT, absolute);

/**
 * The root a gate should use, honouring an environment override.
 *
 * This replaces `process.env.X ?? process.cwd()`. The override exists so a gate
 * can be pointed at a fixture tree by its own test; the cwd fallback exists for
 * no reason at all, and is the hole described in this file's header.
 *
 * @param envName Environment variable a test uses to redirect the gate.
 */
export const envRoot = (envName: string): string => {
  const override = process.env[envName];
  return override !== undefined && override !== '' ? path.resolve(override) : REPO_ROOT;
};
