/**
 * The scheduler: a worker pool over the gate manifest.
 *
 * CI parallelises the same work at JOB level, ten lanes grouped by what each
 * needs on disk, and gets isolation for free because every lane is a separate
 * runner. One machine with one tree does not get that, so the two facts CI
 * never had to write down are declared per gate instead: `needs` for ordering
 * and `mutex` for shared mutable resources (the per-package dist trees,
 * private/renet/bin, the account vitest state, packages/www/dist).
 *
 * Longest-first dequeuing is what makes the flattened battery pay off: the
 * achievable floor is the longest single gate, not the sum, so the critical
 * path has to start in the first wave.
 *
 * See agent/PLAN-npm-ci-parallel-parity.md sections 3 and 4.2.
 */

import type { ExecOutcome } from './exec';
import type { GateSpec } from './manifest';

type GateStatus = 'ok' | 'fail' | 'skipped';

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

export async function runPool(
  specs: readonly GateSpec[],
  opts: PoolOptions
): Promise<GateResult[]> {
  const byId = indexById(specs);
  const position = new Map(specs.map((spec, i) => [spec.id, i]));
  const results = new Map<string, GateResult>();
  const unstarted = new Set(specs.map((spec) => spec.id));
  const running = new Map<string, Promise<{ id: string; outcome: ExecOutcome }>>();
  const held = new Set<string>();
  let slots = 0;
  let heavyRunning = 0;
  let stopped = false;

  // A missing or corrupt duration cache must never fail the run, so an
  // unknown gate is simply assumed cheap-ish and sorts late.
  const expected = (spec: GateSpec): number =>
    opts.durations.get(spec.id) ?? (spec.weight ?? 1) * 5000;
  // Clamped: a gate declaring more weight than the whole budget would never
  // be admissible and would hang the pool at --jobs 1.
  const effWeight = (spec: GateSpec): number =>
    Math.min(Math.max(1, spec.weight ?? 1), Math.max(1, opts.jobs));
  const rank = (a: GateSpec, b: GateSpec): number =>
    expected(b) - expected(a) || (position.get(a.id) ?? 0) - (position.get(b.id) ?? 0);

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
    for (const group of spec.mutex ?? []) held.add(group);
    opts.onStart?.(spec);
    running.set(
      spec.id,
      opts.exec(spec).then((outcome) => ({ id: spec.id, outcome }))
    );
  };

  while (unstarted.size > 0 || running.size > 0) {
    // A dependency that failed poisons its dependents transitively, so run
    // the propagation to a fixpoint. Reporting them as skipped rather than
    // passed is what keeps a broken prerequisite from reading as green.
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
      if ((spec.mutex ?? []).some((group) => held.has(group))) continue;
      launch(spec);
    }

    if (running.size === 0 && unstarted.size > 0) {
      // Nothing is in flight and nothing was admissible: the budget is
      // smaller than the head of the queue. Admit it anyway rather than
      // spin. Mutex cannot be the blocker here, since nothing holds one.
      const head = ready.find((spec) => !(spec.mutex ?? []).some((group) => held.has(group)));
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
    for (const group of spec.mutex ?? []) held.delete(group);

    const failed = outcome.code !== 0 || outcome.vacuity !== undefined;
    record({
      id,
      gate: spec.gate,
      status: failed ? 'fail' : 'ok',
      ms: outcome.ms,
      exitCode: outcome.code,
      stdout: outcome.stdout,
      stderr: outcome.stderr,
      rerun: spec.run,
      vacuity: outcome.vacuity,
    });
    if (failed && opts.failFast) stopped = true;
  }

  // Manifest order, not completion order: the exit code and the summary must
  // be identical across runs even though the scheduling never is.
  return specs.map((spec) => {
    const result = results.get(spec.id);
    if (result === undefined)
      throw new Error(`ci-runner: internal error, no result for ${spec.id}`);
    return result;
  });
}
