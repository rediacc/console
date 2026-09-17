Status: measured, ZERO shadow-gate ledgers recorded
Owner: f4da5c2e (writer, gate-test ledger coverage)
Date: 2026-09-09

# Gate-test twin coverage via `scripts/lib/shadow-gate.ts`: why 0 pairs were recorded

**Headline: I recorded ZERO `.ci/shadow/*.observations.jsonl` pairs for gate-test twins.**
Not because the tree wasn't clean enough to try, and not because I ran out of batch time. `shadow-gate.ts`, unmodified, **cannot produce an `EQUIVALENT` verdict for any of the 149 `.ci/scripts/test/gates/test-*.sh` <-> `.ci/rediacc_ci/tests/gates/test_gate_*.py` pairs**, for a structural reason common to the whole population, demonstrated below with a real planted defect on a real
clean tree, not argued from reading the code.

There is also a second finding that changes the shape of the whole question: **a different, purpose-built, currently-live equivalence control already exists for 141 of the 149 twins** (`test_twin_parity.py::test_port_and_twin_agree`), runs in CI on every push, and is backed by its own hash-keyed ledger (`.ci/shadow/twin-parity.ledger.jsonl`, already 231+ lines). The census's "0 of
149 gate tests carry a [shadow-gate] ledger" is correct as literally stated but is easy to misread as "gate-test equivalence is unchecked", which is false.

## 0. Method: how a `--record` was even attempted in a shared, dirty branch checkout

`shadow-gate.ts --record` refuses unconditionally on a dirty tree (rule 4, no override flag). This branch (`0906-1`) carries ~24-49 files of concurrent, uncommitted work from other sessions throughout this task, none of which is mine to touch:

```
$ npx tsx scripts/lib/shadow-gate.ts --pair test-probe-scratch --old 'true' --new 'true' --record
✗ test-probe-scratch: ledger write REFUSED -- the working tree is DIRTY ...
EXIT: 3
```

That is real and load-bearing, not a hypothetical: recording directly against `/home/developer/console` was never going to work while this branch is shared. The workaround, used for everything below: a **local, disposable, full clone of the exact same HEAD** (`git clone --local --no-hardlinks --single-branch --branch 0906-1 --no-tags . <scratch>`), with `node_modules` and each
`packages/*/node_modules` **symlinked in** (not copied) so `npx tsx` / `pytest` work without a second install, and the symlink names added to `.git/info/exclude` in the clone only (a local, untracked git setting, not a content change) because `.gitignore`'s `node_modules/` pattern does not match a symlink named `node_modules` -- only a real directory. Verified this reproduces the
exact committed tree id:

```
$ git -C <scratch-clone> rev-parse HEAD^{tree}
c70e241d78ad169f04bffea1e64d9c05e74c810a
$ (cd /home/developer/console && git rev-parse HEAD^{tree})   # before any of my edits
c70e241d78ad169f04bffea1e64d9c05e74c810a
$ npx tsx scripts/lib/shadow-gate.ts --repo <scratch-clone> --pair x --old true --new true --json
  "tree": { "id": "c70e2...", "head": "917d1902d...", "branch": "0906-1", "clean": true, ... }
```

This technique is real and reusable -- a future session recording gate-test or any other ledger from a dirty shared branch should clone-and-symlink rather than wait for a clean checkout that a multi-session branch may never have. **The real console repo at `/home/developer/console` was never modified by any of this**; every plant, commit and revert happened only inside the
throwaway clone (verified: `git status --porcelain` on the real repo shows none of the touched files before/after).

## 1. The structural blocker, demonstrated on a real planted defect

Picked `test-actions-release-age.sh` / `test_gate_actions_release_age.py` -- both drive the **same real TypeScript helper** (`scripts/lib/release-age.ts`) through `npx tsx`, so their assertion messages are, by construction, the closest thing in this estate to two callers of one function: bash's `assert_eq` and python's `harness.Harness.assert_eq` build the identical string
(`"<msg>: expected '<exp>', got '<act>'"`), verified by reading both implementations side by side (`.ci/scripts/test/lib/test-helpers.sh:36-41` and `.ci/rediacc_ci/tests/gates/harness.py:391-398`). If any pair in the whole population were going to reach `EQUIVALENT`, it would be this one.

**Plant** (in the scratch clone only, committed there so the tree stays clean for `--record`, never touching the real repo):

```ts
// scripts/lib/release-age.ts, isWithinFreshnessWindow
- return nowMs < eligibleAtMs(publishedMs, minReleaseAgeMs);
+ return nowMs > eligibleAtMs(publishedMs, minReleaseAgeMs); // PLANTED DEFECT
```

