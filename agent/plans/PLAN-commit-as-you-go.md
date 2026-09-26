# PLAN: commit as you go, one branch, one PR

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: no-dep -- none for T0-T3 or the drain D0-D10; T9 serialises with PLAN-stop-hook-focus-mode.md on .claude/commands/pr-*.md (see Concurrency); PLAN-per-commit-review.md waits on T6/T7
Priority: P0. This is an operator ruling, and the tree holds 342 uncommitted console paths plus 86 in private/account.
Concurrency: parallel. There is one exception: T9 edits `.claude/commands/pr-*.md` and `.claude/agents/pr-babysitter.md`, which Y also owns, so T9 waits until Y's section 8 edits have landed.
Owns: .claude/rediacc_hooks/commit_policy.py, .ci/config/commit-policy.json, .claude/rediacc_hooks/guards/block_commit_on_main.py, .claude/rediacc_hooks/guards/block_second_branch.py, .claude/rediacc_hooks/guards/block_ci_skip_token.py, .claude/rediacc_hooks/guards/block_no_review_ineligible.py, .claude/rediacc_hooks/guards/block_git_hook_bypass.py, .claude/rediacc_hooks/guards/test-block_{commit_on_main,second_branch,ci_skip_token,no_review_ineligible,git_hook_bypass}.py, .claude/rediacc_hooks/git/** (T8 only), CLAUDE.md (Session Defaults rule 1 and the "Never push to main" section), .claude/output-styles/standing-orders.md
Worklist: the lead adds this with `worklist.py --add`.

**Operator ruling, 2026-09-25 (verbatim):** `Let's change that rule because massive amount of changes becomes mountains which is bad for reviews. So, if we really need to fix some bugs on main then okay but otherwise we must follow the branch naming rules to open new branches if we're working on main. So, maybe git commit hook can help? [no-review] could be used for hotfixes or existing tags/writint maybe [no-ci?]? not sure check and decide. But we should only allow single branch and single PR only. AI agents sometimes decides to open new branches. I don't allow them.`

**Line numbers** refer to the working tree on `0923-1` on 2026-09-25. If they drift, re-anchor on the named function or constant.

## 0. Checking the brief: where this plan agrees and where it does not

1. **Replace rule 1: agreed.** One change: the lead commits, not the writer (section 3.3).
2. **"`git checkout -b` / `switch -c` / `branch <name>` is already hook-blocked": false.** Only `git worktree add` is blocked outright (`block_worktree_add.py`, ORDER 28). `block_nonstandard_branch_name.py:141-143` only checks the branch *name*. It allows `main` and any `^[0-9]{4}-[0-9]+$`. So `git checkout -b 0925-1` from `0923-1` goes through today.
   - `git push origin HEAD:0925-1` is not checked either. It creates a new remote branch, and `block_push_to_protected_branch.py` only looks at pushes to `main`.
   - No guard counts branches anywhere. That is the gap this plan fills.
3. **"`[no-review]` for hotfixes": disagreed.** A hotfix on `main` never goes through a PR, so the per-commit review is the only review it gets.
   - Z's reviewer runs after the commit, asynchronously, so reviewing a hotfix adds no delay.
   - `[no-review]` is kept only for commits that are purely writing (section 4.2).
   - One more problem: Z's `uncovered()` walks `merge-base(origin/main)..HEAD` (PLAN-per-commit-review.md:111). On `main` that range is empty, so as Z is written, hotfixes would never be reviewed at all. T7 fixes this.
4. **`[no-ci]`: rejected** (section 4.3). Instead, a new guard refuses GitHub's own skip tokens in commits the agent writes.
5. **"Genuine hotfix on main, then commit": agreed for the commit only.** The push to `main` stays the operator's own `!` command.
   - `block_push_to_protected_branch.py` is unconditional, and its header explains why: the ruleset's admin bypass lets any push through.
   - `pr-merge.md:196-213` still says "commit on `main` and push", which contradicts the guard. T9 corrects that doc.

### Findings found while exploring (all fixed in this plan)

- **F1, a false positive seen live this session.** `block_nonstandard_branch_name` refused a read-only `grep -n -e "checkout -b" -e "git branch [a-z0-9]" ...` because it read the quoted pattern as a branch name.
  - Cause: the guard strips heredocs but deliberately not quoted strings (`block_nonstandard_branch_name.py:88-91`).
  - Fix (T2): both this guard and the new `block_second_branch` detect branch creation with one shared, lexer-based parser in `commit_policy.branch_creations()`.
- **F2.** Nothing counts branches, and nothing checks pushes to new remote branch names (point 2 above). Closed by T2.
- **F3.** Nothing refuses `--no-verify`, `git commit -n` or `-c core.hooksPath=...` (a grep of the guards finds none). This only matters once git-level hooks exist. Closed by T8.
- **F4.** `pr-merge.md:196-213` ("commit on main and push") contradicts `block_push_to_protected_branch`. Fixed in T9.
- **F5.** `block_untagged_commit` demands a `PR-TASK:` trailer even on `main`, where there is no `agent/pr/main.md`. The check at `:316` then falls back to shape only, so a hotfix has to invent an epic id. Closed by T3.
- **F6.** Z never reviews commits made on `main` (point 3). Closed by T7.
- **F7.** No guard stops an agent's commit from carrying `[skip ci]` or its siblings. On a PR head, GitHub then skips the workflow, and the required `CI Complete` check sits at "Expected" forever. Closed by T4.

## Tasks

At most three writers:
- **A** owns `commit_policy.py`, the config and the five new guards with their suites.
- **B** owns the edits to existing guards and the worklist/stop-hook changes.
- **The lead** owns the docs, the drain and the Z/Y edits.

Order:
- T0 comes first.
- T1 freezes the `commit_policy` API before T2-T5 start.
- The drain D0-D10 can run as soon as T0 is done. It needs none of the new guards, because it happens entirely on `0923-1`.

- [ ] T0 [lead] Live probes, with the answers recorded in this plan:
  - (a) Does PreToolUse fire for a sub-agent's Bash call? Does the payload carry `agent_id`/`agent_type`? Probe: a throwaway guard that logs the payload keys, driven by one Explore sub-agent.
  - (b) Does git 2.53's `reference-transaction` hook see `git branch -m` as one transaction (create plus delete)?
  - (c) Is `gh pr list --head <b> --state merged` readable offline? Record the result.
- [ ] T1 [A] Build `.claude/rediacc_hooks/commit_policy.py` (section 5.1) and `.ci/config/commit-policy.json` (section 5.2). Freeze the API.
- [ ] T2 [A] Build `block_second_branch.py` (pre-bash, ORDER 46) and move F1's parser into `commit_policy.branch_creations()`. Re-point `block_nonstandard_branch_name.py` at the parser, regenerate its golden with the intentional delta recorded, and add the F1 case.
- [ ] T3 [A] Build `block_commit_on_main.py` (ORDER 45), which defines `[hotfix]` (section 4.1). In `block_untagged_commit.py`, exempt `main` + `[hotfix]` from the trailer requirement (F5) and regenerate its golden.
- [ ] T4 [A] Build `block_ci_skip_token.py` (ORDER 47) (section 4.3).
- [ ] T5 [A] Build `block_no_review_ineligible.py` (ORDER 48) (section 4.2).
- [ ] T6 [B] Worklist changes:
  - The tick arm requires `commit:<sha>` or `nocommit:<reason>` (section 3.4).
  - Re-scope PLAN-uncommitted-work-exposure-check.md's `V_UNCOMMITTED_RISK` from "informational" to a push to commit.
  - Add its key to Y's focus keep-list and to `wl_roster.CAP_WAIT_KEEPS`.
- [ ] T7 [lead] Edit PLAN-per-commit-review.md:
  - Rewrite section 5 and the rule-1 decision in section 13, which no longer applies.
  - Handle `[no-review]` in `uncovered()`: write a `Verdict: skipped (no-review)` stub after re-checking eligibility in-process.
  - Extend `uncovered()` to `origin/main..HEAD` when the branch is `main` (F6).
  - Point it at `.ci/config/commit-policy.json` for the eligible globs.
- [ ] T8 [A] Optional, depending on decision 2: git-level hooks (section 5.3) and `block_git_hook_bypass.py` (ORDER 49) for F3.
- [ ] T9 [lead] Update the docs (section 7), including F4. `block_second_open_pr.py` gets a new message and a regenerated golden.
- [ ] T10 [A, B] Tests (section 6). Each writer owns the tests for its own files. Every guard gets a fire case, an inverse case and a DEFECT control.
- [ ] T11 [lead] Add every new guard to `scripts/data/hook-inventory-baseline.json`, then run `check-hook-integrity`, `test_dispatch.py` (ORDER contiguity) and `test_guards_differential.py`.
- [ ] D0-D10 [lead] The one-time drain (section 8).

## 1. The new rule 1 (replaces CLAUDE.md:15-27 and standing-orders.md:11-15)

**Title: "1. Verified work is committed as it lands, on the one branch."**

Verified work is committed right away, in small, reviewable commits on the single current branch. Uncommitted work should never pile up.

- **What makes a unit "verified".** A change set is a verified unit when all of the following are true:
  - it serves one stated purpose inside one epic (one `PR-TASK:` id);
  - its acceptance check has been run and its exit code read: a named test, gate or command with `rc=0`, or for writer output, the lead's spot-check (Standing Order 4);
  - it touches only paths this session owns: its own edits and the file lists its writers reported.
- **Cadence.** The unit is committed as soon as it is verified, and before the next unit starts.
  - Worklist items: commit first, then tick with `commit:<sha>`.
  - Writers: the lead commits each writer's spot-checked output as that writer's report is accepted.
  - Size: a unit above 20 files needs a proof line anyway (`block_unproven_bulk_transform.py:45`), and that is the signal to split it.
- **Commit form.** `git add -- <new paths>`, then `git commit -F <msg> -- <paths>`. The pathspec guard already enforces the `--` form (`block_pathspecless_git_commit.py:70,111`).
  - Subject: Conventional Commits.
  - Body: the verification commands with their exit codes.
  - Trailer: `PR-TASK: <id>`.
  - No Co-Authored-By line (`block_commit_meta.py` refuses one).
  - No amending; a mistake gets a new fix commit (`block_git_amend.py`).
- **Pushing is separate from committing.** Pushes are backups and CI triggers, never one per commit. Push:
  - at an epic milestone;
  - at least every 2 hours of committed work;
  - before a stop that leaves unpushed commits.

  Each push still needs a `ci:quick` receipt (`block_unverified_push.py`). With a shared tree, use `--receipt-out` from a clean clone (ci-gates.md:67).
- **Unchanged.** Never `checkout`/`restore`/`stash`/`clean` to undo a mistake of the session's own making. Other sessions' uncommitted paths are theirs, so never commit them by inference.
- **One branch, one PR** (section 2). There is no "ask" path for a second one; the operator runs it with `!` if they want it.
- Rewrite standing-orders.md rule 5 ("There is no safety net") to say the net is now the commit, and keep the ban on restore/stash.

## 2. Branch and PR rules (`block_second_branch`, `block_commit_on_main`, `block_second_open_pr`)

**The invariant.** In each repo (console, plus each submodule under `private/` listed in `.gitmodules`) there is at most one live non-`main` local branch. All of them carry the same `MMDD-N` name. Each repo has at most one open PR, and its head is that branch.

A local branch counts as **not live** once its PR is MERGED or CLOSED. `gh pr list --head <b> --state all` answers this, and it is only asked when someone tries to create a branch, which is rare.

### What `block_second_branch` refuses

The same act is caught in every form:
- `checkout -b/-B`, `switch -c/-C`, `branch <new>`;
- `push <remote> <src>:<new>` or `push -u <remote> <new>` where `<new>` is not the current single branch;
- `gh pr create --head <other>`;
- `gh api ... /git/refs -X POST`.

A creation is allowed only when all of these hold:
1. the checkout is on `main`;
2. no live branch exists;
3. the name is today's `MMDD-(MAX+1)`, with MAX taken from consumed PR heads, the same computation as `block_nonstandard_branch_name`'s message;
4. in a submodule, the name must equal the console's current branch (the coordinated rule, pr-merge.md:24).

These are always allowed:
- a rename `branch -m <live> <new>`, because the count stays at 1 and `block_stale_pr_branch_date`'s advice depends on it;
- the read and delete forms;
- `/tmp` fixture repos;
- repos outside this checkout, using the same `target_root` exemption as `block_nonstandard_branch_name.py:94-98`.

If `gh` fails while a creation is being judged, the guard refuses. Its message says so, and names the operator's `!` route.

### When the checkout is on `main`

`block_commit_on_main` refuses any commit on `main` that is not `[hotfix]`. Its message gives the fix: `git switch 0923-1` if a live branch exists, otherwise `git switch -c <computed MMDD-N>`. Either carries the uncommitted work across.

After `/pr-merge`, step 7 now deletes the merged local branch in console and in each submodule (`git branch -D <merged>`, only after `gh pr view --json state` shows MERGED). That keeps the next cut simple.

### `block_second_open_pr.py:156-196`

The logic stays: `--author @me`, per target repo, fails closed. Only the message changes (`ALREADY_OPEN`, `:57-72`): the "ask the operator" paragraph is replaced with "there is no agent path; the operator runs `! gh pr create` if they want a second PR". CLAUDE.md:19-20 changes to match.

### Sub-agents

These guards apply to every Bash call, the lead's and the sub-agents'. That relies on T0(a) confirming that PreToolUse fires inside sub-agents. If T0(a) shows it does not, T8's git-level layer becomes required rather than optional.

## 3. Cadence mechanics

### 3.1 Why the lead commits

Writers never commit. That is already the worker contract at `pr-babysitter.md:146`. Three reasons:
1. Standing Order 4 says an unchecked report is not trusted. A writer committing its own work would commit exactly that unchecked work, and the no-amend rule means undoing it takes a second commit.
2. Four writers committing at once race on `index.lock` and on the HEAD ref. An agent that hits a stale-lock error tends to delete the lock file.
3. `git commit -- <paths>` builds a temporary index from HEAD plus only the named paths. The lead's one commit therefore stays correct even while writers' `git mv` entries sit in the shared index. This is the property `block_pathspecless_git_commit` is there to protect.

### 3.2 Enforcing it

If T0(a) shows `agent_id` in the payload, add an arm to `block_commit_on_main`'s module: refuse `git commit` when `agent_id` is present. If it is not in the payload, the rule lives in the writer brief template and in Z's audit, which records the commit's session.

### 3.3 Order of operations

Writer report arrives → lead spot-checks it → lead commits by path with the trailer → lead ticks the item with `commit:<sha>` → next unit.

### 3.4 Tick evidence (T6)

`worklist.py --tick` (`worklist.py:1063-1066`) gains a rule next to the door gate. The evidence must contain one of:
- `commit:<hex>`, which must resolve through `wl_checks.completion_evidence`'s object check (`wl_checks.py:370-400`) and pass `merge-base --is-ancestor <sha> HEAD` in root or a submodule;
- `nocommit:<no-tracked-change|research|operator-deferred>`.

This is a shape check only. Whether the claim is true is left to the judge. New refusal key: `no-commit-ref`.

## 4. Commit-message tags (the minimal set)

Today:
- The only tag in use is GitHub's native `[skip ci]`, and only in bot release commits: `update_homebrew_tap.py:183-187` and `advance_contract_floor.py:210`.
- `ci.yml:110` also tests it on push. `ci-quality.yml:63-69` explains why it is load-bearing there.
- `scope-engine.cjs`, `skip-plan-reconcile.cjs` and `initialize.sh` read no tags from commit messages.
- `claude-review.yml` has no skip tag. It never reviews draft PRs, and #590 is a draft.

### 4.1 `[hotfix]`: new, allowed only on `main`, required there

- **Where it goes:** at the end of the commit subject.
- **What counts as a hotfix:** either
  - (a) the main-only failure class of pr-merge step 5 (pr-merge.md:196-213): a job that failed on `main` never ran, or ran differently, on the PR's own run; or
  - (b) the operator called it a hotfix in this task.
- **Required with it:** a trailer `Hotfix-Evidence:` carrying either the red main run id or URL (case a) or `ASKED:<ISO minute>` (case b). The second form reuses `completion_evidence`'s transcript check (`wl_checks.py:373`).
- **Size limit:** at most 5 files. This is decision 4.
- **No `PR-TASK:` needed** (T3).
- **Off `main`, `[hotfix]` is refused** so the audit stays clean.
- **Reviewed by Z** (T7).
- **Pushed only by the operator**, with `!`.

### 4.2 `[no-review]`: new, allowed only on writing-only commits, recorded

- **Eligible:** every path matches `no_review_eligible` in `.ci/config/commit-policy.json`: `agent/**`, `docs/**`, and `**/*.md` outside `.claude/`.
  - `.claude/{commands,agents,output-styles,skills}/**` are **not** eligible, because they are agent programs.
  - Neither is CLAUDE.md, which is policy.
- **Checked twice:**
  - at commit time by `block_no_review_ineligible`, which reads `-m`, `-F -` heredocs and `-F <file>` the way `block_untagged_commit.py` does, and the pathspec list;
  - again by Z's reviewer, which writes `Verdict: skipped (no-review)` only after re-checking eligibility against `git show --name-only <sha>`.
- **What the tag means:** reviewing is still the default. The tag makes skipping explicit, and a commit that is eligible but untagged is reviewed anyway, which costs little.
- **Gitlink-only commits** need no tag. Z already writes `skipped (gitlink-only)` for them.
- **"Existing tags" in the ruling:** they create no commits, so they need no tag.

### 4.3 `[no-ci]`: rejected. GitHub's skip tokens are refused for agents.

Reasons:
1. On a `pull_request` or `push` event, GitHub checks the head commit for `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`, `[actions skip]` and a `skip-checks: true` trailer. A skipped workflow leaves its required checks pending, and ruleset 12344707 requires `CI Complete` and `Review Complete`. The PR would be stuck at "Expected" until something else is pushed. On `main`, skipping also skips the release, which is exactly why the bot commits use it.
2. A custom `[no-ci]` would need new wiring in `initialize` to still post `CI Complete` while skipping jobs. That would be a second skip path parallel to the attested scope-engine skip-plan and the pointer-bump fast path (ci-gates.md:336-338), which already make cheap commits cheap in CI.
3. CI runs per push, not per commit, and supersede-cancellation runs only the head. Committing more often costs nothing in CI once pushes are batched (section 1).
4. The local `ci:quick` receipt must be green before any push anyway.

`block_ci_skip_token` therefore refuses all six GitHub forms plus `[no-ci]` in agent commit messages. CD's own bot commits run through subprocess in CI, so the guard never sees them.

## 5. Where the rules are enforced

### 5.1 `commit_policy.py` (T1, frozen API)

- `branch_creations(cmd, root) -> list[Creation(repo_root, name, kind)]`, built on the shared lexer (`shellscan.lifted_commands` / `target_root`, not quote-blind regexes);
- `live_branches(repo_root, gh=True) -> list[str]`;
- `next_branch_name(repo_root) -> str`;
- `commit_message_text(cmd, root) -> str`, lifted from `block_untagged_commit`'s three readable shapes;
- `commit_paths(cmd) -> list[str]`;
- `tags(msg) -> set`;
- `skip_tokens(msg) -> list`;
- `no_review_eligible(paths, cfg) -> (bool, offenders)`;
- `hotfix_ok(msg, paths, cfg) -> (bool, reason)`.

Everything is pure and stdlib-only, so T8's git hooks can import the same code.

### 5.2 `.ci/config/commit-policy.json`

Keys: `no_review_eligible`, `no_review_denied`, `hotfix_max_files` (5), `skip_tokens`, `branch_shape` (`^[0-9]{4}-[0-9]+$`). Each key has a `$comment` citing this plan.

### 5.3 Git-level hooks (T8, decision 2)

- **What exists today:** no `core.hooksPath` (`git config --get-regexp '^core\.'` shows none), no `.githooks`, no husky, no lefthook. `.git/hooks` holds only samples. `scripts/pre-commit-check.sh` is a manual script (PLAN-biome-only-lint.md:46).
- **Proposal:** Python shims in `.claude/rediacc_hooks/git/`:
  - `commit-msg`: tags, skip tokens, `main` needs `[hotfix]`;
  - `reference-transaction`: in the `prepared` state, abort when a `refs/heads/*` creation (old = zero oid) breaks the single-branch rule, using the local check only, no `gh`;
  - `pre-push`: destination checks.

  They are Python because `check_language_policy.py` freezes the set of shell files under `.claude`.
- **Installation:** a new setup phase after `init-submodules.sh` (`.ci/rediacc_ci/setup/phases.py:64`) runs `git config core.hooksPath <abs>` in console and in each submodule. It is local config only, so `/tmp` fixtures and CI checkouts are unaffected.
- **What it adds:** it catches the operator's terminal and `!` commits, and subprocess commits (`worklist.py --git`, Z's `--review-commit`, release scripts run locally). None of these reach PreToolUse.
- **Operator override:** `COMMIT_POLICY_OK=1`, recommended in decision 2.
- **Bypass guard:** `block_git_hook_bypass` (pre-bash) refuses agent use of `commit --no-verify` or `-n`, `push --no-verify`, `-c core.hooksPath=...` and `git config core.hooksPath <value>`. Reads such as `git config --get` and `git log -n 5` are allowed.
- **Which layer rules:** the pre-bash layer stays authoritative for agents, because only it can query `gh` and give rich messages. The git layer is a local-only backstop.

## 6. Tests (T10), in the style of the repo's guard suites

- Every new guard declares `OWN_SUITE = True`, `EDGE_CASES` and a single `DEFECT` tuple. Each gets a `test-<stem>.py` beside it that drives `dispatch.py`, with fixture repos under a `rediacc_ci.runtmp` run directory. `test-block_push_to_protected_branch.py` is the model.
- Each suite includes a DEFECT control: plant `DEFECT` in a copy of the guard and assert that at least one fire case flips to allowed (the pattern at `test_wl_focus.py:683-695`).
- ORDER values 45-49 are appended so the order stays contiguous (the current pre-bash maximum is 44, `block_unsatisfiable_pid_wait`). `test_dispatch.effective_order` checks this.

| Guard | Fire | Inverse | DEFECT planted |
|---|---|---|---|
| block_second_branch | on `0923-1`: `checkout -b 0925-1`, `switch -c 0925-1`, `branch 0925-1`, `push origin HEAD:0925-1`, `push -u origin 0925-1`, `gh pr create --head 0925-1`, `sh -c '...'` wrapped; on `main` with `0923-1` live: `checkout -b 0925-1`; in a submodule: `-b 0925-9` while console is on `0923-1` | on `main` with no live branch: today's MAX+1; `branch -m 0923-1 0925-1`; `branch -d x`; `--show-current`; in a submodule: `-b 0923-1`; a `/tmp` repo; the F1 grep line; a heredoc body | the live-count test → `if False:` |
| block_commit_on_main | on `main`: commit without `[hotfix]`; `[hotfix]` with 6 files; `[hotfix]` without `Hotfix-Evidence`; `[hotfix]` on `0923-1`; `git -C private/account commit` on account `main` | the same commit on `0923-1`; a valid hotfix; a `/tmp` repo | the `main` arm → `if False:` |
| block_ci_skip_token | all 6 GitHub forms plus `[no-ci]`; the trailer form; a `-F` file; a `-F -` heredoc | `echo '[skip ci]'`; `git log --grep`; a `/tmp` repo | token regex emptied |
| block_no_review_ineligible | `[no-review]` with a `.ts` path; with `.claude/commands/x.md`; with CLAUDE.md; with `[hotfix]` | `[no-review]` with `agent/plans/x.md` and `docs/y.md`; an untagged `.ts` commit | eligibility → always true |
| block_git_hook_bypass (T8) | `commit --no-verify`, `commit -n`, `-c core.hooksPath=/dev/null commit`, `config core.hooksPath x`, `push --no-verify` | `config --get core.hooksPath`, `log -n 5`, `commit -F m -- a` | the `-n` arm → `if False:` |

Changes to existing guards and code, each with its golden regenerated through `tests/regolden.py` and the intentional delta written in the commit body:
- `block_nonstandard_branch_name` (F1 case);
- `block_untagged_commit` (a `main`+`[hotfix]` fixture; the no-`[hotfix]` case on `main` still refuses);
- `block_second_open_pr` (message);
- `block_settled_questions` (the message at `:82-97` quotes the old rule 1);
- worklist: the tick arm's `no-commit-ref` refusal and its inverse (`commit:<real sha>`, `nocommit:research`), plus a fabricated sha that must be refused.

## 7. Docs (T9)

- CLAUDE.md:
  - `:15-27` becomes section 1 of this plan;
  - `:19-20` gets the one-PR text;
  - `:372` ("standing default is to land nothing") is rewritten to "commit on the one branch; `main` only for `[hotfix]`, pushed by the operator";
  - `:374` also names `[hotfix]`.
- `.claude/output-styles/standing-orders.md`: `:11-15` and `:33-35`.
- `.claude/commands/pr-merge.md`:
  - `:196-213`: the agent commits `[hotfix]` on `main` and the operator pushes with `!` (F4);
  - `:276-296`: step 7 deletes the merged local branch in every repo; the next cut is `block_second_branch`'s computed name.
- `.claude/commands/pr-babysit.md`:
  - the snapshot and "absorb" text (`:110`) becomes "drain residue: commit by path, by epic";
  - the Current state block (`:13-21`) adds a "live local branches" line.
- `.claude/agents/pr-babysitter.md:83-89`: the snapshot becomes the drain fallback. `:146` stays as is.
- `.claude/agents/gate-author.md:114`, `.claude/agents/media-pipeline.md:319` and `.claude/commands/handoff.md:65`: remove the "stays uncommitted" lines.
- `.claude/skills/pr-epics/SKILL.md`: the cadence and the `commit:<sha>` tick.
- `docs/agent-reference/ci-gates.md`: a new "Commit policy" section covering the tags, the refused skip tokens and the reasons from section 4.3.
- `docs/agent-reference/TRAPS.md:1078` and `docs/ci-overhaul/08-driver-contract.md:119`: re-word the "uncommitted until asked" premise.
- `agent/plans/PLAN-uncommitted-work-exposure-check.md`: re-scope (T6).
- PLAN-per-commit-review.md (T7).
- Memory `feedback_commit_push_backup_no_babysit.md`: the lead updates it to point at the new rule 1.

## 8. The one-time drain of 0923-1 (D0-D10)

**Scope.** The console tree has 342 paths. By area:

| Area | Paths |
|---|---|
| `.claude/rediacc_hooks` | 99 |
| `.claude/oracles` (deletions) | 54 |
| `packages/cli` | 32 |
| `.ci/rediacc_ci` | 31 |
| `packages/www` | 27 |
| `agent/plans` | 23 |
| `.claude/hooks` | 21 |
| scripts, config, docs and the rest | remainder |

`private/account` has 86 paths (50 of them in `web/src`). PR #590 (console) and account #88 are both open on `0923-1`. The branch already has 1008 commits ahead of `origin/main`.

**Timing.** The drain runs **before Z's T2 lands**, so `review_epoch` leaves it out. #590 stays a draft throughout, so the GitHub review does not fire either.

**Rules for every batch:**
- one epic;
- at most 19 files, or a proof line for `block_unproven_bulk_transform`;
- `git add --` the untracked files, then `git commit -F msg -- <paths>`;
- the body lists the verification commands and their exit codes;
- a `PR-TASK:` trailer from agent/pr/0923-1.md (`e87fa3ce`, `24c98380`, `55627c58`, `f8ff8ede`, `e4eaf80b`, `01c7d773`).

**Steps:**
- **D0: preparation.**
  - Put Y's focus mode on `merge`, or confirm no writer is live.
  - Save a backup with `git diff --binary > <scratchpad>/drain-0923-1.patch`, plus the same inside `private/account`.
  - Build an attribution map from each dirty path to its epic, using plan `Owns:` headers, worklist item file lists and round-log "files touched" lists.
  - Paths nobody can attribute go to the operator through `/ask` (decision 7). They are never committed by inference.
- **D1: agent records** (`agent/worklist/*.jsonl`, `agent/reggate/0923-1.jsonl`, `agent/INDEX.md`, `agent/d778be9d`, `agent/ledgers`), under `e87fa3ce`. Verify with `check:ci-plan-folders` and the tree-shape gate.
- **D2: `agent/plans/*.md`** (23 files, two batches). Verify with the `check:ci-plan-*` gates and the prose-style gate.
- **D3: the bash-oracle retirement.** This covers the 54 `.claude/oracles` deletions, the goldens, the guards and the `rediacc_hooks/tests` changes (27), plus `hook-inventory-baseline.json`. It is split by chain into pre-bash, pre-edit, stop and post-bash, each carrying the "sampled and read" proof. Verify with `pytest .claude/rediacc_hooks/tests` (dispatch, wiring, differential, golden drift), every `test-block_*.py`, and `check-hook-integrity`.
- **D4: the stop hook and its context and post-bash hooks** (21 files), under `01c7d773` and the retro work. Verify with `test_wl_cap_wait.py`, `test_wl_focus.py` and the full `test_wl_*.py` suite.
- **D5: CI and gates.** This covers `.ci/rediacc_ci` (31), `.ci/{scripts,config,policy}`, `scripts/{gates,lib,data,ci-runner}`, `package.json`, `package-lock.json` and `biome.json`, under `e87fa3ce` and `55627c58`. Verify with `pytest .ci/rediacc_ci/tests`, `check:ci-lockfile`, and a whole `npm run ci:quick` run in a clean clone at this HEAD.
- **D6: `packages/cli` and `packages/shared`**, under `f8ff8ede` and `e4eaf80b`, split by epic. Verify with the CLI typecheck and vitest.
- **D7: `packages/www`** (27). The epic comes from the D0 map. Verify with the www build and the search-index gate.
- **D8: `docs/` and TRAPS.md.** These are writing only.
- **D9: `private/account`** (86 files), under `e4eaf80b`. Committed inside the submodule on `0923-1` in these batches:
  1. routes, services, dto, db and middleware together with `drizzle/0053_device_code_handoff.sql` and its metadata;
  2. `web/src`, in 3 batches by feature directory;
  3. tests and e2e.

  Verify with account `tsc`, web vitest (640/640), the integration tests and the drizzle migration check.
- **D10: finish.** Commit the console pointer bump for `private/account`. Get the `ci:quick` receipt, push account, then push console. Tick every drain item with `commit:<sha>`.

## 9. Operator decisions (to go through /ask; the recommended option is first)

1. **Hotfix review.** Z reviews hotfixes, and `[no-review]` is refused on `[hotfix]` / hotfixes may carry `[no-review]`.
2. **Git-level hooks.** Install them for everyone, with an operator override `COMMIT_POLICY_OK=1` / pre-bash guards only / git-level with no override.
3. **`[no-review]` eligible set.** Writing only (`agent/**`, `docs/**`, `*.md` outside `.claude/`) / also regenerated artifacts such as locales and search indexes.
4. **Hotfix size limit.** At most 5 files / none.
5. **Push cadence.** Epic milestones, at least every 2 hours, and before a stop with unpushed commits / every commit, which costs a full CI run per push.
6. **Hotfix push.** The operator's `!` only, with the guard unchanged / let agents push `[hotfix]` commits to `main`.
7. **Drain residue nobody can attribute.** Commit it under a new "carried-in residue" epic after an /ask listing / leave it uncommitted and name it in the stop report.
8. **Timing of the drain.** Before Z's T2 lands / after, reviewing it in full.

### Critical Files for Implementation
- /home/developer/console/.claude/rediacc_hooks/guards/block_nonstandard_branch_name.py (the F1 parser to replace; the model for `block_second_branch`)
- /home/developer/console/.claude/rediacc_hooks/guards/block_untagged_commit.py (message readers to lift into `commit_policy`; the F5 exemption)
- /home/developer/console/.claude/rediacc_hooks/guards/block_second_open_pr.py (message change; the one-PR invariant)
- /home/developer/console/CLAUDE.md and /home/developer/console/.claude/output-styles/standing-orders.md (rule 1 replacement)
- /home/developer/console/agent/plans/PLAN-per-commit-review.md (sections 5 and 13, and `uncovered()` for `main` and `[no-review]`)

## Operator rulings (2026-09-25, AskUserQuestion)

- **Decision 2 (git-level hooks): everyone, with the `COMMIT_POLICY_OK=1` override.** T8 is required, not optional; agents are refused `--no-verify` / `-c core.hooksPath=` (`block_git_hook_bypass`).
- **Decision 5 (push cadence): epic milestones, at least every 2 hours of committed work, and before a stop with unpushed commits.**
- **Decision 1 (hotfix review): always reviewed.** `[no-review]` is refused on `[hotfix]`.
- **Decision 7 (unattributable drain residue): the lead analyses and commits it now, pr-babysit style, without showing the list to the operator.** Operator: `I know there are failures right now. We're in transition, acceptable.` The drain (D0-D10) therefore runs immediately, before the guards exist.
- Decisions 3, 4, 6 and 8 take the plan's recommendation: writing-only `[no-review]` set; hotfix limit 5 files; the operator pushes `main` with `!`; the drain runs before Z's T2.

