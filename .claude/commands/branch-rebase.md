---
description: Rebase the current branch (console + every submodule that has a matching branch) onto its base branch, submodule-first, resolving the gitlink conflicts that plain `git rebase` gets wrong. Rebase and verify, then republish only through step 5's guarded lease push - merges nothing, lands nothing, opens no PR. Use to refresh a long-running branch onto a moved main before or during a PR.
argument-hint: "[base]  (optional; defaults to main. A feature branch is legal: see below)"
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git rev-list:*), Bash(git ls-tree:*), Bash(git remote:*), Bash(gh pr list:*)
---

## Current state

- Branch: !`git branch --show-current`
- Working tree: !`git status --short | grep -v '.claude/settings.local.json' || echo '(clean aside from settings.local.json)'`
- Submodule pointers: !`git submodule status private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(unavailable)'`
- Base: !`echo "origin/${ARGUMENTS:-main}" | tr -d ' '`
- Branch vs base (left=base-only, right=branch-only): !`b="origin/${ARGUMENTS:-main}"; b="$(echo "$b" | tr -d " ")"; git rev-list --left-right --count "$b"...HEAD 2>/dev/null || echo '(unavailable -- does that base exist? run git fetch origin first)'`
- Matching branches in submodules: !`cb="$(git branch --show-current)"; for d in private/renet private/account private/elite private/homebrew-tap; do [ -e "$d/.git" ] || continue; if git -C "$d" show-ref --verify --quiet "refs/heads/$cb" || git -C "$d" ls-remote --exit-code --heads origin "$cb" >/dev/null 2>&1; then echo "  $d: HAS $cb"; else echo "  $d: none"; fi; done; true`

## Task: rebase the current branch onto `origin/$ARGUMENTS` (default `main`)

Rebase the current branch onto `origin/<base>` across the console repo **and** every submodule carrying a branch of the same name. `<base>` is the first token of `$ARGUMENTS`, defaulting to `main`.

**A FEATURE BRANCH IS A LEGAL BASE, and the threading is the whole point.** This argument was advertised for weeks while every executable line said `origin/main`, so passing `0826-2` rebased the console onto it and then VERIFIED against `main` -- a false pass on the one case worth checking. It was deleted for that reason and restored when the operator pointed out they stack onto a
feature branch routinely. So:

- the console rebases onto `origin/<base>`;
- **submodules always rebase onto their OWN `origin/main`**, never onto `<base>`. A
submodule's work lands on its own main; `<base>` is a console ref and means nothing inside `private/renet`. `--git verify-rebase` learned this the hard way, refusing with "could not compare" on its first live run;
- step 4 verifies the CONSOLE against `origin/<base>` and each SUBMODULE against its own
`origin/main`. Mixing those two is the corruption this section exists to prevent.

**Stacking has a second act, and skipping it is how a branch rots.** All five repos are rebase-merge only, so merging the parent PR REWRITES its SHAs. Your branch then carries the pre-merge ones and must be rebased AGAIN, onto `origin/main`, where git drops the patch-identical duplicates. A commit count that falls across that second rebase is CORRECT, which is why step 4 asks by
patch identity rather than by count.

**This command lands nothing.** It does not merge, does not touch a PR, does not tag, does not deploy. It ends with a rebased local branch and an explicit verification report. Contrast `/pr-merge`, which is the release path; this is the *maintenance* path that keeps a branch current while it is still open.

Submodule map (path → GitHub repo): `private/renet` → `rediacc/renet`, `private/account` → `rediacc/account`, `private/elite` → `rediacc/elite`, `private/homebrew-tap` → `rediacc/homebrew-tap`.

### Why this is not just `git rebase main`

Because of the **gitlink**. When both the base and your branch moved a submodule pointer, the rebase stops with `UU <submodule>`, and *both* obvious resolutions are silently wrong. Verified on a purpose-built fixture, 2026-08-26:

| You type | You get | What it actually does |
|---|---|---|
| `git checkout --ours <sm>` | base's pointer | **drops your submodule work** |
| `git checkout --theirs <sm>` | your PRE-rebase tip | **drops the base's work**, and pins a commit the submodule rebase just orphaned |
| correct | the submodule's **rebased** tip | contains both |

