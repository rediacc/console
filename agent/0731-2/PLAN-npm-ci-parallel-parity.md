# PLAN: npm run ci parity gate + parallel runner
Status: done
Owner: ci-parallel-plan agent, branch 0731-2
Updated: 2026-07-31

## Status

Implemented in full; header flipped 2026-08-05 after verification (see git log b389ac305 / b685cd590). Everything below is the plan as written at design time and is superseded by this line.

Design complete, nothing implemented. Every number below was measured on this
branch during planning, not estimated from reading. Two implementation agents
with disjoint file ownership; the split is in section 9.

The one thing an implementer must internalise before touching anything: **the
runner and the parity gate cannot land separately.** `scripts.ci` today is a
93-step `&&` string, and both existing parity gates parse that string as their
input (`check-gate-reachability.ts:50`, `check-ci-chain-parity.ts:158`). The
moment `scripts.ci` becomes `tsx scripts/ci-runner/run.ts`, both gates read an
empty chain and go green over everything. That is the exact failure class
issue #549 is about, and shipping the runner alone would manufacture it at
scale. One branch, one PR, both halves.

---

## 1. What runs where, measured

### 1.1 `npm run ci` today

`package.json:144` is a single `&&` chain naming 93 npm keys. Following
`npm run` transitively (root scripts plus workspace manifests) gives **92
distinct reachable keys** resolving to **105 distinct leaf commands** (script
paths plus bare tools like `tsc`, `eslint`, `knip`, `syncpack`, `vitest`).

Two aggregators do most of the fan-out:

- `check:i18n` (`package.json:106`): 19 leaf gates, `&&`-chained, so it stops at
  the first failure and hides the rest.
- `check:ci-quality-gates` -> `.ci/scripts/test/run-all.sh` (`package.json:64`):
  globs and runs all 56 files in `.ci/scripts/test/gates/`, serially
  (`run-all.sh:41-97`).

### 1.2 CI's quality tier

`ci.yml:394-408` has exactly one quality job, `uses: ./.github/workflows/ci-quality.yml`.
That file is **ten lanes**, not one job per gate: `Static`, `Branch`,
`Submodule Branches`, `Code`, `Content`, `Packages`, `i18n`, `Built-www Gates`,
`Security`, `Go`. Every gate step carries
`if: ${{ !cancelled() && steps.setup.outcome == 'success' }}` (`ci-quality.yml:21-27`)
so a lane reports all of its failures in one round. `continue-on-error` is
banned repo-wide by `check-workflows.sh` and appears nowhere in either file.

`review-gate` (`ci.yml:420-462`) is a separate job that `needs: quality`; its
three gates are all already in `.ci-chain-exempt` as GitHub-API-only.

Resolving every workflow `run:` block the same way (npm keys expanded
transitively, script paths taken literally) gives **239 leaf commands** across
all workflows.

### 1.3 The two set differences

Method matters here, and getting it wrong is the whole problem. See section 1.4.

**Direction A, the #549 class (in the chain, executed by no CI job): 7.**

| Leaf | Chain key | Note |
|---|---|---|
| `scripts/check-jq-boolean-default.ts` | `check:ci-jq-boolean-default` | the proven #549 instance; its presence here is the control that the analysis fires |
| `scripts/check-gate-reachability.ts` | `check:ci-gate-reachability` | the gate that polices reachability is itself never run by CI |
| `scripts/check-i18n-cross-locale.ts` | `check:ci-i18n-cross-locale` | same script named in `check-gate-reachability.ts:18-20` as having shipped broken behind a flag nothing invoked |
| `scripts/check-locale-sources.ts` | `check:ci-locale-sources` | |
| `.ci/scripts/security/check-autopilot-workflow-invariants.sh` | `check:ci-autopilot-workflow` | |
| `.ci/scripts/test/test-rdc-sh-env.sh` | `check:ci-rdc-sh-env` | CI runs its sibling `test-install-sh-config.sh` by path (`ci-quality.yml:169-171`) but never this one |
| `packages/www/scripts/list-tutorial-render-pairs.js` | `check:ci-tutorial-render-queue` | |

Two of the seven have a gate test under `.ci/scripts/test/gates/` that does
drive the real script against the real tree, and `run-all.sh` does run in CI
(`ci-quality.yml:884-886`): `test-autopilot-workflow-invariants.sh:23-24`
points `GATE` and `REAL` at the live `autopilot.yml`, and
`test-tutorial-render-queue.sh:79` runs `node "$PREDICATE" --selftest` against
the real tree. So those two are covered in CI **by their test, not by a gate
step**.

This is precisely where a naive reverse gate would greenwash #549 and must not:
`check-jq-boolean-default.ts` is ALSO named by a gate test
(`test-gate-anti-vacuity.sh:104`), and that test ran green in CI for weeks while
the real scan never executed once. Mentioning a script is not executing its real
scan. Therefore **coverage-by-test is never inferred by grep; it is an explicit,
BLOCKER-annotated declaration in the manifest.** See section 6.

**Direction B (executed by CI, not reachable from `npm run ci`): 24 gate-shaped
leaves.** Eight are already in `.ci-chain-exempt` (the GitHub-API set). Fourteen
are release/CD/E2E/install-matrix scripts outside the quality tier and outside
scope. **Two are real quality-tier holes:**

- `.ci/scripts/test/test-write-once-guard.sh`, run in Quality / Static
  (`ci-quality.yml:158-160`)
- `.ci/scripts/test/test-install-script.sh`, run in Quality / Static
  (`ci-quality.yml:162-164`)

