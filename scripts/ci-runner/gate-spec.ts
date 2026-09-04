/**
 * The gate INVENTORY's type shape, split out of manifest.ts on 2026-09-04.
 *
 * WHY SEPARATELY. manifest.ts is 5,654 lines and 192 KB, and three tools parse it as
 * TEXT with regexes keyed on the entry shape (wl_reggate.py, check-gate-id-convention.sh,
 * check_test_file_orphans.py), so it has to keep containing every entry literally. A
 * binder that DERIVES entries from per-gate declarations needs these types without
 * importing 378 entries and 192 KB to get them -- and so does anything else that only
 * wants the shape. Splitting the types is the non-behavioural half of that work: every
 * existing importer keeps working, because manifest.ts re-exports them.
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
  /** Scheduler slots. Default 1. */
  weight?: number;
  /** Memory-hungry (>=4 GB heap). Bounded by --heavy-limit. */
  heavy?: boolean;
  /** Repo-relative globs this gate validates; powers --changed. */
  paths?: string[];
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
