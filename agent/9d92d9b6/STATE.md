## SESSION 9d92d9b6 2026-08-26T14:12:44Z

2026-08-26. Branch `main`, **41 uncommitted paths** including a `private/account`
submodule change. Nothing committed all session, per the operator's standing
big-bang preference ("we don't stop for a new PR yet").

## Machine (was bare at session start)

node v22.23.2 + npm 10.9.8, gcc 15.2.0, Go 1.26.4, jq 1.8.1, gh 2.98.0.
**gh IS authenticated** (mfbayraktar) and `git credential fill` exits 0, so PR
commands work. Docker CLI present, NO engine (WSL integration off); advisory
only. `./run.sh setup` is idempotent, proven byte-identical across two runs with
a stamp-invalidation control.

## Current work: epic-structured PRs (plan approved)

Plan at `/home/developer/.claude/plans/good-now-we-still-expressive-curry.md`.
Goal: one big-bang PR whose body is generated from the worklist with a section
per epic, whose commits carry `PR-TASK: <epic-id>`, and whose review runs once
per epic so nothing is skipped for being crowded out.

**E1-E5 DONE.** `.claude/hooks/stop/wl_epic.py` (epic sidecar; survives
`compact()`, which is the whole reason it is a sidecar), `worklist.py --epic` and
`--publish`, `agent/pr/<branch>.md` snapshot, `.ci/scripts/pr/sync-epic-block.sh`,
`scripts/check-pr-epic-block.ts`, `.claude/hooks/pre-bash/block-untagged-commit.sh`,
`scripts/check-pr-task-trailers.ts`, `.ci/scripts/review/epic-context.sh`
(allow-listed at `claude-review-reusable.yml:250`).

**E6 PARTIAL** (`#2c862d9e`, the item carries the full design). Landed:
`common.sh` `review_report_count` takes an optional epic and keys on the producer
constant `**Claude finished (epic <id>)`; `review_epic_ids <branch>`;
`claude-review-gate.sh` declares `REVIEW_EPIC`, writes it into the report header
and scopes `reports_posted` to it. Both coherence gates pass WITH their control
mutants firing.

**STILL TO DO on E6, and none of it is blocked:**
1. `check-review-report-replies.sh` selects the NEWEST report only (its jq at
   ~line 153) and 110 lines downstream key on that single `REPORT`. Per-epic it
   must be newest-PER-EPIC: a loop around the whole body, not a selection tweak.
   It is merge-blocking, so a half-restructure risks making a PR permanently
   unmergeable, which is what that gate exists to prevent.
2. A matrix over `review_epic_ids` in `.github/workflows/claude-review-reusable.yml`.
3. An `{{EPIC_ID}}` placeholder in `emit_prompt` (`claude-review-gate.sh:176`),
   the ONLY substitution point.

## Also landed this session, outside the plan

`.claude/hooks/require-jq.sh` (jq absent had silently made ALL 27 PreToolUse
hooks exit 0 = allow); `wl_git.py` + `--git`; `block-settled-questions.sh` +
`standing-orders` output style; `run.sh` split to `.ci/lib/setup.sh` with node/
compiler/Go/jq/gh bootstrap; `compact()` made non-lossy (it was dropping
basetext/lastnote/triage/deferral-WHY every run); `block-raw-pr-body-edit.sh`;
two false-positive fixes in `rotation check`.

## Verified now

Worklist suite 351 PASS / 0 FAIL. All 13 gates exit 0: pr-epic-block,
pr-task-trailers, bootstrap-idempotency, git-tool-safety, native-rebuild,
em-dash-surfaces, ci-parity, agent-hint-liveness, gate-reachability,
hooks-resolvable, tracked-sidecars, review-cap-coherence, review-turn-capacity.

## Open

`[?] #54f9fcb0` SES 403, operator-only: `private/account/.env`'s
AWS_SES_ACCESS_KEY_ID is in no `ses-*` slug while `rotation check` passes every
slug, so only `.env` is stale. Needs a rotate or the secret AWS never shows
twice. Reported at `./run.sh setup`, never blocking (rotation is an ops task).

## Next action

Continue E6 item 1: wrap `check-review-report-replies.sh`'s body in a function
and drive it once per epic id from `review_epic_ids`, keeping the
newest-wins-per-epic rule so superseded reports are never re-litigated. Then
items 2 and 3. Do NOT stop between steps; the operator has said so explicitly.