Neither is in the chain and neither is exempt. The existing forward gate cannot
see them because `BARE_GATE` (`check-ci-chain-parity.ts:62`) matches only
`.ci/scripts/(quality|security)/check-*.sh`: these live in `.ci/scripts/test/`
and start with `test-`. Recorded as F3.

### 1.4 The measurement trap, found live, and what it dictates

The first version of this analysis reported **zero** direction-A findings. The
cause: it regexed the whole workflow file text for `npm run <key>`, and
`ci-quality.yml:550` reads

```yaml
      - name: Validate every workflow gate is in `npm run ci`
```

The step **name** contains the literal `npm run ci`. Expanding that as an
invocation made the entire chain "CI-executed" and the reverse direction
vacuously empty. A gate built that way would have reported perfect parity
forever.

The existing gate has a cousin of this defect. `check-ci-chain-parity.ts:186-189`
carefully builds a comment-stripped `code` string, then line 197 iterates
`text.matchAll(...)` -- the original, comments included -- for named gates.
Recorded as F2.

Three rules fall out, and they are load-bearing for section 6:

1. Parse `run:` blocks, never whole-file text. Step `name:`, `env:` values, `if:`
   expressions and YAML comments are not invocations.
2. `npm run ci` and `npm run quality` may never count as coverage for anything.
   Treat their appearance in a `run:` block as an error, not as coverage.
3. Every reconciliation runs against a planted control before its green is
   trusted (section 8).

---

## 2. Where the time goes, measured

Method: each of the 92 reachable chain keys run individually via
`npm run --silent <key>`, sequentially, 300 s cap, wall time recorded. Machine:
20 cores, 56 GB RAM, warm `node_modules`. Raw data:
`scratchpad/gate-times.tsv` (session-local, not committed).

**Serial total: 1041.6 s, about 17.4 minutes.** Head of the distribution:

| Gate | Seconds | Note |
|---|---|---|
| `check:ci-quality-gates` | **443.0** | hit the 300 s cap, re-measured uncapped: 57 tests, 611 assertions, serial |
| `lint` | 120.9 | pure duplicate of the next row, see F1 |
| `check:lint` | 116.7 | |
| `check:ci-dead-bash` | 38.2 | |
| `check:ci-editorconfig` | 37.4 | |
| `check:ci-renet` | 24.4 | |
| `check:ci-lockfile` | 24.3 | |
| `check:ci-external-links` | 22.0 | network |
| `check:ci-account-portal` | 21.6 | |
| `check:ci-account-server` | 19.2 | vitest |
| `check:ci-shell-lint` | 18.8 | |
| `check:ci-no-otlp-creds` | 16.1 | |

The tail is long and cheap: the great majority of gates finish under 2 s. That
is the ideal shape for a worker pool, because the achievable floor is the
**longest single gate**, not the sum.

**Which makes `check:ci-quality-gates` the whole ballgame.** At 443 s it is 43%
of the serial total, and it is one opaque npm key wrapping
`.ci/scripts/test/run-all.sh`, which globs `.ci/scripts/test/gates/test-*.sh`
and runs them one at a time (`run-all.sh:41-97`). If the runner schedules it as
a single unit, the parallel floor is 443 s and the best possible speedup is
about 2.4x no matter how many cores the box has.

**So flattening it is a requirement, not an optimisation.** Its 57 tests look
independent (each builds its own fixtures in a `mktemp -d`), but see F8 before
assuming it: one of them failed in the full serial battery today and could not
be reproduced. Treat per-test isolation as a hypothesis the implementer
verifies, not as a given. Two ways to flatten, and the plan recommends the
first:

1. **Enumerate them into the manifest** as 57 entries with a shared
   `qualityGateTest` tag, so the pool schedules them individually alongside
   everything else and the summary names the specific failing test.
   `npm run check:ci-quality-gates` stays as-is for CI, which still wants one
   step. The parity gate then needs one manifest-level rule: the set of
   manifest entries tagged `qualityGateTest` must equal the glob
   `.ci/scripts/test/gates/test-*.sh` on disk, so a newly added test cannot be
   silently omitted from the local run. That equality check is cheap and it is
   what stops this flattening from becoming its own #549.
2. Teach `run-all.sh` an internal `--jobs` flag. Simpler to write, but it
   duplicates the scheduler in bash, keeps the 443 s unit opaque to
   longest-first scheduling, and loses per-test reporting in the summary.

With the flattening, the expected floor is set by `check:lint` (116.7 s) plus
scheduling slop, which is roughly a 7x to 8x improvement on the measured serial
total. Without it, 2.4x.

Two pre-existing reds the implementer will meet on the first full run, neither
caused by this work (the only file this planning session wrote is the plan
itself):

