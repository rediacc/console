/**
 * The scheduler: a worker pool over the gate manifest.
 *
 * CI parallelises the same work at JOB level, ten lanes grouped by what each
 * needs on disk, and gets isolation for free because every lane is a separate
 * runner. One machine with one tree does not get that, so the facts CI never
 * had to write down are declared per gate instead: `needs` for ordering, and
 * `mutex` / `reads` for shared mutable resources (the per-package dist trees,
 * private/renet/bin, the account vitest state, packages/www/dist, and the
 * working tree itself).
 *
 * Longest-first dequeuing is what makes the flattened battery pay off: the
 * achievable floor is the longest single gate, not the sum, so the critical
 * path has to start in the first wave.
 *
 * ---------------------------------------------------------------------------
 * THE ISOLATION CONTRACT (W2.4b). Defined here ONCE and implemented identically
 * by the other scheduler in this repo, `.ci/scripts/test/run-all.sh`.
 *
 *   A gate names the shared resources it touches. `mutex: [r]` is an EXCLUSIVE
 *   claim on r; `reads: [r]` is a SHARED claim on the same r. Two gates may
 *   overlap unless one of them holds r exclusively and the other holds r at
 *   all. Shared never conflicts with shared. One namespace, two claim strengths:
 *   a multiple-readers / single-writer lock, keyed on strings.
 *
 * WHY A SECOND CLAIM STRENGTH EXISTS AT ALL, since exclusive-only was enough
 * for the five build resources this file was written for. The hazard the
 * gate-test battery actually has is asymmetric: two of those tests WRITE into
 * the real tree (they drive code that hardcodes the real tree and offers no
 * fixture seam), while a dozen others RECURSIVELY ENUMERATE the same
 * directories. A file appearing or vanishing mid-`cp -r` is a hard error under
 * `set -euo pipefail`, so writer-versus-scanner must be excluded -- but
 * scanner-versus-scanner must NOT be, or twenty-one read-only tests serialise
 * for nothing. An exclusive-only mutex can express one of those or the other,
 * never both, which is precisely why run-all.sh grew a private three-set
 * scheduler instead of declaring anything.
 *
 * WHAT THE TWO SCHEDULERS DID BEFORE THIS, and it is worth stating plainly
 * because they disagreed for months without anything noticing. run-all.sh
 * carried the membership as two hand-maintained NAME LISTS inside the runner
 * (WRITER_TESTS, SCANNER_TESTS) and honoured them. The manifest carried nothing:
 * measured 2026-09-06 at commit ac817a647, all three real-tree writers --
 * gate-test:gate-paths-exist, gate-test:gate-anti-vacuity,
 * gate-test:generate-tag-inputs -- are registered with NO mutex, and zero of the
 * 147 qualityGateTest entries carry one. So `npm run ci` schedules exactly the
 * combination run-all.sh's own header calls "a flake manufactured by the
 * runner", while the CI step that runs the same 147 tests is protected. The
 * isolation was real in one scheduler and absent in the other, and the only
 * thing keeping the difference invisible is that the two are rarely both hot.
 *
 * The resource names are PATH-SCOPED (`tree:<dir>`), so the declaration says
 * what a gate touches rather than which bucket someone put it in, and a new
 * gate declares itself instead of being added to a list in a runner.
 * ---------------------------------------------------------------------------
 *
 * See agent/PLAN-npm-ci-parallel-parity.md sections 3 and 4.2.
 */

import type { ExecOutcome } from './exec';
import type { GateSpec } from './manifest';

/**
 * `blocked` is a gate that COULD NOT RUN, as distinct from one that ran and
 * judged the code red. A missing toolchain is not evidence about the code, and
 * conflating the two is what makes a pre-push lane unusable: measured
 * 2026-08-27, ten of twelve reds on a normal developer tree were ambient, three
 * of them purely "this machine lacks ruff / workers-types".
 *
 * It is NOT a skip. A gate that opts into this must exit CANNOT_RUN
 * deliberately and say what is missing; the default for any other non-zero exit
 * is still `fail`. And it stays visible: the footer counts it, the receipt
 * records it, and the pre-push guard WARNS on it rather than staying quiet --
 * "a linter that cannot run is a gate that cannot fail" remains true, so this
 * makes that state loud rather than forgiving it.
 */