The correct commit is in **neither conflict stage**. It does not exist until the submodule has itself been rebased, which is why step 2 runs before step 3 and why `--ours`/`--theirs` must never appear in this flow. Both wrong answers leave a clean tree and a rebase that reports success, so nothing downstream catches them; the submodule silently travels back in time and the next
`/pr-merge` ships that rollback.

Inspect the stages rather than guessing:

```bash
git ls-files -u <submodule>   # stage 1 = base(ancestor), 2 = upstream, 3 = replayed
```

### 0. Preconditions (stop and report if any fail)

- **Not already on the base branch.** Rebasing `main` onto `main` is a no-op at best;
if the current branch IS the base, there is nothing to do. Say so and stop.
- **A rebase rewrites history, and this tree has no safety net** (CLAUDE.md: work stays
uncommitted, no stash, no restore). Before touching anything, record the pre-rebase tips so any outcome is recoverable, and **print them in the final report**:

  ```bash
  # SET THE BASE ONCE, HERE, and use $BASE everywhere below. Every later step
  # defaults to main if it is unset, so a base named only in prose silently
  # rebases onto main while you believe otherwise -- which is precisely the
  # corruption that got this argument deleted the first time.
  BASE="${ARGUMENTS%% *}"; BASE="${BASE:-main}"
  git fetch origin "$BASE" || { echo "no such base: origin/$BASE"; exit 1; }
  echo "base = origin/$BASE"

  cb="$(git branch --show-current)"
  echo "console $cb = $(git rev-parse HEAD)"
  for d in private/*/; do d="${d%/}"; [ -e "$d/.git" ] || continue
    echo "$d = $(git -C "$d" rev-parse HEAD)"; done
  ```

Recorded SHAs are enough, and they are the DEFAULT here: `git reflog` keeps them reachable and nothing pollutes the branch namespace. If you want a durable ref instead, use a **tag** (`git tag prerebase-$(date +%m%d) <branch>`) or take the next free `MMDD-N`. Do **not** decorate the branch name: `0826-1-prerebase` is refused by `block-nonstandard-branch-name.sh`, because step 3
below matches a submodule branch against the console branch name EXACTLY, and a suffixed name matches nothing while looking like it belongs to the wave.

These SHAs are the recovery path (`git reset --hard <sha>` by the operator, or `git reflog`). A rebase that goes wrong is recoverable ONLY while they are known.
- **Working tree clean except `.claude/settings.local.json`.** `git rebase` refuses to start
over ANY modified tracked file (`error: cannot rebase: You have unstaged changes.`), settings.local.json included. That one file is the harness's permission file, rewritten on every granted permission and never committed or stashed, so step 3 carries it across the rebase with its skip-worktree bit. Every other modified path is a refusal that is correct. Do not clear it for it.

**If it is NOT clean, identify whose work it is first.** This tree is shared and a concurrent session may hold uncommitted work here. **Never** `git add`, `stash`, `restore` or `checkout` those paths to make the precondition pass. That destroys another session's work and is banned by CLAUDE.md. Report what is dirty and stop; the operator or the owning session decides.
- **Submodules clean too.** `git submodule status` must show no `+`/`-`/`U`. A dirty
submodule worktree will be carried into, or block, the pointer resolution in step 3.
- **Sibling repos under `private/` that are NOT submodules** are out of scope entirely.
Discover them, never hardcode:

  ```bash
  for d in private/*/; do d="${d%/}"; [ -e "$d/.git" ] || continue
    git config -f .gitmodules --get-regexp path 2>/dev/null | awk '{print $2}' \
      | grep -qx "$d" || echo "NON-SUBMODULE: $d"; done
  ```

Never rebase, add, or bump one. Report if any is dirty and move on.
- **Was this branch already pushed?** Decide it now, because it changes how step 5 ends:

  ```bash
  cb="$(git branch --show-current)"; git ls-remote --exit-code --heads origin "$cb" >/dev/null 2>&1 \
    && echo "PUSHED: republish with the lease push of step 5 after the rebase" \
    || echo "LOCAL ONLY: a plain push will work after the rebase"
  ```