- **F7: `check:deps` exits 1** on branch 0731-2 today (8.8 s, rc=1).
- **F8: `test-claude-hooks.sh` is flaky in the existing SERIAL harness.** It
  failed in the full 57-test `run-all.sh` battery (443 s run, "56 passed, 1
  failed"), then passed standalone (452 cases, 0 failures) and passed again
  under `./run-all.sh 'test-c*.sh'` (5 tests, 131 s). Cause not identified. This
  matters to the design twice over: it is a live counter-example to "these tests
  are independent", and it is the kind of failure that a parallel runner will be
  blamed for. Establish a serial baseline before turning parallelism on, so the
  first parallel red can be attributed honestly.

Two structural observations from the same data:

- **`lint` and `check:lint` are the same eslint run twice.** `package.json:143`
  is `eslint packages scripts private/account`; `package.json:114` is the same
  invocation plus `--max-warnings 0` plus a biome lint. The second strictly
  subsumes the first, so 120.9 s of the chain buys nothing. Recorded as F1.
- **Aggregators hide failures behind `&&`.** `check:i18n` chains 19 leaf gates
  with `&&` (`package.json:106`), so the first non-zero exit hides the other
  eighteen. (It passed in 10.5 s on this tree, exit 0, so that is a property of
  the chaining, not something this measurement observed firing.) The runner must
  flatten aggregators into individually scheduled gates for exactly this reason:
  it is a reporting fix as much as a speed fix, and it is the same defect CI
  already fixed at lane level with `!cancelled()`.

### 2.1 Ordering and isolation constraints, verified

These constrain the pool. Each was verified by reading the gate, cited.

- **Writes `packages/*/dist` and `*.tsbuildinfo`.** `check:types` runs
  `tsc -b packages/shared packages/provisioning packages/cli`
  (`package.json:149`). `.ci/scripts/quality/check-command-tree.sh:42` runs
  `npm run build:packages` internally, and so does
  `.ci/scripts/quality/check-cli-contract.sh:29`. Concurrent builds of the same
  projects race on the same output directory. Mutex group `build-artifacts`;
  once `build:packages` is a scheduled node those two internal builds become
  redundant work worth removing. Checked and NOT affected:
  `check:ci-command-planes` (`packages/cli/scripts/check-command-planes.ts`)
  does not build.
- **Writes/needs `private/renet/bin/renet`.** `check-renet-types.sh:54` invokes
  `"$RENET_DIR/bin/renet" functions generate-types`; `check:ci-renet` runs the
  renet quality battery which rebuilds it. Mutex group `renet-bin`. (The gate
  itself writes only to a `mktemp -d`, `check-renet-types.sh:50`, so the output
  side is safe; the binary is the shared resource.)
- **Account vitest suites.** `check:ci-account-server`
  (`.ci/scripts/private/run-account.sh test` -> full vitest suite),
  `check:ci-account-scope-audit`, `check:ci-console-coverage`
  (`package.json:76-80`). Each spawns its own worker pool and touches local D1
  state. Mutex group `account-vitest`, and each carries a high weight.
- **Needs `packages/www/dist`.** `check:ci-seo`, `check:ci-redirects`,
  `check:ci-cta-bolt`. In CI these run only in the Built-www lane after
  `npm run build:www` (`ci-quality.yml:790-808`), and `check:ci-seo`'s
  built-HTML link scan **self-skips** without `packages/www/dist`
  (`ci-quality.yml:738-740`). `npm run ci` never builds www, so today that scan
  is vacuous locally. Recorded as F5.
- **Memory.** `lint`, `check:lint` and `fix:lint` all set
  `NODE_OPTIONS=--max-old-space-size=8192` (`package.json:114,143`). `knip` and
  `tsc` are also heap-hungry. Concurrency must be bounded by memory as well as
  by core count, or a 20-way fan-out OOMs the box.

---

## 3. How CI parallelises the same work

CI's answer is job-level: ten lanes grouped by **what they need on disk** (bare
checkout / node / node+submodules / node+build / go) so a lane pays its setup
once (`docs/agent/ci-gates.md:54-60`). Within a lane, gates are serial steps.
Isolation is total between lanes (separate runners), so CI never had to think
about mutual exclusion.

The local runner cannot copy that: one machine, one tree, one set of build
outputs. So it needs the two things CI gets for free, declared explicitly: a
**dependency edge** for ordering and a **mutex group** for shared mutable
resources. Everything else parallelises freely.

Two CI facts to carry over deliberately:

- **Run everything, report everything.** `ci-quality.yml:21-27` and
  `ci-gates.md:63-66` ("Do not fix the first red and push"). The runner defaults
  to keep-going for the same reason.
- **The lane grouping is not a parallelism model**, it is a setup-cost model.
  Do not port the lane names into the manifest; port the resource facts.

---

## 4. Design part 1: the parallel runner

New directory `scripts/ci-runner/`, run via tsx, no new dependencies (node
built-ins only: `node:child_process`, `node:os`, `node:fs`).

```
scripts/ci-runner/
  run.ts        CLI entry: arg parsing, load manifest, build graph, drive pool, exit code
  pool.ts       scheduler: worker pool, weights, mutex groups, dependency edges
  exec.ts       one gate: spawn, capture stdout and stderr SEPARATELY, time it
  report.ts     streaming lines, failure blocks, final summary table, --json
```

### 4.1 Wiring

```jsonc
"ci":        "tsx scripts/ci-runner/run.ts",
"ci:list":   "tsx scripts/ci-runner/run.ts --list",
"ci:serial": "tsx scripts/ci-runner/run.ts --jobs 1",
```

`npm run quality` stays an alias of `ci` (`package.json:145`). Every individual
`check:*` key stays in package.json unchanged: they are the rerun commands the
runner prints, and dropping them would break every muscle-memory invocation and
every workflow step.

### 4.2 Scheduling

- Default worker budget: `os.availableParallelism() - 2`, floor 1. Override with
  `--jobs N` or `CI_JOBS=N`.
- Each gate declares `weight` (slots it occupies, default 1) and `heavy`
  (boolean). The pool admits a gate while `sum(weight) <= jobs` **and**
  `heavyRunning < heavyLimit`. `heavyLimit` defaults to
  `max(2, floor(jobs / 4))`; override with `--heavy-limit`. This is the memory
  guard: eslint, knip, tsc and the vitest suites are `heavy`.
- `needs: string[]` gives ordering edges. A gate whose dependency FAILED is
  reported as **skipped**, never as passed, and skipped gates make the run
  non-zero.
- `mutex: string[]` gives mutual exclusion. Two gates sharing any group never
  overlap. Groups from section 2.1: `build-artifacts`, `renet-bin`,
  `account-vitest`, `www-dist`.
