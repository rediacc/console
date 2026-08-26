---
description: Rebase the current branch (console + every submodule that has a matching branch) onto its base branch, submodule-first, resolving the gitlink conflicts that plain `git rebase` gets wrong. Rebase and verify ONLY - merges nothing, lands nothing, and never force-pushes. Use to refresh a long-running branch onto a moved main before or during a PR.
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git rev-list:*), Bash(git ls-tree:*), Bash(git remote:*), Bash(gh pr list:*)
---

## Current state

- Branch: !`git branch --show-current`
- Working tree: !`git status --short | grep -v '.claude/settings.local.json' || echo '(clean aside from settings.local.json)'`
- Submodule pointers: !`git submodule status private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(unavailable)'`
- Branch vs base (left=base-only, right=branch-only): !`cb="$(git branch --show-current)"; git rev-list --left-right --count origin/main...HEAD 2>/dev/null || echo '(unavailable)'`
- Matching branches in submodules: !`cb="$(git branch --show-current)"; for d in private/renet private/account private/elite private/homebrew-tap; do [ -e "$d/.git" ] || continue; if git -C "$d" show-ref --verify --quiet "refs/heads/$cb" || git -C "$d" ls-remote --exit-code --heads origin "$cb" >/dev/null 2>&1; then echo "  $d: HAS $cb"; else echo "  $d: none"; fi; done; true`

## Task: rebase the current branch onto `origin/main`

Rebase the current branch onto `origin/main` across the console repo **and** every
submodule carrying a branch of the same name.

**The base is not configurable, and the `[base]` argument was DELETED rather than
implemented.** It was advertised for weeks and never used: the executable rebase below
is `origin/main`, submodules always base on their own `main`, and step 4 verifies
containment against `origin/main`. Passing a feature branch rebased the console onto it
while the verification checked main -- a false pass, on the one case worth checking.
Making the knob real would mean threading a per-repo base through the submodule loop,
the classifier and the containment check, and the code is right that submodules base on
their own main. There is one operator and no external consumer, so the knob is gone.

If you genuinely need to stack on another feature branch, do it by hand and know what
you are buying: all five repos are rebase-merge only, so merging the parent PR REWRITES
its SHAs. Your branch then carries the pre-merge ones and must be rebased again onto
`origin/main`, where git drops the patch-identical duplicates. A commit count that
falls across that second rebase is CORRECT, which is why step 4 no longer compares
counts.

**This command lands nothing.** It does not merge, does not touch a PR, does not tag,
does not deploy. It ends with a rebased local branch and an explicit verification
report. Contrast `/pr-merge`, which is the release path; this is the *maintenance*
path that keeps a branch current while it is still open.

Submodule map (path → GitHub repo): `private/renet` → `rediacc/renet`,
`private/account` → `rediacc/account`, `private/elite` → `rediacc/elite`,
`private/homebrew-tap` → `rediacc/homebrew-tap`.

### Why this is not just `git rebase main`

Because of the **gitlink**. When both the base and your branch moved a submodule
pointer, the rebase stops with `UU <submodule>`, and *both* obvious resolutions are
silently wrong. Verified on a purpose-built fixture, 2026-08-26:

| You type | You get | What it actually does |
|---|---|---|
| `git checkout --ours <sm>` | base's pointer | **drops your submodule work** |
| `git checkout --theirs <sm>` | your PRE-rebase tip | **drops the base's work**, and pins a commit the submodule rebase just orphaned |
| correct | the submodule's **rebased** tip | contains both |

The correct commit is in **neither conflict stage**. It does not exist until the
submodule has itself been rebased, which is why step 2 runs before step 3 and why
`--ours`/`--theirs` must never appear in this flow. Both wrong answers leave a clean
tree and a rebase that reports success, so nothing downstream catches them; the
submodule silently travels back in time and the next `/pr-merge` ships that rollback.

Inspect the stages rather than guessing:

