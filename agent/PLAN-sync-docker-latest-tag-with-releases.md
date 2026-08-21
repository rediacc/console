# PLAN: the nightly asserts an unreleased version against the last released image
Status: done
Owner: e6500e92
Updated: 2026-08-21

Worklist item `#481e3bf0`. Verified against `main` at `ba7b175c1` on 2026-08-20.

## Symptom

Scheduled Console CI fails on `Validate Install Methods / Linux (x64)` and `(arm64)`:

```
✓   Version: 1.2.27
→ TEST: Docker Pull and Run
latest: Pulling from rediacc/rdc
✗ Version mismatch: expected '1.2.27', got '1.2.26'
```

Reproduced on runs `32323997586` (2026-08-20T02:15Z) and `32208001410`, both on the
previous main `6584a8795`. It is deterministic, not flaky.

## Root cause, traced end to end

Four facts, each checked against the tree rather than inferred:

1. `ci.yml:302` gates the `scope` step on `github.event_name == 'pull_request'`. On a
   `schedule` run the step never executes, so every `steps.scope.outputs.*` is empty.
2. `ci.yml:1276` admits the job on `run_install_methods != 'false'`. Empty is not
   `'false'`, so the job RUNS on schedule. The gate reads like a guard and cannot act
   as one for this event.
3. `assert-channel-for-event.sh:24-31` requires `schedule` to resolve an EMPTY channel,
   so `ci.yml:1280` passes `docker_tag: ''`.
4. `.ci/config/constants.sh:27` then does `DOCKER_TAG="${DOCKER_TAG:-latest}"`. An
   empty-string value takes the default, so `DOCKER_TAG` becomes `latest` before the
   test script runs.

The consequence is that `test-install-methods.sh:750`,
`local tag="${DOCKER_TAG:-${VERSION}}"`, is DEAD CODE. `constants.sh` guarantees
`DOCKER_TAG` is non-empty, so the `:-${VERSION}` arm can never be taken. The comment
above it ("DOCKER_TAG env var overrides version-based tag") describes a fallback that
does not exist.

So the job pulls the last RELEASED image and asserts the NEXT version against it. It
fails whenever `main` carries commits since the last tag, which is the normal state.

### Reproduced locally, with controls

```
$ env -u DOCKER_TAG bash .ci/scripts/test/test-install-methods.sh \
    --dry-run --method docker --version 1.2.27
✓ [DRY-RUN] Would run: docker pull 'ghcr.io/rediacc/rdc:latest' ...   <- the defect

$ DOCKER_TAG=edge bash .ci/scripts/test/test-install-methods.sh \
    --dry-run --method docker --version 1.2.27
✓ [DRY-RUN] Would run: docker pull 'ghcr.io/rediacc/rdc:edge' ...     <- control, tag honored
```

The second command is the control: it proves the probe can print a tag other than
`latest`, so the first result is the bug and not the harness failing to report.

`resolve-version.sh --current` is `1.2.26`; `--bump-type patch` is `1.2.27`.

## Why this is getting worse, not staying still

`dispatch-release.sh` skips the whole release when the merged PR carries `bump-none`.
PR #569 carried it deliberately, so `:latest` stays at `1.2.26` while `main` keeps
computing `1.2.27`. Every `bump-none` merge widens the gap and the nightly stays red
until some later merge earns a release. A permanently red nightly is the real cost
here: it trains readers to ignore the one run that watches main.

## Options

**A. Gate the job on a non-empty channel (RECOMMENDED).**
`ci.yml:1273-1276` gains `needs.initialize.outputs.channel != ''`, exactly as
`validate-promote` already does at `ci.yml:1331-1334`. That block states the principle
verbatim: "Skipping is the honest outcome, not a workaround", because with no channel
there is nothing staged and the job has no subject. It names Stage Artifacts and
Validate Install Methods as the other two instances of the same class, so this is the
already-decided answer, applied to the one site that still lacks it.

Cost is small and should be stated rather than glossed: the schedule run currently
SKIPS Binary Download too (`0 passed, 0 failed, 1 skipped`), so the job has little
subject on this event either way.