- **Longest-first**: ready gates are dequeued by descending expected duration, so
  the critical path starts early. Expected duration comes from
  `.ci/cache/gate-durations.json` (gitignored, EWMA-updated each run); a missing
  or corrupt cache falls back to `weight * 5s` and must never fail the run.
- Cycle detection at graph-build time, with the cycle printed. A cycle is a
  manifest bug and must fail loudly rather than deadlock.

### 4.3 Two synthetic nodes

`build:packages` and `build:www` are manifest entries with `gate: false`: they
are prerequisites, not validations. They run only when something that `needs`
them is in the selected set, and they hold `build-artifacts` / `www-dist`
respectively. Adding `build:www` is what closes F5, and longest-first
scheduling means it starts in the first wave and is largely free on 20 cores.

### 4.4 Output contract

The operator's ask verbatim: quiet on success, helpful on failure, fast agent
iterations. Concretely:

Header, one line: `ci-runner: 94 gates, 18 workers, keep-going`

Per gate on completion, streamed:

```
  ok    check:ci-lockfile                    24.3s
  ok    check:format                          0.7s
```

On failure, streamed immediately (do not hold it to the end; an agent tailing
the output should see it as it happens):

```
FAIL  check:ci-foo                           12.4s   exit 1
  rerun: npm run check:ci-foo
  --- stdout ---
  <complete captured stdout, unmodified, untruncated>
  --- stderr ---
  <complete captured stderr, unmodified, untruncated>
  (stderr was empty)
```

**stdout and stderr are captured and printed separately, never merged.** House
rule (CLAUDE.md, "Run the real thing"): a wrapper that merges them hides
progress-text-on-stdout and swallowed-output defects, which is a class this repo
has been bitten by. `--merge-output` exists as an opt-in for a gate whose
interleaving matters.

Footer:

```
================================================================
150 gates: 147 ok, 2 failed, 1 skipped     wall 141.2s (serial 1041.6s, 7.4x)
================================================================
slowest:
  120.9s  check:lint
   24.3s  check:ci-lockfile
   ...
FAILED:
  check:ci-foo      npm run check:ci-foo
  check:ci-bar      npm run check:ci-bar
SKIPPED (dependency failed):
  check:ci-baz      needs build:packages
rerun all failures:
  npm run check:ci-foo && npm run check:ci-bar
================================================================
```

`--json` emits one machine-readable object (per-gate id, status, ms, exitCode,
stdout, stderr, rerun) for agent consumption. Exit code is 1 if any gate failed
or was skipped, 0 otherwise, deterministic and independent of scheduling order.

### 4.5 Fail-fast: recommendation and justification

**Default keep-going. `--fail-fast` opt-in.**