**Bash twin, driven for real:**

```
$ bash .ci/scripts/test/gates/test-actions-release-age.sh
TEST: test-actions-release-age
PASS: the gate delegates to the shared window, so exercising the lib exercises the gate
FAIL: a release minutes old must be deferred, not demanded: expected 'deferred', got 'eligible'
exit 1
```

One finding (bash halts at the first `log_fail`).

**Python port, driven for real** (`--tb=line`, the closest pytest gets to bash's one-line shape):

```
$ pytest -q --tb=line .ci/rediacc_ci/tests/gates/test_gate_actions_release_age.py
.FF......  [100%]
E   rediacc_ci.tests.gates.harness.GateAssertionError: a release minutes old must be
    deferred, not demanded: expected 'deferred', got 'eligible'
.../harness.py:378: rediacc_ci.tests.gates.harness.GateAssertionError: a release minutes
    old must be deferred, not demanded: expected 'deferred', got 'eligible'
E   rediacc_ci.tests.gates.harness.GateAssertionError: a release well past the window
    must still be demanded: expected 'eligible', got 'deferred'
2 failed, 7 passed
```

Two findings: pytest does not stop at the first failing test **function**, only at the first failing assertion **inside** one.

**Actual `shadow-gate.ts` verdict**, run for real against the clean planted tree:

```
$ npx tsx scripts/lib/shadow-gate.ts --repo <scratch-clone> --pair wtest-actions-release-age \
    --old 'bash .ci/scripts/test/gates/test-actions-release-age.sh' \
    --new 'PYTHONDONTWRITEBYTECODE=1 <pytest> -q --tb=line .ci/rediacc_ci/tests/gates/test_gate_actions_release_age.py'

✗ wtest-actions-release-age: MISMATCH_FINDINGS -- exit codes agree at 1, but 1 finding(s)
  are old-only and 2 are new-only
  only-old  [error] a release minutes old must be deferred, not demanded: expected 'deferred', got 'eligible'
  only-new  [error] <repo>/.ci/rediacc_ci/tests/gates/harness.py:378: rediacc_ci.tests.gates.harness.GateAssertionError: a release minutes old must be deferred, not demanded: expected 'deferred', got 'eligible'
  only-new  [error] <repo>/.ci/rediacc_ci/tests/gates/harness.py:378: rediacc_ci.tests.gates.harness.GateAssertionError: a release well past the window must still be demanded: expected 'eligible', got 'deferred'
```

**Fixing the cardinality mismatch alone is not enough.** Re-ran with `pytest -x` (stop at first failure, matching bash's halt-on-first semantics exactly):

```
$ npx tsx scripts/lib/shadow-gate.ts --repo <scratch-clone> --pair wtest-actions-release-age-x \
    --old 'bash .ci/scripts/test/gates/test-actions-release-age.sh' \
    --new '... pytest -q -x --tb=line .../test_gate_actions_release_age.py'

✗ wtest-actions-release-age-x: MISMATCH_FINDINGS -- exit codes agree at 1, but 1 finding(s)
  are old-only and 1 are new-only
  only-old  [error] a release minutes old must be deferred, not demanded: expected 'deferred', got 'eligible'
  only-new  [error] <repo>/.ci/rediacc_ci/tests/gates/harness.py:378: rediacc_ci.tests.gates.harness.GateAssertionError: a release minutes old must be deferred, not demanded: expected 'deferred', got 'eligible'
```

Now the cardinality matches (1 vs 1) and **the underlying message is byte-identical as a substring** -- and it is still `MISMATCH_FINDINGS`, because `shadow-gate.ts`'s normalizer has no rule that strips pytest's `<file>:<line>: <ExceptionType>: ` prefix. `classify()`'s `findingRe` option only ever *classifies* a line as a finding (a boolean test); the actual stripping happens
exclusively through the fixed `MARKERS` table (`✗ `, `FAIL:`, `ERROR:`, `::error::`, etc.), and none of those match pytest's own traceback shape. `--mask-sha` doesn't help either -- this isn't a sha, it's a decorated exception line.

**This generalizes to the whole population, not just this one twin.** Checked five more modules at random (`age_check`, `blocker_validator`, `breakpoint_drift`, `label_inventory`, `swallowed_failures`): all use the same shared `gate` fixture (`.ci/rediacc_ci/tests/gates/conftest.py`) and the same `harness.Harness.log_fail` / `assert_*` methods that raise `GateAssertionError`
(`.ci/rediacc_ci/tests/gates/harness.py:368-410`), which pytest reports with the identical `<path>:<line>: <exc>: <message>` decoration under any `--tb` mode short of a custom reporter. The blocker is in the shared harness and in pytest's own default reporting, not in any one twin.

**To make `shadow-gate.ts` reach `EQUIVALENT` for gate-test twins needs one of two shared code changes, neither of which is a "twin genuinely needs a fix to be drivable" scoped edit:**

1. Teach `classify()` a marker for pytest's `<path>:<line>: <ExceptionType>: ` shape that
*strips* the file/line/exception-type prefix and keeps only the message -- a change to `scripts/lib/shadow-gate.ts` itself, which is the shared comparator behind all 82 existing quality-gate ledgers. Changing its normalization rules retroactively affects how every one of those is re-verified.
2. Give the shared `gate` fixture / `harness.py` a bash-compatible failure printer (emit
`FAIL: <msg>` to stderr the way `test-helpers.sh` does, in addition to raising) -- a change to the harness used by all 141 ported modules' output shape, and it still leaves the cardinality question (bash halts at the first failing function; a `test_port_and_twin_agree`-shaped full run does not, unless invoked per-function or with `-x`).

Either is a real, scoped, doable change -- but it is an edit to shared infrastructure with a wide blast radius, which is bigger than "record a first ledger row" and is not something I did unilaterally from a session scoped to `.ci/shadow/**` plus narrow twin fixes. I did not touch `scripts/lib/shadow-gate.ts` or `.ci/rediacc_ci/tests/gates/{harness,conftest}.py`.

## 2. The equivalence control that already exists and is already live

`.ci/rediacc_ci/tests/gates/test_twin_parity.py::test_port_and_twin_agree` is a real, currently-passing, continuously-run differential for exactly this population:

- It drives the bash twin as a subprocess and the pytest port in-process/nested, on every
`check:ci-pytest` invocation.
- It compares **verdict agreement** (twin rc==0 vs port rc==0 -- `test_twin_parity.py:697-712`)
and **case-set membership** (every `test_*` the twin *declares and calls* must have a same-named `def test_*` in the port), which is a materially different and, for a unit-test battery, more appropriate equivalence question than shadow-gate's literal finding-text multiset.
- It has its own hash-keyed reuse ledger, **already on disk** at
`.ci/shadow/twin-parity.ledger.jsonl` (231 lines as of this session, e.g. `{"at":"2026-09-08T...","subject":"test_gate_dead_case_arms","twin":".../test-dead-case-arms.sh","twin_sha":"...","port_sha":"...","agreed":true}`), explicitly modelled on the shadow-gate ledger shape (`test_twin_parity.py:620-624`: "The shape deliberately mirrors `.ci/shadow/*.observations.jsonl`").
- Verified LIVE, for real, not from reading the docstring: ran a 5-module slice --
`pytest -q test_twin_parity.py -k "age_check or blocker_validator or breakpoint_drift or label_inventory or swallowed_failures"` -> `5 passed`. All five reused a cached agreement row rather than re-driving (the hash-reuse path -- `may_reuse()`, `test_twin_parity.py:591-616` -- prints `REUSED a recorded agreement` and returns without re-running either side when neither the twin's
nor the port's file content has changed since the last `agreed: true` row).
- Ran the shadow-gate CLI's own `--selftest` for a sanity check on the tool I was using: `0`
rows failed, confirming `shadow-gate.ts` itself is not the thing that's broken here.

**Reachability, for the whole class, not case by case.** Every one of the 149 bash gate-test scripts is its own `gate-test:<n>` leaf in `scripts/ci-runner/manifest.ts` / `gates.lock.json`, wired to the **"Quality-gate unit tests"** step in `.github/workflows/ci-quality.yml` (`npm run check:ci-quality-gates`, driving `run-all.sh`/`battery.py` directly against the bash files).
Separately, **every** python port is collected and run by `npm run check:ci-pytest` in the **"Python package tests"** step of the *same job* (`quality-security`), which is where `test_twin_parity.py` lives. Confirmed by reading `.github/workflows/ci-quality.yml:1973-1982` directly: both steps run, in that order, in the same job, unconditionally. So for gate tests -- unlike the
quality gates, where the census found a live workflow (`autopilot.yml:252`) invoking a bash twin that no other step still reaches -- **both sides are demonstrably reachable for the entire 149-item population today.** The 8 twins with no declared `BASH_TWIN` (`test-autopilot-breakpoint-alignment.sh`, `test-autopilot-no-bypass.sh`, `test-ci-job-aggregation.sh`,
`test-commit-identity.sh`, `test-go-module-sync.sh`, `test-plan-housekeeping.sh`, `test-regions-sync.sh`, `test-toolchain.sh` -- one fewer than the census's 9, since a port apparently landed for one between the census and now) simply have no port to be equivalence-checked against yet; that is a porting gap, not a reachability gap.

## 3. What this means for W7P5-c's licence, and what I recommend

The census's condition **C1** (a shadow-gate ledger at K=5) is the wrong instrument for this half of the estate as things stand -- not because nobody has run it yet, but because running it cannot succeed without a shared-code change (section 1). Two honest paths forward, both requiring a driver/operator decision I am not making unilaterally:

1. **Make the shared code changes in section 1**, then genuinely record shadow-gate.ts
ledgers the way this session tried to. Real, scoped, but touches shared infrastructure (`shadow-gate.ts`'s comparator or the whole ported-test harness's reporting shape) used by the other 82 ledgers or all 141 ported modules respectively.
2. **Recognize `test_twin_parity.py::test_port_and_twin_agree` plus its
`.ci/shadow/twin-parity.ledger.jsonl` as the equivalence evidence for gate-test twins**, in place of a shadow-gate ledger. It already answers the same question (does the port agree with the twin) continuously rather than over 5 sampled trees, and it is already wired into CI. This would mean C1 for gate tests reads "a passing `test_port_and_twin_agree` case", not "a `--assert --k 5`
shadow ledger" -- a definitional change to the licence, not a code change, and squarely the driver's or operator's call.

I did not pick one and act on it; both are bigger than a coverage-recording session and both were flagged rather than decided.

## 4. What was and wasn't touched

- **Recorded: 0 shadow-gate.ts pairs.** None of the 149 twins got a `.ci/shadow/*.jsonl`
row from me, for the reasons above. Writing one that reads `MISMATCH_FINDINGS` would not help toward a K=5 `EQUIVALENT` licence anyway, so there was nothing productive to record.
- **Left alone, exactly as instructed:** `.ci/scripts/test/gates/**` (read-only, never
edited or run destructively -- every bash twin I drove was read and executed, never modified), `.ci/config/**`, `.ci/scripts/quality/**`, `scripts/lib/shadow-gate.ts`, `.ci/rediacc_ci/tests/gates/{harness,conftest,test_twin_parity}.py`, and everything under `.ci/shadow/w7p5a-*` (the other writer's).
- **The real repository (`/home/developer/console`) was never modified by any experiment
in this report.** Every plant, commit, and the one `sed` edit happened only inside a throwaway local clone at `/tmp/claude-1000/-home-developer-console/f4da5c2e-8ce0-4880-939c-fa85f310fc66/scratchpad/clean-clone`, which I intend to delete after this report is filed (or leave for inspection if asked -- it is pure scratch, 417 MB, reproducible from the commands in section 0).
- **Gates run, with exit codes:**
  - `npx tsx scripts/lib/shadow-gate.ts --selftest` -> 0 (tool's own controls pass)
  - `bash .ci/scripts/test/gates/test-actions-release-age.sh` (planted tree, scratch clone) -> 1 (real failure, expected)
  - `pytest -q --tb=line .../test_gate_actions_release_age.py` (planted tree, scratch clone) -> 1 (real failure, expected)
  - `npx tsx scripts/lib/shadow-gate.ts --repo <clone> --pair wtest-actions-release-age --old ... --new ...` -> 1 (`MISMATCH_FINDINGS`, the finding of this report)
  - same with `-x` on the python side -> 1 (`MISMATCH_FINDINGS`, narrower but still not `EQUIVALENT`)
  - `pytest -q test_twin_parity.py -k "actions_release_age"` (real repo, unplanted) -> 0 (1 passed)
  - `pytest -q test_twin_parity.py -k "age_check or blocker_validator or breakpoint_drift or label_inventory or swallowed_failures"` (real repo, unplanted) -> 0 (5 passed)
  - `npx tsx scripts/lib/shadow-gate.ts --repo <clone> --pair test-probe-scratch --old true --new true --record` (dirty real repo, before the clone workaround) -> 3 (dirty-tree refusal, the finding that justified the clone technique)

## 5. Measured remainder

**All 149 remain unrecorded**, 141 with a declared `BASH_TWIN` (blocked structurally per section 1), 8 without one yet (blocked on porting, which is W7P3/P4's work, not this session's). Nothing here is a "coherent batch, partially done" -- it is a full-population finding: the mechanism named for this task does not fit this class of twin without a shared-infrastructure decision, and
that decision is not mine to make from this seat.
