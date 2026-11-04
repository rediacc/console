# PLAN: worktree lease: detached worktrees from one repo tool, landed by cherry-pick, followed by the Stop hook and collected by GC, with /tmp clones of this origin refused

Status: approved -- operator /ask ASKED:2026-11-04T10:15Z, the four answers under Rulings; worklist #c88e1401; PR-TASK 1f877343.
Depends-On: no-dep -- every box edits files this plan owns; W0 runs first and its recorded decision selects the submodule shape W2 builds. #105d59a7 is absorbed by W13.
Owns: agent/plans/PLAN-worktree-lease.md, .ci/rediacc_ci/dev/worktree.py, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/dev/worktree_spike.py, .ci/rediacc_ci/tests/test_dev_worktree.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/ops/live_proof.py, .ci/rediacc_ci/paths.py, scripts/ci-runner/quick-clone.ts, scripts/ci-runner/lease-seed.ts, .gitignore, .claude/settings.json, .claude/config/effort.json, .claude/rediacc_hooks/lifecycle.py, .claude/rediacc_hooks/commit_policy.py, .claude/rediacc_hooks/git/**, .claude/rediacc_hooks/guards/block_worktree_add.py, .claude/rediacc_hooks/guards/test-block_worktree_add.py, .claude/rediacc_hooks/guards/block_lease_boundary.py, .claude/rediacc_hooks/guards/test-block_lease_boundary.py, .claude/rediacc_hooks/guards/block_origin_clone.py, .claude/rediacc_hooks/guards/test-block_origin_clone.py, .claude/rediacc_hooks/guards/block_settled_questions.py, .claude/rediacc_hooks/guards/block_plan_concurrency.py, .claude/rediacc_hooks/guards/test-block_plan_concurrency.py, .claude/rediacc_hooks/guards/block_agent_cap.py, .claude/rediacc_hooks/guards/block_commit_of_live_writer_file.py, .claude/hooks/stop/wl_core.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/test-wl_worktrees.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_planconc.py, .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/worklist_messages.py, .claude/commands/pr-merge.md, .claude/commands/pr-babysit.md, .claude/commands/writers-now.md, .claude/agents/pr-babysitter.md, CLAUDE.md, docs/agent-reference/ci-gates.md, docs/agent-reference/TRAPS.md, docs/agent-reference/local-env.md, scripts/data/doc-registry.md, .ci/scripts/quality/check_policy_inventory.py, .ci/scripts/quality/check_plan_deps.py, scripts/lib/pins/drivers/npm.ts, .ci/rediacc_ci/tests/test_dev_worktree_lease_walkers.py, .ci/rediacc_ci/tests/test_dev_worktree_lease_gates.py, .ci/rediacc_ci/setup/githooks.py, scripts/ci-runner/run.ts
Owner: d778be9d
Updated: 2026-11-04
First-Seen: 2026-11-04
Priority: P1 -- operator order 2026-11-04: agents need a guided worktree in place of /tmp clones, and nothing today follows or collects one
Concurrency: parallel -- W2, W4, W8 and W10 share `.ci/rediacc_ci/dev/worktree_lease.py` and its test file, so they land one at a time; the hook and guard files overlap other live plans at different lines and `block_plan_concurrency` serializes those writers; W1 moves the root every Stop-hook member reads, so it lands as its own commit before any later box.
Live-Proof: none -- CI and agent tooling only: `surfaces.owns_surfaces` over this Owns list returns no surface, so no live receipt is owed; ruling #11c34df3 (the operator request behind the surface map, closed with its four answers)

## Rulings

Operator /ask, ASKED:2026-11-04T10:15Z, verbatim choices:

- Tree shape and creator: "Detached, repo tool".
- /tmp clones: "Refuse them".
- Landing: "Lead cherry-picks".
- Submodules: "Yes, submodule first".

The order behind them:

> we need a new guided solution to allow worktree and avoid using /tmp based clones. Worktree faster and better... the system doesn't allow multiple branches because I want AI agents avoid making multiple pull requests... the worktree clone should be done with internal python tools and we should also care about cleaning up the worktrees. stop hook should be aware of the existing ones. So, following and GC is needed.

## Measured facts

Read on 2026-11-04 at console 9524cedb8, git 2.53.0, Claude Code 2.1.318. Nothing below was created to measure it: no worktree exists yet, so every timing is W0's job.

- `git worktree list --porcelain` prints the main checkout alone, and `.claude/worktrees/` is empty.
- Harness metadata holds 47 agent metas with `worktreePath`, the newest dated 2026-10-30, each `.claude/worktrees/agent-<id>` on branch `worktree-agent-<id>`.
- `.claude/worktrees/` is ignored only through `.git/info/exclude` (line 11, the harness's `claude-code-runtime` block), not `.gitignore`. `.worktrees/` is in `.gitignore:152`.
- Submodule git directories are `.git/modules/private/<name>`, one level deeper than `.git/modules/*`: renet 123M, account 43M, elite 1.5M, homebrew-tap 1.1M.
- Tracked files: console 10,393 (198.6 MB by `git ls-tree -l`), renet 1,657, account 1,396, elite 12, homebrew-tap 2.
- Unpushed right now: account 7 commits, renet 1. Live branch `1104-1` in console, account and renet. elite and homebrew-tap have no branch checked out.
- `core.hooksPath` is local config in the console and in each `.git/modules/private/*` config, pointing at `.claude/rediacc_hooks/git`. A fresh clone carries none of it.
- `.git/modules/private/renet/config` sets `core.worktree=../../../../private/renet`.
- Console `origin` is a promisor (`remote.origin.promisor=true`, `[blob:none]`); account and renet are not.
- 15 `node_modules` directories to depth 4 hold 96,886 paths: root 36,570, private/account 25,723, private/account/web 14,544, workers/www 5,272, the rest smaller.
- Sizes: root node_modules 993M, `.ci/cache/toolchain` 2.1G, `private/bin` 1.7G, `private/renet/bin` 1.2G, `packages/shared/dist` 8.7M.
- Devices: the checkout and `~/.cache` share device 2096, and `/tmp` is tmpfs on device 118, so `cp -al` from the checkout into /tmp cannot hard-link.
- `writer_cap` is 25 in `agent/plans/QUEUE.md` (operator 2026-10-23); the default is 4.
- `packages/e2e-tests/.env` and `.env.groupb` exist and are ignored.
- Walkers: `paths.walk_tree` prunes `.claude/worktrees` (`.ci/rediacc_ci/paths.py:179`) and 18 gate files use it; 17 files under `.ci/scripts` and `.ci/rediacc_ci/quality` call `os.walk` or `rglob`; 88 files under `scripts/gates` and `scripts/lib` use `readdirSync` or a glob.

## The harness contract

Sources: code.claude.com/docs/en/hooks.md and worktrees.md, fetched 2026-11-04, and the 2.1.318 binary for the input object.

Confirmed by the docs:

- `WorktreeCreate` fires for `claude --worktree`, `EnterWorktree`, subagent `isolation: "worktree"`, workflow agents, background sessions and remote-control. It replaces default git behaviour entirely, `.worktreeinclude` included, and it does not fire for `git worktree add` through Bash.
- Input is the common fields plus `name`: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `name`. The binary builds it the same way (`{...rp(e,pe()),hook_event_name:"WorktreeCreate",name:n}`).
- A command hook prints the path as the last non-empty line of stdout. Any non-zero exit or a missing path fails creation. There is no matcher support.
- An absolute path holding `.` or `..`, or passing through a symlink below the repository root, is refused, as is a `.claude` or `.claude/worktrees` that is a symlink.
- `WorktreeRemove` input adds `worktree_path`. A non-zero exit fails removal while the directory exists; exit 0 counts as removed whether or not anything was deleted.
- The hook does not run for a finished subagent, in the docs' words:

  > When a subagent or a workflow agent finishes, Claude Code keeps the worktree your WorktreeCreate hook made for it and doesn't run your WorktreeRemove hook. Remove those worktrees yourself when the work is done.

- `ExitWorktree` refuses a hook-created worktree unless `discard_changes: true`, which leaves the hook as the last check.
- The harness sweep keeps any worktree without its own marker, hook-created ones included, so nothing but this plan's GC ever removes a lease.
- `${CLAUDE_PROJECT_DIR}` stays at the project root and the input's `cwd` follows the agent (stated for `EnterWorktree` and the desktop app).
- A session or subagent in a worktree is refused an Edit into the main checkout, a Bash cwd in the main checkout, and a git redirect into it (`git -C`, `--git-dir`, `cd`). A plain write by a non-git command is not refused.

Still unverified, each proved live in W5:

- That `name` is `agent-<agentId>` when a hook is configured. Evidence is inference: the binary's `function $4i(e){return`agent-${e}`}`, its slug patterns `/^agent-a[0-9a-f]{16}$/` and `/^wf_[0-9a-f]{8}-[0-9a-f]{3}-\d+$/`, and the 47 metas.
- Whether `agent_id` reaches this hook. The docs give it only to hooks firing inside a subagent, and this one fires before the subagent exists.
- Whether `agent-<id>.meta.json` records `worktreePath` for a hook-made tree.
- That a detached linked tree passes the `Refusing to use <path> as an isolation worktree` check.
- That `CLAUDE_PROJECT_DIR` stays put for a subagent, which the docs state only for the other two routes.
- The hook's time budget. The binary passes `timeoutMs:tu`, whose value was not read, and whether the `timeout` key in settings.json moves it for this event.
- That the isolation checks admit `./run.sh worktree ...` from inside a lease, whose git runs in a subprocess the command text does not show.

## What the code refuted

Each entry is a claim the design started from, and what replaces it.

- **scripts/ci-runner/quick-clone.ts:182-237 does not use `--reference`.** It sets `submodule.<name>.url` to the live submodule in the clone's config (:220), runs `submodule update --init --no-fetch` (:221-234), and fetches `+refs/heads/*` from the live submodule (:186). `git submodule update --reference` would still clone from the URL, so an unpushed gitlink needs a fetch anyway.
- **That recipe cannot be copied into a linked tree.** A linked worktree shares the common `config`, so `git config submodule.<name>.url` at :220 and :237 would rewrite the LIVE console's config while every other session reads it. W0's two candidates avoid it: a submodule worktree, or a direct `git clone --shared` into the lease path.
- **The same sharing reaches `info/exclude`.** quick-clone's `syncCaches` appends to `<git-dir>/info/exclude` (:381-391). In a lease that file is the live one. The three lines are anchored and harmless there, W2 adds them once, and the box says so.
- **`--reference to .git/modules/*`** names the wrong level: the stores are `.git/modules/private/<name>`.
- **"The hook gets only `name`."** It also gets `session_id`, `transcript_path` and `cwd`. The owner session comes from `session_id`, and only the agent id rests on the slug.
- **`WorktreeRemove` as the cleanup path for writers.** It never runs for a subagent or workflow agent. GC is the only remover; `gc-hook` exists for `ExitWorktree` and session exits, and its refusal is the last check on that route.
- **`status --porcelain` empty as a GC test.** Submodule-first landing leaves the lease's own gitlink behind its submodule, so the console row ` M private/renet` shows forever. GC reads `--porcelain=v2` and excuses a gitlink row only when its field is `SC..` (commit moved, nothing modified, nothing untracked); the submodule is then judged on its own.
- **`git cherry` as the whole landed test.** Patch-id differs for a commit whose landing needed conflict resolution, and for any console commit touching a gitlink whose submodule commit was rewritten. W8 adds `cherry-pick -x`, and a source sha counts as landed when `(cherry picked from commit <sha>)` is in the live history or on main. W7 keeps gitlinks out of writer commits, so the second case does not arise.
- **`git worktree remove` as a backstop.** Its manual says unclean worktrees "or ones with submodules" need `--force`, and every console lease has gitlinks in its index. Git's own cleanliness check therefore never runs here, so the GC predicate is the only protection.
- **`git worktree list --porcelain` covering submodules.** It sees a submodule tree only under candidate A. Under candidate B a submodule clone is on no list, so `wl_worktrees` walks lease records and checks each submodule path by `git -C`.
- **.claude/rediacc_hooks/guards/block_second_branch.py:195 seeing the pin.** It never does: `push_destinations` drops every `refs/` destination outside `refs/heads/` (.claude/rediacc_hooks/commit_policy.py:488), `_created_heads` skips it (.claude/rediacc_hooks/git/githooks.py:170), and pre-push skips it (.claude/rediacc_hooks/git/githooks.py:440). `git push origin refs/worktrees/x` passes all three, so W7 adds an explicit refusal at both layers.
- **.claude/rediacc_hooks/guards/block_second_branch.py:189 as the extension point for clones.** That loop runs over `branch_creations`, and `git clone` yields no Creation, so it is never reached. The clone refusal is a sibling guard. The clone also closes a real hole: line 189 skips any repository outside the checkout, so a /tmp clone can cut a second branch and push it today.
- **`wl_scratch.git_doubt` as the unlanded test.** It runs `rev-list HEAD --branches --not --remotes` (.claude/hooks/stop/wl_scratch.py:183). A lease's work is judged against the local live branch, which holds unpushed commits right now, so this reads every landed commit as undelivered. `lease_texts`, `lease_holder`, `process_cwds`, `_remove`, `tree_facts` and the `--no-optional-locks` rule carry over; `git_doubt` does not.
- **`process_cwds` as liveness.** A subagent's shell does not live between its tool calls, so an empty cwd list does not prove a writer has finished. The verified worker comes from `wl_roster`; cwd stays as one more reason to keep.
- **Worklist redirect for every linked tree.** A session in an operator's `.worktrees/<MMDD-N>` has its own branch and rightly its own store (.claude/hooks/stop/wl_store.py:752 says so about the journal). The redirect applies only under `<main>/.claude/worktrees/`.
- **A verb that performs the cherry-picks.** `review_commit.py` fires on `git cherry-pick` at a command position in the Bash text, so a verb running it in a subprocess starts no review. `land` prints the lines and the lead runs them.
- **Docs the brief did not list.** CLAUDE.md rule 1 says "Writers never commit", which the landing ruling reverses. `.claude/rediacc_hooks/guards/block_worktree_add.py:1181` tells agents to prefer "a plain `git clone`", which the clone ruling refuses. TRAPS.md `stale-isolated-worktree-base` and .claude/agents/pr-babysitter.md:85 describe the old world. W14 carries all four.
- **#105d59a7's lease.** Its only lease (2026-11-04T10:16Z, worker `af8782a8f8ae756ca`, "auto-lease: named by live task") is the worker of #c88e1401's "plan draft" lease, so it appears to come from this draft's brief naming the id. No commit on the branch mentions it and `wl_planconc.py` and `block_plan_concurrency.py` are clean. W13 owns the fix.

## Design

### 1. The verbs

`./run.sh worktree <verb>`, in `.ci/rediacc_ci/dev/worktree_lease.py`, dispatched from `COMMANDS` in `worktree.py`:

- `lease [--name <slug>] [--owner <id8>]`: make one tree and print its absolute path as the last stdout line, everything else on stderr.
- `leases [--json]`: every lease with owner, base, dirty count and unlanded commits per repo.
- `land <id>`: read-only. Check each unlanded commit has a `PR-TASK:` trailer, touches no gitlink and no `agent/**`, and print the exact `git cherry-pick -x` and gitlink commit lines, submodules first.
- `gc [--write] [--id <id>]`: list by default; `--write` deletes what passes every rule.
- `lease-hook` and `gc-hook`: the `WorktreeCreate` and `WorktreeRemove` entries, reading the hook's JSON on stdin.
- `pin`: move the pin for the tree it runs in; the `post-commit` shim calls it.

The name passes today's guard: `.claude/rediacc_hooks/guards/block_worktree_add.py:135` and `RUN_SH_CREATE` (:53) match only `create`, and `PHRASE_VERB` (:655) only `add|create`. The guard does not read `run.sh` while it is tracked and unchanged. `python3 .ci/rediacc_ci/dev/worktree.py lease` is refused while that file is modified, by the "script" arm the guard documents at :654, so `./run.sh` is the one spelling a box's accept uses.

### 2. The tree

Path `<main>/.claude/worktrees/<id>`, returned realpath-normalized because the harness refuses anything else. `id` is the hook's `name`, or `<owner>-<n>` from the CLI.

1. **Cap first.** `wl_roster.writer_cap(root)` against the trees on disk, finished and unlanded ones included, because an unlanded tree is the pressure to land. A refusal names `./run.sh worktree gc`. `.ci/rediacc_ci/proof/surfaces.py` already imports a Stop-hook module, so the import is not a new shape.
2. **Console.** `git worktree add --detach <path> <tip>` where tip is the live branch's commit, or `main` between branches. Uncommitted work in the main tree is not in it, by definition.
3. **Lock it.** `git worktree lock --reason lease:<id>`, so `git worktree remove --force` and `git worktree prune` refuse without `-f -f`. The harness sweep never releases a lock it did not set.
4. **Submodules at the gitlinks of tip**, shape per W0, with `core.hooksPath` set when the shape does not share config. A gitlink on an unpushed local commit must resolve.
5. **Seed**, by one TS entry `scripts/ci-runner/lease-seed.ts` calling quick-clone's exported `syncDependencies`, `syncBuilds` and `assertNoSelfLoop`, not a Python port of `lockDifference`:
   - `cp -al` for each `node_modules`, because a symlinked root resolves `@rediacc/shared` to the live tree (scripts/ci-runner/quick-clone.ts:12);
   - `ln -sfn` for `.ci/cache/toolchain`, `.ci/cache/bin`, `.venv`;
   - `cp -al` for `private/renet/bin` and `private/bin`;
   - `packages/shared/dist` copied when `git status --porcelain -- packages/shared` is empty in the main tree, built in the lease otherwise, since a live `dist` from dirty source would judge the wrong code;
   - `packages/e2e-tests/.env*` copied with their modes.
6. **No devbox, no tmux, no branch.**
7. **Record.** `<common-dir>/rediacc-worktrees/<id>.json` with id, path, owner session, agent id, base per repo and created-at. It sits beside the git data as the worklist journal does (.claude/hooks/stop/wl_store.py:752), untracked and shared. The plan and item are read lazily from the agent's first prompt through `wl_leasehelp.first_prompt`, as `wl_planconc.live_plans` does.

Two hazards follow from the location, which quick-clone refuses for its own clone (scripts/ci-runner/quick-clone.ts:6, :474-476):

- **Upward resolution.** A package missing from a lease's `node_modules` resolves upward to the live `<main>/node_modules`. Every member directory the live tree has installed is seeded, and W2's control proves resolution stays inside.
- **Walkers.** ci:quick runs in a clean clone without `.claude/worktrees`, so the quick lane is immune. A run in the live tree, such as `npm run ci -- --narrow`, is not. W3 sweeps the walkers.

`.claude/worktrees/` also joins `.gitignore`, because the `.git/info/exclude` line is the harness's and machine-local.

### 3. Commit, pin, land

- A writer commits on the lease's detached HEAD with the usual pathspec form and never pushes. `block_untagged_commit` allows a detached checkout with no epic check (:309), so `land` checks the trailer instead.
- The new `post-commit` shim pins `refs/worktrees/<id>` to HEAD, in the shared console refs and in the live submodule store. Under candidate B that means `git -C <live module> fetch <lease sub> +HEAD:refs/worktrees/<id>`.
- Plural on purpose: the manual's per-worktree refs are `refs/bisect`, `refs/worktree` and `refs/rewritten`. The singular spelling would die with the tree, and a W4 control pins this.
- The pin moves only forward. On a non-ancestor it stays put and HEAD counts as a second tip, which GC never removes silently. `block_destructive_git_restore` and `block_git_amend` already refuse the usual ways there.
- A pin is visible to `git log --all` readers (`.ci/scripts/quality/check_plan_record.py:1238`, `.claude/hooks/stop/wl_planrec.py:946`). A blob cited only from an unlanded commit would resolve in the main checkout and fail in CI's transport clone, so a W4 control writes that down. Neither `git clone --local` nor quick-clone's fetch refspecs carry `refs/worktrees/*` into a clone.
- The lead spot-checks, then runs what `land` prints: for each submodule in order, `git -C private/<name> cherry-pick -x <sha>...` on its live branch, then `git add -- private/<name>` and `git commit -F <msg> -- private/<name>` in the console, then the console's own picks. A submodule with no live branch gets the console's name first, which `_judge_local` admits.
- Hypotheses W8 proves: cherry-pick refuses when the index differs from HEAD, so a peer's staged path holds the landing rather than riding it; `-x` keeps the `PR-TASK:` trailer parseable.
- **Reviews.** `wl_review.trigger` returns nothing without a branch (:1212), so a lease commit starts no review, and the lead's typed `git cherry-pick` starts one per landed commit. `max_spawn_per_trigger` is 5, so a larger landing drains on the next trigger or through `--review-run`.

### 4. One store

`wl_core.project_root` resolves a `.git` FILE pointing at `<common>/worktrees/<id>` to the main checkout when the tree sits under `<main>/.claude/worktrees/`, by reading `<git-dir>/commondir`, with no subprocess on this hot path. The docstring's warning about `/modules/` stays true because the rule keys on `worktrees/` plus `commondir`. The twins `_local_project_start` and `_local_worklist_path` in worklist.py move in lockstep, as their docstrings demand.

The sweep of sibling writers:

| Writer | Reaches its root through | From a lease after W1 |
|---|---|---|
| `wl_store.store_dir`, `agent_root`, STATE.md | `project_root` | main |
| `wl_review` `agent/reviews` (:236-245) | root argument | main |
| `wl_planqueue` QUEUE.md (:30) | root argument | main |
| `wl_outcomes`:36, `wl_hints`:143, `wl_retro`:241, `wl_claimcheck`:453, `wl_effort_tune`, `wl_liveproof`:54 | root argument | main, a W1 test per writer proves it |
| `block_turbo_early_push`:673, `block_backup_unverified_push`:409 | `CLAUDE_PROJECT_DIR`, else show-toplevel | main, W5 confirms the variable |
| `live_proof.py`:698, `live_tier.py`:31 | `paths.repo_root()`, file-derived | refused from a lease (W9) |
| `wl_store` journal (:752) | `--git-dir`, per checkout on purpose | unchanged |
| `.ci/cache/*`, receipts | the tree | per tree on purpose |

### 5. Harness route

`.claude/settings.json` gains `WorktreeCreate` and `WorktreeRemove`, entries in `lifecycle.PATTERNS`, and a regenerated CLAUDE.md hook table. Every route the contract lists then lands on one tool, including `EnterWorktree` and `isolation: "worktree"`, which today reach `git worktree add` where `block_worktree_add` cannot see them. An operator's `claude --worktree` gets a detached lease too; `! git worktree add` and `./run.sh worktree create` stay the operator's way to a real second checkout.

The owner is `session_id`. The agent id is taken from `name` matching `agent-<id>`, and is empty when it does not match. A later stop fills it from the metas' `worktreePath` when W5 shows the harness records one, and the tree stays attributed to the session either way.

`gc-hook` runs the GC predicate on `worktree_path` and exits non-zero on anything unsafe, because exit 0 counts as removed.

### 6. Guards

- **`block_worktree_add`.** `create` and `git worktree add` stay refused. New arm: `git worktree remove|move|prune|lock|unlock` naming a path under `.claude/worktrees`, so a tree leaves only through GC. The edge control at :1276 keeps `/tmp/wt` allowed. Messages at :1175-1203 stop recommending a clone and name `./run.sh worktree lease`.
- **`block_lease_boundary`**, new, pre-bash, active only when the command's repo is a lease tree or a submodule of one. Refuses `git push`, `gh pr`, `git switch`, `git checkout <branch>`, `git branch <new>`, `git cherry-pick`, `git rebase`, `git worktree *`, and a `git commit` whose staged set holds a gitlink or `agent/**`. `git switch main` is the case that matters, since `main` is checked out nowhere when the live branch is. A git-level arm in `pre-commit` and `pre-push` backs it for subprocesses.
- **`pre-push`** refuses any `remote_ref` under `refs/worktrees/` from every repo, because a pin never leaves the machine.
- **`block_origin_clone`**, new, pre-bash. Refuses `git clone` and `gh repo clone` whose source normalizes to an origin or mirror of the console or a submodule, or to a local path inside this checkout or its git directory, wherever the target is.
  - The target-independence widens the literal "/tmp" of the ruling: `git clone <ours> ~/x` is the same second tree, and a /tmp-only test is refused by moving one directory over.
  - `git init` plus `git fetch <ours>` is the same act and has the same arm.
  - It reads program text through `block_worktree_add.interpreter_programs`, drawing the same edge: a string built at run time is out of reach, and that is stated in the docstring.
  - Allowed: a source with no origin of ours (a fixture repository or an unrelated URL).
  - Structurally untouched: ci:quick's clone under `~/.cache/rediacc/ci-quick-clones`, and test harnesses, whose `git clone` runs in a subprocess no PreToolUse hook sees. W6 proves it by running them.
  - A diagnosis that really needs a pristine clone is the operator's `!`. docs/agent-reference/TRAPS.md:1743 already reproduces CI's object set with `git rev-list --objects HEAD` and no clone.
- **`block_settled_questions:61-64`.** The routing regexes stay, because the question remains settled: the lead stays in the main checkout and writers get leases through /writers-now. Its docstring and the text at :219 change, and an edge case pins "Should this writer get a lease?" as refused.

### 7. Stop hook

`.claude/hooks/stop/wl_worktrees.py` enumerates `git worktree list --porcelain` in the console and each submodule store, plus records and pins, and joins them:

- `worktree-unlanded` (block, owner session only): a lease of this session with no live writer, and dirty paths or unlanded commits. It names `land` and `gc`.
- `worktree-orphan` (advisory): a tree with no record, a record with no tree, or a pin with neither.
- A peer's leases are one reported line each and never block, the rule for peer items.
- `wl_roster` supplies liveness and `lease_holder` matches a worklist `[>]` item. Status runs with `--no-optional-locks`, for the reason `.claude/hooks/stop/wl_scratch.py:171` records. Full figures are computed for this session's leases, and only when HEAD or the index moved since the last stop, so a stop with 25 leases does not spend its budget on 125 `git status` calls.
- Both keys register in `.claude/config/effort.json`, which the effort-table rule enforces. A wind-down phase changes nothing about them, since a lost commit is not hygiene.

### 8. GC

A tree is removed automatically only when every rule holds:

1. its realpath is a direct child of `<main>/.claude/worktrees`, and `.worktrees/` is never touched;
2. no live lease or verified worker holds it and no process has a cwd in it;
3. `--porcelain=v2` is empty in the tree and in every submodule, except a gitlink row of field `SC..`;
4. for each repo, every commit in `git cherry <live tip> <pin>` and in `<live tip>..HEAD` is landed by patch-id or by its `-x` line.

Otherwise it is listed with the failing rule and asked about, per `.claude/commands/pr-merge.md:86-90`: byte-identical or superseded content is safe, and anything else is reported, never deleted. The ask is a `[?]` with `DEFAULT: keep the tree and report it`, because a `[?]` default executes and deletion must never be one.

Removal order: unlock, the submodule trees, then `git worktree remove --force` once the predicate has passed, then delete pins and record. `--force` is unavoidable (see the refutations), so the predicate is the only guard.

**Ignored files.** `git status --porcelain` does not show them, so rule 3 cannot see them. Everything the seed made is ignored and rebuildable, and removing a hard link costs only the name. A writer's own ignored output, such as a log, a `.ci/cache` run or an edited `.env`, dies with the tree. That is the decision `.claude/hooks/stop/wl_scratch.py:16` made for clones: every tree that ran a test holds ignored output, so keeping on it would keep every tree. The GC listing says so on its summary line, and the brief tells writers that a result worth keeping goes in the report or a commit.

### 9. Gates

Full gates run only in the main checkout at landing: `ci:quick` and `vm:check`, the receipts the push guards read. From a lease, `ci:quick` is refused in `routeOf`, since `cloneDirFor` keys on the checkout path and would make a new kept clone for every lease. `vm:check` is refused because it restarts the shared dev gateway. `npm run ci -- --narrow` and named tests stay allowed: they write no receipt.

### 10. Writers and concurrency

`/writers-now` spawns each writer with `isolation: "worktree"`, including siblings of one plan. Its step-2 paragraph (.claude/commands/writers-now.md:34) and step 4 (:42) are rewritten: the measured reason there, a tree cut from `origin/main` with empty submodules, is gone. The brief gains four lines: commit on the detached HEAD, never push, no `agent/**`, no gitlink. Writer boxes tick only after the lead lands, so rule 1's `commit:<sha>` names the landed sha.

`block_plan_concurrency` judges `Owns`, not cwd, and that stays its input. What changes is the verdict for an isolated spawn. The `overlap` refusal becomes a stderr note naming the witness path, because two trees cannot corrupt each other and a clash now surfaces as a cherry-pick conflict at landing. The `mutex` refusals stay: an `exclusive` plan's reason is usually a regeneration whose result is wrong against concurrent changes, wherever it runs. A spawn without isolation is judged as today.

`wl_roster.edit_paths` and `block_commit_of_live_writer_file` drop paths under `.claude/worktrees/`, because a writer's edits there are not dirt in the main tree.

Same-message blindness (#105d59a7) belongs here: /writers-now starts everything in one message, so the mutex and the cap both rely on seeing siblings the Stop event cannot list yet. An admitted spawn appends a short-lived claim under `flock`, with read, decide and append inside one lock, and the next pre-agent call counts it. Whether the harness runs same-message PreToolUse hooks in parallel is not known, and the lock makes either order safe.

### 11. Docs that change together

All in W14, as the last box, so the rules never describe a tool that has not landed:

- CLAUDE.md lines 7-8, the worktree warning.
- CLAUDE.md rule 1 "Writers never commit" and its review-record sentence, and rule 4 on disjoint ownership in the main tree.
- `.claude/rediacc_hooks/guards/block_settled_questions.py:61-64` context (W6 scope in section 6).
- `.claude/commands/pr-babysit.md:76`, `.claude/commands/writers-now.md:34,42`.
- `.claude/commands/pr-merge.md:82-83` (it teaches `git worktree remove --force`), `:95`, whose `.claude/hooks/pre-bash/block-worktree-add.sh` no longer exists; the guard is `.claude/rediacc_hooks/guards/block_worktree_add.py`.
- `.claude/agents/pr-babysitter.md:85`.
- `docs/agent-reference/ci-gates.md:543` and the guard table, `local-env.md`.
- TRAPS.md `stale-isolated-worktree-base` (closed by the hook) and a new entry for the shared-config hazard.

Memory entries `feedback_scratch_clone_symlink_ln_sfn.md` and `feedback_worktree_diff_deletions.md` go stale once W6 lands; they live outside the tree, so the lead updates them.

## Tasks

- [x] W0 [lead] Spike: submodule worktrees against shared clones, timed, with a recorded decision. Changes: `.ci/rediacc_ci/dev/worktree_spike.py`, committed before it runs because `block_worktree_add` refuses an untracked script naming the phrase (:654). It builds a throwaway lease on the real tree two ways. Candidate A: `git -C .git/modules/private/<name> worktree add --detach`. Candidate B: `git clone --shared --no-checkout <module> <lease>/private/<name>`, then detached checkout of the gitlink. For each it records wall time per step (console tree, each submodule, seed), disk delta and inode delta, and answers: does an unpushed gitlink check out; is `core.worktree` ignored in a linked submodule tree; does `git status` in the console lease read the gitlink; does `commit_policy.superproject` name the lease; does `core.hooksPath` apply and fire; can a pin reach the live store; does `git submodule status` work; does removal leave the live module's `git fsck` clean. Also times `node_modules` `cp -al` for all 15 directories.
  Decision rule: A unless any answer fails or its time exceeds B's by more than 2x; the decision, table and raw numbers go into Verification notes. Removal of its own trees is part of the run.
  Owns: .ci/rediacc_ci/dev/worktree_spike.py, agent/plans/PLAN-worktree-lease.md. Accept: `python3 .ci/rediacc_ci/dev/worktree_spike.py --fixture` rc 0 with a planted missing gitlink going rc 1, then `python3 .ci/rediacc_ci/dev/worktree_spike.py --live` rc 0, `git worktree list --porcelain` showing only the main checkout afterwards, and a `Decision:` line in Verification notes.
    (ticked) 2026-11-04T11:06:51Z by d778be9d: commit:6192506930a --fixture rc=0, --plant-missing-gitlink rc=1, --live rc=0, only the main checkout listed after, no refs/worktrees, Decision: A at line 307

- [x] W1 [writer] One store from a lease tree. Changes: `project_root` and both worklist.py twins per Design 4; a test per writer in the sweep table.
  Owns: .claude/hooks/stop/wl_core.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/test-wl_worktrees.py. Accept: `python3 .claude/hooks/stop/test-wl_worktrees.py root` rc 0 with these controls: from a fixture lease's own copy of worklist.py, `--add` appends to the main store and the copy's store stays byte-identical (with the rule removed this goes red); a fixture `.worktrees/0128-1` keeps its own store; a `.git` file into `modules/` is unchanged; `$WORKLIST_STORE_DIR` still wins; `wl_core.project_root` starts no subprocess, asserted by a `subprocess.run` that raises. Also `python3 .claude/hooks/stop/worklist.py --path` rc 0 printing the same path as before the change in the main tree.
    (ticked) 2026-11-04T11:08:51Z by d778be9d: commit:b545e01be test-wl_worktrees.py root rc=0, 63 controls; --path rc=0 unchanged; the rule-removed case is the suite's own control

- [x] W2 [writer] `lease`, with the tree of Design 2. Changes: `worktree_lease.py`, the dispatch in `worktree.py`, `scripts/ci-runner/lease-seed.ts`, the `.gitignore` line and the exclude lines, submodule shape per W0.
  Owns: .ci/rediacc_ci/dev/worktree.py, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, scripts/ci-runner/lease-seed.ts, .gitignore. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease.py -k lease` rc 0, whose fixture has a submodule on a local-only commit, asserting: HEAD detached at the live tip; submodule at the gitlink; console `.git/config` byte-identical before and after (the shared-config control, red with quick-clone's `git config submodule.<name>.url`); `status --porcelain` empty; `@x/shared` resolving inside the lease; a package absent from the lease not resolving to the live `node_modules`, or the seed refusing; a `writer_cap` of 1 refusing the second lease; last stdout line a normalized absolute path; `refs/heads` unchanged; `--help` touching nothing. Then `./run.sh worktree lease --name w2-proof` rc 0 on the real tree, `npm test` rc 0 in its `packages/shared`, and the tree left in place for W10's real run to collect.
    (ticked) 2026-11-04T11:32:24Z by d778be9d: commit:d52243fab lease tests 30 passed; test_dev_worktree 59 passed; ./run.sh worktree lease --name w2-proof rc 0; npm test in its packages/shared 893 passed; refs/heads unchanged

- [x] W3 [writer] Walkers. Changes: a survey of the 17 raw walkers and 88 TS walkers for a root-anchored walk reachable from a live-tree run; those found move to `paths.walk_tree` or its TS twin, or carry a reason why the prefix cannot occur. The survey also names any gate already enforcing the walker rule, and no new gate is added where one exists.
  Owns: .ci/rediacc_ci/paths.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, agent/plans/PLAN-worktree-lease.md, and the walker files the survey names, added to the header with `check_plan_deps.py --set-x` before they are edited. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease_walkers.py -k walkers` rc 0, which plants a marker file at `.claude/worktrees/x/marker` in a fixture and runs the surveyed entries over it, asserting none reports the marker; a raw `os.walk` control reports it, so the instrument can fail. The survey table goes in Verification notes.
    (ticked) 2026-11-04T11:59:06Z by d778be9d: commit:7d612a0b1 commit:5c7d228f7 pytest test_dev_worktree_lease_walkers.py -k walkers rc=0, 7 passed, raw os.walk and glob controls report the marker, red with the prune removed rc=1. Survey table in Verification notes, test file named there

- [x] W4 [writer] Pins. Changes: `.claude/rediacc_hooks/git/post-commit`, the `pin` verb, forward-only movement.
  Owns: .claude/rediacc_hooks/git/**, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease.py -k pin` rc 0 with controls: a commit in a fixture lease moves `refs/worktrees/<id>`, visible from the main checkout and from another lease; the singular `refs/worktree/<id>` is not visible from the main checkout, the reason for the spelling; after `git worktree remove --force` the commit still resolves through the pin and survives `git gc --prune=now`; `reference-transaction` does not refuse the pin; a commit in the main checkout moves nothing; a non-ancestor HEAD leaves the pin in place; a pin-only blob is visible to `git log --all --find-object`, unreachable in a `git clone --local` and absent from a `--no-local` clone, the recorded limit.
    (ticked) 2026-11-04T11:59:05Z by d778be9d: commit:2d3491e31 pytest test_dev_worktree_lease.py -k pin rc=0, 14 passed: pin moves and is seen from main and another lease, singular ref unseen, survives remove plus gc --prune=now against an unpinned control, reference-transaction admits it, a main commit moves nothing, a non-ancestor HEAD leaves it. The blob clause corrected in Verification notes: --local hard-links objects, so absence holds for reachability and for --no-local

- [ ] W5 [lead] The harness route, proved live. Changes: `WorktreeCreate` and `WorktreeRemove` in `.claude/settings.json`, `lifecycle.PATTERNS`, `lease-hook`, `gc-hook`, with a temporary input log under `.ci/cache/` for one run. Each item under "Still unverified" gets its answer in Verification notes.
  Owns: .claude/settings.json, .claude/rediacc_hooks/lifecycle.py, .ci/rediacc_ci/dev/worktree_lease.py, CLAUDE.md, scripts/data/doc-registry.md, agent/plans/PLAN-worktree-lease.md. Accept: `npx tsx scripts/gen/gen-docs.ts --write` then `npm run check:ci-doc-region-parity` rc 0; a real `Agent` spawn with `isolation: "worktree"` whose report prints `git rev-parse HEAD`, `git branch --show-current` (empty), `git submodule status` and `readlink -f node_modules/@rediacc/shared`, compared by the lead with the live tip; a `lease-hook` given a cap-exceeded fixture exits non-zero and the spawn fails with the message; `gc-hook` on a dirty fixture exits non-zero with the directory intact; `gc-hook` on a clean one exits 0 with the directory gone.

- [x] W6 [writer] Refuse clones of this origin. Changes: `block_origin_clone.py` and its suite; its arm for `git init` plus `git fetch`; the `block_worktree_add` messages and remove arm.
  Owns: .claude/rediacc_hooks/guards/block_origin_clone.py, .claude/rediacc_hooks/guards/test-block_origin_clone.py, .claude/rediacc_hooks/guards/block_worktree_add.py, .claude/rediacc_hooks/guards/test-block_worktree_add.py, .claude/rediacc_hooks/guards/block_settled_questions.py. Accept: `python3 .claude/rediacc_hooks/guards/test-block_origin_clone.py` rc 0, each driven through the dispatcher. Refused: `git clone https://github.com/rediacc/console.git /tmp/x`, the `.git` and ssh spellings, each submodule URL, the gitlab mirror, `git clone --shared /home/developer/console /tmp/x`, `git clone .git/modules/private/renet ~/x`, `gh repo clone rediacc/console`, `sh -c` and `python3 -c` wrappers, `git init /tmp/x && git -C /tmp/x fetch <ours>`. Allowed: `git clone /tmp/fixture /tmp/y`, an unrelated URL, `echo git clone <ours>`, a heredoc body. With the guard's DEFECT planted, the suite goes red. Then the new suite `python3 .claude/rediacc_hooks/guards/test-block_worktree_add.py` rc 0 with `./run.sh worktree lease` allowed and `git worktree remove .claude/worktrees/x` refused, `npm run check:ci-guard-mention-anchoring` rc 0, and the structural proof with the guard live: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 (its quick-clone section makes real clones) and `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree.py` rc 0.
    (ticked) 2026-11-04T11:59:07Z by d778be9d: commit:d52243fab commit:fbe4c4495 commit:7180e35b5 test-block_origin_clone.py rc=0, test-block_worktree_add.py rc=0 with lease allowed and remove refused and plants flipped, check:ci-guard-mention-anchoring rc=0, run.ts --selftest rc=0, test_dev_worktree.py 59 passed

- [x] W7 [writer] The lease boundary. Changes: `block_lease_boundary.py` and suite, the git-level arms in `githooks.py` for gitlink and `agent/**` commits from a lease and for any `refs/worktrees/` push.
  Owns: .claude/rediacc_hooks/guards/block_lease_boundary.py, .claude/rediacc_hooks/guards/test-block_lease_boundary.py, .claude/rediacc_hooks/git/**, .claude/rediacc_hooks/commit_policy.py. Accept: `python3 .claude/rediacc_hooks/guards/test-block_lease_boundary.py` rc 0. Refused from a fixture lease: `git push origin HEAD:1104-1`, `git push origin refs/worktrees/x`, `git push origin HEAD:refs/worktrees/x`, `gh pr create`, `git switch main`, `git switch -c x`, `git checkout 1104-1`, `git cherry-pick`, a commit staging a gitlink, a commit staging `agent/plans/x.md`. Allowed there: `git commit -F m -- src/x.ts`, `git status`, `git log`. The same commands from the main checkout are not this guard's business. The git-level arm has its own control: a subprocess `git push` of a pin is refused by the `pre-push` shim with `COMMIT_POLICY_OK` unset. DEFECT planted, suite red.
    (ticked) 2026-11-04T11:32:25Z by d778be9d: commit:d52243fab test-block_lease_boundary.py rc 0, 50 refused and 64 allowed; --plant-defect rc 1; test_dispatch and githook suites 141 passed

- [ ] W8 [writer] `land`, and landed detection. Changes: the `land` verb, the `-x` plus patch-id reader in `worktree_lease.py`.
  Owns: .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease.py -k land` rc 0 in a fixture with a submodule and a console commit: the printed lines run as printed land the submodule first and re-bump the gitlink; the source sha reads landed afterwards by patch-id; a conflict-resolved pick reads landed by its `-x` line and not by patch-id, with `git cherry` alone reading it unlanded, the control for why `-x` exists; a commit with no `PR-TASK:` trailer makes `land` exit 1; a `PR-TASK:` trailer stays readable by `git interpret-trailers --parse` after `-x`; a peer's staged path makes the cherry-pick refuse with the path unmoved; a rebase of the live branch keeps the source reading landed.

- [x] W9 [writer] Gates only at landing. Changes: `routeOf` refuses a lease; `vm_check.py` and `live_proof.py` refuse from a lease with the reason.
  Owns: scripts/ci-runner/quick-clone.ts, .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/ops/live_proof.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py. Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 with the new quick-clone control that a linked lease checkout routes to a refusal and creates no directory under `ci-quick-clones`, and a control that the main checkout still routes to the clone; `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease_gates.py -k gates` rc 0 with `vm_check` and `live_proof record` refused in a fixture lease and running to their usual arg error in the fixture main tree; `npm run ci -- --narrow --list` rc 0 inside a lease.
    (ticked) 2026-11-04T11:59:08Z by d778be9d: commit:6ef4aa335 commit:da41ab617 run.ts --selftest rc=0, pytest test_dev_worktree_lease_gates.py -k gates 9 passed rc=0 (file named in Verification notes), npm run ci -- --narrow --list rc=0 inside the fresh lease w9-seed

- [ ] W10 [writer] GC. Changes: `gc` and its predicate, `leases`, reuse of the `wl_scratch` helpers named under the refutations.
  Owns: .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_dev_worktree_lease.py -k gc` rc 0, one tree per rule, each listed KEEP with its rule and left byte-identical under `--write`: a dirty tree, a dirty submodule, an untracked file, an unlanded commit, an unlanded submodule commit, a live lease, a live cwd, a path outside `.claude/worktrees`, a symlink, a `.worktrees/` tree. One tree passes in spite of an `SC..` gitlink row and is deleted only with `--write`; without it, the listing changes nothing. An ignored file does not keep a tree and the summary line says so. A pin of a removed tree with landed commits is deleted, with unlanded commits kept. Hard-link control: a `node_modules` file's content and link count in the main tree are unchanged after removal.

- [x] W11 [writer] The Stop hook follows leases. Changes: `wl_worktrees.py`, the `worktree-unlanded` and `worktree-orphan` keys, the effort entries, the message lines.
  Owns: .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/test-wl_worktrees.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/config/effort.json. Accept: `python3 .claude/hooks/stop/test-wl_worktrees.py stop` rc 0: an owner's finished lease with an unlanded commit blocks and names `land`; the same lease is one report line and no block for a peer session; a lease with a live writer does not block; a tree with no record and a pin with no tree each produce the advisory; the status probe leaves the lease's `.git` index mtime unchanged; a second stop with nothing moved runs no `git status`, asserted by a counting stub. `npm run check:ci-plan-record` rc 0 for the effort-table rule, red with a key removed from effort.json.
    (ticked) 2026-11-04T11:35:19Z by d778be9d: commit:6ef4aa335 test-wl_worktrees.py stop rc 0 under plain python3; check:ci-plan-record rc 0

- [x] W12 [writer] Concurrency reads isolation. Changes: the `overlap` verdict for an isolated spawn in `wl_planconc.spawn_verdict`, the note in `block_plan_concurrency`, the lease prefix in `wl_roster.edit_paths` and `block_commit_of_live_writer_file`.
  Owns: .claude/hooks/stop/wl_planconc.py, .claude/hooks/stop/wl_roster.py, .claude/rediacc_hooks/guards/block_plan_concurrency.py, .claude/rediacc_hooks/guards/test-block_plan_concurrency.py, .claude/rediacc_hooks/guards/block_commit_of_live_writer_file.py. Accept: `python3 .claude/rediacc_hooks/guards/test-block_plan_concurrency.py` rc 0 with: an overlapping spawn with `isolation: "worktree"` admitted and its note on stderr; the same spawn without isolation still refused; a `mutex` refusal for both. `python3 .claude/hooks/stop/test-plandeps.py` rc 0. A roster control: a live writer's edit under `.claude/worktrees/x/src/a.ts` does not subtract `src/a.ts` from the lead's fix-set.
    (ticked) 2026-11-04T11:22:43Z by d778be9d: commit:2aa2f7c6f test-block_plan_concurrency.py rc=0, test-plandeps.py rc=0, test-block_commit_of_live_writer_file.py 30 cases rc=0, test_wl_roster 128 passed

- [x] W13 [writer] Same-message spawns (#105d59a7). Changes: the claim file under `flock` read by `block_plan_concurrency` and `block_agent_cap`, its expiry.
  Owns: .claude/hooks/stop/wl_planconc.py, .claude/rediacc_hooks/guards/block_plan_concurrency.py, .claude/rediacc_hooks/guards/test-block_plan_concurrency.py, .claude/rediacc_hooks/guards/block_agent_cap.py. Accept: `python3 .claude/rediacc_hooks/guards/test-block_plan_concurrency.py` rc 0 reproducing the 2026-11-04 shape: three spawns in one message with no Stop event between them, the third refused where its plan is exclusive; two processes racing on one mutex leave exactly one admitted; an expired claim counts for nothing; a cap of 1 refuses the second same-message writer. With the claim read removed, the first control goes red. A live spawn pair is recorded in Verification notes, answering whether the harness runs the hooks in parallel.
    (ticked) 2026-11-04T11:13:47Z by d778be9d: commit:4392bc0de test-block_plan_concurrency.py rc=0 (w1, r1, r2, e1, c1, d1); live set in Verification notes shows hooks run in sequence

- [ ] W14 [writer] Docs and rules together. Changes: every line in Design 11, `/writers-now` spawning into leases.
  Owns: CLAUDE.md, .claude/commands/pr-merge.md, .claude/commands/pr-babysit.md, .claude/commands/writers-now.md, .claude/agents/pr-babysitter.md, docs/agent-reference/ci-gates.md, docs/agent-reference/TRAPS.md, docs/agent-reference/local-env.md, scripts/data/doc-registry.md. Accept: `npx tsx scripts/gen/gen-docs.ts --write`, then `npm run check:ci-doc-region-parity` and `npm run check:ci-prose-style` rc 0; `grep -rn "block-worktree-add.sh\|Writers never commit\|isolation.*NOT\|plain .git clone" CLAUDE.md .claude/commands .claude/agents .claude/rediacc_hooks/guards/block_worktree_add.py` prints nothing; a planted stale line makes that grep print.

- [ ] W15 [lead] One writer end to end, in the real tree. Changes: none beyond what a real box needs: one small open box of a live plan touching renet and the console, run through /writers-now, landed, reviewed, collected.
  Owns: agent/plans/PLAN-worktree-lease.md. Accept: `./run.sh worktree leases` showing the lease and its unlanded commits while the writer runs; the Stop hook naming it after the writer ends and before landing; `./run.sh worktree land <id>` printing renet first; the printed lines run; `git submodule status` clean; one review record per landed commit in each repo (`worklist.py --review-run <me>` listing none uncovered); `./run.sh worktree gc --write` removing the tree; `git for-each-ref refs/worktrees` empty; `npm run ci:quick` and `npm run vm:check -- --changed` rc 0 in the main checkout; the worklist store holding the writer's events with the lease's copy never written. The transcript of commands goes in Verification notes.

## Alternatives rejected

- **A second branch per writer.** The rulings forbid it: "Detached, repo tool", and `block_second_branch` plus `reference-transaction` are why a detached tree needs no exception.
- **A shared worktree per plan.** Siblings would edit one tree, which is the problem leases remove.
- **Trees outside the checkout**, the way quick-clone places its clone. It removes the walker and upward-resolution hazards, but the harness's default and its path checks assume `.claude/worktrees`, `paths.walk_tree` already prunes it, and a path outside the repo moves the isolation question to harness checks this plan cannot test beyond W5.
- **`extensions.worktreeConfig`**, to give each lease its own config. It changes the repository format for the live tree and every session sharing it.
- **Python port of the seed.** `syncDependencies` and `lockDifference` are tested in quick-clone's selftest; a second copy would drift.
- **`WorktreeRemove` doing the cleanup.** It never fires for the writers this plan exists for.
- **A branch ref under `refs/heads/` for the pin.** It would count as a live branch in `commit_policy.live_branches`.

## Verification notes

W0 live run, 2026-11-04 (`worktree_spike.py --live` rc=0, on HEAD 619250693; `--fixture` rc=0; `--fixture --plant-missing-gitlink` rc=1; afterwards `git worktree list --porcelain` showed only the main checkout and `git for-each-ref refs/worktrees` nothing; shared state changed: none).

Decision: A -- every answer passed and A is within 2.0x B: submodule seconds 2.474 for A, 1.977 for B; total 6.650 and 6.916.

W13 live spawn set, 2026-11-04: three writers spawned in one message (W7, W11, W12) held these hook spans in the spawn claims file: entered 1793790779.36 to 1793790784.03, 1793790785.93 to 1793790790.62, 1793790792.29 to 1793790796.78. The spans do not cross, so the harness ran the hooks one after another on this measurement.


W3 walker survey, 2026-11-04. Real counts: 20 `os.walk` sites in 17 files against the plan's 17, and 211 TS files touching directory reads or globs, 178 of them testing for directories, against the plan's 88. `paths.walk_tree` (.ci/rediacc_ci/paths.py:182) already pruned the `.claude/worktrees` pair, there is no TS twin and none was added, since `glob` defaults to `dot:false` and `**` never enters `.claude`. No gate refuses a raw walker, and none was added. The TS half was classified from grep and sampled reads, not all 178 files in full; the lead's own grep for `dot: true` and recursive `readdir` found one more candidate, `scripts/gates/check-control-in-string.ts:200`, anchored at `SCAN_DIR` `scripts`, so safe.

| Walker | Class | Reason or fix |
|---|---|---|
| `.ci/scripts/quality/check_policy_inventory.py:271` | FOUND | root-anchored `os.walk` when `git ls-files` fails; moved to `paths.walk_tree` |
| `.ci/scripts/quality/check_plan_deps.py:1147` | FOUND | root-anchored `rglob` in the non-git fallback; moved to `paths.walk_tree` |
| `scripts/lib/pins/drivers/npm.ts` `importersOf` | FOUND | `dot:true` glob from the manifest dir; ignores `.claude/worktrees/**` |
| `workflow_gates`, `ci_workflow_invariants`, `gh_retry_shell`, `release_run`, `wl_checks:449` | SAFE | anchored at `.github`, `.ci` or `.claude` subdirectories, a package or `private/` |
| `trap_registry:649`, `check-dead-bash`, `drivers/shared.ts listFiles` | SAFE | walk only when the root is no git work tree |
| `account_lifecycle_shadow_driver`, `local_common_actions_shadow_driver`, `worktree_spike`, `scripts/gates/check-deps.ts:2056` | SAFE | a sandbox or fixture tree |
| `upload_repos_to_r2`, `verify_artifact_attestation`, `validate_stage_artifacts`, `collect_drill_diagnostics` | SAFE | staging or dist directories |
| `block_binary_deploy:284`, `block_user_only_command_shell_write:303` | SAFE | walk a source the user's copy names |
| `lease-seed.ts`, `quick-clone.ts` | SAFE | lease-aware, or run inside a clone |

W4 correction, 2026-11-04: the Accept first said "absent from a `git clone --local`", which holds for reachability only, and now says so. `--local` hard-links objects, so `cat-file` still finds the blob while `log --all` does not; a `--no-local` clone lacks it. The test `test_dev_worktree_lease.py` records both.

W3's walker test sits in `test_dev_worktree_lease_walkers.py`, and W9's gate test in `test_dev_worktree_lease_gates.py`, because another writer held the lease test file at the time. Their Accept lines were corrected to those paths; the `-k` selections did not change.

W0 records `Decision:` here, W3 its walker survey, W5 the answer to each unverified harness item, W13 the same-message order, W15 the end-to-end transcript.
