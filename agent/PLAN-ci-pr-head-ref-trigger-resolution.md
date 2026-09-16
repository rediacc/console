# PLAN: widen check:ci-pr-head-ref-completeness from "a setter exists" to "the setter resolves on every trigger"
Status: draft
Owner: d778be9d
Updated: 2026-09-16

The gate asserts that every workflow step invoking a `PR_HEAD_REF`-preferring script
carries a `PR_HEAD_REF` (or `GITHUB_HEAD_REF`) key in its `env:` block. It never reads
the VALUE. `f1ce6911f` fixed a setter whose expression covered two of its workflow's
three triggers and resolved to the empty string on the third; the gate was green
throughout. This widens it to cross-reference each setter expression against the
triggers its step can actually run under.

## The bug this is chasing, restated precisely

`.github/workflows/claude-review-reusable.yml:139` (step `Read the published snapshot`,
declared at `:120`) read, before `f1ce6911f`:

```yaml
PR_HEAD_REF: ${{ github.event.pull_request.head.ref || github.event.workflow_run.head_branch }}
```

That file's own `on:` block declares `workflow_call` only. Its sole local caller is
`.github/workflows/claude-review.yml:90`, whose `on:` declares `workflow_run`,
`pull_request` and `workflow_dispatch`, and whose calling job's `if:`
(`claude-review.yml:70-88`) admits all three. On the `workflow_dispatch` path both
clauses are empty, `.ci/scripts/review/discover-epics.sh:23-25` refused, and the review
died at its first job. `github.ref_name` was added as a third clause.

Two things made this invisible to the gate, and BOTH must be addressed:

1. **The gate reads values not at all.** `step_sets_var()`
   (`.ci/scripts/quality/check_pr_head_ref_completeness.py:124-129`) is
   `"PR_HEAD_REF" in env or "GITHUB_HEAD_REF" in env`. Any expression satisfies it.

2. **The gate never even reached that step.** Its corpus is READERS, and
   `find_readers()` (`:85-103`) drops any reader whose text matches `LOUD_FAILURE`
   (`:75`, applied at `:99`) on the argument that "a reader that fails LOUD when the
   variable is unset has already solved the problem itself". `discover-epics.sh:25`
   prints `PR_HEAD_REF is unset; refusing to guess a branch` — it matches, so it was
   exempt. The premise is wrong for the RESOLUTION question: a loud reader has not
   solved anything, it has converted a silent skip into a guaranteed red run.
   Measured now: `find_readers()` returns exactly three files
   (`.ci/scripts/quality/check-review-report-replies.sh`,
   `scripts/gates/check-pr-epic-block.ts`, `scripts/gates/check-pr-task-trailers.ts`)
   and the gate prints `2 PR_HEAD_REF reader(s) all have a setter in every invoking
   step (1 not invoked from any workflow, nothing to check)`.

The fix for (2) is not to delete the `LOUD_FAILURE` exemption — it is correct for the
question CHECK 1 asks. It is to give the new check a DIFFERENT CORPUS: **workflow steps
that SET the variable**, enumerated from the workflow files directly, with no reader
resolution in the path.

## Current implementation, as verified

- Single file, `.ci/scripts/quality/check_pr_head_ref_completeness.py`, registered at
  `package.json:141`, `scripts/ci-runner/manifest.ts:1319-1331`,
  `scripts/ci-runner/gates.lock.json:1251-1263`. Runs at
  `.github/workflows/ci-quality.yml:775-776`, lane `quality-code`.
- **There is no bash twin.** `ls .ci/scripts/quality/` has no
  `check-pr-head-ref-completeness.sh`, and no `.ci/rediacc_ci/quality/` module mirrors
  it. It is a native-Python (tier-2) gate, the same classification a previous session
  confirmed for its sibling `check:ci-workflow-submodule-deps` (worklist `f4da5c2e`
  item `6d928fdf`). **Nothing needs porting; the change lands in ONE file.**
