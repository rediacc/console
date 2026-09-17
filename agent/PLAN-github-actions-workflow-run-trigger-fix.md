# PLAN: Claude Review trigger reliability -- workflow_dispatch head-SHA gap, not workflow_run non-delivery
Status: compacted
Owner: review-trigger-plan agent, branch 0731-2
Full-Text: f7a5351a9 agent/PLAN-github-actions-workflow-run-trigger-fix.md
Full-Text-Blob: 5a72b31733f38380ee001b6361fbfba1b40657e5
Record-Sig: 87e086b4

## Why
The brief assumed `workflow_run` never fired for Console CI completions on PR #550. Live verification did not support that: it fires reliably at roughly 2 to 7 minutes measured from the moment `CI Complete` actually turns green, and the investigation had been comparing against the run's `createdAt`, which is when the run was QUEUED on a branch whose CI takes 50 to 70 minutes. Three
real problems remained. F1, confirmed and structural: a `workflow_dispatch`-invoked Claude Review run's own `head_sha` is the ref it was dispatched against, never the PR head, so `review-status.sh` resolved no PR and the listener silently no-opped every time the manual escape hatch was used. F2, a hygiene failure that READ like "no review happened", because one check-run title
covered both "never reviewed" and "reviewed five minutes ago, nobody replied". F3, concurrency cancellation, plausible and never observed.

## Outcome
SHIPPED as specified, F1 and F2 both, with F3 deliberately not built. Header `done` is TRUE. Measured 2026-09-06.

- F1 in `.github/workflows/review-status.yml` (blob
3a312b4e2c00eb447c64d196a4feb8d679b6d4a9): the `workflow_dispatch` trigger with the `pr_number` input at `:43-46`, the `format('dispatch-{0}', inputs.pr_number)` concurrency fallback at `:62`, and the `PR_NUMBER` passthrough at `:114`, all three byte-for-byte the shapes the plan specified.
- F1 in `.ci/scripts/review/review-status.sh` (blob
b0f9c15c1a64d15bb10c4b57e361a98076da567e): `workflow_dispatch` joins the case arm at `:200` beside the comment and review events.
- The nudge step is in `.github/workflows/claude-review-reusable.yml`, hardcoded to
`rediacc/console` with the reasoning preserved in the comment at `:570-581`: the reusable is also called from the private submodule repos, where `github.repository` reads something else, and `review-status.yml` exists only in console.
- F2's title split is live: `.ci/scripts/review/review-status.sh:407` "Reviewed, but needs attention (see
failures)" against `:409` "Review is not complete for this head".
- The controls are still in `.ci/scripts/test/gates/test-review-status.sh` (blob
69c158055413aea7b7c0f47086b0f53d7c584339), renumbered T07 to T10 since.
- Landing: console commit 9076d8ad7, "fix(ci): thread the resolved PR into
review-status.yml on workflow_dispatch" (2026-08-01).

## Lessons
- MEASURE LATENCY FROM COMPLETION, NOT FROM CREATION. The entire premise of the brief
("the trigger is dead") came from comparing a downstream timestamp against an upstream run's queue time on a branch whose CI runs over an hour.
- A check-run TITLE is an interface. F2 was not a trigger bug at all; it was one string
covering two opposite situations, and it is the most likely reason a working pipeline kept being re-dispatched by hand.
- Naming F3 as unproven and declining to build it was the right call, and saying so in
the plan is what stops a later session either building it on faith or rediscovering the suspicion from scratch.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:32:37Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: .ci/scripts/review/review-status.sh, .ci/scripts/review/claude-review-gate.sh
Gates: none
Why-Source: author
Read-History: `git show 5a72b31733f38380ee001b6361fbfba1b40657e5` recovers the text; `git log --find-object=5a72b31733f38380ee001b6361fbfba1b40657e5 --all` names the commit

## History
- 2026-09-06T17:32:37Z compacted by 8f55d4f0 from `done` (record-sig 87e086b4)
