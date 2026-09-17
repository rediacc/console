/**
 * The `--changed` selection contract: fail OPEN on scope, REFUSE on a change set
 * that cannot be trusted.
 *
 * WHY THIS IS A MODULE AND NOT FOUR LINES IN `run.ts`. The two halves below pull in
 * opposite directions and the second one was missing, so the first one looked like the
 * whole design:
 *
 *   FAIL OPEN ON SCOPE. Measured on this tree 2026-09-09 against
 *   scripts/ci-runner/gates.lock.json: 474 entries, 464 with `gate: true`, and exactly
 *   46 of those declare `paths`. 418 gates declare none. Scoping a run by `paths` alone
 *   therefore says nothing about 90% of the estate, so an entry with no `paths` is
 *   selected for EVERY non-empty change set. That rule already existed and is preserved
 *   here verbatim; what did not exist was anything asserting it.
 *
 *   THOSE FOUR NUMBERS ARE A TIMESTAMP, NOT A CONSTANT. They moved to 475/465/46/419
 *   within the hour, from another session's manifest entry. `check:ci-changed-selection`
 *   recomputes them from the lock and prints the shape on every run, which is the only
 *   form of this measurement a reader should trust.
 *
 *   REFUSE AN UNUSABLE CHANGE SET. "Nothing changed" and "the differ broke" arrive in
 *   the same shape -- an empty file list -- and under the fail-open rule above the
 *   empty list is the ONE input for which fail-open silently inverts into fail-closed:
 *   every path-declaring gate is dropped because no file matched it, while the
 *   no-paths gates all survive. The run then reports a green having skipped exactly the
 *   gates that were scoped on purpose.
 *
 * WHAT THAT COST, MEASURED BEFORE THE FIX, on the real invocation:
 *
 *     $ CI_RUNNER_BASE=refs/heads/__no_such_ref__ npx tsx scripts/ci-runner/run.ts --list --changed
 *     ci-runner: --changed could not resolve a merge base against refs/heads/__no_such_ref__; selecting every gate
 *     ... rc=0, 418 `gate` lines
 *
 *   Against 464 on a full `--list`. The warning says "selecting every gate" and the
 *   selection drops 46 of them, so the instrument reported work it had not done -- and
 *   it did so on the exact code path that fires when git is unavailable, which is the
 *   path a CI runner takes on a shallow clone.
 *
 * WHY REFUSAL AND NOT "SELECT EVERYTHING". Selecting everything would be safe and
 * silent, and silence is what let this sit. A caller that asked to be scoped and cannot
 * be told what changed has asked a question with no answer; answering it with a full
 * run hides a broken differ for as long as the machine stays fast enough. The exit code
 * is the signal, and the message names the fix (drop `--changed`, or set
 * `CI_RUNNER_BASE` to a ref that resolves).
 */

/** The narrow shape `select()` needs. Structural, so `GateSpec` satisfies it. */
export interface PathScopedSpec {
  readonly id: string;
  readonly paths?: readonly string[];
}

/**
 * `origin` is the whole point of this type. A caller that swallows a git failure and
 * returns `[]` has destroyed the difference between "clean tree" and "no answer", and
 * both of those must refuse anyway -- but for DIFFERENT reasons, and a reader fixing
 * one of them needs to be told which they have.
 */
export interface ChangeSet {
  readonly files: readonly string[];
  readonly origin: 'resolved' | 'unresolved';
  readonly base: string;
  /** Why the differ could not answer. Required when `origin` is `unresolved`. */
  readonly reason?: string;
}

export class ChangeSetRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChangeSetRefusal';
  }
}

/**
 * Throws unless the change set can bear a scoping decision.
 *
 * Three refusals, and the first is the one nobody writes: a selector handed an empty
 * MANIFEST would report "0 gates selected, all fine". Zero inputs is a failure, never
 * a pass.
 */
export function refuseUnusableChangeSet(
  specs: readonly PathScopedSpec[],
  changeSet: ChangeSet
): void {
  if (specs.length === 0) {
    throw new ChangeSetRefusal(
      'the selector was handed ZERO gates, so any selection it reports is vacuous. ' +
        'Its green would mean nothing. Check that scripts/ci-runner/manifest.ts still ' +
        'exports GATES and that the caller passed them.'
    );
  }
  if (changeSet.origin === 'unresolved') {
    throw new ChangeSetRefusal(
      `--changed cannot scope this run: the differ gave no answer against ` +
        `${changeSet.base} (${changeSet.reason ?? 'no reason recorded'}). An unanswerable ` +
        `question is not an empty answer. Run without --changed to select every gate, or ` +
        `set CI_RUNNER_BASE to a ref that resolves (a shallow clone often cannot reach ` +
        `origin/main; \`git fetch --deepen=100\` or \`fetch-depth: 0\` fixes it).`
    );
  }
  if (changeSet.files.length === 0) {
    throw new ChangeSetRefusal(
      `--changed found ZERO changed files against ${changeSet.base}, and refuses to ` +
        `report a green on that. Nothing changed and the differ broke are the same shape ` +
        `here, and the empty set is the one input where scoping silently inverts: every ` +
        `path-declaring gate is dropped for want of a match while the rest survive, so ` +
        `the run looks scoped and is simply missing them. If the tree really is clean, ` +
        `there is nothing to check -- drop --changed.`
    );
  }
}

export interface ChangedSelection<T> {
  readonly chosen: readonly T[];
  /** The SHAPE, not just the verdict, so a reader can see a number collapse. */
  readonly note: string;
  readonly scoped: number;
  readonly unscoped: number;
  readonly matched: number;
}

/**
 * Fail-open selection. `matches(file, globs)` is injected so this module owns no glob
 * dialect: `run.ts` already has one, and a second implementation of the same matcher is
 * a second thing to drift.
 *
 * THE FAIL-OPEN CLAUSE IS `spec.paths === undefined`, NOT `!spec.paths?.length`. An
 * entry that declares `paths: []` has said something -- "nothing selects me" -- and
 * conflating that with saying nothing is how a typo becomes an exemption. Neither form
 * is in the lock today; the distinction is written down before one appears.
 */
export function selectChanged<T extends PathScopedSpec>(
  specs: readonly T[],
  changeSet: ChangeSet,
  matches: (file: string, globs: readonly string[]) => boolean
): ChangedSelection<T> {
  refuseUnusableChangeSet(specs, changeSet);
  const unscoped = specs.filter((s) => s.paths === undefined);
  const scoped = specs.filter((s) => s.paths !== undefined);
  const matched = scoped.filter((s) => changeSet.files.some((f) => matches(f, s.paths ?? [])));
  // Order is preserved from `specs` rather than concatenating the two buckets: the pool uses array index as a scheduling tiebreaker, so reordering here would change the run without changing the set.
  const keep = new Set<T>([...unscoped, ...matched]);
  const chosen = specs.filter((s) => keep.has(s));
  const note =
    `--changed (${changeSet.files.length} file(s) vs ${changeSet.base}): ` +
    `${chosen.length} selected = ${unscoped.length} declaring no paths (always selected) ` +
    `+ ${matched.length} of ${scoped.length} path-scoped`;
  return {
    chosen,
    note,
    scoped: scoped.length,
    unscoped: unscoped.length,
    matched: matched.length,
  };
}