- **There is no pytest file either.** `.ci/rediacc_ci/tests/gates/` contains no
  `test_gate_pr_head_ref*.py`. Its test convention is the inline `controls()` at
  `:161-218`: synthetic fixtures in a `tempfile.TemporaryDirectory()`, each direction
  asserted, `fail()` at `:155-159` exiting 1 with `✗ CONTROL FAILED ... A clean result
  below would mean nothing, so this gate refuses` BEFORE anything real is judged. New
  controls go there, same shape.
- It parses with PyYAML (`import yaml`, `:46`). Its gate header (`:34-40`) declares
  `needs: none` — a known, deliberate disagreement recorded in worklist `8f55d4f0`
  item `8cb54d6e` (the lane installs PyYAML inline at `ci-quality.yml`, but `lanes.ts`
  derives capabilities from workflow structure and cannot see inline pip installs).
  **Do not reopen that.** `.ci/rediacc_ci/workflows.py` is a dependency-free parser
  built to replace exactly these eight PyYAML gates (it names this one in its docstring
  at `:6`), and it already models triggers (`Workflow.triggers`, `workflows.py:705`,
  with the PyYAML `on:`→`True` bug fixed by design) — but it has **no production
  consumer yet**, only `.ci/rediacc_ci/tests/test_workflows.py`. Making this gate the
  first cutover is a separate decision with its own acceptance. This plan stays on
  PyYAML and pays the one tax that costs: the `on:` key.

**The `on:` trap, verified.** `yaml.safe_load('.github/workflows/ci.yml')` yields keys
`['name', True, 'permissions', 'concurrency', 'jobs']` — `True in d` is True, `'on' in d`
is False. Every trigger read must be `doc.get(True) or doc.get("on") or {}`.
`check_secret_reachability.py` carries the same workaround, and
`workflows.py:44-52` documents it as the one deliberate divergence from PyYAML.

## Detection algorithm

### CHECK 1 (unchanged)

Reader corpus, `LOUD_FAILURE` exemption, `step_sets_var()` presence test. Keep as is.

### CHECK 2 (new): trigger resolution over the SETTER corpus

**Corpus.** Every `(workflow, job, step)` in `.github/workflows/*.yml` whose `env:`
block contains a `PR_HEAD_REF` or `GITHUB_HEAD_REF` key. Seven such steps exist today:

| site | expression |
| --- | --- |
| `ci.yml:673` (step `:662`) | `${{ github.event.pull_request.head.ref }}` |
| `ci-quality.yml:538` | `GITHUB_HEAD_REF: ${{ github.head_ref }}` |
| `ci-quality.yml:665` | `GITHUB_HEAD_REF: ${{ github.head_ref }}` |
| `ci-quality.yml:1114` (step `:1103`) | `${{ github.event.pull_request.head.ref }}` |
| `ci-quality.yml:1121` (step `:1118`) | `${{ github.event.pull_request.head.ref }}` |
| `ci-quality.yml:2200` (step `:2196`) | `${{ github.event.pull_request.head.ref }}` |
| `claude-review-reusable.yml:139` (step `:120`) | `... || ... || github.ref_name` |

**Step 1 — effective trigger set.** Start from the workflow's own `on:` keys. If the
only key is `workflow_call`, the file is a callee: replace the set with the UNION of
the effective trigger sets of its local callers, resolved by scanning every
`.github/workflows/*.yml` for a job whose `uses:` is `./.github/workflows/<this
file>` and recursing (guard against cycles; depth is 2 in this tree). Verified call
edges: `ci.yml:506 → ci-quality.yml`, `claude-review.yml:90 →
claude-review-reusable.yml`.

Then intersect, in order, with the narrowing of the caller job's `if:`, this job's
`if:`, and the step's `if:`.

