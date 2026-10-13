/**
 * The ONE answer `scripts/` gives to "a private submodule this gate reads is
 * not checked out".
 *
 * THE DEFECT IT CLOSES (worklist #11bcecca, 2026-10-08). Gates that read a file
 * under `private/<submodule>/` printed a skip line and exited 0 when the file
 * was absent. Locally that is the right call: a fresh clone without
 * `--recursive` must stay workable. In CI it is a gate that cannot fail: a
 * workflow checkout that lost `submodules: true` (or a lane that only inits one
 * submodule) turns every such gate into a green tick over nothing, and the tick
 * reads exactly like a pass.
 *
 * THE CONTRACT is the one `.ci/rediacc_ci/core/common.py` `require_submodule`
 * (the port of the deleted bash `common.sh` function) already carries, three
 * outcomes and not two:
 *
 *   present          -> true
 *   absent, in CI    -> a loud refusal naming the missing paths and the fix,
 *                       then process.exit(1). Not a return value: a caller
 *                       cannot forget to act on it.
 *   absent, locally  -> a loud skip line that says it is a hard failure in CI,
 *                       then false. The caller skips (or, for a gate that
 *                       scans several submodules, scans the rest).
 *
 * CI IS ANY SET `CI` OR `GITHUB_ACTIONS` VALUE THAT IS NOT AN EXPLICIT OFF (see
 * `inCi`). GitHub Actions exports both as `true` on every runner.
 *
 * THE SEAM. `SUBMODULE_PRESENCE_ROOT` replaces the repository root when a gate
 * builds a submodule path through `submodulePath()`. A gate's own test points it
 * at a directory that does not exist, so every `private/...` path the gate reads
 * is absent, and asserts both arms: exit non-zero under `CI=true`, exit 0
 * without. One seam for every gate, on the `REDIACC_CI_ROOT` precedent
 * (`.ci/rediacc_ci/paths.py`), instead of one per-gate spelling each.
 */

import fs from 'node:fs';
import path from 'node:path';
import { NC, RED, YELLOW } from './console.js';
import { envRoot, REPO_ROOT } from './repo-root.js';

/** The root `private/<submodule>/...` paths resolve against: the repo, unless the SUBMODULE_PRESENCE_ROOT seam (set by a gate's test) moves it. */
export const submoduleRoot = (): string => envRoot('SUBMODULE_PRESENCE_ROOT');

/**
 * An absolute path under the (possibly relocated) root.
 *
 * @param segments Path segments relative to the repository root, starting with `private/<submodule>`.
 */
export const submodulePath = (...segments: string[]): string =>
  path.resolve(submoduleRoot(), ...segments);

/**
 * True on a CI runner: CI is any SET value other than an explicit off (`CI=1` counts too, and the value is trimmed). check-account-email-templates failed on any truthy `CI` before this helper existed (review 2bc9b47a.1), so the
 * literal-`true` reading would have turned a missing submodule on a `CI=1` runner into a silent skip.
 */
export function inCi(env: NodeJS.ProcessEnv = process.env): boolean {
  const on = (v: string | undefined): boolean =>
    v !== undefined && v.trim() !== '' && !/^(0|false|no|off)$/i.test(v.trim());
  return on(env.CI) || on(env.GITHUB_ACTIONS);
}

export type SubmoduleVerdict =
  | { state: 'present'; missing: [] }
  | { state: 'absent-ci' | 'absent-local'; missing: string[] };

/**
 * The pure decision: which of `paths` are absent, and what that means here.
 *
 * @param paths Files or directories the gate cannot run without.
 * @param env The environment to judge CI from.
 * @param exists The existence probe, injectable so the decision is testable without a tree.
 */
export function submoduleVerdict(
  paths: readonly string[],
  env: NodeJS.ProcessEnv = process.env,
  exists: (p: string) => boolean = fs.existsSync
): SubmoduleVerdict {
  if (paths.length === 0) {
    // Asking about nothing would answer "present" for a gate that checks nothing.
    throw new Error('submoduleVerdict: called with no paths; that would certify an empty scope');
  }
  const missing = paths.filter((p) => !exists(p));
  if (missing.length === 0) return { state: 'present', missing: [] };
  return { state: inCi(env) ? 'absent-ci' : 'absent-local', missing };
}

/** `private/<name>` for a path under the root, or null when the path is not in a submodule. */
export function submoduleOf(p: string): string | null {
  const rel = path.relative(submoduleRoot(), p).split(path.sep).join('/');
  const m = /^private\/[^/]+/.exec(rel);
  return m ? m[0] : null;
}

const shown = (p: string): string => {
  const rel = path.relative(submoduleRoot(), p);
  return rel.startsWith('..') ? p : rel;
};

/**
 * Gate on the presence of submodule paths: true when all are present, false
 * (after a loud skip line) when any is absent locally, and process.exit(1)
 * (after naming the fix) when any is absent in CI.
 *
 * @param label What the gate would have checked, as the reader should see it.
 * @param paths Files or directories under `private/` the gate cannot run without.
 */
export function requireSubmodule(label: string, paths: readonly string[]): boolean {
  const verdict = submoduleVerdict(paths);
  if (verdict.state === 'present') return true;

  const subs = [
    ...new Set(verdict.missing.map(submoduleOf).filter((x): x is string => x !== null)),
  ];
  const list = verdict.missing.map(shown).join(', ');
  if (verdict.state === 'absent-ci') {
    console.error(`${RED}✗ ${label}: required in CI but missing: ${list}${NC}`);
    console.error('  A skip here would report success while checking nothing.');
    console.error(
      `  Fix the workflow checkout (submodules: true, or git submodule update --init${subs.length > 0 ? ` ${subs.join(' ')}` : ''}).`
    );
    process.exit(1);
  }
  const why = subs.length > 0 ? ` (${subs.join(', ')} not checked out)` : '';
  // NOT CHECKED rather than SKIPPED: a gate whose scope is several submodules
  // scans the ones that are present after this line, so only the named part is unread.
  console.log(`${YELLOW}⊘ NOT CHECKED: ${label}: ${list} absent${why}.${NC}`);
  console.log('  Skipped here, outside CI; under CI this is a hard failure.');
  return false;
}

/**
 * The submodule paths `.gitmodules` declares, for a gate whose scope is every
 * submodule rather than one file in one of them.
 *
 * @param root The repository whose `.gitmodules` is read; always the real one.
 */
export function declaredSubmodules(root: string = REPO_ROOT): string[] {
  const file = path.join(root, '.gitmodules');
  if (!fs.existsSync(file)) return [];
  return [...fs.readFileSync(file, 'utf8').matchAll(/^\s*path\s*=\s*(\S+)\s*$/gm)].map((m) => m[1]);
}

/**
 * The `.git` marker of every declared submodule, relocated by the seam. An
 * uninitialised submodule is an EMPTY directory git leaves behind, so the
 * directory alone would read as present; its `.git` entry is what a checkout
 * creates.
 *
 * Refuses an empty declaration: no `.gitmodules` (or a parse that found
 * nothing) would otherwise certify every submodule present by checking none.
 */
export function declaredSubmoduleMarkers(): string[] {
  const subs = declaredSubmodules();
  if (subs.length === 0) {
    console.error(
      `${RED}✗ .gitmodules declared no submodules; the presence check has lost its subject.${NC}`
    );
    process.exit(1);
  }
  return subs.map((s) => submodulePath(s, '.git'));
}