```bash
git ls-files -u <submodule>   # stage 1 = base(ancestor), 2 = upstream, 3 = replayed
```

### 0. Preconditions (stop and report if any fail)

- **Not already on the base branch.** Rebasing `main` onto `main` is a no-op at best;
  if the current branch IS the base, there is nothing to do. Say so and stop.
- **A rebase rewrites history, and this tree has no safety net** (CLAUDE.md: work stays
  uncommitted, no stash, no restore). Before touching anything, record the pre-rebase
  tips so any outcome is recoverable, and **print them in the final report**:

  ```bash
  cb="$(git branch --show-current)"
  echo "console $cb = $(git rev-parse HEAD)"
  for d in private/*/; do d="${d%/}"; [ -e "$d/.git" ] || continue
    echo "$d = $(git -C "$d" rev-parse HEAD)"; done
  ```

  Recorded SHAs are enough, and they are the DEFAULT here: `git reflog` keeps them
  reachable and nothing pollutes the branch namespace. If you want a durable ref
  instead, use a **tag** (`git tag prerebase-$(date +%m%d) <branch>`) or take the next
  free `MMDD-N`. Do **not** decorate the branch name: `0826-1-prerebase` is refused by
  `block-nonstandard-branch-name.sh`, because step 3 below matches a submodule branch
  against the console branch name EXACTLY, and a suffixed name matches nothing while
  looking like it belongs to the wave.

  These SHAs are the recovery path (`git reset --hard <sha>` by the operator, or
  `git reflog`). A rebase that goes wrong is recoverable ONLY while they are known.
- **Working tree clean except `.claude/settings.local.json`.** Rebase refuses to start
  on a dirty tree, and that refusal is correct. Do not clear it for it.

  **If it is NOT clean, identify whose work it is first.** This tree is shared and a
  concurrent session may hold uncommitted work here. **Never** `git add`, `stash`,
  `restore` or `checkout` those paths to make the precondition pass. That destroys
  another session's work and is banned by CLAUDE.md. Report what is dirty and stop;
  the operator or the owning session decides.
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
    && echo "PUSHED: rebase will require a force-push the assistant cannot perform" \
    || echo "LOCAL ONLY: a plain push will work after the rebase"
  ```

### 1. Fetch, so "base" means the real base

```bash
git fetch origin --prune
for d in private/renet private/account private/elite private/homebrew-tap; do
  [ -e "$d/.git" ] && git -C "$d" fetch origin --prune
done
```

Rebase onto `origin/main`, never the possibly-stale local `main` ref.

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
  gitlink may still conflict in step 3 (if the base moved it); resolve that by
  **ancestry**, not by preference. See step 3's second table.
- **Conflicts inside a submodule are real code conflicts.** Resolve them there, commit,
  and only then continue. Do not `--skip`: it silently DROPS the commit being replayed.
- If a submodule branch was already pushed, its rebase also needs a force-push it
  cannot do. Note it for step 5; do not attempt it.

### 3. Rebase the console branch

```bash
git rebase origin/main
```

Every conflict falls into one of two kinds and they are resolved differently.

**a. Ordinary file conflicts.** Resolve normally, `git add <paths>`,
`git rebase --continue`. Keep edits surgical; `git add -A` is banned by
`block-blanket-git-add.sh`.

**b. Gitlink conflicts (`UU <submodule>`).** Never `--ours`/`--theirs` (see the table
above). Pick by which case the submodule is in:

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
# stopping. `git rebase --abort`, restore the step-0 SHAs, and hand it to the
# operator with both candidate SHAs and what each contains.
#
# wl_git.py's resolve_gitlink_target refuses this same case rather than guessing.
# Agreeing with the tool is the point.
```

Then stage the **path**, which is how a gitlink is marked resolved, and continue:

```bash
git add <sm>
git rebase --continue
```

**Never `git rebase --skip`.** It drops the commit outright. If the branch is
unrecoverable, `git rebase --abort` returns to the pre-rebase state recorded in step 0.

