/**
 * The gate INVENTORY's type shape, split out of manifest.ts on 2026-09-04.
 *
 * WHY SEPARATELY. manifest.ts is 5,654 lines and 192 KB. A binder that DERIVES entries
 * from per-gate declarations needs these types without importing 378 entries and 192 KB
 * to get them -- and so does anything else that only wants the shape. Splitting the types
 * is the non-behavioural half of that work: every existing importer keeps working, because
 * manifest.ts re-exports them.
 *
 * THE THREE TEXT PARSERS ARE GONE, and this paragraph used to give them as the reason
 * manifest.ts "has to keep containing every entry literally". wl_reggate.py, then
 * the gate-id-convention gate and check_test_file_orphans.py (both on 2026-09-06, W2.4a),
 * were each moved onto `scripts/ci-runner/gates.lock.json`, the committed JSON projection
 * of this literal. All three had been wrong in the same silent direction: the regex read
 * 259 of 261 entries in one case and 373 of 420 in another, always short, always green.
 * The literal is still the source of truth -- gen-gates-lock.ts projects it and
 * check:ci-gates-lock keeps the two faithful -- but no longer because anything parses it
 * as text, so do not cite a text parser as the constraint that keeps it in this shape.
 */

export interface GateSpec {
  /**
   * Skip the per-gate process-tree sampler for this gate. Only for gates that
   * PLANT structural defects on purpose: check:ci-resprofile's selftest spawns an
   * unreaping parent with four zombies, and the sampler caught it on the first
   * default-on run -- a correct finding on a fixture, which would have poisoned
   * the E6 fire rate in any seed. The profiler must not profile its own test.
   */
  noProfile?: boolean;
  /** npm script key, or a synthetic node id like 'build:packages'. */
  id: string;
  /** Exact command to run, and the exact rerun line printed on failure. */
  run: string;
  /**
   * false for prerequisite nodes (build:*) that validate nothing, and for the
   * CI-side aggregate check:ci-quality-gates whose 62 constituents are
   * scheduled individually. A false entry runs only when something that
   * `needs` it is in the selected set, so an aggregate with no dependents
   * never runs locally.
   */
  gate: boolean;
  /** Ordering edges: ids that must succeed first. */
  needs?: string[];
  /** Mutual-exclusion groups: no two gates sharing a group overlap. */
  mutex?: string[];
  /**
   * Resources this gate READS but does not write. Paired with `mutex`, which
   * names what it WRITES; a `tree:<x>` in one may not overlap a `tree:<x>` in the
   * other concurrently.
   *
   * WHY THIS FIELD EXISTS AND WHY IT WAS MISSING. W2.4 declared isolation a
   * path-scoped contract and built BOTH readers -- `pool.ts` and the gate battery's
   * `classify_from_lock` -- but the second claim it reads, `reads`, was never added
   * here. So the 21 scanner gate tests were UNDECLARABLE by construction, the lock
   * carried no `reads` key on any of 456 entries, and the battery ran on its loud
   * fallback ("no 'tree:' isolation declared ... falling back to the hand-maintained
   * W/S lists in this file") for the whole time the box read as done. A contract
   * implemented by two readers with no data to read is not a contract.
   */
  reads?: string[];
  /** Scheduler slots. Default 1. */
  weight?: number;
  /** Memory-hungry (>=4 GB heap). Bounded by --heavy-limit. */
  heavy?: boolean;
  /**
   * Step-level `env:` for the emitted workflow step, declared in the gate header as
   * `env-<KEY>:` lines. `gen-gates-lock.ts` serialises the whole spec, so this reaches the
   * lock with no code change there -- which is the point of putting it HERE rather than
   * teaching a second file about it.
   *
   * WHY IT HAS TO BE DECLARED AT ALL: 17 registered steps carry `env:` in `ci-quality.yml`
   * and no lock entry records one, so a `gate-bind` rewrite that took ownership of such a
   * step would drop its env and report success. Measured receipt: strip `DOCKERHUB_TOKEN`
   * from `check:ci-docker-image-freshness` and the whole battery still runs green.
   */
  env?: Record<string, string>;
  /**
   * An extra condition ANDed onto the standard step guard, never replacing it.
   * `gate-bind.ts:emitStep` parenthesises it, so a `when` containing `||` cannot bind
   * looser than the `&&` and run the step on a failed setup. `steps.` is refused in the
   * header parser: a gate that can see step outcomes can contradict the guard, which is
   * invariant 11 re-opened through a side door.
   */
  when?: string;
  /** Repo-relative globs this gate validates; powers --changed. */
  paths?: string[];
  /**
   * Required whenever `paths` is present; refused otherwise (cardinality
   * equality, both directions -- `check:ci-paths-origin`). `'declared'` means a
   * human enumerated the globs by hand, and each one is asserted to match at
   * least one tracked file -- a glob matching nothing is exactly as wrong as a
   * `paths` array with none, and just as invisible without this check.
   * `` `derived:${tool}` `` names an id (an npm script key, or another gate id)
   * that PRINTS the paths list, one per line, on a re-run; the check re-runs it
   * and asserts the output still equals the declared array, so a derivation
   * that has drifted from what it once produced is caught rather than trusted.
   * No entry uses `derived:` yet -- W2.5's tier 2 (traced paths) is separate,
   * later work -- so that branch is proven only by `--selftest`'s fixture.
   */
  pathsOrigin?: string;
  /**
   * Too expensive for the pre-push lane. ABSENT MEANS FAST, deliberately: a
   * new gate is enforced before a push until someone takes it out on purpose,
   * which is the fail-safe direction. Opting out is the one mechanism -- there
   * is no second exemption file -- so the reason lives in a comment beside it.
   *
   * The threshold is measured, not judged: `.ci/cache/gate-durations.json`
   * holds per-gate timings from real runs, and check:ci-gate-manifest's tier
   * oracle asserts this field against them in BOTH directions. (It named a
   * `check:ci-gate-tiers` until 2026-09-02; no such gate has ever existed, so
   * a reader looking for the guard found nothing and could conclude the field
   * was unasserted. The guard is real, it just lives in the manifest gate.) A gate marked slow that is in
   * fact cheap fails just as loudly as the converse, because the cheap-marked-
   * slow direction is the invisible one: the push stays fast and the coverage
   * quietly shrinks.
   */
  slow?: true;
  /** Set on the 62 entries flattened out of .ci/scripts/test/gates/. Their set
   *  must equal the on-disk glob; see assertion 7 in section 6.3. */
  qualityGateTest?: boolean;
  /** Leaf commands this gate ultimately executes. The parity oracle compares
   *  these, not the npm key, because CI frequently invokes the same underlying
   *  script under a different key or by bare path. */
  leaves: string[];
  /** How CI runs this gate. See section 6 for every variant and its rules. */
  ci: CiCoverage;
}

export type CiCoverage =
  /** A workflow step runs it. Verified against the parsed workflow. */
  | { kind: 'step'; workflow: string; job: string; step: string }
  /** A gate test under .ci/scripts/test/gates/ drives its REAL scan against the
   *  REAL tree, and run-all.sh runs in CI. Requires `test` plus a BLOCKER
   *  reason naming the line that proves the real scan runs. Never inferred. */
  | { kind: 'test'; test: string; blocker: string }
  /** Deliberately local-only. Requires a BLOCKER reason. */
  | { kind: 'local-only'; blocker: string };