### 1. Fetch, so "base" means the real base

```bash
git fetch origin --prune
for d in private/renet private/account private/elite private/homebrew-tap; do
  [ -e "$d/.git" ] && git -C "$d" fetch origin --prune
done
```

Rebase onto `origin/<base>`, never the possibly-stale local ref.

### 2. Rebase the submodules FIRST (only those with a matching branch)

Order is load-bearing: step 3's correct gitlink is the tip this step produces.

For each submodule that has a branch matching the console branch name:

```bash
cb="$(git branch --show-current)"
git -C <sm> checkout "$cb"
git -C <sm> rebase origin/main          # submodules always base on their own main
git -C <sm> rev-parse HEAD              # <-- the tip step 3 needs; record it
```

- A submodule whose branch is **already up to date** rebases to a no-op. Fine, record
the tip anyway.
- A submodule with **no matching branch** is not rebased and not checked out. Its
gitlink may still conflict in step 3 (if the base moved it); resolve that by **ancestry**, not by preference. See step 3's second table.
- **Conflicts inside a submodule are real code conflicts.** Resolve them there, commit,
and only then continue. Do not `--skip`: it silently DROPS the commit being replayed, and `block_rebase_over_foreign_dirt` refuses it.
- If a submodule branch was already pushed, its rebase needs the step 5 lease push,
submodule before console. Note it for step 5; nothing pushes before step 4 verifies.

### 3. Rebase the console branch

The rebase runs inside a skip-worktree window on `.claude/settings.local.json`: the bit is set just before it, stays set while the rebase is stopped, and is cleared as soon as no rebase is in progress. `git rebase --continue` refuses over the modified file exactly as the start does (measured 2026-10-20, git 2.53: rc 1, with the misleading `You must edit all merge conflicts`), and the harness can rewrite the file while a conflict waits, so clearing the bit at the first stop breaks the next `--continue`.

```bash
git update-index --skip-worktree .claude/settings.local.json
git rebase "origin/${BASE:-main}"
# THE RELEASE LINE: clears the bit once no rebase is in progress, a no-op while one is stopped.
test -d "$(git rev-parse --git-path rebase-merge)" || git update-index --no-skip-worktree .claude/settings.local.json
```

The release line runs after EVERY command that can end the rebase: this first `git rebase`, each `git rebase --continue` below, and `git rebase --abort`. It is one self-contained line rather than a shell function because each agent Bash call starts a fresh shell, so a function defined at the start would be gone by the first `--continue`. A finished or aborted rebase clears the bit; a stopped one keeps it. `.claude/hooks/stop/worklist.py --git rebase-continue --execute` keeps the same window by itself: it sets the bit before each `--continue` when the file is modified, and clears it when the rebase finishes. A bit left set hides every later edit of the file from `git status`, which step 4 checks.

If the base itself changed settings.local.json, the rebase does not start: git refuses with `Your local changes to the following files would be overwritten by checkout: .claude/settings.local.json`, keeps the local file, and leaves no rebase in progress, so the release line clears the bit. Report it and stop; taking the base's version discards the local permissions, which is the operator's call.

Every conflict falls into one of two kinds and they are resolved differently.

**a. Ordinary file conflicts.** Resolve normally, `git add <paths>`, `git rebase --continue`, then the release line. Keep edits surgical; `git add -A` is banned by `block-blanket-git-add.sh`.

**b. Gitlink conflicts (`UU <submodule>`).** Never `--ours`/`--theirs` (see the table above). Pick by which case the submodule is in:

| Submodule case | Correct gitlink | How |
|---|---|---|
| Has a matching branch (rebased in step 2) | that branch's **new** tip | `git -C <sm> checkout <new-tip>` |
| No matching branch; base moved it forward | the **base's** commit | `git -C <sm> checkout <stage-2 sha>` |
| No matching branch; your branch bumped it to already-merged work | whichever is the **descendant** | test with `merge-base` below |