**Step 2 — `if:` narrowing (sound, conservative).** Split the condition into top-level
`&&` conjuncts at paren depth 0.
- A conjunct `github.event_name == 'X'` → intersect with `{X}`.
- A conjunct `github.event_name != 'X'` → remove `X`.
- A conjunct that is a parenthesised disjunction in which EVERY disjunct contains a
  `github.event_name == '...'` term → intersect with the union of those names.
- Anything else → no narrowing.

Never widen. This is sound because `A && event_name == 'x'` cannot be true off `x`,
whatever `A` is. Real anchors in this tree:
- `ci.yml:592` — `needs.initialize.outputs.is_bot != 'true' && github.event_name ==
  'pull_request'`. A `needs.` conjunct beside an event equality; narrows to
  `{pull_request}`. **Without this rule the gate emits a false positive on
  `ci.yml:673`, which is already correct.**
- `ci-quality.yml:514` — same shape, narrows `quality-branch` to `{pull_request}`;
  covers `ci-quality.yml:538`.
- `claude-review.yml:70-88` — a three-way parenthesised disjunction, every disjunct
  containing an event equality; narrows to `{workflow_run, pull_request,
  workflow_dispatch}`, i.e. no loss, which is what made the original bug reachable.
- `ci-quality.yml:634` — `inputs.is_bot != 'true' && (github.event_name ==
  'pull_request' || github.ref == 'refs/heads/main')`. One disjunct is NOT an event
  test, so no narrowing. Handled by the exemption below instead.
- `ci-quality.yml:690` and `ci.yml:495-496` — `inputs.is_bot`/`full_suite` only; no
  narrowing, which is why the three `quality-code` sites are findings.

**Step 3 — clause coverage.** Split the expression on `||` inside `${{ ... }}` and map
each clause to the events on which it is non-empty:

| clause shape | non-empty on |
| --- | --- |
| `github.event.pull_request.*` | `pull_request`, `pull_request_target`, `pull_request_review`, `pull_request_review_comment` |
| `github.event.workflow_run.*` | `workflow_run` |
| `github.event.issue.*` | `issue_comment`, `issues` |
| `github.event.comment.*` | `issue_comment`, `pull_request_review_comment` |
| `github.head_ref`, `github.base_ref` | `pull_request`, `pull_request_target` |
| `github.ref_name`, `github.ref`, `github.sha`, `github.repository`, `github.run_id`, `github.event_name`, `github.actor` | ALL |
| a quoted literal, or `format(...)` | ALL |
| `github.event.inputs.<n>` | `workflow_dispatch` |
| `inputs.<n>` | `workflow_dispatch` if declared under `on.workflow_dispatch.inputs`; for a callee, the triggers on which each caller's `with: <n>:` value is itself provably non-empty (recurse), else UNKNOWN |
| anything else (`env.*`, `steps.*`, `needs.*`, `secrets.*`, a function call) | UNKNOWN |

A single UNKNOWN clause marks the whole expression covered on every trigger and emits
nothing. Unknowns are counted and printed in the success line, so the gate cannot go
quiet by failing to understand its corpus.

**A finding is: a trigger in the effective set with no covering clause.** Report
`file:line`, the step name, the uncovered trigger(s), and the expression.

**Explicit non-goal, state it in the docstring.** This proves NON-EMPTINESS, not
CORRECTNESS. `github.ref_name` makes any expression trivially covered on every
trigger; on a `pull_request` event it is `<n>/merge`, not a branch. That is fine here
because it is always LAST in these chains and the event-scoped clause wins first — but
the gate cannot check that, and a plan that pretends otherwise is worse than one that
names the hole.

## Avoiding false positives

Two exemptions beyond `if:` narrowing, each grounded in a reader that really behaves
this way:

