# PLAN: per-commit reviews replace the GitHub review

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-stop-hook-focus-mode.md, PLAN-plan-priority-concurrency.md, PLAN-ci-time-budget.md, PLAN-commit-as-you-go.md#T6, PLAN-commit-as-you-go.md#T7 -- operator order Z last; reuses Y's focus keep-list and X's Owns: header, overlaps W on ci.yml and ci-quality.yml; commit-as-you-go T6/T7 edit this plan and land before its T2
Priority: P1 -- proposed by AI (the operator: "per-commit reviews become the main quality signal")
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/post-bash/review_commit.py, .claude/hooks/stop/test-commit-review.py, .claude/rediacc_hooks/guards/block_review_file_edit.py, .claude/rediacc_hooks/guards/block_push_with_unrecorded_reviews.py, .ci/config/commit-review.json, .ci/rediacc_ci/review/**, .ci/scripts/review/**, .github/workflows/claude-review*.yml, .github/workflows/review-status.yml, .ci/rediacc_ci/quality/agent_session_archival.py, agent/reviews/**
Worklist: (lead adds this with `worklist.py --add`)

**Operator order, 2026-09-25 (section Z):** `Replace the GitHub-side PR review with per-commit reviews ... Keep the GitHub PR labeling. Remove the GitHub review job and its workflow wiring ... I'd start with only high-severity findings blocking.`

## Tasks

At most three writers, each owning its own files: A owns the reviewer core, B the stop hook, verbs and guards, C the CI side. T1 freezes the API that everything else calls.

- [ ] T1 [A] Build `.claude/hooks/stop/wl_review.py` (section 2): `Finding`, `Review`, `parse(text)`, `render(review)`, `body_sig()`, `branch_dir(root, branch)`, `branch_state(root, branch, fold)`, `uncovered(root, branch)`, `spawn_detached(...)`, `run_review(...)`. Add `.ci/config/commit-review.json` (section 3.4). This API is frozen before T2 to T9 start.
- [ ] T2 [A] Add the post-bash member `.claude/hooks/post-bash/review_commit.py` and register it in `lifecycle.PATTERNS["post-bash"]` (section 3.1). Regenerate the post-bash `timeout` in `.claude/settings.json` from `lifecycle.py --hooks`.
- [ ] T3 [A] Build the reviewer runner, prompt, schema validation and anchor checks (sections 3.2 and 3.3).
- [ ] T4 [A] Handle the agent/ collisions: add `"reviews"` to `wl_store.AGENT_RESERVED_DIRS` and a `reviews` class to `.ci/policy/tree-shape.json`, add a prose-style `exempt_paths` entry, and update agent/README.md (section 9).
- [ ] T5 [B] Add the worklist verbs `--review-mark`, `--review-commit`, `--review-run` and `--prune-reviews` (the last is a thin arm over C's function) to `.claude/hooks/stop/worklist.py`. Add their usage text to worklist_messages.py and CLAUDE.md's verb block (sections 5 and 6).
- [ ] T6 [B] Wire the stop hook (section 7): new keys `commit-review` and `commit-review-malformed`, advisories through `outq_add`, a rewritten pr-finish box, retire `review-red`/`review-unreadable`, and add the new keys to the ladder, `test-always-tier.py`, `wl_roster.CAP_WAIT_KEEPS` and Y's focus keep-list.
- [ ] T7 [B] Add the guards `block_review_file_edit.py` (pre-edit plus pre-bash write shapes) and `block_push_with_unrecorded_reviews.py` (pre-bash), each with EDGE_CASES, a DEFECT tuple and its own suite, and add both to `scripts/data/hook-inventory-baseline.json`.
- [ ] T8 [C] Move labeling to `.ci/rediacc_ci/review/pr_labels.py`, which reads verdicts from the review files, and run it from ci.yml's `label-guide` job (section 8).
- [ ] T9 [C] Extend the housekeeper `agent_session_archival` with finding S2 and the prune function; give quality-branch a token (section 10).
- [ ] T10 [operator] Remove `Review Complete` from main's required status checks (section 11, step 3). This is the precondition for T11.
- [ ] T11 [C] Tear down the review system (section 11), submodule PRs first. It closes only when the grep in 11.5 returns nothing.
- [ ] T12 [A,B,C] Tests and mutation controls (section 12). Each writer owns the tests for its own files.
- [ ] T13 [lead] Run one live smoke: a real haiku review of a real commit on this branch. Record cost and wall time in the tick evidence and in commit-review.json's `$comment`.

## 0. What exists now, and the findings that shape the design (all high severity)

- **H1. `Review Complete` is a REQUIRED check on main.** Measured today with `gh api repos/rediacc/console/rules/branches/main`, the required checks are `CI Complete` and `Review Complete`. `review-status.yml` posts that check (`.github/workflows/review-status.yml:1-32`). Deleting the workflow while the ruleset still requires the check makes every PR permanently unmergeable, the same shape as PR #553 (`docs/ci-overhaul/06-progress.md:1293`). The teardown PR itself cannot merge until the check stops being required. So the operator has to remove it (T10) before T11 merges.
- **H2. PR labeling lives inside the review job, and half its input is model output.** The "Apply PR labels" step is at `.github/workflows/claude-review-reusable.yml:583-592`. `run_apply_labels` (`.ci/rediacc_ci/review/claude_review_gate.py:1135-1300`) merges two inputs: a mechanical floor built from the file list, and the model's `json:pr-labels` verdict (bump plus kind). Deleting the job deletes labeling. So labeling moves (section 8), and the per-commit reviewer takes over producing the verdict.
- **H3. A detached child would still block the commit.** `lifecycle.run_pattern` runs each post-bash member with `subprocess.run(..., capture_output=True)` (`.claude/rediacc_hooks/lifecycle.py:375`). A background reviewer that inherits those pipes keeps `communicate()` waiting until the review finishes, so the Bash tool call would hang for the whole review. The spawn must use `stdin=DEVNULL`, send stdout/stderr to a log file, set `start_new_session=True` and `close_fds=True`. This is the same grandchild-pipe trap `.claude/hooks/stop/wl_proc.py:3-8` documents.
- **H4. `claude -p` runs the repo's own hooks.** The Stop hook's recursion guard is `STOPHOOK_CHILD`, checked in the first statement of `main()` (`.claude/hooks/stop/worklist.py:1683`). `.claude/hooks/stop/wl_judge.py:784-785` sets it. If the reviewer ran with the repo as its cwd, it would also fire SessionStart and PostToolUse and show up as a phantom session in the worklist. So the reviewer does what the judge does: neutral cwd, `STOPHOOK_CHILD=1`, `--tools ""` (`.claude/hooks/stop/wl_judge.py:786-806`). It also sets `COMMIT_REVIEW_CHILD=1`, and the new hook refuses to run when that is set.
- **H5. `agent/reviews` collides with session detection.** Every directory under agent/ that is not in `AGENT_RESERVED_DIRS` (`.claude/hooks/stop/wl_store.py:175-177`) is treated as a peer session. Without a change, the hook reports a peer session called "reviews" to every session, and `check:ci-tree-shape` goes red on T4/T5 (`.ci/rediacc_ci/quality/tree_shape.py:157-195`, `.ci/policy/tree-shape.json:110-111`).
- **H6. prose-style lints model-written text.** `.ci/config/prose-style-rules.json` `globals.include` covers every `*.md` outside `exclude_dirs`, and agent/ is not excluded. A haiku claim could turn CI red over prose nobody in the repo wrote.
- **H7. Two other repos call the reusable at `@main`.** `private/account/.github/workflows/claude-review.yml:47` and `private/renet/.github/workflows/claude-review.yml:45` call it, and `.github/external-callers.yml:22-41` declares both. Deleting it in console first breaks their runs at startup. Their callers must be removed first, in submodule PRs. The reusable's header also names `elite`; T11 checks rediacc/elite's live workflows with `gh api` before deleting anything.
- **H8. The existing housekeeper is `check:ci-agent-session-archival`.** Its own docstring says "agent/<session>/ directories accumulate for ever". It already has a 14-day `grace_days` (`.ci/config/agent-session-archival.json:28`), a `--check/--status/--move` verb set (`.ci/scripts/quality/check_agent_session_archival.py:22-31`) and a quality-branch step (`.github/workflows/ci-quality.yml:618-620`). It is the right thing to extend. But quality-branch has only `contents: read` and no token (`.github/workflows/ci-quality.yml:527-536`), so a merged-at lookup needs a permission added (section 10).

Other findings (below high, but still load-bearing):

- **M1.** agent/README.md:28 records an operator decision from 2026-08-18: "No branch anywhere in the path". The spec (2026-09-25) explicitly asks for `agent/reviews/<branch>/`, and `agent/reggate/<branch>.jsonl` and `agent/pr/<branch>.md` are already precedents. The spec wins. README gets a paragraph saying reviews are per-branch on purpose, because a finding is about the branch's diff, not about a session.
- **M2.** A W12 comment in `.ci/config/plan-lifecycle.json` says the operator's standing rule is "nothing is deleted". The spec explicitly orders a deleting `--prune-reviews`. Contents survive in git history, and nothing cites review files durably (the verb refuses if something does, section 10).
- **M3.** `git commit --amend` is hook-blocked (`.claude/rediacc_hooks/guards/block_git_amend.py:23-37`). So sha rewrites come from `/branch-rebase` or the operator's own terminal. Both are handled by patch-id matching and a coverage check (section 4).
- **M4.** Parts of the stop hook assume the GitHub review and retire with it:
  - the `review-red` path (`.claude/hooks/stop/wl_checks.py:3471-3510`, `.claude/hooks/stop/wl_ci.py:147,383-500`);
  - the pr-finish "Claude-reviewed" box (`.claude/hooks/stop/wl_checks.py:3554`);
  - `.claude/hooks/stop/test-always-tier.py:29,42`;
  - the ladder entries at `.claude/hooks/stop/wl_checks.py:2125,2159`.

## 1. Flow in one paragraph

A `git commit` succeeds in any Bash tool call (lead or sub-agent). The post-bash member sees a new commit on the branch that has no review yet and no reviewer running. It starts a detached reviewer and returns in well under a second. The reviewer runs a tool-less haiku call with a JSON schema over `git show <sha>`, validates the anchors, and atomically writes `agent/reviews/<branch>/<sha>.md` into the worktree. It never touches the index. The stop hook reads that directory:

- an open `high` finding blocks the stop;
- `medium` and `low` findings are advisory;
- each finding is closed only through `worklist.py --review-mark`.

Review files ride the session's next commit or `--review-commit`. A pre-push guard makes sure finished reviews reach the PR. Labels are computed in Console CI from the review files. The housekeeper turns CI red on review directories whose branch merged more than 14 days ago, and `--prune-reviews` removes them.

## 2. Review file schema (`agent/reviews/<branch>/<sha40>.md`)

```
# Review 3f9a1c2e: fix(cli): repo list honours --json

Commit: 3f9a1c2e7d0b...40hex
Repo: console                      # or private/account, private/renet
Branch: 0923-1
Parent: 81be...40hex
Patch-Id: 5c0e...40hex             # git patch-id --stable; identity across rebase
Reviewed-At: 2026-09-25T15:02:11Z
Model: claude-haiku-4-5-20251001
Diff: 18233 bytes, 7 files, truncated: no
Unreviewed: (none)                 # files cut by the diff cap, comma list
Verdict: findings                  # findings | clean | skipped (gitlink-only) | failed (<reason>)
Labels: bump=patch kind=bug why=<=200 chars>
Dropped: 0                         # findings whose file is not in this commit
Body-Sig: 9d1f0a6b2c4e8a11         # sha256[:16] over the canonical finding lines

## Findings

### 3f9a1c2e.1 [high] packages/cli/src/commands/repo/list.ts:88
Anchor: in-diff                    # in-diff | outside-diff
Claim: <one line, <= 600 chars, em dashes normalised to "--", newlines collapsed>
Resolution: open
```

- **Finding id** is `<sha8>.<n>`, with n counted from 1 in model order after validation. It stays the same across rebases, because the file keeps the name of the sha it reviewed.
- **Severity** is `high`, `medium` or `low`. The prompt defines each one (3.3).
- **Resolution grammar.** `parse()` enforces it strictly; anything else counts as malformed:
  - `Resolution: open`
  - `Resolution: fixed <sha40> | <me8> <isoZ>`
  - `Resolution: not-a-bug | <evidence> | <me8> <isoZ>`
  - `Resolution: deferred #<item> | <me8> <isoZ>`
- **Body-Sig** covers `id|severity|file|line|anchor|claim` for every finding. It does not cover Resolution lines, so `--review-mark` never re-signs anything.
  - A hand edit that downgrades a severity or rewrites a claim fails the check and becomes `commit-review-malformed`.
  - Honest limit: anyone can recompute the sig, because there is no secret. It catches accidental and casual edits. The real protection is the edit guard (T7).
- **Verdict values.** `skipped (gitlink-only)` is written for pointer-bump commits, so coverage stays honest. Commits that only touch `agent/reviews/` get no file at all; coverage excludes them by a path rule, so there is no endless loop of reviews of reviews.

## 3. Trigger, reviewer, prompt, model

### 3.1 Post-bash member `review_commit.py`

- **Placement.** It goes into `lifecycle.PATTERNS["post-bash"]["members"]` after `refresh_pr_body.py` and before trapguard (`.claude/rediacc_hooks/lifecycle.py:129-140`), as `{"command": ..., "timeout": 10}`. The settings.json timeout is re-derived from `hooks_block()`.
- **Exit status.** Always 0, like its siblings.
- **Early exits:**
  - `STOPHOOK_CHILD` or `COMMIT_REVIEW_CHILD` is set;
  - the command does not invoke `git` with the subcommand `commit|rebase|cherry-pick|merge|revert|pull` in command position. Detection goes through `shellscan.lifted_commands` plus a command-position regex, the same anchoring `.claude/rediacc_hooks/guards/block_git_amend.py:26-28` uses, so prose and `echo` never match.
- **Target repo.** `shellscan.target_root(scan, root, verb=...)` (`.claude/rediacc_hooks/shellscan.py:441-463`), so `git -C private/account commit` resolves to the submodule.
- **What counts as success.** The hook does not parse `tool_response`, which has no exit code (trapguard `.claude/hooks/trapguard/dispatch.py:73`). Instead it recomputes `wl_review.uncovered(root, branch)`: commits in `merge-base(origin/main)..HEAD`, newest first, capped at 20. It drops merge commits, commits touching only `agent/reviews/`, and commits older than `review_epoch` (a config value set to the landing date, so older branch history is not back-reviewed). A commit counts as covered when a review file with its sha or its patch-id exists, or a live lock exists. A failed commit creates no new sha, so the "never fire on failure" property is structural rather than parsed.
- **Branch.** Resolved at trigger time. A detached HEAD during a rebase reads `rebase-merge/head-name`; any other detached HEAD is logged and skipped, and the coverage advisory picks it up later. The branch is passed to the child, so a later checkout cannot misfile the review.
- **Spawn.** At most `max_spawn_per_trigger` (5) uncovered commits:
  ```python
  Popen([python3, worklist.py, "--review-run", me, sha, "--branch", br, "--repo", rel, "--child"],
        stdin=DEVNULL, stdout=log, stderr=STDOUT, start_new_session=True, close_fds=True, cwd=root)
  ```
  The log goes to `<TMP>/claude-worklist/reviews/<sha>.log`. A reviewer that has setsid'd is re-parented away from the harness, so `wl_bgsweep` (anchored on the harness pid) never flags it as an orphan shell.

### 3.2 Runner (`worklist.py --review-run` -> `wl_review.run_review`)

- **Per-sha lock.** `O_CREAT|O_EXCL` on `<TMP>/claude-worklist/reviews/locks/<sha>.lock` holding `{pid, start, branch}`. A lock whose pid is dead is stale and gets replaced. A second trigger for the same sha is a no-op.
- **Concurrency cap.** `max_concurrent` (2) slot files. A child waits for a slot, polling every 5s for up to 15 minutes. If none frees up, it writes `Verdict: failed (queue timeout)`.
- **Inputs, all read from the object store, never the working tree:**
  - `git show --stat --format=%B <sha>`;
  - `git show -U8 --no-color <sha>`, capped at `diff_cap_bytes` (80000). Files cut by the cap are listed under `Unreviewed:`;
  - `git show <sha>:<path>` for anchor checks.
  This makes the result deterministic no matter what the session edits or commits next.
- **Patch-id short-circuit.** If a review with the same patch-id already exists in the branch directory, the runner writes nothing and exits, because it is a rebased copy.
- **Model call.** Through `wl_proc.run` (process-group kill, `.claude/hooks/stop/wl_proc.py:40-56`):
  ```
  claude -p <prompt> --output-format json --json-schema <schema> --model <cfg.model>
    --tools "" --max-budget-usd <cfg.budget_usd>
  ```
  with timeout `timeout_s` (240), cwd `<TMP>/claude-worklist/.review` and env `STOPHOOK_CHILD=1 COMMIT_REVIEW_CHILD=1`. An answer with no structured output gets exactly one retry, reusing `wl_judge.retry_schema_exhaustion`.
- **Anchor validation.**
  - A finding whose `file` is not in the commit's changed paths is dropped and counted under `Dropped:`.
  - A `line` outside ±8 lines of a new-side hunk keeps its severity but is marked `Anchor: outside-diff`.
- **Failure.** Any failure still writes a file with `Verdict: failed (<reason>)` and no findings. The failure is visible, and coverage reports it.
- **Write.** Temp file plus `os.replace`. The runner never runs `git add`: the index is shared, and `block_pathspecless_git_commit.py`'s header records sub-agent index sweeps.

### 3.3 Model and prompt

- **Model.** `claude-haiku-4-5-20251001`, the dated haiku build the judge already pins and measured ($0.011-$0.026 warm, `.claude/hooks/stop/wl_judge.py:25-26`). It lives in `.ci/config/commit-review.json`, not in an env var, so `wl_review` stays sealed and needs no worklist-env-registry row.
- **Budget.** $0.30 per call.
- **Schema.**
  ```
  {verdict: findings|clean,
   findings[<=8]: {severity, file, line:int>=1, claim<=600},
   labels: {bump: none|patch|minor|major, kind: [bug|feature|docs|ci], why<=200}}
  ```
- **Prompt body** (stored in `wl_review.PROMPT`):

  > You review ONE git commit of the rediacc console monorepo. You see only its message and diff. Report defects this commit INTRODUCES or EXPOSES, nothing else.
  > Severity:
  > high = on the changed path it will produce wrong behaviour, data loss, a security hole, a broken build or a CI gate that can no longer fail;
  > medium = a real bug only on an edge path, changed behaviour with no test, or a comment that states the wrong behaviour;
  > low = anything else worth a line.
  > Style and naming are never above low. Do not speculate about code you cannot see. Every finding names a file from this diff and a line number in the NEW version of that file. The claim must say what goes wrong and when, in one sentence a reviewer can check. If the commit only moves or renames text, answer clean. Also classify the commit for release labels: bump none (no user-facing change), patch, minor (new capability), major (only recommend); kind from bug, feature, docs, ci.
  > COMMIT MESSAGE: ... STAT: ... DIFF (may be truncated; truncated files listed): ...

### 3.4 `.ci/config/commit-review.json`

Keys: `model`, `budget_usd`, `timeout_s`, `max_concurrent`, `max_spawn_per_trigger`, `diff_cap_bytes`, `block_at: "high"`, `review_epoch`, `retention_days: 14`, each with a `$comment`.

`retention_days` is read by the housekeeper (section 10), so the number exists in exactly one place.

## 4. Concurrency and sha rewriting

- **Two commits in quick succession.** They are independent children, each with its own lock, its own `git show <sha>` against its own parent, and its own output file. Nothing is shared except the 2-slot semaphore. Diffs come from the object store, so a child cannot see the second commit's changes.
- **The same commit triggered twice** (for example commit, then an immediate push that re-runs the trigger). The lock makes the second trigger a no-op.
- **Rebase (`/branch-rebase`) or an operator amend in a terminal.**
  - New shas with the same patch-id count as covered through the existing file's `Patch-Id:`. Findings and resolutions carry over, because findings are keyed by id, not sha.
  - Commits whose patch-id changed (conflict resolution, an amend) show up as uncovered. The post-bash trigger on `git rebase`/`cherry-pick` reviews up to 5 of them; the rest appear in the coverage advisory with `worklist.py --review-run <me> <sha>`.
  - A review in flight across a rebase still writes under the old sha. Patch-id matching makes it count for the new one.
- **`fixed <sha>` after a rebase.** The verb resolves the sha at mark time. A mark that names a pre-rebase sha stays valid as text. The stop hook does not re-verify old marks, only their grammar, so a rebase never reopens a closed finding.
- **Branch switch while a review runs.** The file goes to the branch recorded at trigger time. While a different branch is checked out it shows up as untracked. The stop hook reads only the current branch's directory, so no false block results.

## 5. How the review file gets committed (without breaking "work stays uncommitted until asked")

Review files exist only because a commit happened, and a commit happens only when the operator asked for commits on this branch. They are the record of an authorized commit, the same class as `agent/reggate/<branch>.jsonl` and `agent/pr/<branch>.md`, which already ride PRs (.gitignore:165-170 comment).

1. The reviewer writes the file uncommitted and unstaged.
2. The session carries it on its next commit (`git commit -F msg -- <paths> agent/reviews/<branch>/`), or runs `worklist.py --review-commit <me>`. That verb:
   - picks exactly the finished, untracked or modified files in the current branch's directory (never files with a live lock);
   - runs `git add -- <files>` and then `git commit -F <msg> -- <files>`, which commits only those paths;
   - uses the message `chore(reviews): record reviews for <sha8 list>` plus a `PR-TASK:` trailer copied from the newest reviewed commit;
   - calls `block_untagged_commit`'s id check in-process, because a git subprocess is invisible to the pre-bash guards, the same caveat `--git` records at `.claude/hooks/stop/worklist.py:2133-2139`. It also applies the commit-identity rule and never adds a Co-Authored-By line.
3. `block_push_with_unrecorded_reviews.py` (pre-bash, `git push` of this branch) refuses the push while a finished review file is untracked or modified, and prints the `--review-commit` command. Reviews still in flight never block the push; they ride the next one.
4. The pr-finish box and pr-merge preconditions require no reviewer in flight and every review committed (section 7).
5. **Rejected alternatives:**
   - The reviewer commits the file itself. That moves HEAD under the session, races the shared index, and creates commits nobody asked for.
   - The file stays untracked until merge. The spec needs it tracked so it moves between machines.
6. **Operator decision [?]:** add one sentence to CLAUDE.md rule 1: "review records of an authorized commit ride the same branch". DEFAULT: add it.

## 6. `worklist.py --review-mark <me> <finding-id> <fixed|not-a-bug|deferred> <arg...>`

- **Dispatch.** A new arm beside `--plan-tick` (`.claude/hooks/stop/worklist.py:2269`), plus a bare-verb arity guard. Without the guard a bare `--review-mark` falls through to the stdin hook path, the hang documented at `:1936-1939`. Every new arm goes before the unknown-verb catch-all.
- **Finding the file.** Glob the current branch's directory for `### <id> `. Refuse on zero or more than one match.
- **`fixed <sha>`.** Accept only if:
  - the sha resolves in the review's `Repo:`;
  - `merge-base --is-ancestor <sha> HEAD`;
  - `<reviewed-commit>` is an ancestor of `<sha>`, and the two differ;
  - `git diff-tree <sha>` touches the finding's file, or its rename target (`--find-renames`).
  Otherwise refuse and name which check failed.
- **`not-a-bug <evidence...>`.** The evidence must be at least 20 characters and contain at least one citation that `wl_checks.citation_state` resolves (a `path:line` that exists), or a sha that is on the branch. A bare opinion is refused.
- **`deferred #<item>`.** The item must exist in the fold, be open, `[?]` or `[>]`, and its text must contain the finding id. After that, the stop hook treats the finding as resolved while the item exists. Ticked counts as resolved. If the item is removed, the finding reopens.
- **Write.** An flock on `<TMP>/claude-worklist/reviews/locks/<sha>.mark`, re-read, replace only that one `Resolution:` line, `os.replace`. Then print the file path and the reminder that the change rides the next commit.
- **Never by hand.** `block_review_file_edit.py` refuses Edit/Write/MultiEdit on `agent/reviews/**`. The pre-bash half catches redirections, `tee`, `sed -i` and `python -c` open-for-write on those paths, with the same heredoc/quote-aware scan as `block_roundlog_write.py` (ORDER after 9). The verbs themselves write through Python, which no guard sees.

## 7. Stop-hook rules

- **Compute once.** `wl_review.branch_state(root, C.git_branch(root), fold)`, called in `run_stop` right after the pr-finish block (`.claude/hooks/stop/wl_checks.py:3526-3590`).
- **Blocking keys** (both `always=True`):
  - `commit-review` (T_MISSION, placed where `review-red` sits now, `.claude/hooks/stop/wl_checks.py:2125`). Fires on any finding with severity at or above `block_at` (`high`) and `Resolution: open`, or a `deferred` whose item no longer exists. The message lists at most 5 findings (id, severity, file:line, the first 160 characters of the claim) and the three exact `--review-mark` commands.
  - `commit-review-malformed` (T_INTEGRITY). Fires on a parse error, a bad Resolution grammar or a Body-Sig mismatch, and names the file and the failing line.
- **Advisories, never blocking** (`outq_add` with `refresh_min=60`):
  - open medium and low findings, count plus ids;
  - reviewers in flight (N);
  - `Verdict: failed` files, with the `--review-run` command;
  - uncovered commits, with the `--review-run` commands;
  - finished review files that are not yet committed, with the `--review-commit` command.
- **pr-finish box.** "Claude-reviewed" (`.claude/hooks/stop/wl_checks.py:3849`) becomes: "per-commit reviews clean: every branch commit covered and not failed, no reviewer in flight, no open `high` finding, reviews committed". It is computed from `branch_state` and no longer needs a store-backed `pr:<n>/reviewed` tick. The threads box stays for human review threads.
- **Keep-lists.** Add both blocking keys to `wl_roster.CAP_WAIT_KEEPS` (`.claude/hooks/stop/wl_roster.py:55-80`) and to Y's focus keep-list (they protect the PR). Also add them to `test-always-tier.py`'s list.
- **Retire.**
  - `review-red` and `review-unreadable` in the ladder (`.claude/hooks/stop/wl_checks.py:2125,2159`) and at :3471-3510.
  - `wl_ci.review_gate_row`, `review_gate_detail`, `review_red`, `reviewmark_path`, `REVIEW_MAX_BLOCKS` and `CI_NONBLOCKING_CONTEXTS` (`.claude/hooks/stop/wl_ci.py:148,384-500`) along with their selftest cases (:987-1090).
  - `M.V_REVIEW_RED`, `M.REVIEW_NOTE_DOWNGRADED` and `M.V_REVIEW_UNREADABLE` (`.claude/hooks/stop/worklist_messages.py:220-275`).
  - `.claude/hooks/stop/test-always-tier.py:29,42`.
  - The marker text in `.claude/hooks/stop/wl_git.py:850`.
- **Threshold.** Only `high` blocks at launch, per the operator. It can be raised to `medium` by editing one config line, with no code change.

## 8. Keeping the PR labeling

- **Port.** `run_apply_labels` moves to `.ci/rediacc_ci/review/pr_labels.py` together with `MANAGED_LABELS`, `DOCS_ONLY_RE`/`CI_ONLY_RE`, the ledger reconciliation (`LEDGER_PREFIX`, `APPLIED_RE`) and the "bump-major is never applied automatically" rule.
- **Verdict source.** The `Labels:` lines of `agent/reviews/<head-branch>/*.md` at the PR head. It no longer reads `EXECUTION_FILE` or the comment fence (the `.ci/rediacc_ci/review/claude_review_gate.py:1190-1226` arms are deleted).
- **Aggregation:**
  - bump is the highest of `patch` and `minor` over all commits;
  - `bump-none` only when every reviewed commit says `none`, which keeps its "removed on release-worthy pushes" semantics (.github/labels.yml:81-83);
  - `major` is logged as a recommendation only;
  - kind is the union.
- **Wiring.** A step in ci.yml's `label-guide` job (`.github/workflows/ci.yml:466-487`):
  - add `issues: write` next to `pull-requests: write`, because create-on-demand labels need it;
  - add `.ci/rediacc_ci` and `agent/reviews` to its sparse checkout;
  - `env: GH_TOKEN: github.token, PR_NUMBER, HEAD_REF`.
  The module logs and returns 0 on every failure, so a fork PR's read-only token cannot fail the job.
- **Lag.** Labels trail the newest commit's review by one push. The merge path requires reviews to be committed, so the last push before merge carries the final labels.
- **Housekeeping.** Update label_inventory's `CREATE_ON_DEMAND` comment, `.github/labels.yml:65-99` (which references `claude-review-gate.sh --apply-labels`), and turn `test_gate_review_labels.py` into `test_review_pr_labels.py`.

## 9. Collisions with existing gates

- **Reserved dirs.** Add `"reviews"` to `wl_store.AGENT_RESERVED_DIRS`, with a comment in the style of the reggate paragraph at `.claude/hooks/stop/wl_store.py:170-174`. Add a `reviews` class to `.ci/policy/tree-shape.json` `agent_dirs.classes`, because T5 requires the two to be equal in both directions.
- **prose-style.** Add an `exempt_paths` entry `{"glob": "agent/reviews/**", "reason": "BLOCKER: machine-written review records; claims are model output quoted verbatim, not repository prose"}`. It is exempt, not excluded, so it is counted on every run. The renderer still normalises em dashes and newlines.
- **plan-folders.** Not affected: `is_plan_path` only matches `agent/plans/**` and `agent/PLAN-*.md`.
- **doc-registry.** Not affected: the providers do not enumerate agent/ directories. The teardown does remove rows, so each removed row goes under `retired.<provider>` in `scripts/data/doc-registry-preport.json` with its reason (`scripts/gen/gen-docs.ts:404-440`), then `npx tsx scripts/gen/gen-docs.ts --write`.
- **scope-map.** `agent/` is already a zero-job module (`.ci/scripts/ci/scope-map.cjs:27-33,141`), so a reviews-only push costs one fast-path CI round.
- **em-dash-surfaces.** Does not scan agent/ (`scripts/gates/check-em-dash-surfaces.ts:106-141`).

## 10. The prune gate (extending the existing housekeeper)

- **New finding S2** in `.ci/rediacc_ci/quality/agent_session_archival.py`: "agent/reviews/<b>/ belongs to a branch merged N days ago (> retention_days)".
  - Candidates are the tracked directories from `git ls-files agent/reviews/`, minus the current branch (`GITHUB_HEAD_REF` in CI, `git branch --show-current` locally).
  - `retention_days` is read from `.ci/config/commit-review.json`, so the number has one home.
- **The merged-at oracle** is `gh pr list --repo rediacc/console --state merged --head <b> --json mergedAt` (take the max).
  - The git history cannot answer. Rebase-merge keeps committer dates equal to author dates on this repo (measured today: `git log origin/main --format=%an|%cn|%aI|%cI` shows no merge-time committer date). A `%cI`-based age would be a gate that cannot fail.
  - An unmerged branch is never a finding; `--status` shows it.
- **Anti-vacuity.**
  - No token in CI raises `CannotRunError` (exit 2).
  - Locally without `gh`, only S2 is skipped, loudly, following the module's existing shallow-refusal pattern.
- **CI wiring.** quality-branch gets `permissions: pull-requests: read`. The "Agent session archival" step gets `env: GH_TOKEN: ${{ github.token }}` (`.github/workflows/ci-quality.yml:625-627`). `check-workflow-gates` is re-run.
- **`--prune-reviews [--write]`.**
  - Implemented once as `ASA.prune_reviews(root, write)`, exposed as a gate-script verb and as `worklist.py --prune-reviews <me> [--write]` (a thin arm).
  - Without `--write` it is a report and exits 0, like `--sweep`.
  - With `--write` it deletes the due directories from the worktree only, without touching the index, and prints `git commit -F <msg> -- agent/reviews/<b>/...`.
  - It refuses when any tracked text file outside `agent/reviews/` cites a path inside a due directory, and lists the citers.

## 11. Removing the GitHub review job (ordered, submodule first)

1. **Phase 1, additive.** T1-T7 land, and per-commit reviews run alongside the old pipeline for at least one PR. This is ordering forced by H1, not a compatibility window.
2. **Phase 2.** T8 (labels) and T9 (prune) land. Labels are now written by label-guide. Removing the old "Apply PR labels" step here avoids double writes to the ledger comment.
3. **Phase 3, operator only (T10).** Remove `Review Complete` from main's required status checks, via the ruleset UI or `gh api -X PUT repos/rediacc/console/rulesets/<id>`. Check the result with the `rules/branches/main` read shown in H1.
4. **Phase 4 (T11).**
   - **Submodules first.** Delete `private/account/.github/workflows/claude-review.yml` and `private/renet/.github/workflows/claude-review.yml` in their own PRs, merge them, then bump the pointers. Remove the two entries from `.github/external-callers.yml:22-41`. Confirm elite with `gh api`.
   - **Console deletes:**
     - workflows: `claude-review.yml`, `claude-review-reusable.yml`, `review-status.yml`;
     - `.ci/scripts/review/{claude-review-gate.sh, review-status.sh, discover-epics.sh, epic-context.sh, prompts/}`;
     - `.ci/rediacc_ci/review/{claude_review_gate.py, review_status.py, discover_epics.py}`, plus `epic_context.py` only if `test_pr_sync_epic_block.py` does not need it;
     - `.ci/rediacc_ci/core/review_budget.py`, after untangling `core/common.py` and `infra/ci_env.py`;
     - gates `check:ci-review-turn-capacity`, `check:ci-review-cap-coherence`, `check:ci-review-prompt-render`, from package.json, `scripts/ci-runner/manifest.ts`, ci-quality.yml steps, then `npm run gen:gates-lock`/`gate:bind`;
     - Review Gate's "Check unreplied review reports" step (ci.yml, near :653) and `review_report_replies.py`. Its only subject is the Claude report comment. Untangle `review_comments.py`'s import of it.
     - their tests and goldens; `.ci/shadow/w7p*-review*` ledgers and their twin-parity rows; entries in `python-env-registry.json`, `python-types-baseline.json`, `prose-style-baseline.json`, `secret-reachability.json` and `actions_vars`;
     - `Review Complete` in `.github/workflows/watchdog-monitor.yml:148`;
     - `discover_epics` in `check_pr_head_ref_completeness.py`.
   - **Console keeps:** the Review Gate job with resolved threads and review comments (bot-agnostic, human threads), `block_premature_ready`, and PR-TASK trailers and epics (they feed the PR body block). Update `block_untagged_commit.py`'s WHY text to say so.
   - **Out of scope, decision [?]:** `claude-mention.yml` (the @claude responder, not the review job). DEFAULT: keep.
   - **Docs:**
     - `.claude/commands/pr-babysit.md:57`, `.claude/commands/pr-merge.md:108,117,154`, `.claude/commands/branch-rebase.md:251`;
     - `.claude/agents/pr-babysitter.md:110`;
     - `.claude/skills/pr-epics/review.md`;
     - `docs/agent-reference/TRAPS.md:139,160`, `ci-gates.md`;
     - the comments in `.github/workflows/ci.yml:566-568` and `.github/workflows/ci-quality.yml:645`.
     The new finish line is: "green, ready, per-commit reviews clean (section 7), human threads resolved".
5. **Exit criterion.** This must return only archive, plan and progress-history hits:
   ```
   git grep -nE "claude-review|Claude Review|Review Complete|claude-reviewed|review-status|review_status" -- ':!agent/archive' ':!agent/plans' ':!docs/ci-overhaul' ':!.ci/cache'
   ```

## 12. Tests (the spec's four, plus mutation controls)

Every suite runs its controls before its real cases. A control that cannot fail makes the whole suite fail.

1. **A commit produces a review file.** `.claude/rediacc_hooks/tests/test_review_commit_hook.py`.
   - Setup: a temp git repo, a stub `claude` on PATH that sleeps 3s and prints a canned `structured_output` with one high and one medium finding. It asserts `STOPHOOK_CHILD=1` and a cwd outside the repo, and exits 3 otherwise.
   - Drive `lifecycle.run_pattern("post-bash", payload)` with a PostToolUse payload for `git commit -m x -- f`.
   - Assert the hook returns in under 1s, the file appears within 10s, and `parse()` yields `<sha8>.1 [high] f:<line>` with a Claim and `Resolution: open`.
   - Cases: a failed commit ("nothing to commit") writes nothing; a reviews-only commit writes nothing; `git -C sub commit` produces `Repo: sub`; a gitlink-only commit writes `skipped`; the same sha triggered twice spawns once; two commits back to back give two files with disjoint findings; a rebased copy with the same patch-id writes nothing.
   - Mutations:
     - swap `start_new_session`+DEVNULL for inherited pipes: the hook takes at least 3s, red;
     - drop the covered check: the failed-commit case spawns, red;
     - drop the agent/reviews path rule: the reviews-only case spawns, red;
     - drop `STOPHOOK_CHILD` from the child env: the stub exits 3 and the file says `failed`, red.
2. **An unmarked high finding blocks the stop.** `.claude/hooks/stop/test-commit-review.py`, which drives `run_stop` against a fixture branch directory.
   - An open high gives a `commit-review` block naming the id.
   - Control: an open medium gives an advisory only, no block.
   - A severity downgraded by hand, or a claim edited, gives `commit-review-malformed`.
   - A deferred item that was removed reopens the finding.
   - Mutations: `>=` changed to `>` in the threshold comparison, red; Body-Sig check disabled, red on the hand-edit case.
3. **A marked finding allows the stop.** Same file.
   - `--review-mark <id> fixed <sha>` with a valid descendant sha that touches the file: the stop passes.
   - Refusals, each red if accepted: a sha not on the branch, a sha that does not touch the file, the reviewed sha itself, `not-a-bug` with no resolvable citation, `deferred #nonexistent`, and a deferred item whose text lacks the id.
   - Mutation: skip validation in the mark verb, and the refusal cases turn red.
   - Guard suites (T7): Edit on `agent/reviews/x/y.md` refused, `cat > agent/reviews/...` refused, `echo "agent/reviews"` allowed, a push with an untracked finished review refused, a push with only in-flight reviews allowed.
4. **The prune gate fails, then passes after pruning.** An extension of `.ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py` using a fixture repo and a stubbed oracle.
   - A directory merged 15 days ago: `--check` exits 1 naming the verb. Run `--prune-reviews --write` and commit: `--check` exits 0.
   - Controls: merged 13 days ago, no finding; unmerged, no finding; the current branch, never a finding; oracle unavailable in CI, exit 2, not 0; a citing file blocks `--write`.
   - Mutations: inverted age comparison, red; `None` treated as "merged long ago", red on the unmerged case.
5. **Labels.** `test_review_pr_labels.py`.
   - [patch, minor] gives `bump-minor`; [none, none] gives `bump-none`; [none, patch] removes a ledger-recorded `bump-none`; `major` is never applied; a hand-applied label is never removed; a name outside the whitelist is refused.
   - Mutation: aggregate by last instead of max, red.
6. **Teardown.** `check-workflow-gates` CHECK 4 is green with the external-callers entries removed. The gen-docs verify run is green with the `retired` rows. The grep in 11.5 is recorded in the tick evidence.

## 13. Operator decisions (to go through /ask)

- [?] CLAUDE.md rule 1 carve-out for review records (section 5). DEFAULT: add the sentence.
- [?] T10: remove `Review Complete` from the main ruleset. This is operator-only (repo admin). DEFAULT: the operator runs it once Phase 2 is green.
- [?] Keep `claude-mention.yml`. DEFAULT: keep; it is not the review job.
- [?] `review_epoch`. DEFAULT: the day T2 lands, so older commits on open branches are not back-reviewed.

### Critical Files for Implementation
- /home/developer/console/.claude/rediacc_hooks/lifecycle.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.ci/rediacc_ci/review/claude_review_gate.py (source of the labeling port; deleted afterwards)
- /home/developer/console/.ci/rediacc_ci/quality/agent_session_archival.py