```bash
# which of the two candidates is newer?
rec=$(git ls-files -u <sm> | awk '$3==2{print $2}')   # upstream/base side
mine=$(git ls-files -u <sm> | awk '$3==3{print $2}')  # replayed side
git -C <sm> merge-base --is-ancestor "$rec" "$mine" && echo "mine is NEWER (take mine)"
git -C <sm> merge-base --is-ancestor "$mine" "$rec" && echo "base is NEWER (take base)"
# neither printed => genuinely DIVERGED. STOP HERE.
#
# This is terminal, not a step. The old text sent you back to step 2, which you
# only reach from the "no matching branch" rows -- so it pointed at a step that by
# construction does not apply, and the next thing a session reaches for is
# --ours/--theirs, which the table above proves is silently wrong.
#
# No correct resolution for this case has ever been executed in this repo, so
# there is no procedure to follow and inventing one here would be worse than
# stopping. `git rebase --abort` and the release line, restore the step-0 SHAs, and hand it to the
# operator with both candidate SHAs and what each contains.
#
# wl_git.py's resolve_gitlink_target refuses this same case rather than guessing.
# Agreeing with the tool is the point.
```

Then stage the **path**, which is how a gitlink is marked resolved, and continue:

```bash
git add <sm>
git rebase --continue
# then the release line from the top of this step
```

**Never `git rebase --skip`.** It drops the commit outright, and `.claude/rediacc_hooks/guards/block_rebase_over_foreign_dirt.py` refuses it in this checkout and its submodules, pointing to `--abort`. If the branch is unrecoverable, `git rebase --abort` returns to the pre-rebase state recorded in step 0, and the release line follows it.

### 4. Verify: a rebase that "succeeded" can still be wrong

The failure mode this command exists to prevent produces a **clean tree and a green rebase**, so the tree state alone proves nothing. Check the content:

- `git status --short` → nothing but `.claude/settings.local.json`.
- `git ls-files -v .claude/settings.local.json` → tagged `H`, not `S`: the step-3 window is closed.
- `git submodule status` → no `+`/`-`/`U`.
- **Every gitlink points at a commit that contains both sides.** For each submodule the
rebase touched, confirm the base's work is actually reachable from the recorded tip:

  ```bash
  git -C <sm> merge-base --is-ancestor origin/main HEAD \
    && echo "<sm>: contains base" || echo "<sm>: DOES NOT CONTAIN BASE, wrong gitlink, redo step 3"
  ```

This is the check that catches an `--ours`/`--theirs` mistake, and nothing else does. Note the ref: each submodule is checked against its OWN `origin/main`, never against `$BASE`, which is a console ref and means nothing inside `private/renet`.
- **The console contains its base**, which nothing checked until 2026-08-27. With
`$BASE` = `main` this is nearly always true by construction, so its absence cost nothing and hid; with a FEATURE-BRANCH base it is the assertion that catches a rebase onto the wrong ref, which is the failure the `[base]` argument makes possible:

  ```bash
  git merge-base --is-ancestor "origin/${BASE:-main}" HEAD \
    && echo "console: contains origin/${BASE:-main}" \
    || echo "console: DOES NOT CONTAIN ITS BASE -- you rebased onto something else"
  ```
- **Your commits survived**, and a COUNT cannot tell you that. Rebase-merge rewrites
SHAs, so when a stacked branch re-rebases after its parent PR merges, git correctly drops the patch-identical duplicates and the count legitimately falls. The old instruction ("should equal the branch-only count, minus any the base absorbed") asked you to eyeball the difference between a correct drop and a `--skip` that ate a commit, which is exactly the judgement it should have
been making for you.

Ask by PATCH IDENTITY instead. `git cherry` marks each commit `+` (not upstream) or `-` (an equivalent is already upstream):

  ```bash
  git cherry "origin/${BASE:-main}" HEAD | awk '$1=="-"{print "absorbed: " $2}'
  git rev-list <pre-rebase-tip-from-step-0>..HEAD --format=%s   # what you still carry
  ```

