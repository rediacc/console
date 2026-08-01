# PLAN: Claude Review trigger reliability -- workflow_dispatch head-SHA gap, not workflow_run non-delivery
Status: done
Owner: review-trigger-plan agent, branch 0731-2
Updated: 2026-08-01

## Headline conclusion (read this before the rest)

The finding brief assumed `workflow_run` never fires for PR #550's Console CI
completions. **Live verification does not support that.** `workflow_run`
fires reliably, with ~2-7 minute latency measured from the moment Console
CI's own `CI Complete` check actually turns green (not from the run's
`createdAt`, which is when the run was *queued* -- Console CI on this branch
runs 50-70 minutes wall-clock, and comparing Claude Review timestamps against
`createdAt` instead of the real completion time is what made the trigger look
dead in the initiating investigation).

Three real, verified problems exist, none of which is "the primary trigger
does not fire":

1. **CONFIRMED, structural, small fix (do this).** A `workflow_dispatch`-invoked
   `Claude Review` run's own `head_sha` (and therefore
   `github.event.workflow_run.head_sha` in the downstream `review-status.yml`
   listener) is the ref it was dispatched against (`main`), never the PR
   head. `review-status.sh` resolves the PR via
   `commits/${WR_HEAD_SHA}/pulls`, which fails for a dispatch-sourced
   completion, so `review-status.yml` silently no-ops
   (`.ci/scripts/review/review-status.sh:146-149`, "no open PR for ...;
   nothing to report") every time the manual escape hatch is used. This is
   exactly why the session has had to post a throwaway PR comment after every
   `workflow_dispatch` call, as documented in `claude-review.yml`'s own
   header. Confirmed live below.

2. **Real but not a trigger bug: a hygiene failure reads as "no review
   happened."** `Review Complete` can (and did, repeatedly, on this PR) go
   `failure` even when the current head genuinely *was* reviewed, because
   `check-review-report-replies.sh` requires a human reply to the newest
   review report. The failure text already names the report and gives the
   exact `gh` command, but the *check-run title* ("Review is not complete for
   this head") reads identically whether nothing was ever reviewed or a
   review completed five minutes ago and nobody replied yet. That ambiguity
   is a very plausible reason the operator kept re-dispatching a pipeline
   that had already done its job.

3. **Speculative, not confirmed: concurrency cancellation.** `claude-review.yml`'s
   concurrency group is keyed only by `head_branch`
   (`claude-review-${{ github.event.workflow_run.head_branch || ... }}`),
   with `cancel-in-progress: true`. A later trigger whose *own* job will end
   up `if:`-skipped (e.g. a `workflow_run` event from a `cancelled`-conclusion
   Console CI re-run) still enters the same concurrency group and would
   cancel a real, in-progress review for an earlier, still-current push. I
   could not find a job that was actually cancelled mid-review in the sample
   pulled (every sampled `review` job that didn't run to completion was
   `skipped`, not `cancelled` mid-flight) -- so treat this as a plausible
   contributing factor on a fast-push PR, not a proven defect. Worth a
   narrow, low-risk improvement (scope the group by something that
   distinguishes "this trigger will actually run the review" from "this
   trigger's job is a guaranteed no-op"), not a rewrite.

**Recommendation on the brief's three candidate directions:** skip (a) (a
redundant `pull_request: [synchronize]` trigger) entirely -- it solves a
problem that the evidence does not show is happening, and it reintroduces
exactly the "reviews before CI is green" risk the file's header already
argues against. Do (c) (thread the real PR through the dispatch path) as the
primary fix -- it is the one confirmed defect. Add a narrow, low-cost version
of (b) (a reconciliation poller) as a genuine safety net for the residual
risk that GitHub's `workflow_run` delivery has a rare miss (a documented,
if uncommon, platform behavior independent of this repo's YAML) or that item
3 above turns out to be real under sustained fast pushes -- scoped to detect
"CI is green on the current head and there has never been a Review Complete
check-run of any conclusion for it," which cannot false-positive on the
hygiene case in problem 2.

---

## Verified live

All commands run against `rediacc/console`, branch `0731-2` / PR #550, on
2026-08-01 starting ~06:00Z. Real output pasted, not paraphrased.

### V1. Console CI run history for the PR branch (initial read -- later shown to be time-mismatched, see V6)

```
$ gh run list --repo rediacc/console --branch 0731-2 --workflow ci.yml -L 20 \
    --json databaseId,conclusion,event,createdAt,headSha,status
```
Returned 14 runs, `createdAt` ranging 2026-07-31T11:44:46Z to
2026-08-01T06:03:01Z, mixing `success` and `cancelled` conclusions. This
field is when the run was *queued*, not when it finished -- see V6.

### V2. Claude Review's own run list

```
$ gh run list --repo rediacc/console --workflow "Claude Review" -L 30 \
    --json databaseId,headSha,event,createdAt,status,conclusion
```
Showed `headSha` as `77e7a6ef4baed947bbb55c2ece97664c955c8d68` (or a few
other values) on almost every entry, `workflow_run` and `workflow_dispatch`
alike, none matching any PR-branch CI `headSha` from V1. This is the
observation the initiating brief read as "workflow_run never fires for the
PR branch." It does not mean that -- see V3.

### V3. Why V2's headSha is not evidence of anything

```
$ gh api repos/rediacc/console/actions/runs/30658744756 \
    --jq '{id, head_sha, head_branch, event, status, conclusion, name, run_attempt, created_at}'
{"conclusion":"success","created_at":"2026-07-31T19:20:57Z","event":"workflow_run",
 "head_branch":"main","head_sha":"77e7a6ef4baed947bbb55c2ece97664c955c8d68",
 "id":30658744756,"name":"Claude Review","run_attempt":1,"status":"completed"}
```
Fetched GitHub's own docs for the `workflow_run` event
(`https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_run`):

> `GITHUB_SHA` is set to the last commit on the default branch. `GITHUB_REF`
> points to the default branch.

This is documented, universal behavior for **every** `workflow_run`-triggered
run, regardless of which branch's source workflow triggered it. The run's own
top-level `head_sha`/`head_branch` API fields always read "main" for a
`workflow_run`-triggered run. Comparing them against a PR branch's CI SHAs
(as V2 does) can never show a match, firing or not. **This single fact
invalidates the "zero automatic entries" reading of V2.**

### V4. A second listener proves nothing about delivery either way by the same flawed method, but confirms the pattern is universal, not claude-review.yml-specific

`autopilot.yml` also declares `workflow_run: { workflows: ["Console CI",
"Claude Review"] }`. Its run list shows the identical
`head_branch: "main"` pattern on every entry
(`gh api "repos/rediacc/console/actions/workflows/autopilot.yml/runs?per_page=30"`).
This rules out "claude-review.yml's YAML specifically mismatches something"
(e.g. a workflow `name:` drift) as the cause, since a second, independently
written workflow shows the exact same top-level metadata shape. Confirmed
directly: `ci.yml`'s `name:` field reads `Console CI` identically on
`origin/0731-2`, `origin/main`, and the local working tree (`git show
origin/<branch>:.github/workflows/ci.yml | head -5`, all three identical) --
so a workflow-name mismatch, the other classic cause of `workflow_run`
silently not matching, is ruled out too.

### V5. Check-runs on real PR-branch commits show reviews actually happening

```
$ gh api repos/rediacc/console/commits/0ded390cb052368b9656f1ae580e4c6e41796e6b/check-runs \
    --jq '.check_runs[] | {name, status, conclusion, started_at, completed_at}'
```
Includes (abridged):
```
{"name":"Claude","conclusion":"skipped", ...}          x2 (dedup: already reviewed)
{"name":"Review Status","conclusion":"cancelled", ...}  x3 (superseded by a newer head)
{"name":"Review Complete","conclusion":"failure","started_at":"2026-08-01T05:58:09Z", ...}
```
Full body of that `Review Complete` failure (`.output.summary`, verbatim):
```
PR #550 -- head `0ded390cb052368b9656f1ae580e4c6e41796e6b`, last reviewed `0ded390cb052368b9656f1ae580e4c6e41796e6b`.

## Failures

- `check-review-report-replies.sh` failed:

```
Checking review report replies for PR #550...
...
The newest automated review report has not been addressed:
  https://github.com/rediacc/console/pull/550#issuecomment-5150085038
...
```

## Context

- Currency: head `0ded390cb052368b9656f1ae580e4c6e41796e6b` is the reviewed SHA.
- Review reports posted: 3/5 (cap 5 for a 16552-line diff).
```
**"Currency: head ... is the reviewed SHA."** This head genuinely was
reviewed. The `failure` conclusion is entirely the unreplied-report hygiene
gate (problem 2 above), not a missing review.

For `9474720f4717b4849cd37b700a3055828d3abd8f` (a `cancelled`-conclusion CI
run, i.e. a superseded push): `Claude` job `skipped` at `04:16:37Z`/`04:16:38Z`,
`Review Status success` and `Review Complete failure` at `04:16:41Z`/`04:16:51Z`
-- **27-41 seconds** after that CI run's own `cancelled` completion. This is
the *correct* behavior (no review for a superseded/cancelled CI run) firing
fast, not a delivery failure.

### V6. Real trigger-to-review latency, measured correctly (CI-Complete-green time, not run-createdAt)

Review report comments on PR #550
(`gh api repos/rediacc/console/issues/550/comments --paginate --jq '.[] | select(.body | startswith("**Claude finished")) | {id, created_at, body}'`):

| Commit | `CI Complete` check green at | First review report posted at | Latency |
|---|---|---|---|
| `5440e49a` | 2026-07-31T21:29:32Z | 2026-07-31T21:36:19Z | ~7 min |
| `0ded390c` | 2026-08-01T05:51:51Z | 2026-08-01T05:57:18Z | ~5.5 min |
| `21586a38` (current head at investigation time) | 2026-08-01T06:56:07Z | 2026-08-01T06:58:18Z | ~2 min |

All three are consistent with a healthy, promptly-firing `workflow_run`
listener. (`cc55ca9e`'s review, by contrast, was triggered by the
`pull_request: [ready_for_review]` path, not `workflow_run` -- its own run
list entry shows `"event":"pull_request"`, `createdAt` matching the PR's
`ready_for_review` flip, not Console CI's completion -- so it is not a
`workflow_run` data point either way.)

Note the run-level `createdAt` field used in V1 for `0ded390c` was
`2026-08-01T04:54:01Z` -- that is when the run was *queued*, not when it
finished. Its `CI Complete` check (the actual completion signal
`workflow_run` fires on) did not go green until `05:51:51Z`, **57 minutes
later**. Console CI on this branch has heavy E2E/OPS/Docker matrix jobs; a
50-70 minute wall clock between "run queued" and "run's terminal check
green" is normal for this pipeline, and is very likely why the operator
believed several rounds had already "failed to fire" when the trigger simply
had not had anything to fire on yet.

### V7. The confirmed workflow_dispatch -> review-status.yml gap, live

```
$ gh api repos/rediacc/console/issues/comments/5146712466 --jq '{id, created_at, updated_at, body}'
{"body":"<!-- claude-reviewed: 21586a38dea09090d11aa85b2456ac407aec20b1 -->\nAutomated Claude review completed for commit 21586a3.\nCost: $0.9428 (claude-sonnet-5 7873out) | 30 turns | 2m16s\n...",
 "created_at":"2026-07-31T19:30:20Z","id":5146712466,"updated_at":"2026-08-01T06:59:32Z"}
```
The marker comment (upserted, same comment ID reused across heads) confirms
the current head `21586a38` was reviewed and the marker updated at
`06:59:32Z`. At that same moment:
```
$ gh api repos/rediacc/console/commits/21586a38dea09090d11aa85b2456ac407aec20b1/check-runs \
    --jq '.check_runs[] | select(.name=="Claude" or .name=="Review Status" or .name=="Review Complete")'
```
returned **nothing** -- no `Review Status` or `Review Complete` check-run
existed for the current head at all, despite the review having genuinely
completed. This run overlapped with a live `workflow_dispatch` invocation
(`gh run list --workflow "Claude Review"` showed a `workflow_dispatch` run
`in_progress` starting `06:56:31Z` alongside a `workflow_run` entry
`in_progress` at `06:56:10Z`, both against `head_branch: main`), consistent
with `claude-review-gate.sh`'s own documented behavior for the
`workflow_dispatch` path (`.ci/scripts/review/claude-review-gate.sh:403-413`):
it resolves `head_sha` correctly via `gh pr view "$pr" --json headRefOid`, so
the *review itself* and its marker land on the right commit -- but
`review-status.yml`'s `workflow_run` listener only ever sees
`github.event.workflow_run.head_sha` = the dispatch ref (`main`, per V3's
documented behavior), so its `commits/${WR_HEAD_SHA}/pulls` lookup
(`.ci/scripts/review/review-status.sh:133-135`) cannot resolve PR #550, and
the script exits at line 146-149 ("no open PR for ...; nothing to report")
without posting anything. This is the exact gap `claude-review.yml`'s header
already documents as needing the `issue_comment` workaround
(lines 17-25 of that file), now confirmed end-to-end against a live run
rather than assumed from the comment.

---

## The fix

### F1 (primary). Close the workflow_dispatch head-SHA gap by having the reusable workflow directly nudge `review-status.yml`, instead of relying on GitHub's `workflow_run` head_sha resolution for that path.

**File: `.github/workflows/review-status.yml`**

Add a `workflow_dispatch` trigger carrying a `pr_number` input, parallel to
`claude-review.yml`'s existing one:

```yaml
on:
  workflow_run:
    workflows: ["Claude Review"]
    types: [completed]
  pull_request_review:
    types: [submitted, dismissed]
  pull_request_review_comment:
    types: [created, edited, deleted]
  issue_comment:
    types: [created, edited, deleted]
  workflow_dispatch:
    inputs:
      pr_number:
        description: 'PR number to re-evaluate (used when the workflow_run entry point could not resolve the PR, e.g. after a Claude Review workflow_dispatch)'
        required: true
        type: string
```

Update the concurrency group (currently
`review-status-${{ github.event.workflow_run.head_branch || github.event.pull_request.number || github.event.issue.number }}`,
lines 43-47) to add the new source:

```yaml
concurrency:
  group: >-
    review-status-${{ github.event.workflow_run.head_branch
      || github.event.pull_request.number
      || github.event.issue.number
      || format('dispatch-{0}', inputs.pr_number) }}
  cancel-in-progress: true
```

Update the job-level `if:` (line 59-61) so `workflow_dispatch` is not
filtered out by the existing `issue_comment`-only guard (that guard is
irrelevant to `workflow_dispatch`, but the condition as written is `!=
'issue_comment' || ...`, which already passes for any other event name --
**no change needed here**, verify only).

Pass the new input through to the script (env block, lines 74-81): add
`PR_NUMBER: ${{ github.event.pull_request.number || github.event.issue.number || inputs.pr_number }}`.

**File: `.ci/scripts/review/review-status.sh`**

Extend the `EVENT_NAME` case statement (lines 126-144) so `workflow_dispatch`
resolves the PR the same way `pull_request_review` /
`pull_request_review_comment` / `issue_comment` already do (`pr="$PR_NUMBER"`,
`require_var PR_NUMBER`), since a dispatch always carries an explicit PR
number and needs no SHA-based lookup at all:

```bash
case "${EVENT_NAME:-}" in
    workflow_run)
        require_var WR_HEAD_SHA
        pr="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${WR_HEAD_SHA}/pulls" \
            --jq '[.[] | select(.state == "open")] | first | .number // empty')"
        ;;
    pull_request_review | pull_request_review_comment | issue_comment | workflow_dispatch)
        require_var PR_NUMBER
        pr="$PR_NUMBER"
        ;;
    *)
        log_error "Unsupported EVENT_NAME: ${EVENT_NAME:-unset}"
        exit 1
        ;;
esac
```

The rest of the script (currency check, hygiene checks, `post_check`) needs
no change -- it already re-reads the PR's live head SHA and posts against
that, regardless of how `pr` was resolved. Note the `workflow_run`-specific
branch at lines 216-225 (reading `WR_CONCLUSION` to flag a failed/timed-out
triggering run) must stay gated on `EVENT_NAME == workflow_run` exactly as
now -- a `workflow_dispatch` re-evaluation has no `WR_CONCLUSION` to read and
must not attempt to.

**File: `.github/workflows/claude-review-reusable.yml`**

Add a step after "Record reviewed SHA" (currently the last step, ends at
line 368-369) that, only for the `workflow_dispatch` entry point, tells
`review-status.yml` which PR to look at instead of leaving it to infer from
`workflow_run.head_sha`:

```yaml
      # workflow_dispatch's own head_sha (and therefore the head_sha that
      # review-status.yml would read off github.event.workflow_run.head_sha
      # once THIS run completes) is the ref it was dispatched against, never
      # the PR head -- documented GitHub Actions behavior, not a bug here.
      # review-status.yml's commits/.../pulls lookup finds nothing for that
      # SHA and silently no-ops. Tell it directly which PR to re-check
      # instead of relying on SHA inference for this one entry point.
      # Verified live 2026-08-01: PR #550's marker updated correctly on a
      # workflow_dispatch review, but no Review Status/Review Complete
      # check-run appeared until this was worked around by hand.
      - name: Nudge review-status.yml with the resolved PR
        if: always() && steps.gate.outputs.go == 'true' && github.event_name == 'workflow_dispatch'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh workflow run review-status.yml --repo rediacc/console --ref main \
            -f pr_number="${{ steps.gate.outputs.pr_number }}"
```

Use `always()` to match the "Record reviewed SHA" step immediately above it:
a spent attempt (no report posted) still deserves a re-evaluation, since the
budget/cap state changed even if the marker did not advance.

This directly replaces the manual "post a throwaway PR comment to fire
`issue_comment`" workaround with an automatic call, using the exact same
`workflow_dispatch`-with-`pr_number` shape `claude-review.yml` itself
already uses -- no new pattern introduced.

**Callers.** `claude-review-reusable.yml` is shared with the private
submodule repos (per its own header, "callable from console itself AND from
the private submodule repos"). Those callers do not set `required_check`
(the empty-string default, per the reusable's own comment at lines 10-15),
but the new step here does not depend on `required_check` at all -- it fires
for any `workflow_dispatch` completion regardless of caller. Confirm the
`gh workflow run review-status.yml --repo rediacc/console` call is
unconditionally scoped to `rediacc/console` (hardcoded, not
`github.repository`) since `review-status.yml` only exists in console, not
in the submodule repos -- a submodule caller invoking this reusable via
`workflow_dispatch` must still be able to nudge console's review-status,
not attempt to run a workflow that does not exist in its own repo. Verify
this against `github.repository` inside a submodule caller's context before
implementing (it will read `rediacc/account` or similar there, which is why
the target repo must stay hardcoded to `rediacc/console`).

### F2 (secondary, cheap, do alongside F1). Make a hygiene-only failure visually distinct from "never reviewed."

**File: `.ci/scripts/review/review-status.sh`**

In the verdict block (lines 317-326), when `currency_ok == true` but hygiene
produced failures (i.e. the head genuinely was reviewed but a hygiene script
failed), use a distinct title so the check-runs list itself communicates the
right next action without opening the summary:

```bash
conclusion="success"
title="Reviewed at the current head"
if ((${#failures[@]} > 0)); then
    conclusion="failure"
    if [[ "$currency_ok" == true ]]; then
        title="Reviewed, but needs attention (see failures)"
    else
        title="Review is not complete for this head"
    fi
elif ((${#warnings[@]} > 0)); then
    conclusion="success"
    title="Reviewed, with warnings"
fi
```

This is a pure string change with no behavioral effect on `conclusion` (still
`failure` either way -- correctly, since an unreplied report **should**
block, per the script's own design intent). It only changes what shows up in
the GitHub checks list, so a future push does not read a stale-looking
"review is not complete" title when the review is in fact complete and
waiting on a human reply.

### F3 (safety net, lower priority). A narrow reconciliation poller, scoped to avoid false positives against F2's legitimate hygiene-failure case.

Not urgent given F1 addresses the one confirmed structural gap and V6 shows
the primary trigger is healthy. Implement only if the operator wants
insurance against a genuine rare `workflow_run` delivery miss or an
unconfirmed concurrency-cancellation loss (problem 3). If built:

**File: `.github/workflows/review-status.yml`** (or a new small workflow --
implementer's judgment, but prefer extending this one over adding a fifth
workflow that also claims `Review Complete`, per the acyclicity test's own
enforcement, see T6 below) -- add:

```yaml
on:
  schedule:
    - cron: '37 */3 * * *'   # offset from autopilot's '17 */2 * * *' to avoid runner contention
```

New step, gated `if: github.event_name == 'schedule'`: list open PRs where
`CI Complete` is green on the current head AND there is **no**
`Review Complete` check-run of *any* conclusion for that head at all (a
`failure` conclusion already means F1/F2's machinery evaluated it --
skip those; the gap this closes is a head with `CI Complete` green and
zero `Review Complete` entries, meaning the pipeline plausibly never
even attempted it). For each such PR, call `gh workflow run
review-status.yml --ref main -f pr_number=<n>` using the exact `workflow_dispatch`
path built in F1 -- this reuses F1's code, it does not add a second one.

**Do not** build this as a call into `claude-review.yml` (that would
re-trigger a full review pass, burning review budget on every sweep); it
should only re-run `review-status.yml`'s own currency/hygiene check, which
is idempotent and free.

---

## Tests to add

Extend `.ci/scripts/test/gates/test-review-status.sh` in place -- same fake
`gh`, same fixture shape, same `setup()`/`with_temp_dir` harness already
there. Every new behavior gets a FIRE case (the defect, planted, must
produce the new/changed result) and a CONTROL case (the surrounding healthy
behavior must be unaffected), per the file's own existing convention (see
`test_stale_head_fails` vs `test_current_head_succeeds` as the paired
example already in the suite).

### T1. `workflow_dispatch` resolves the PR directly (FIRE: the gap F1 closes)

```bash
test_workflow_dispatch_resolves_pr_directly() {
    local t="$1"
    setup "$t"
    # No commit-pulls fixture entry needed at all for this path -- the whole
    # point is EVENT_NAME=workflow_dispatch must never call commits/.../pulls.
    echo '[]' >"$t/fixtures/commit-pulls.json"
    run_status "$t" EVENT_NAME=workflow_dispatch PR_NUMBER=42
    assert_exit_code 0 "$LAST_RC" "workflow_dispatch must resolve without a commit->PR lookup"
    assert_eq "$(posted "$t" '.conclusion')" success "current marker + clean hygiene, same as any other entry point"
    assert_eq "$(posted "$t" '.head_sha')" "$NEW_SHA" "check-run anchored to the PR's live head, not any dispatch ref"
    log_pass "workflow_dispatch (PLANTED: empty commit-pulls) still resolves PR #42 via PR_NUMBER"
}
```

### T2. PLANTED DEFECT PROOF: before F1, a workflow_run event carrying the dispatch ref's SHA (not the PR head) silently no-ops -- this is the exact bug reproduced

```bash
test_workflow_run_with_unassociated_sha_reports_nothing() {
    local t="$1"
    setup "$t"
    # The dispatch ref's SHA belongs to no open PR -- commits/.../pulls returns [].
    echo '[]' >"$t/fixtures/commit-pulls.json"
    local MAIN_SHA="3333333333333333333333333333333333333333"
    run_status "$t" EVENT_NAME=workflow_run WR_HEAD_SHA="$MAIN_SHA" WR_CONCLUSION=success \
        WR_HTML_URL=https://example.invalid/run/dispatch
    assert_exit_code 0 "$LAST_RC" "an unresolvable PR is a no-op, not an error"
    assert_eq "$(captured_method "$t")" "" "nothing is posted when workflow_run's head_sha resolves to no PR"
    log_pass "CONTROL: workflow_run path genuinely cannot resolve a dispatch-ref SHA (this is why F1 adds a separate workflow_dispatch path rather than 'fixing' this lookup)"
}
```
This is the CONTROL half proving the defect is real and is not something a
future edit accidentally already fixed inside the `workflow_run` branch --
if this test ever starts posting something, F1's premise (this path
structurally cannot work for a dispatch-sourced SHA) needs re-checking.

### T3. `workflow_dispatch` requires `PR_NUMBER` (anti-vacuity, mirrors the existing pattern at lines 379 / `require_var`)

```bash
test_workflow_dispatch_requires_pr_number() {
    local t="$1"
    setup "$t"
    run_status "$t" EVENT_NAME=workflow_dispatch
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "workflow_dispatch without PR_NUMBER must abort, not silently report nothing"
    fi
    assert_contains "$LAST_OUT" "PR_NUMBER" "the abort names the missing var"
    log_pass "PLANTED missing PR_NUMBER on workflow_dispatch => hard exit"
}
```

### T4. F2's title distinction (FIRE: reviewed-but-hygiene-failed vs CONTROL: never-reviewed)

```bash
test_hygiene_only_failure_title_says_reviewed() {
    local t="$1"
    setup "$t"   # marker already on NEW_SHA (current head) by default
    write_hygiene "$t" 0 1 0   # check-review-comments.sh fails; currency stays true
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "hygiene failure still fails the check"
    assert_eq "$(posted "$t" '.output.title')" "Reviewed, but needs attention (see failures)" \
        "title distinguishes a reviewed-but-unaddressed head from a never-reviewed one"
    log_pass "PLANTED hygiene failure on a CURRENT-head PR => title says 'Reviewed, but needs attention'"
}

test_unreviewed_head_title_unchanged() {
    local t="$1"
    setup "$t"
    echo '[]' >"$t/fixtures/comments.json"   # CONTROL: no marker at all
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "still fails"
    assert_eq "$(posted "$t" '.output.title')" "Review is not complete for this head" \
        "CONTROL: a genuinely unreviewed head keeps the original title"
    log_pass "CONTROL: unreviewed head keeps 'Review is not complete for this head', unaffected by F2"
}
```

### T5. Workflow-syntax assertions (extend `test_workflow_does_not_trigger_on_pull_request`, or add a sibling)

```bash
test_review_status_has_workflow_dispatch_with_pr_number() {
    local wf="$REPO_ROOT/.github/workflows/review-status.yml"
    grep -qE '^  workflow_dispatch:[[:space:]]*$' "$wf" ||
        log_fail "review-status.yml lost its workflow_dispatch trigger"
    grep -q "pr_number:" "$wf" ||
        log_fail "review-status.yml's workflow_dispatch has no pr_number input"
    log_pass "review-status.yml declares workflow_dispatch with a pr_number input"
}
```
Pair with a CONTROL re-run of `test_workflow_does_not_trigger_on_pull_request`
unmodified -- it must still pass after F1, proving the new trigger did not
also add a `pull_request` trigger by accident (the two are easy to conflate
when editing the `on:` block by hand).

### T6. Acyclicity control stays green (no new test, but MUST verify)

`test_no_ci_job_references_review_complete` (lines 506-572) already greps
every workflow file for `Review Complete` outside `review-status.yml` and
its two documented `watchdog-monitor.yml` exceptions. F1 adds no new
reference to that context string anywhere, so this existing test is the
regression control for F1/F2 -- run it, do not skip it, and do not add any
`needs:`/`if:` coupling on `Review Complete` while implementing F1's new
step in `claude-review-reusable.yml`.

### T7 (only if F3 is built). Poller does not re-fire on a legitimate hygiene failure

```bash
# Pseudocode for whatever script/step implements F3's sweep -- exact shape
# depends on where F3 lands (new script vs inline step). The property to
# prove either way:
test_poller_skips_pr_with_existing_review_complete_of_any_conclusion() {
    # PLANTED: a PR whose current head has a Review Complete check-run with
    # conclusion=failure (a real hygiene failure, F2's case). The poller must
    # NOT re-dispatch it -- re-dispatching would burn review budget for
    # nothing, since the marker already proves the head was reviewed.
    :
}
test_poller_dispatches_pr_with_green_ci_and_no_review_complete_at_all() {
    # CONTROL: a PR whose current head has CI Complete green and zero
    # Review Complete check-runs of any conclusion. This is the actual gap
    # F3 exists to close.
    :
}
```

---

## Implementer notes

- F1 is the only piece with cross-repo blast radius (the reusable workflow
  is shared with submodule callers) -- read `claude-review-reusable.yml`'s
  own header again before touching it; the ordering invariants documented
  there (workspace-root-first checkout, `TRACK_PROGRESS` forced false,
  `persist-credentials: false` on the PR-head checkout) are unrelated to
  this fix and must not be disturbed by adding a step after "Record reviewed
  SHA".
- `MAX_REVIEWS_PER_PR` / `review_cap_for()` in `.ci/scripts/lib/common.sh`
  are unrelated to this fix; do not touch them.
- Every file:line reference above was checked against the tree at
  `/home/muhammed/monorepo/console` on branch `0731-2` as of this plan's
  `Updated:` date. Re-verify line numbers before editing if other work has
  landed on `review-status.yml`, `review-status.sh`, or
  `claude-review-reusable.yml` in the meantime -- this PR (#550) has had
  five rounds of pushes in under a day, so drift is likely.
- Do not implement F3 unless the operator asks for it; F1+F2 already close
  every confirmed defect. Flag F3 as available but not built, with the
  reasoning above (no confirmed delivery-miss found, only a plausible
  concurrency-cancellation risk that a fast-push PR like this one could
  still exercise).

## Status

F1 and F2 implemented as specified: `review-status.yml` gained the
`workflow_dispatch` trigger with `pr_number`, the concurrency group's
`dispatch-{0}` fallback, and the `PR_NUMBER` env passthrough;
`review-status.sh`'s case statement resolves `workflow_dispatch` via
`PR_NUMBER` alongside the existing comment/review events; and
`claude-review-reusable.yml` gained the "Nudge review-status.yml with the
resolved PR" step, hardcoded to `rediacc/console` per the plan's caller note.
F2's title split (`Reviewed, but needs attention (see failures)` vs `Review
is not complete for this head`) landed in the verdict block. T1-T6 added to
`test-review-status.sh` (T1-T3 for F1, T4 for F2, T5 for the workflow-syntax
assertion, T6 re-verified unmodified); full suite 27/27 green, including the
acyclicity control (T6), which caught and forced a reword of one of this
fix's own comments that had accidentally repeated the literal string
`Review Complete` -- a live proof the gate still fires on real drift.
shellcheck/shfmt/actionlint/check-workflows.sh all clean. F3 not built, per
the plan's own instruction not to build it unless asked.