type GateStatus = 'ok' | 'fail' | 'blocked' | 'skipped';

/**
 * Exit code a gate uses to say "I could not run", borrowed from the POSIX
 * convention automake uses for a skipped test. Chosen because it cannot collide
 * with a real verdict: 1 is a finding, 2 is usage, 124 is a timeout, 127 is
 * not-found (which is a genuine breakage, not a considered "cannot run").
 */
// NOT exported: nothing outside this module imports it, and knip's --treat-config-hints-as-errors counts an unused export as a finding. The shell gates that exit 77 (check-python-lint.sh, shfmt.sh) cannot import a TypeScript constant anyway, so the value is duplicated there as a literal
// with this comment as its reference point.
const CANNOT_RUN = 77;

export interface GateResult {
  id: string;
  /** Mirrors GateSpec.gate: false nodes are prerequisites, not validations. */
  gate: boolean;
  status: GateStatus;
  ms: number;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  /** The exact command to re-run this gate by hand. */
  rerun: string;
  /** On a skip: which dependency killed it, or that --fail-fast stopped the run. */
  reason?: string;
  /** On a zero-exit gate the runner failed anyway; see exec.ts vacuityCheck. */
  vacuity?: string;
}

export interface PoolOptions {
  jobs: number;
  heavyLimit: number;
  failFast: boolean;
  /** Expected ms per id, for longest-first ordering. Missing ids fall back. */
  durations: Map<string, number>;
  exec: (spec: GateSpec) => Promise<ExecOutcome>;
  onStart?: (spec: GateSpec) => void;
  onFinish?: (result: GateResult) => void;
}

function mustGet(byId: Map<string, GateSpec>, id: string): GateSpec {
  const spec = byId.get(id);
  if (spec === undefined) throw new Error(`ci-runner: internal error, unknown gate id ${id}`);
  return spec;
}

function indexById(all: readonly GateSpec[]): Map<string, GateSpec> {
  const byId = new Map<string, GateSpec>();
  for (const spec of all) {
    if (byId.has(spec.id)) throw new Error(`ci-runner: duplicate manifest id: ${spec.id}`);
    byId.set(spec.id, spec);
  }
  return byId;
}

/**
 * A cycle would deadlock the pool with no diagnostic, which is the worst
 * possible way for a manifest bug to present. Detect it over the WHOLE
 * manifest at graph-build time and print the path.
 */
function assertAcyclic(all: readonly GateSpec[], byId: Map<string, GateSpec>): void {
  const done = new Set<string>();
  const onStack = new Set<string>();
  const trail: string[] = [];

  const visit = (id: string): void => {
    if (done.has(id)) return;
    if (onStack.has(id)) {
      const from = trail.indexOf(id);
      const cycle = [...trail.slice(from), id].join(' -> ');
      throw new Error(`ci-runner: dependency cycle in the manifest: ${cycle}`);
    }
    onStack.add(id);
    trail.push(id);
    for (const need of byId.get(id)?.needs ?? []) visit(need);
    trail.pop();
    onStack.delete(id);
    done.add(id);
  };

  for (const spec of all) visit(spec.id);
}

/**
 * Validate the manifest and expand a selection into the set the pool will run:
 * the selected gates plus the transitive closure of their `needs`.
 *
 * The closure is what makes `gate: false` nodes work. build:packages and
 * build:www validate nothing, so they are never selected directly; they run
 * only because something that needs them was selected. Returned in manifest
 * order so the summary is stable across runs.
 */
