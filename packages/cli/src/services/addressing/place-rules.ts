/**
 * `@place` acceptance rules and the canonical refusal texts (spec/03 §3).
 *
 * `@place` has exactly three legitimate referent classes (06 §6.4b): backup
 * artifacts, `term connect` targets, and redundant confirmation on live refs.
 * Destination flags (`--to`/`--from`/`--on`) take a BARE place name and are NOT
 * modelled here — they are flags, not refs.
 *
 * This module is the data (`placeAcceptance`) plus the two teaching-error
 * builders every verb shares (`placeConflictError` §3.2, `termConnectCollision
 * Error` §3.3) and the parse-time gate (`assertPlaceAccepted`). The canonical
 * message texts are reproduced verbatim from the spec, with only the concrete
 * names substituted, because scripts and later waves match against them.
 */

import { ERROR_CODES } from '../../types/errors.js';
import { ambiguous, CliExitError, stateMismatch } from '../../utils/cli-exit-error.js';

/**
 * How a verb class treats an `@place` on its positional ref (spec/03 §3.1).
 *
 * - `required-referent`  — `@place` is mandatory and names the artifact's home
 *                          (`backup restore shop:nightly@backup-1`).
 * - `optional-filter`    — `@place` narrows a listing to one place.
 * - `target-select`      — `@place` selects the repo shell vs the machine shell
 *                          (`term connect`).
 * - `accepted-verified`  — a live ref: a matching `@place` is redundant and
 *                          accepted, a contradiction is exit 12 (§3.2).
 * - `rejected-at-parse`  — the noun has no `@place` semantics; exit 2.
 */
export type PlaceAcceptance =
  | 'required-referent'
  | 'optional-filter'
  | 'target-select'
  | 'accepted-verified'
  | 'rejected-at-parse';

/**
 * The repo verbs that take a LIVE ref and therefore accept a redundant-or-
 * contradictory `@place` (spec/03 §3.1, third row, enumerated verbatim). A repo
 * verb NOT in this set (e.g. `create`, which names a not-yet-live repo) rejects
 * `@place` at parse, like the non-repo nouns.
 */
export const REPO_VERBS_ACCEPTING_PLACE: ReadonlySet<string> = new Set([
  'up',
  'down',
  'status',
  'delete',
  'fork',
  'push',
  'pull',
  'migrate',
  'promote',
  'secret',
  'sync',
  'cat',
  'diff',
  'logs',
  'exec',
  'tunnel',
  'commit',
  'branch',
  'checkout',
  'log',
  'merge',
  'trim',
  'policy',
  'admin',
  'replicate',
]);

/**
 * Classify how a command treats `@place` on its ref, from its space-split path
 * (`["repo", "up"]`, `["backup", "restore"]`, `["term", "connect"]`).
 *
 * The default is `rejected-at-parse`: a verb accepts `@place` only if it is in
 * the §3.1 table. That keeps the surface honest — nouns with no place semantics
 * (machine, datastore, cluster, storage, config, backup strategy) refuse it, and
 * so do repo verbs that do not address a live ref.
 */
export function placeAcceptance(path: readonly string[]): PlaceAcceptance {
  const [noun, verb] = path;
  if (noun === 'backup' && verb === 'restore') return 'required-referent';
  if (noun === 'backup' && verb === 'list') return 'optional-filter';
  if (noun === 'term' && verb === 'connect') return 'target-select';
  // A single-segment path has no verb; Set.has then simply misses and falls
  // through to the rejected-at-parse default.
  if (noun === 'repo' && REPO_VERBS_ACCEPTING_PLACE.has(verb)) {
    return 'accepted-verified';
  }
  return 'rejected-at-parse';
}

/**
 * Parse-time gate: refuse `@place` on a noun that has no place semantics
 * (spec/03 §3.1 last row), exit 2. A no-op for every other class — those either
 * require `@place`, filter on it, select with it, or verify it later (§3.2). The
 * `required-referent` class's missing-place check is the verb's own concern, not
 * a parse-time universal, so it is not enforced here.
 */
export function assertPlaceAccepted(path: readonly string[], hasPlace: boolean): void {
  if (!hasPlace) return;
  if (placeAcceptance(path) === 'rejected-at-parse') {
    throw new CliExitError(ERROR_CODES.VALIDATION_ERROR, `${path[0]} names do not take @place.`);
  }
}

/**
 * The §3.2 conflict error (exit 12), used by every `accepted-verified` verb when
 * the addressed `@place` contradicts the repo's derived placement. Canonical
 * text reproduced verbatim from spec/03 §3.2; silent retargeting never happens.
 */
export function placeConflictError(
  refName: string,
  placedAt: string,
  addressedPlace: string
): CliExitError {
  return stateMismatch(
    `${refName} is placed at ${placedAt}; you addressed ${refName}@${addressedPlace}. ` +
      `For the pushed backup copy on ${addressedPlace} use ` +
      `"rdc backup restore ${refName}@${addressedPlace}"; to move the repo use ` +
      `"rdc repo migrate ${refName} --to ${addressedPlace}".`
  );
}

/**
 * The §3.3 `term connect <bare>` namespace-collision error (exit 11): a bare
 * name matches BOTH a repository and a machine. Canonical text reproduced
 * verbatim from spec/03 §3.3, with the collided name substituted.
 */
export function termConnectCollisionError(name: string): CliExitError {
  return ambiguous(
    `${name} is both a repository and a machine. ` +
      `Use "term connect ${name}@<machine>" for the repository shell, ` +
      `or "term connect <machine-name>" for the machine shell.`
  );
}