Or let the tool do all of it, which is the same two oracles with the per-repo base already threaded -- `--git verify-rebase` checks the console against the base you pass and each SUBMODULE against its own `origin/main`, because it reads `.gitmodules`:

  ```bash
  .claude/hooks/stop/worklist.py --git snapshot > /tmp/pre.snap   # BEFORE the rebase
  .claude/hooks/stop/worklist.py --git verify-rebase /tmp/pre.snap "origin/${BASE:-main}"
  ```

It reports carried / absorbed / MISSING per repo and refuses on MISSING. Prefer it: the hand-run commands above and this verb encode the same rule, and two copies of a rule drift -- the prose copy is the one that drifted last time.

A commit that is neither carried nor marked absorbed is MISSING, and that is the `--skip` case. Nothing else distinguishes the two.
- **Build/test the result**, because a textually clean rebase can still be semantically
broken (your branch and the base each edited around the other). At minimum `npx tsc --noEmit --project packages/cli/tsconfig.json` plus the suites covering the touched packages; `npm run ci` if the rebase pulled in wide changes.

### 5. Publishing the rebased branch

A rebase rewrites history, so an already-pushed branch can only be updated with a force-push. `.claude/rediacc_hooks/guards/block_git_force_push.py` refuses `--force`, `-f`, `--mirror` and `+refspec` unconditionally, and since the operator ruling of 2026-10-02 (PLAN-plan-per-pr-loop M3) it admits exactly one form: `git push --force-with-lease origin <branch>` on the repository's one live `MMDD-N` branch. `warn_remote_drift` lets that lease push through when every remote-only commit is patch-equivalent to a rebased local one, and refuses it, naming the commit, when the remote holds work the rebase never saw. Do not try other variants; do not "temporarily" edit either guard.

The push is deliberately absent from this command's `allowed-tools`, which pre-approves read-only probes only, as `pr-merge.md` and `pr-babysit.md` do. Whether a force-push prompts is the session's permission mode, the same as for the fetch and rebase of steps 1-3, and under every mode the guard above admits no other form.

- **Branch never pushed** → a plain `git push -u origin <branch>` is fine; do it and
say so.
- **Branch already pushed** → republish it with the lease push, or with the mediated verb
`.claude/hooks/stop/worklist.py --git force-push <branch> --execute`. Submodules first, same order as the rebase:

  ```
  git -C private/<sm> push --force-with-lease origin <branch>
  git push --force-with-lease origin <branch>
  ```

Print the recorded pre-rebase SHAs in the report, so the push can be undone. `--force-with-lease` (not `--force`) is what refuses to clobber someone else's push.
- **An open PR on this branch will re-run CI** once the force-push lands. Per-commit review
  records carry over by `Patch-Id:`: a rebased commit whose patch is unchanged still counts as reviewed.
A commit whose patch changed (a conflict resolution, an amend) shows up as uncovered; `.claude/hooks/stop/worklist.py --review-run <me> <sha>` reviews it. Say so in the report, and name what `python3 .claude/hooks/stop/wl_review.py --check` prints, because `/pr-merge` requires it clean. Do not flip anything ready here.

### 6. Report

State, in this order:
- The pre-rebase SHAs from step 0 (the recovery path), and the base SHA rebased onto.
- Per repo: rebased / already-current / skipped-no-branch, with old tip → new tip.
- Every gitlink conflict hit and which case-table row resolved it. Naming the rule
applied is the point; "resolved the conflict" hides exactly the mistake this command is built to prevent.
- The step-4 verification results, including the `contains base` check per submodule and
the commit-count comparison.
- Which gates were run and which were skipped.
- The push status: pushed, or the exact operator commands still outstanding.
- Anything left dirty and whose it is.

**Do not** merge, open, flip, or land anything. The branch is rebased and verified, and the next move belongs to whoever invoked this command. No command file calls it by name: it is reached from the `REBASE LOCALLY` notice `block_unverified_push` prints, by the operator, or at the two points the per-PR loop rebases onto `origin/main` (`.claude/agents/pr-babysitter.md` step 2, and `.claude/commands/pr-merge.md` step 3 when the branch is not a pure fast-forward).