export function buildGraph(all: readonly GateSpec[], selected: ReadonlySet<string>): GateSpec[] {
  const byId = indexById(all);

  for (const spec of all) {
    for (const need of spec.needs ?? []) {
      if (!byId.has(need)) {
        throw new Error(`ci-runner: ${spec.id} needs '${need}', which is not a manifest id`);
      }
    }
  }
  assertAcyclic(all, byId);

  const keep = new Set<string>();
  const add = (id: string): void => {
    if (keep.has(id)) return;
    keep.add(id);
    for (const need of mustGet(byId, id).needs ?? []) add(need);
  };
  for (const id of selected) {
    if (!byId.has(id)) throw new Error(`ci-runner: selection names unknown gate '${id}'`);
    add(id);
  }

  return all.filter((spec) => keep.has(spec.id));
}

/**
 * Shared claims, read structurally rather than off the type.
 *
 * `mutex` has been a declared `GateSpec` field since the pool was written;
 * `reads` is the other half of the isolation contract and its declaration lands
 * with the registry change that populates it (see the W2.4b proposal). Reading
 * it structurally means this scheduler already honours the field the day the
 * data arrives, and behaves exactly as it does today until then -- an absent
 * `reads` is an empty claim set, which is the same graph the pool has always
 * built. It is NOT a compatibility shim to keep around: once gate-spec.ts
 * declares `reads?: string[]`, this function collapses to `spec.reads ?? []`.
 */
function sharedClaims(spec: GateSpec): readonly string[] {
  const declared = (spec as GateSpec & { reads?: unknown }).reads;
  return Array.isArray(declared) ? declared.filter((r): r is string => typeof r === 'string') : [];
}