**E1 — the step hands the reader `github.event_name`.** If any value in the step's
`env:` block is exactly `${{ github.event_name }}`, the reader branches on the event
and takes a different resolution path on the triggers the expression does not cover.
Static trigger coverage is then not a defect predicate. Anchors:
- `.ci/rediacc_ci/quality/branch.py:219` returns early unless `GITHUB_EVENT_NAME ==
  'pull_request'`; its step is `ci-quality.yml:536-540`.
- `ci-quality.yml:663-668` passes `GITHUB_EVENT_NAME` beside an empty-on-push
  `github.head_ref`; this is what keeps `ci-quality.yml:665` silent, since its job
  `if:` (`:634`) does not narrow.
- `review-status.yml:105` (`EVENT_NAME: ${{ github.event_name }}`) →
  `.ci/scripts/review/review-status.sh:148` `case "${EVENT_NAME:-}"`, whose
  `workflow_run` arm resolves the PR from `WR_RUN_ID` and an artifact instead.
- `claude-review-reusable.yml:282` → `.ci/scripts/review/claude-review-gate.sh:782`,
  the same shape.

**E2 — `if:` narrowing** (Step 2 above), whose load-bearing anchor is `ci.yml:673`.

**Deliberately NOT an exemption: a waiver comment.** House rule is never to suppress a
gate to get past it. The two honest fixes are a covering clause or a narrowing `if:`,
and both are cheap; a marker would only preserve the ambiguity this gate exists to end.

**Expected verdict on the real tree, before any fix:** three findings
(`ci-quality.yml:1114`, `:1121`, `:2200`), zero false positives, and the historical
`claude-review-reusable.yml:139` would have fired pre-`f1ce6911f` and is silent after.

## The three live findings, and their fixes

`ci-quality.yml` is `workflow_call`-only; its sole caller is `ci.yml:506`, whose `on:`
(`ci.yml:3-30`) declares `push` (branches `[main]`), `pull_request`, `schedule`, and
`workflow_dispatch` (documented at `:17-18` as the nightly rehearsal, guarded to main).
Neither the calling job's `if:` (`ci.yml:495+`) nor `quality-code`'s (`ci-quality.yml:690`)
narrows by event. So on push/schedule/dispatch all three expressions are empty.

These are the MILDER shape the fixed bug was not: nothing hard-refuses, so nothing goes
red. `check-pr-epic-block.ts:134-147` and `check-pr-task-trailers.ts:439-451` both fall
through to `git branch --show-current` and then print `skipped: on an unknown branch`.
The workflow's own comment at `ci-quality.yml:1109-1113` already says so in prose. The
class is identical; only the failure mode differs, and a gate that catches one shape and
not the other leaves half the class live.

**`:1114` and `:1121` — add `|| github.ref_name`.** Same one-clause remedy as
`f1ce6911f`, and it is genuinely better than the status quo: on every non-`pull_request`
trigger `ci.yml` runs against `main`, so the clause resolves to `main`, and both readers
already special-case `branch === 'main'` with `skipped: on main; the epic block is a PR
artefact`. The skip becomes an HONEST skip with the right reason instead of an
indistinguishable-from-broken one. On `pull_request` the first clause wins, so
`github.ref_name`'s `<n>/merge` value can never shadow it.

This also retires a sibling without touching it: `PR_BASE_REF:
origin/${{ github.event.pull_request.base.ref }}` (`manifest.ts:1031`) evaluates to the
literal `origin/` on push — non-empty garbage. With the `main` skip taken first, that
value is never reached.

Narrowing the steps with `if: github.event_name == 'pull_request'` is the alternative.
It is NOT recommended as the primary: both steps are `emit: false` hand-written steps
(their headers' `blocker:` at `check-pr-epic-block.ts:30-37` and
`check-pr-task-trailers.ts:35-38` explain why), so `when:`
(`scripts/lib/gate-header.ts:103`) does not reach them, and a newly-skipping step
interacts with `check:ci-gate-skip-announcer` /
`.ci/scripts/quality/announce-gate-skips.sh`. One clause avoids all of it.