**B. Assert the current released version on schedule.**
Pass `--version $(resolve-version.sh --current)` when the channel is empty, turning
the step into a genuine published-artifact check: does `:latest` report the version
its tag claims. More coverage than A, but it changes what the step MEANS depending on
the event, and a step whose assertion silently differs per trigger is the class of
instrument this repo has been burned by.

**Independent of A or B**, repair the dead fallback at `test-install-methods.sh:750`:
either drop the `:-${VERSION}` arm and its comment, or stop `constants.sh:27` from
rewriting an explicitly-empty `DOCKER_TAG`. Leaving a fallback that cannot fire is
precisely the "check that cannot fail" pattern `docs/agent-reference/TRAPS.md` exists
to catch. Prefer fixing the site that lies (`:750`) over `constants.sh:27`, which is
shared and whose `latest` default other callers may legitimately want.

## Tests, and each must be shown to FIRE

- A gate test in `.ci/scripts/test/gates/` asserting `validate-install` carries the
  `channel != ''` condition. Plant the defect by removing the condition and confirm
  the test goes red; restore and confirm green. A gate that was never watched failing
  is not evidence.
- A dry-run assertion pinning the computed image per DOCKER_TAG value: empty must NOT
  silently become `latest` once :750 is repaired. Control: `DOCKER_TAG=edge` still
  yields `:edge`.
- After the change, confirm on a real scheduled run (or the documented
  schedule-equivalent `workflow_dispatch` on main, guarded at `ci.yml:189-193`) that
  `Validate Install Methods` reports `skipped` and `CI Complete` still passes.
  `assert-ci-complete.sh` must forgive the skip; verify it does rather than assume it,
  the way `VALIDATE_PROMOTE` is already forgiven.

## Explicitly out of scope

Changing release cadence, or making `bump-none` merges publish a `:latest`. The label
is working as designed; the nightly's assertion is what is wrong.

## As implemented, 2026-08-20 (uncommitted)

Option A, plus the dead-fallback repair. Both changes are local and uncommitted.

- `.github/workflows/ci.yml` -- `validate-install` now also requires
  `needs.initialize.outputs.channel != ''`, with a comment tracing the four-step
  cause and naming the two nightly runs. Verified `VALIDATE_INSTALL` is in
  `SOFT_REQUIRED` (`assert-ci-complete.sh:38`), so the skip cannot redden
  `CI Complete` while a genuine failure still does.
- `.ci/scripts/test/test-install-methods.sh` -- the unreachable
  `${DOCKER_TAG:-${VERSION}}` is now plainly `${DOCKER_TAG}`, with the reason
  recorded. Behavior is byte-identical: the same three dry-run probes
  (unset, `edge`, `pr-569`) produce the same images before and after.
- `ci.yml` parses as YAML; `shellcheck -S error` is clean on the script; and
  `test-ci-complete-tiers.sh`, `test-workflow-contracts.sh`,
  `test-scope-gate-outputs.sh` and `test-workflow-inline.sh` all exit 0.

### The regression test IS written, and the obvious design was wrong

Stated plainly rather than quietly dropped. The natural class-level invariant --
"a job that passes `channel` into a reusable workflow must gate on
`channel != ''`" -- is FALSE. `stage-artifacts` passes the channel and must RUN
with an empty one; it is correct precisely because it skips only its two
metadata assertions internally (see `test-stage-artifacts-channel.sh`, which
tests that the skip stayed narrow). A universal rule would fire falsely there,
and an allowlist to silence it is the suppression shape this repo refuses.

So the remaining choice is between a bespoke ci.yml-invariants gate carrying one
assertion (new gate plus its three-point wiring and a both-directions mutation
test, mirroring `check-autopilot-workflow-invariants.sh`), or moving the refusal
into `test-install-methods.sh` so it can be fixture-tested the way the
stage-artifacts fix was. The second is more in keeping with how this class was
fixed before. Either way the test must be watched failing on a planted defect
before it counts.