Justification, in the repo's own terms. CI already made this exact call for the
same reason: every quality step carries `!cancelled()` so one push surfaces every
failure in the lane (`ci-quality.yml:21-27`), and `ci-gates.md:63-66` states the
consequence as a rule ("Do not fix the first red and push -- read the whole
lane's step list first"). A local runner that stops at the first red would be
strictly worse than the CI it exists to predict.

It is also what the operator's stated goal ("so AI can go with faster
iterations") actually requires: with keep-going, N independent failures cost one
run; with fail-fast they cost N runs. The current `&&` chain is fail-fast, and
section 2 shows exactly what that costs -- `check:i18n` stops at its first
failing leaf and hides eighteen others.

Fail-fast remains available for the tight edit loop where the first failure is
the only one you care about.

### 4.6 Selection flags

`--only <glob,...>`, `--skip <glob,...>`, `--changed` (gates whose declared
`paths` intersect `git diff --name-only` against the merge base). `--changed` is
a convenience for iteration and **must never be the default**: a partial run
reporting green is the vacuity failure this whole plan exists to prevent, so the
summary line states loudly which selection was applied and the `--json` output
carries a `partial: true` flag.

---

## 5. The manifest: the single source both halves consume

`scripts/ci-runner/manifest.ts`, a typed TS module. Precedent for the shape is
`.ci/scripts/ci/scope-map.cjs`: a hand-verified lookup table plus a pure
function, deliberately offline so a unit test can exercise it in milliseconds
(`scope-map.cjs:1-17`).

**This interface is frozen by this plan.** Agent 2 authors the file; Agent 1
imports it read-only. Neither edits the other's files.

```ts
export interface GateSpec {
  /** npm script key, or a synthetic node id like 'build:packages'. */
  id: string;
  /** Exact command to run, and the exact rerun line printed on failure. */
  run: string;
  /** false for prerequisite nodes (build:*) that validate nothing. */
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
  /** Set on the 57 entries flattened out of .ci/scripts/test/gates/. Their set
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

export const GATES: readonly GateSpec[];
/** Workflows outside this set are not part of the parity surface. Computed,
 *  not hand-listed: see section 6.2. */
export function paritySurface(repoRoot: string): string[];
```

---

## 6. Design part 2: the bidirectional parity gate

### 6.1 One gate replaces two, because there are three relations, not two

The three sets are: **K** = `check:ci-*` keys defined in package.json, **C** =
leaf commands the local chain executes, **W** = leaf commands the CI quality
surface executes. Today:

- R1 (`K -> C`, defined implies locally reachable) = `check-gate-reachability.ts`
- R2 (`W -> C`, CI-run implies locally reachable) = `check-ci-chain-parity.ts`
- R3 (`C -> W`, locally-run implies CI-run) = **nobody**, which is #549

Patching in a third script leaves three tools disagreeing about how to resolve a
gate, and the resolution logic is exactly where the bugs live (section 1.4). One
gate, one resolver, three assertions.

**`scripts/check-ci-parity.ts` subsumes and replaces both existing scripts.**
`scripts/check-ci-chain-parity.ts` and `scripts/check-gate-reachability.ts` are
deleted. Clean break, no compatibility shims: one operator, no external
consumers.

There is a second, harder reason this must be one change. Once `scripts.ci` is
the runner invocation, R1 and R2's input (the `&&` string) no longer exists.
Both old gates would silently pass over an empty chain. The new gate's C is the
**manifest**, not a string.

### 6.2 The parity surface is computed, never hand-listed

Direction B produced 14 release/CD/E2E scripts that are correctly out of scope.
Listing them as exemptions would be 14 permanent lies in a suppression file. So
scope is structural: the surface is the transitive closure of
`uses: ./.github/workflows/*` reachable from `ci.yml`'s `quality` job
(`ci.yml:394-408`), plus the `review-gate` job's steps
(`ci.yml:420-462`).

Computed by iterating `uses:`, never by matching names. This is the same
technique `test-scope-engine.sh` uses and the reason it is registered in the
anti-vacuity harness (`test-gate-anti-vacuity.sh`, the `closure` entry): a
computed closure cannot be silently retired by renaming a file, whereas a
hand-listed one can. Adding a new lane workflow therefore cannot escape the
gate.

### 6.3 The assertions

Run in this order, all evaluated before exiting so one run reports everything:

1. **Preflight, anti-vacuity.** Refuse to run and exit non-zero if: the manifest
   declares zero gates; `.github/workflows` is absent or empty; the computed
   parity surface is empty; package.json defines zero `check:ci-*` keys. The
   diagnostic must say "Refusing to run", matching the convention the
   anti-vacuity registry pins (`test-gate-anti-vacuity.sh:104-106`).
2. **Tautology guard.** Any `run:` block inside the parity surface that invokes
   `npm run ci` or `npm run quality` is an ERROR, named and failed. It would make
   every other assertion vacuous.
3. **R1, `K -> manifest`.** Every `check:ci-*` key in package.json appears as a
   manifest `id`, or is exempt. A defined-but-unlisted gate is inert.
4. **R2, `W -> manifest`.** Every gate-shaped leaf executed by the parity surface
   is some manifest entry's `leaves` member, or is exempt. "Gate-shaped" widens
   the current `BARE_GATE` (`check-ci-chain-parity.ts:62`) from
   `.ci/scripts/(quality|security)/check-*.sh` to also cover
   `.ci/scripts/test/test-*.sh`, which is what F3 needs.
5. **R3, `manifest -> W`** (the new direction). Every entry with
   `ci.kind === 'step'` must have its declared `workflow`/`job`/`step` actually
   exist in the parsed workflow, and that step's `run:` block must resolve to one
   of the entry's `leaves`. Entries with `ci.kind === 'test'` or `'local-only'`
   must carry a BLOCKER reason. Anything else fails.
6. **Manifest hygiene.** Every `id` resolves to a real package.json script (or is
   a declared synthetic node); every `needs` target exists; no cycles; every
   `leaves` entry names a file that exists on disk.

7. **Flattened-battery equality.** The set of manifest entries tagged
   `qualityGateTest` must equal the on-disk glob `.ci/scripts/test/gates/test-*.sh`,
   which is the same glob `run-all.sh:26,46` uses. Neither side may gain a test
   the other lacks. Without this, flattening the battery (section 2) would
   recreate #549 fifty-seven times over: a new test would run in CI via
   `run-all.sh` and never locally, or be listed locally and silently dropped.

Many-to-one coverage is normal and expected: all 57 of those entries declare the
same `ci` pointer, the single `check:ci-quality-gates` step at
`ci-quality.yml:884-886`. Assertion 5 checks that the pointer resolves, not that
it is unique, and assertion 7 is what keeps the fan-out honest.

Assertion 5 is what makes the manifest un-rottable. A pure manifest can drift
(someone edits the workflow, forgets the manifest) and a pure parse can be wrong
(section 1.4). Declaring the pointer AND verifying it against the parsed
workflow means either side moving alone is a failure.

### 6.4 Resolution rules, distilled from the measurement

- Extract `run:` blocks only: a `run: cmd` scalar, or a `run: |` / `run: >` block
  scalar consumed by indentation. Never whole-file text. Strip comment lines
  inside the block.
- Expand `npm run <key>` transitively through root and workspace manifests,
  honouring `-w` / `--workspace=` (carry over `scriptExists`,
  `check-ci-chain-parity.ts:111-136`).
- Compare **leaf commands**, not npm keys. CI runs `npm run typecheck` while the
  chain names `check:types`, and CI runs `npm run version:check` while the chain
  names `check:version` -- identical bodies, different keys
  (`package.json:149,150` versus `:113,151`; `ci-quality.yml:344-346,383-385`).
  A key-level comparison reports those as breaks; a leaf-level one does not.
- Never descend into shell scripts to infer coverage. `run-all.sh` runs 56 gate
  tests and grepping them for a script name is exactly how #549 would have been
  greenwashed. Coverage via a test is declared (`ci.kind === 'test'`) with a
  BLOCKER naming the line that proves the real scan runs, and reviewed by a human
  once.

### 6.5 Exemptions

`.ci-chain-exempt` is renamed `.ci-parity-exempt` and gains a direction tag,
because the two directions need different justifications ("cannot run locally"
versus "cannot run in CI"). Format keeps the shared BLOCKER convention
(`docs/agent/suppressions.md:27-32`), parsed with `parseBlockeredList` /
`verifyAllBlockers` exactly as today (`check-ci-chain-parity.ts:93-94`).

```
# BLOCKER: <reason>
ci-only  .ci/scripts/quality/check-branch.sh
```

Directions: `ci-only` (CI runs it, the chain deliberately does not; the eight
existing GitHub-API entries migrate here verbatim with their reasons) and
`local-only` (the chain runs it, CI deliberately does not). Prefer
`ci.kind: 'local-only'` in the manifest over an exempt-file entry for the second
case; the file is for asymmetries the manifest cannot express.

Consequential edits the rename forces, all of which must land in the same commit:

- `.ci/scripts/ci/scope-map.cjs:51` lists `.ci-chain-exempt` in
  `ROOT_MANIFESTS`; update it or a rename silently changes CI scope
  classification.
- `docs/agent/suppressions.md:21` (mechanism table) and `:77` (liveness oracle
  table).
- `scripts/check-suppression-liveness.ts:361`, `:367` and `:391` (the probe
  definition, its entry reader, and the remediation string that still names
  `npm run check:ci-chain-parity`). The oracle now has to respect the direction
  tag: a `local-only` entry is live when the chain still runs it, not when a
  workflow does.

### 6.6 What the gate will find on day one

The seven direction-A leaves in section 1.3 will fail immediately. That is the
point, and **they get resolved, not exempted**:

- The two with real gate-test coverage (`check-autopilot-workflow-invariants.sh`,
  `list-tutorial-render-pairs.js`) become `ci.kind: 'test'` with a BLOCKER citing
  `test-autopilot-workflow-invariants.sh:23-24` and
  `test-tutorial-render-queue.sh:79` respectively.
- The other five get a real workflow step in the appropriate lane of
  `ci-quality.yml`. `check:ci-gate-reachability`, `check:ci-jq-boolean-default`
  and `check:ci-rdc-sh-env` belong in Static or Code; `check:ci-i18n-cross-locale`
  and `check:ci-locale-sources` belong in the i18n lane. Adding them is cheap
  (all are fast) and it is the fix #549 asks for.

Both Quality/Static holes from F3 (`test-write-once-guard.sh`,
`test-install-script.sh`) get manifest entries and join the chain. Verify they
run on a developer machine before adding them; if either genuinely cannot, it
gets `ci-only` with a real BLOCKER, not silence.

---

## 7. Constraints the implementation must respect

- **npm, not pnpm.** `.npmrc` sets `ignore-scripts=true`; the runner spawns
  `npm run` and inherits that, which is correct and must not be overridden.
- **No new dependencies.** Node built-ins only. A worker pool is ~150 lines; a
  dependency here would also trip `minimum-release-age=1440` and the audit gate.
- **knip strictness.** `lint:unused` runs `knip --treat-config-hints-as-errors`.
  Every export in `scripts/ci-runner/` must be consumed, or be reachable from a
  binary entry knip recognises. Do not add a `knip.jsonc` ignore; make the
  exports used. `manifest.ts`'s exports are consumed by both the runner and the
  parity gate, so they are live by construction.
- **Shell gates.** Any new or edited `.sh` must pass `shellcheck.sh` and
  `shfmt.sh`. The house shfmt flags are `-i 4 -ci`; plain `-i 4` breaks case-arm
  indentation.
- **New gate placement.** A new gate lives in `.ci/scripts/quality|security/` or
  carries a `check:ci-*` npm key, per the widened `BARE_GATE` rule in 6.3.4.
- **Do not run `npm run ci` from a workflow** to "fix" parity. It would collapse
  the ten lanes into one serial job and trip the tautology guard in 6.3.2.
- **Shared tree.** Neither agent may `git checkout`, `restore`, `stash` or
  `clean`, and neither may run a repo-wide regenerate script. The tree carries
  other sessions' uncommitted work.

---

## 8. Anti-vacuity: proving both halves can FIRE

Per the house rule and the `check-schema-coverage.ts:34-44` template, each
instrument proves itself on a planted defect before its green means anything.

### 8.1 In-process controls

- **Parity gate**: on every run, before the real check, resolve a synthetic
  in-memory fixture carrying one planted asymmetry in each direction and assert
  both are reported. Modelled on `check-gate-reachability.ts:104-136`, which
  already does exactly this with a synthetic `planted` package. Also assert the
  escape hatch silences a finding, so the exemption path itself is exercised.
  If any leg does not fire, print `CONTROL FAILED` and exit non-zero without
  running the real check.
- **Runner**: `--selftest` drives a synthetic manifest containing one gate that
  exits 1 with known text on both streams, and asserts the runner exits 1, prints
  that text from both streams, and names the gate in the summary. Wire
  `--selftest` into the gate's npm script so it cannot sit behind a flag nothing
  invokes -- the failure mode `check-gate-reachability.ts:16-20` records for
  `check-i18n-cross-locale.ts`, and the one
  `test-tutorial-render-queue.sh:100-110` pins by asserting the npm key really
  carries `--selftest`.

### 8.2 Empty-tree registration

Add to the `REGISTRY` in `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`:

```
    "check-ci-parity.ts|Refusing to run"
```

and REMOVE the now-dead `check-ci-chain-parity.ts|blind` and
`check-gate-reachability.ts|Refusing to run` entries (around
`test-gate-anti-vacuity.sh:96-105`). The registry is hand-verified by policy
(`test-gate-anti-vacuity.sh:23-30`); leaving entries for deleted scripts would
make the harness fail for the wrong reason.

The runner is deliberately NOT registered there. Against an empty tree it would
fail on a missing manifest, which is an environment failure wearing a vacuity
failure's exit code -- the exact false signal the registry policy warns about
(`test-gate-anti-vacuity.sh:23-30`, and the reasoning spelled out for
`check-autopilot-no-bypass.sh`). Its control is `--selftest` instead.

### 8.3 Gate test suites

`.ci/scripts/test/gates/test-ci-parity.sh` (replaces `test-chain-parity.sh`;
same fixture style, `CI_PARITY_ROOT` seam mirroring `CHAIN_PARITY_ROOT`,
`check-ci-chain-parity.ts:48-50`):

1. A manifest gate whose declared `ci` step really exists and really runs it: pass.
2. **#549 control**: a manifest gate no workflow `run:` block executes: fail,
   named, direction reported as chain-only.
3. **The name-field control**: a workflow whose step `name:` contains
   `npm run check:foo` while its `run:` does not: must STILL fail as chain-only.
   This is the live defect from section 1.4 pinned as a regression case.
4. `npm run ci` inside a `run:` block: fail with the tautology diagnostic, and no
   gate reported as covered by it.
5. CI-only: a `run:` block invoking `.ci/scripts/quality/check-orphan.sh` with no
   manifest entry: fail, direction ci-only.
6. R1: a `check:ci-*` key in package.json absent from the manifest: fail.
7. Aggregator transitivity: a gate reached only through `check:i18n` counts as
   covered in both directions (the trap `check-gate-reachability.ts:22-25` names).
8. Workspace scoping: `npm run test:unit -w @rediacc/cli` resolves into the cli
   workspace manifest, not the root one.
9. Manifest rot: a `ci` pointer naming a job that does not exist in the named
   workflow: fail.
10. A valid BLOCKER exemption silences a finding; `# BLOCKER: tbd` is rejected by
    the shared validator (carried from `test-chain-parity.sh:154-168`).
11. A script path inside a YAML comment is not an invocation (carried from
    `test-chain-parity.sh:111-123`).
12. Build/deploy/release helper paths are not treated as gates (carried from
    `test-chain-parity.sh:125-138`).
13. Empty workflow tree, and separately empty manifest: refuse to run, non-zero
    (carried from `test-chain-parity.sh:184-195`).
14. Parity surface is computed: a lane workflow reachable only via
    `uses: ./.github/workflows/<new>.yml` is included without being named
    anywhere in the gate.

`.ci/scripts/test/gates/test-ci-runner.sh` (new):

1. All-pass synthetic manifest: exit 0, one line per gate, no gate output printed.
2. One failing gate: exit 1, complete stdout AND stderr printed under separate
   headers, rerun command printed, and every other gate still ran.
3. `--fail-fast`: exit 1 and the remaining gates demonstrably did not run.
4. Mutex: two gates in one group never overlap. Each probe appends start and end
   timestamps to a file; assert no interval overlap.
5. `needs`: a dependent never starts before its dependency finishes; a dependent
   of a FAILED gate is reported skipped, not passed, and the run exits non-zero.
6. `--jobs 2`: maximum observed concurrency is exactly 2 (same timestamp probe).
7. Empty manifest: refuse to run, non-zero.
8. Missing duration cache: runs normally, no crash.
9. Determinism: the exit code and the summary ordering are stable across runs
   even though completion order is not.
10. `--json`: parses, and its per-gate `stdout`/`stderr` match what was printed.

Both suites must emit `PASS:` lines: `run-all.sh:74-81` counts a test that exits
0 without a single `PASS:` as a FAILURE.

---

## 9. Work split: two agents, disjoint file ownership

Both land on branch `0731-2`, uncommitted by default. Max two concurrent writers
(house rule). Neither touches the other's files; if a change seems to require it,
stop and report rather than reaching across.

### Agent R, "runner"

Owns, exclusively:

- `scripts/ci-runner/run.ts`, `pool.ts`, `exec.ts`, `report.ts` (new)
- `.ci/scripts/test/gates/test-ci-runner.sh` (new)
- `package.json` (the `scripts` block, sole writer)
- `.gitignore` (add `.ci/cache/gate-durations.json`)
- `docs/agent/ci-gates.md` (runner usage, the new failure-output shape, the
  `--changed` caveat)

Imports `scripts/ci-runner/manifest.ts` read-only against the interface frozen in
section 5. Does not create or edit it.

Carries these findings:

- **F1**: drop `lint` from the gate set. `check:lint` strictly subsumes it
  (`package.json:114` versus `:143`) and it costs 120.9 s measured. The
  package.json `lint` key stays as a developer convenience; it just leaves the
  chain. (The manifest is Agent P's file, so Agent R states the omission and
  Agent P does not add an entry. Coordinate via this plan, not by editing.)
- **F6**: `check:ci-account-no-admin-role` (`package.json:75`) cannot fail. Its
  body is `! grep -rn '...' ...; echo 'OK: no admin user role'`; the `;` makes
  the exit status the echo's. **Verified live during planning**: on a fixture
  containing `enum customer admin`, the command prints the matching line and
  still exits 0. Fix: replace `;` with `&&` so the negated grep gates the echo.
  Sweep the class first: `check:ci-account-no-node-env-routes`
  (`package.json:79`) uses `&&` and is correct, but grep every other one-liner
  gate in package.json for the same `;` pattern before calling it fixed.
- **Flattening `check:ci-quality-gates`** per section 2: this is the single
  highest-value piece of the runner and must not be descoped. Without it the
  ceiling is 2.4x.
- **F7 / F8, the baseline.** Before enabling parallelism, run the gate set at
  `--jobs 1` and record which gates are red on this tree (`check:deps` at
  minimum). Any red that appears only under parallelism is then attributable;
  without the baseline, F8's existing flake will be blamed on the pool.

Adds to package.json, verbatim, so Agent P never needs to touch the file:

```jsonc
"check:ci-parity": "tsx scripts/check-ci-parity.ts",
```

and removes `check:ci-chain-parity` and `check:ci-gate-reachability`.

### Agent P, "parity"

Owns, exclusively:

- `scripts/ci-runner/manifest.ts` (new; the frozen interface from section 5 plus
  every gate entry)
- `scripts/check-ci-parity.ts` (new)
- `scripts/check-ci-chain-parity.ts`, `scripts/check-gate-reachability.ts`
  (delete)
- `.ci-parity-exempt` (new), `.ci-chain-exempt` (delete)
- `.ci/scripts/test/gates/test-ci-parity.sh` (new),
  `.ci/scripts/test/gates/test-chain-parity.sh` (delete)
- `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` (registry entries only)
- `.ci/scripts/ci/scope-map.cjs` (`ROOT_MANIFESTS` rename only)
- `.github/workflows/ci-quality.yml`
- `docs/agent/suppressions.md`
- `scripts/check-suppression-liveness.ts`

Carries these findings:

- **F2**: the `text` versus `code` inconsistency at
  `check-ci-chain-parity.ts:186-197` dies with the rewrite. Pin it as suite case
  3 so it cannot come back.
- **F3**: `test-write-once-guard.sh` and `test-install-script.sh` get manifest
  entries and CI pointers (`ci-quality.yml:158-164`).
- **F4**: resolve all seven direction-A leaves per section 6.6. Five get real
  workflow steps in `ci-quality.yml`; two get `ci.kind: 'test'` with BLOCKERs.
- **F5**: declare `check:ci-seo` / `check:ci-redirects` / `check:ci-cta-bolt` as
  `needs: ['build:www']` so the built-HTML scan is non-vacuous locally
  (`ci-quality.yml:738-740`). The `build:www` node itself is Agent R's scheduler
  concern; Agent P only declares the edge.

### Sequencing and the seam

The seam is `manifest.ts`. Agent P writes it first (it is also the parity gate's
input), Agent R codes against the frozen interface from day one and does not
block on the entries being complete: a three-entry stub is enough to develop the
pool against, and `test-ci-runner.sh` uses synthetic manifests anyway.

Integration is done when, in one tree:

0. A `--jobs 1` baseline run is recorded first, so F7 and F8 are separated from
   anything the pool causes (section 2, F8).
1. `npm run ci` (the runner) reaches the same verdict as that baseline, and its
   wall time is materially below the serial sum, both numbers printed by the
   summary. Target is the ~7x implied by section 2; anything near 2.4x means the
   quality-gate battery did not get flattened.
2. `npm run check:ci-parity` goes green with zero direction-A findings.
3. `npm run check:ci-quality-gates` goes green including both new suites.
4. `npm run check:ci-shell-lint` and `check:ci-shell-format` pass on both new
   `.sh` files.
5. `npm run lint:unused` passes with no new knip ignore entries.
6. A deliberate defect planted in a real gate makes `npm run ci` exit 1 and print
   that gate's full output. Run it, do not reason about it.

---

## 10. Risks

- **The two halves are one change.** Stated at the top; repeated because it is
  the only way this plan produces #549 again if ignored.
- **Manifest maintenance burden.** Roughly 150 entries once the 57 quality-gate
  tests are flattened in. Mitigated two ways: assertion 6.3.5 makes a wrong or
  stale entry fail the gate rather than rot, naming the exact field; and the
  `qualityGateTest` set is checked for equality against the on-disk glob, so
  those 57 are maintained by a rule rather than by hand.
- **Parallel gates surfacing latent flakiness.** Some gate may depend on a
  resource not yet identified in section 2.1. Symptom is a gate that passes at
  `--jobs 1` and fails under load. Response is a new `mutex` group with the
  resource named, never a retry. Bisect with `ci:serial`. F8 proves this risk is
  already live in the serial harness, so the `--jobs 1` baseline is what
  separates a real parallelism bug from a pre-existing flake.
- **Memory.** 20 cores times an 8 GB heap would OOM a 56 GB box. The `heavy`
  budget in 4.2 is the control; validate it by watching peak RSS on the first
  full parallel run rather than trusting the default.
- **Output volume on a broad failure.** Full capture from twenty failing gates is
  a lot of text. Accepted deliberately: truncation is how a diagnostic becomes
  useless, and the operator asked for helpful failure output. `--json` is the
  route for programmatic consumers that want to slice it.

---

## 11. Evidence index

Measurements taken during planning, all reproducible:

- Per-gate wall times: `npm run --silent <key>` for 90 of the 92 reachable chain
  keys, sequential, 300 s cap, 20-core / 56 GB box, warm `node_modules`. One key
  hit the cap (`check:ci-quality-gates`, rc=124) and was re-measured uncapped at
  443 s. Corrected serial total 1041.6 s.
- `run-all.sh` uncapped: 443 s, 57 tests, 611 assertions, "56 passed, 1 failed"
  (`test-claude-hooks.sh`). Standalone re-run of that test: 452 cases, 0
  failures. Subset re-run `./run-all.sh 'test-c*.sh'`: 5 passed, 0 failed,
  131 s. Not reproduced; recorded as F8, cause unknown.
- Set differences: `run:`-block extraction over `.github/workflows/*.yml` with
  transitive npm-key expansion through root and workspace manifests, compared at
  leaf-command level. Direction A = 7, direction B = 24 (8 already exempt, 14 out
  of scope, 2 real holes).
- The `name:`-field trap: whole-file matching reports direction A = 0; `run:`-block
  matching reports 7. `ci-quality.yml:550` is the line responsible.
- F6: on a fixture containing `enum customer admin`, the
  `check:ci-account-no-admin-role` body prints the match and exits 0.