### 4. Verify: a rebase that "succeeded" can still be wrong

The failure mode this command exists to prevent produces a **clean tree and a green
rebase**, so the tree state alone proves nothing. Check the content:

- `git status --short` → nothing but `.claude/settings.local.json`.
- `git submodule status` → no `+`/`-`/`U`.
- **Every gitlink points at a commit that contains both sides.** For each submodule the
  rebase touched, confirm the base's work is actually reachable from the recorded tip:

  ```bash
  git -C <sm> merge-base --is-ancestor origin/main HEAD \
    && echo "<sm>: contains base" || echo "<sm>: DOES NOT CONTAIN BASE, wrong gitlink, redo step 3"
  ```

  This is the check that catches an `--ours`/`--theirs` mistake, and nothing else does.
- **Your commits survived**, and a COUNT cannot tell you that. Rebase-merge rewrites
  SHAs, so when a stacked branch re-rebases after its parent PR merges, git correctly
  drops the patch-identical duplicates and the count legitimately falls. The old
  instruction ("should equal the branch-only count, minus any the base absorbed") asked
  you to eyeball the difference between a correct drop and a `--skip` that ate a commit,
  which is exactly the judgement it should have been making for you.

  Ask by PATCH IDENTITY instead. `git cherry` marks each commit `+` (not upstream) or
  `-` (an equivalent is already upstream):

  ```bash
  git cherry origin/main HEAD | awk '$1=="-"{print "absorbed: " $2}'
  git rev-list <pre-rebase-tip-from-step-0>..HEAD --format=%s   # what you still carry
  ```

  A commit that is neither carried nor marked absorbed is MISSING, and that is the
  `--skip` case. Nothing else distinguishes the two.
- **Build/test the result**, because a textually clean rebase can still be semantically
  broken (your branch and the base each edited around the other). At minimum
  `npx tsc --noEmit --project packages/cli/tsconfig.json` plus the suites covering the
  touched packages; `npm run ci` if the rebase pulled in wide changes.

### 5. Publishing the rebased branch is the OPERATOR'S step

A rebase rewrites history, so an already-pushed branch can only be updated with a
force-push, and **`.claude/hooks/pre-bash/block-git-force-push.sh` refuses
`--force`, `-f`, `--force-with-lease`, `--mirror` and `+refspec` from the assistant,
unconditionally.** That is deliberate, not an obstacle to route around. Do not try
variants; do not "temporarily" edit the hook.

- **Branch never pushed** → a plain `git push -u origin <branch>` is fine; do it and
  say so.
- **Branch already pushed** → STOP and hand the exact commands to the operator, who
  runs them with the `!` prefix. Submodules first, same order as the rebase:

  ```
  ! git -C private/<sm> push --force-with-lease origin <branch>
  ! git push --force-with-lease origin <branch>
  ```

  Print the recorded pre-rebase SHAs alongside them, so the operator can undo.
  `--force-with-lease` (not `--force`) is what refuses to clobber someone else's push.
- **An open PR on this branch will re-run CI** once the force-push lands, and a rebased
  head **invalidates the Claude review marker** (`<!-- claude-reviewed: <sha> -->` no
  longer matches). Say so in the report: the PR needs a fresh review pass before
  `/pr-merge` will accept it. Do not flip anything ready here.

### 6. Report

State, in this order:
- The pre-rebase SHAs from step 0 (the recovery path), and the base SHA rebased onto.
- Per repo: rebased / already-current / skipped-no-branch, with old tip → new tip.
- Every gitlink conflict hit and which case-table row resolved it. Naming the rule
  applied is the point; "resolved the conflict" hides exactly the mistake this command
  is built to prevent.
- The step-4 verification results, including the `contains base` check per submodule and
  the commit-count comparison.
- Which gates were run and which were skipped.
- The push status: pushed, or the exact operator commands still outstanding.
- Anything left dirty and whose it is.

**Do not** merge, open, flip, or land anything. The branch is rebased and verified; the
next move is the operator's.