**`:2200` — DELETE the env key.** `check:ci-quality-gates` is the pytest battery
(`package.json:152` → `.ci/rediacc_ci/battery.py`). Nothing under `.ci/rediacc_ci/`
reads `PR_HEAD_REF` from the ambient environment — the only two modules that mention it
SCRUB it: `.ci/rediacc_ci/tests/test_review_discover_epics.py:52-61` replaces the whole
environment precisely because "a differential that inherits the developer's environment
passes or fails depending on whether PR_HEAD_REF ... happen to be exported, and both are
exported in CI", and `.ci/rediacc_ci/tests/gates/test_gate_untagged_commit_branch.py:38`
says the same. `test_gate_review_status.py:1831` and
`.ci/scripts/test/gates/test-review-status.sh:1207` each set their own value per call.
So this key is dead, and it is the exact ambient-environment leak two test modules were
written to defend against. Adding a fallback clause to it would be the wrong fix.

**Parity, because the expression lives in more than one place.** For `:1114`/`:1121`
the value is declared THREE times — the gate header (`check-pr-epic-block.ts:40`,
`check-pr-task-trailers.ts:42`), `manifest.ts:1032`/`:1081`, and the workflow — and
`scripts/gates/check-ci-step-env-parity.ts` enforces workflow ↔ lock in both directions
including value-drift. Edit all three and regenerate `gates.lock.json`, or the fix
trades one red for another. `:2200` has no gate-header file (leaf is `battery.py`), so
it is `manifest.ts:5048` + the workflow + the lock.

## Scope: stay PR_HEAD_REF-specific. Recommendation, with evidence.

`grep -rn "github\.event\.[a-z_.]* *||" .github/workflows/*.yml` returns nine sites.
Classified:

- **Four are `concurrency.group`** — `autopilot.yml:131`, `claude-mention.yml:24`,
  `claude-review.yml:63`, `review-status.yml:57-62`. No script reads them, and each
  either ends in a universal fallback (`github.run_id`, `format('dispatch-{0}', ...)`)
  or already covers every declared trigger. `claude-mention.yml:24`
  (`github.event.issue.number || github.event.pull_request.number` against triggers
  `issue_comment`, `pull_request_review_comment`) is a clean real-corpus SILENT case and
  is worth keeping as a control fixture, not as a subject.
- **One is a checkout input** — `claude-review-reusable.yml:76`, `ref:`, two clauses
  against three effective triggers. It IS uncovered on `workflow_dispatch`, but an empty
  `ref:` is MEANINGFUL to `actions/checkout` (it falls back to the workflow's own ref,
  which on that dispatch is the right branch). "Resolves empty" is therefore not a
  defect predicate for `with:` inputs; modelling it needs per-action input semantics.
  Out of scope. Worth one line in the gate's docstring so the next reader does not
  re-derive it.
- **Two are `PR_NUMBER`, and both would be FALSE POSITIVES.**
  `review-status.yml:114` (`pull_request.number || issue.number || inputs.pr_number`
  against five triggers) is uncovered on `workflow_run` BY DESIGN:
  `review-status.sh:148-205` takes the `WR_RUN_ID` + `review-target` artifact path on
  that event, and its comment explains at length why the SHA/number cannot be used
  there. `claude-review-reusable.yml:289` is uncovered on `workflow_run` and
  `pull_request` (`claude-review.yml:90` passes `pr_number: ${{ inputs.pr_number || ''
  }}`, empty on both), and `claude-review-gate.sh:782` `case`s on `EVENT_NAME` for the
  same reason. That is **2 false positives out of 2 candidate `PR_NUMBER` sites — a
  100% noise rate on the one variable the generalisation would add.** Exemption E1 does
  catch both, so the generalisation is not unsafe — it is simply all cost and no yield.

