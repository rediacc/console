# review: one pass per epic, one budget per epic

The flat review's own prompt tells it to skip: make the summary carry a coverage
map naming "areas not reviewed and why". Above roughly 5,600 changed lines the
turn budget is flat at 140 regardless of size. On a big-bang PR that is a licence
to leave work unreviewed. Per-epic passes give each task its own budget instead.

`.github/workflows/claude-review-reusable.yml` runs a `discover-epics` job that
reads the published snapshot, then a matrix over its ids.

## The empty case is the one to get right

A matrix over an empty array does **not run the job at all**, so a PR with no
epics would get no review whatsoever, which is far worse than the crowding this
feature fixes. Discovery therefore emits `[""]`, producing exactly one pass with
`REVIEW_EPIC` empty: byte for byte the flat review that existed before epics.

`fail-fast: false`, so one epic's pass failing cannot cancel the others and leave
the rest silently unreviewed.

## Accounting is keyed per epic

`review_report_count <pr> [epic]` counts the producer constant
`**Claude finished (epic <id>)`. N epics against a 3-pass cap would blow the cap
on round one if the numerator stayed global. Two coherence gates pin this,
`check-review-turn-capacity.sh` (which mutates the literal `per_kloc=25` as its
control) and `check-review-cap-coherence.sh` (DRY numerator and denominator, one
definition in `lib/common.sh`). Change either side and both must still fail on
their own mutants.

`check-review-report-replies.sh` fans out per epic by re-invoking itself with
`REVIEW_EPIC_PREFIX` set. Newest-wins is preserved, but it is now newest **per
epic**: gating only the newest report overall would enforce the last epic's reply
and silently excuse the rest, which is worse than not gating because the
unanswered ones then look cleared.

## Scope is logical, not temporal

An epic's diff is the union of `git log --grep='^PR-TASK: <id>'`, unlike the
follow-up pass which is `LAST_REVIEWED_SHA..HEAD`.

## The context tool is a script, never an agent

`.ci/scripts/review/epic-context.sh <epic-id>` prints the epic's title, its items
with state and tick evidence, any linked `agent/PLAN-*.md`, and its commits. It
must stay a Bash script and stay in the action's `allowed_tools`: the review sets
`--disallowed-tools Task,Agent` after a PR where the reviewer spawned three
background agents, ran out of turns, and posted a placeholder.