### The gate, and how the false-positive risk was designed out

The universal rule stayed rejected. The invariant that shipped is narrower and
discriminating: **a job that passes the channel as a reusable workflow's
`docker_tag` must refuse an empty channel.** `stage-artifacts` consumes the
channel but does NOT pass `docker_tag`, so it is untouched and stays free to run
on the nightly. Tag selection is the discriminating detail, because an empty
channel there resolves to a DIFFERENT IMAGE rather than to nothing.

- `.ci/scripts/security/check-ci-workflow-invariants.sh` (new, wired as
  `check:ci-workflow-invariants`). Parses the workflow with PyYAML rather than
  grepping, so a reflowed `if:` cannot make it unenforceable. Carries a vacuity
  guard: if no job passes a channel-derived `docker_tag` any more, it FAILS
  rather than printing a green nobody earned.
- `.ci/scripts/test/gates/test-ci-workflow-invariants.sh` (new, wired as
  `gate-test:ci-workflow-invariants`). Six cases, all passing.

**The gate was watched failing before it was trusted**, in four directions:

| control | result |
|---|---|
| real ci.yml (fixed) | exit 0 |
| **real ci.yml at 6584a8795, the commit that broke the nightlies** | **exit 1, names `validate-install`** |
| current file mutated to drop the condition | exit 1 |
| `docker_tag` removed entirely (vacuity) | exit 1, `no-candidates` |
| workflow file missing | exit 1, `workflow-missing` |
| minimal correctly-gated fixture | exit 0 |

The second row is the one that matters: the gate rejects the actual historical
workflow whose failure prompted it, so it is not merely self-consistent.

Wiring verified end to end rather than assumed: `check:ci-parity` reports
"the local gate set and the CI quality surface agree in both directions" at 267
gates (was 265), `check_gate_reachability_coverage.py` agrees with all manifest
registrations and reports its own control fired, `shellcheck -S error` is clean,
and `shfmt -i 4 -ci` is clean.

## Closed 2026-08-21: shipped, and where the design actually moved

Status flips to done because every part of this design is implemented and its
gate is registered and reachable. It ships on console PR #570 (branch 0820-1),
commit b0184561c.

Two things changed from the plan as written, and both are worth the record
because a future reader would otherwise repeat the dead end:

**Option A was taken, and Option B was rejected on a reason the plan only
half-stated.** B (assert the CURRENT released version on a schedule run) would
have made one step mean different things on different triggers. That is the
failure shape this repo keeps paying for, so the narrowing is the point.

**The class-level invariant in the "Tests" section was WRONG as first drafted.**
"A job that passes the channel into a reusable workflow must gate on
channel != ''" is false: `stage-artifacts` passes the channel and MUST run with
an empty one, skipping only its two metadata assertions. Had that rule shipped
it would have broken a correct job, and an allowlist to silence it is the
suppression shape this repo refuses. The shipped invariant is scoped to
`docker_tag` specifically, because tag selection is the discriminating detail:
an empty channel there resolves to a DIFFERENT IMAGE rather than to nothing.

### Not covered by this plan, discovered while landing it

The same `main` run that would have proved the nightly fix went red for an
unrelated reason: `Validate Promotion` blew its 60-minute ceiling (61m12s, run
32423301927), which failed CI Complete and meant `Finalize Release Sentinel`
never rendered its verdict. That is tracked and fixed separately on the same PR
(commit f1e57ee32, server-side copy plus
`gate-test:simulate-promotion-serverside`) and is NOT part of this design.

Two external-drift gates were also cleared to get CI moving, neither related to
this design: the `golang:1.26-bookworm` pin past its soak window (via
rediacc/renet#105 plus a pointer bump) and `inquirer` 14.0.2 to 14.1.0.

### What is still unproven, deliberately

Nothing here demonstrates the nightly is GREEN. The fix makes
`Validate Install Methods` skip on a channel-less run, and the proof of that is
a scheduled run reporting `skipped` with `CI Complete` still passing. Until a
nightly has run against this change, the evidence is the gate and its planted
controls, not a live green.