The asymmetry is structural, not accidental. Every `PR_HEAD_REF` reader resolves the
value the SAME way on every event — env, then `GITHUB_HEAD_REF`, then `git branch
--show-current` (`check-pr-epic-block.ts:134-141`, `check-pr-task-trailers.ts:439-446`,
`check-review-report-replies.sh:85`, `discover-epics.sh:23`). That uniformity is exactly
what makes "empty on this trigger" a sound defect predicate. `PR_NUMBER`'s readers do
not have it. Generalising would mean statically reading a `case` over `$EVENT_NAME`
inside a shell script — an order of magnitude more machinery than the bug costs.

**Recommendation: keep the variable set at `{PR_HEAD_REF, GITHUB_HEAD_REF}`** — the
family the gate already knows and already has reader-side patterns for (`:67-68`,
`:75`). Write the event→context table, the `if:` narrower and the caller-chain trigger
resolver as separately named, separately controlled functions so a second variable is a
name plus an exemption rule, and say in the docstring that `PR_NUMBER` was measured and
deliberately excluded, with the two sites named. Broader here is not better; it is two
findings, both wrong.

## Test design

All of it goes in `controls()` (`:161`), the convention this gate already has, running
before any real judgement, each failure through `fail()` (`:155`). Fixtures are
`tempfile.TemporaryDirectory()` workflow files — no real-tree mutation.

**Planted defect (must FIRE).** A callee with `on: {workflow_call:}` and a step setting
`PR_HEAD_REF: ${{ github.event.pull_request.head.ref || github.event.workflow_run.head_branch }}`,
plus a caller whose `on:` declares `pull_request`, `workflow_run` and
`workflow_dispatch` and whose calling job's `if:` admits all three. This is
`claude-review-reusable.yml` as it stood at `f1ce6911f^`, byte-shaped. The control
asserts the finding names `workflow_dispatch` specifically — not merely that something
fired, because a gate that fires with the wrong reason is how the next reader is sent to
the wrong file.

**Fixed form (must stay SILENT).** The same pair with `|| github.ref_name` appended:
`f1ce6911f` as landed.

**Silent controls, one per exemption route, so no route can rot unobserved:**
1. Step-level/job-level `if:` — `needs.x.outputs.y != 'true' && github.event_name ==
   'pull_request'` guarding a `pull_request.head.ref`-only setter, against a four-trigger
   workflow. Models `ci.yml:592`/`:673`. **This one is mandatory: without the narrower,
   the gate emits a false positive on an already-correct site.**
2. `github.event_name` in the step's env (E1) — a `github.head_ref`-only setter beside
   `GITHUB_EVENT_NAME: ${{ github.event_name }}`, against a two-trigger workflow whose
   `if:` does not narrow. Models `ci-quality.yml:663-668`.
3. A parenthesised disjunction whose disjuncts are all event equalities, narrowing to
   exactly the covered set. Models `claude-review.yml:70-88`.
4. An UNKNOWN clause (`env.SOMETHING`) — must be counted as covered and reported in the
   unknown tally, proving the conservative arm is taken rather than silently skipped.

**Negative control on the narrower itself (must FIRE).** `(github.event_name ==
'pull_request' || github.ref == 'refs/heads/main')` — one disjunct is not an event test,
so the narrower must refuse to narrow. Models `ci-quality.yml:634`; without this control
the narrower could over-narrow and silence real findings. Pair it with E1 to show the
real site is exempt for the right reason.

**Parser controls.** Assert `doc.get(True)` is what carries `on:` for a real
PyYAML-parsed workflow, so the `True`-key trap is asserted rather than remembered; and
assert the caller-chain resolver finds `ci.yml` as `ci-quality.yml`'s caller on the real
tree.