export async function runPool(
  specs: readonly GateSpec[],
  opts: PoolOptions
): Promise<GateResult[]> {
  const byId = indexById(specs);
  const position = new Map(specs.map((spec, i) => [spec.id, i]));
  const results = new Map<string, GateResult>();
  const unstarted = new Set(specs.map((spec) => spec.id));
  const running = new Map<string, Promise<{ id: string; outcome: ExecOutcome }>>();
  // The isolation contract's two claim strengths. Exclusive is a set because a
  // resource has at most one writer at a time; shared is a COUNT because any
  // number of readers may hold one and the last one out has to be the one that releases it. A plain Set here would have the first reader to finish unlock a resource three others were still reading, which is the shape of bug that only ever shows up as an unreproducible mid-enumeration error.
  const heldExclusive = new Set<string>();
  const heldShared = new Map<string, number>();
  let slots = 0;
  let heavyRunning = 0;
  let stopped = false;

  // A missing or corrupt duration cache must never fail the run, so an unknown gate is simply assumed cheap-ish and sorts late.
  const expected = (spec: GateSpec): number =>
    opts.durations.get(spec.id) ?? (spec.weight ?? 1) * 5000;
  // Clamped: a gate declaring more weight than the whole budget would never be admissible and would hang the pool at --jobs 1.
  const effWeight = (spec: GateSpec): number =>
    Math.min(Math.max(1, spec.weight ?? 1), Math.max(1, opts.jobs));
  const rank = (a: GateSpec, b: GateSpec): number =>
    expected(b) - expected(a) || (position.get(a.id) ?? 0) - (position.get(b.id) ?? 0);

  // THE CONTRACT, and this is the whole of it. An exclusive claim conflicts with
  // any claim on the same resource; a shared claim conflicts only with an
  // exclusive one. Shared against shared is deliberately admissible, which is the asymmetry the header explains and the reason this is not one Set.
  const blockedByClaim = (spec: GateSpec): boolean =>
    (spec.mutex ?? []).some((r) => heldExclusive.has(r) || (heldShared.get(r) ?? 0) > 0) ||
    sharedClaims(spec).some((r) => heldExclusive.has(r));

  const record = (result: GateResult): void => {
    results.set(result.id, result);
    unstarted.delete(result.id);
    opts.onFinish?.(result);
  };

  const skip = (spec: GateSpec, reason: string): GateResult => ({
    id: spec.id,
    gate: spec.gate,
    status: 'skipped',
    ms: 0,
    exitCode: null,
    stdout: '',
    stderr: '',
    rerun: spec.run,
    reason,
  });

  const launch = (spec: GateSpec): void => {
    unstarted.delete(spec.id);
    slots += effWeight(spec);
    if (spec.heavy === true) heavyRunning += 1;
    for (const r of spec.mutex ?? []) heldExclusive.add(r);
    for (const r of sharedClaims(spec)) heldShared.set(r, (heldShared.get(r) ?? 0) + 1);
    opts.onStart?.(spec);
    running.set(
      spec.id,
      opts.exec(spec).then((outcome) => ({ id: spec.id, outcome }))
    );
  };

  while (unstarted.size > 0 || running.size > 0) {
    // A dependency that failed poisons its dependents transitively, so run the propagation to a fixpoint. Reporting them as skipped rather than passed is what keeps a broken prerequisite from reading as green.
    let changed = true;
    while (changed) {
      changed = false;
      for (const id of [...unstarted]) {
        const spec = mustGet(byId, id);
        const dead = (spec.needs ?? []).find((need) => {
          const r = results.get(need);
          return r !== undefined && r.status !== 'ok';
        });
        if (dead !== undefined) {
          record(skip(spec, `needs ${dead}`));
          changed = true;
        }
      }
    }

    if (stopped) {
      for (const id of [...unstarted]) record(skip(mustGet(byId, id), 'not run (--fail-fast)'));
    }

    const ready = [...unstarted]
      .map((id) => mustGet(byId, id))
      .filter((spec) => (spec.needs ?? []).every((need) => results.get(need)?.status === 'ok'))
      .sort(rank);

    for (const spec of ready) {
      if (slots + effWeight(spec) > opts.jobs) continue;
      if (spec.heavy === true && heavyRunning >= opts.heavyLimit) continue;
      if (blockedByClaim(spec)) continue;
      launch(spec);
    }

    if (running.size === 0 && unstarted.size > 0) {
      // Nothing is in flight and nothing was admissible: the budget is smaller than the head of the queue. Admit it anyway rather than spin. No claim can be the blocker here, since nothing holds one -- but the predicate is still consulted rather than assumed, because "cannot happen" is how a stall turns into a silent over-admission that violates the very exclusion this branch is
      // bypassing.
      const head = ready.find((spec) => !blockedByClaim(spec));
      if (head === undefined) {
        throw new Error('ci-runner: internal error, pool stalled with work outstanding');
      }
      launch(head);
    }

    if (running.size === 0) continue;

    const { id, outcome } = await Promise.race(running.values());
    const spec = mustGet(byId, id);
    running.delete(id);
    slots -= effWeight(spec);
    if (spec.heavy === true) heavyRunning -= 1;
    for (const r of spec.mutex ?? []) heldExclusive.delete(r);
    for (const r of sharedClaims(spec)) {
      const remaining = (heldShared.get(r) ?? 1) - 1;
      if (remaining > 0) heldShared.set(r, remaining);
      else heldShared.delete(r);
    }

    // A vacuity finding always means `fail`, even at CANNOT_RUN: a gate that claims it cannot run AND trips the anti-vacuity oracle is not a machine missing a tool, it is a gate lying about what it did.
    const cannotRun = outcome.code === CANNOT_RUN && outcome.vacuity === undefined;
    const failed = !cannotRun && (outcome.code !== 0 || outcome.vacuity !== undefined);
    record({
      id,
      gate: spec.gate,
      status: cannotRun ? 'blocked' : failed ? 'fail' : 'ok',
      ms: outcome.ms,
      exitCode: outcome.code,
      stdout: outcome.stdout,
      stderr: outcome.stderr,
      rerun: spec.run,
      vacuity: outcome.vacuity,
    });
    if (failed && opts.failFast) stopped = true;
  }

  // Manifest order, not completion order: the exit code and the summary must be identical across runs even though the scheduling never is.
  return specs.map((spec) => {
    const result = results.get(spec.id);
    if (result === undefined)
      throw new Error(`ci-runner: internal error, no result for ${spec.id}`);
    return result;
  });
}