**Vacuity floors, which also drains a baseline entry.**
`.ci/scripts/quality/check_pr_head_ref_completeness.py` is listed in
`scripts/data/enumeration-vacuity-baseline.json:13` as an unguarded enumerating check —
its `len(readers) < 2` at `:226` is a real floor that
`scripts/gates/check-enumeration-vacuity.ts:22-23` cannot recognise (it wants a named
`MIN_*`, an explicit empty refusal, or the word `VACUOUS`). Rename it `MIN_READERS = 2`
and add `MIN_SETTER_STEPS = 6` for the new corpus (seven exist today), then remove the
entry from that shrink-only list.

## Tasks

- [ ] Add the event→context coverage table and `clause_events(expr)` to
      `.ci/scripts/quality/check_pr_head_ref_completeness.py`, with UNKNOWN returning
      "covers everything" and being counted.
- [ ] Add `narrow_by_if(triggers, condition)` implementing the four conjunct rules;
      never widen.
- [ ] Add `workflow_triggers(path)` reading `doc.get(True) or doc.get("on")`, with
      caller-chain resolution for `workflow_call`-only files via `uses:
      ./.github/workflows/<name>` and a cycle guard.
- [ ] Add `find_setter_steps()` enumerating every step whose `env:` carries
      `PR_HEAD_REF` or `GITHUB_HEAD_REF`, with `file:line` for the reporting.
- [ ] Add exemption E1 (`${{ github.event_name }}` present as a value in the step's
      `env:`), with the four real anchors named in a comment.
- [ ] Wire CHECK 2 into `main()` alongside CHECK 1, with separate offender lists and a
      success line that prints both counts plus the UNKNOWN tally.
- [ ] Rename the floor to `MIN_READERS = 2`, add `MIN_SETTER_STEPS = 6`, remove
      `.ci/scripts/quality/check_pr_head_ref_completeness.py` from
      `scripts/data/enumeration-vacuity-baseline.json:13`.
- [ ] Extend `controls()` with the planted defect, the fixed form, the four silent
      controls, the narrower negative control, and the two parser controls.
- [ ] Rewrite the module docstring: what CHECK 2 asserts, why the `LOUD_FAILURE`
      exemption is right for CHECK 1 and absent from CHECK 2, the non-emptiness-not-
      correctness non-goal, and the measured `PR_NUMBER` exclusion with both sites named.
- [ ] Fix `ci-quality.yml:1114` — append `|| github.ref_name`, matching
      `check-pr-epic-block.ts:40` and `manifest.ts:1081`, with a comment citing
      `f1ce6911f`.
- [ ] Fix `ci-quality.yml:1121` — same, matching `check-pr-task-trailers.ts:42` and
      `manifest.ts:1032`.
- [ ] Delete `PR_HEAD_REF` from `ci-quality.yml:2200` and `manifest.ts:5048`; note in
      the commit that nothing under `.ci/rediacc_ci/` reads it and two test modules
      scrub it.
- [ ] Regenerate `scripts/ci-runner/gates.lock.json` and run
      `npm run check:ci-step-env-parity` plus `npm run check:ci-parity`.
- [ ] Run `npm run check:ci-pr-head-ref-completeness` and confirm: three findings before
      the workflow fixes, zero after, and the unknown tally is non-silent.
- [ ] Confirm `npm run check:ci-enumeration-vacuity` accepts the drained baseline entry.

## Notes for the implementer

PR-TASK: e87fa3ce — this widening rides the same epic as `f1ce6911f`, the one-line
unblock that exposed the blind spot. Use that trailer on every commit here.

Two traps worth restating because both have already cost a session:
- PyYAML parses `on:` as the boolean `True`. Verified today on `ci.yml`.
- A path-segment exclusion set matches ANY segment. `EXCLUDE_DIR_PARTS` at `:65` once
  carried `"gates"` and silently blinded this gate to `scripts/gates/` — both of its
  own founding motivating cases — since the day it was written
  (`docs/ci-overhaul/07-tooling-decisions.md:39`, T-11). CHECK 2's corpus does not use
  that set at all; keep it that way.
