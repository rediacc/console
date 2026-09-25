# PLAN: submodule branch-name divergence -- diagnosis, immediate action, and a pre-commit guard

Status: proposed
Depends-On: no-dep -- cites no other plan
Owner: d778be9d
Updated: 2026-09-23

## Immediate recommendation (read this first -- distinct from the guard design below)

**Do not rename anything. Do not touch the local submodule checkouts either.** The state the operator flagged is not accidental drift; it is the correct, intentional result of applying this repo's own already-enforced ONE-OPEN-PR-AT-A-TIME rule to two submodule PRs that predate console's current wave. Concretely, verified live just now:

1. **`private/renet` on `0914-1`: leave it.** `0914-1` carries `rediacc/renet#111`, a real, open PR from an earlier wave. This session legitimately pushed two new commits (`46eacd7`, `4084a20`, retry-loop hardening -- unrelated to `#111`'s original topic) onto that branch *because* `block_second_open_pr.py` (`CLAUDE.md:19-20`) forbids opening a second PR in `rediacc/renet` while `#111` is open, and the documented default (`.claude/commands/pr-babysit.md:58`) is exactly "new work goes onto the OPEN PR's branch." Worklist entry `#45b9e3df` in `agent/worklist/d778be9d.jsonl` records this reasoning at the moment it happened. Renaming `0914-1` now would either strand `#111` (GitHub has no "rename an open PR's head branch" operation) or require opening a second PR, which the hook already refuses.
2. **`private/account` on `0914-1`: leave it.** `0914-1` carries `rediacc/account#87`, a real, open, `MERGEABLE` PR. A *second*, unrelated fix (the main-CI-freshness work) was pushed from a separate scratch clone (`/home/developer/console-ci-fix-scratch`) as `fix/deps-freshness-console-ci` -- confirmed by direct commit comparison to be genuinely different work from `0914-1`, not a duplicate. Its `gh pr create` was **deliberately withheld**, tracked as an open, unresolved `[?]` (id `6f6c87e0`): opening it would either collide with the ONE-OPEN-PR hook or require deciding `#87`'s fate (it carries an unreviewed nodemailer 9->10 major bump this session already blocklisted), and that decision is explicitly the operator's, not a routing call. Nothing here needs a branch rename; it needs the operator's answer to `#6f6c87e0`.
3. **The one real, actionable risk found in this investigation** (not what the operator asked about, but load-bearing for whether "renaming would even help"): console PR **#590** (branch `0923-1`) has its committed gitlinks at `private/renet@4620d5d` and `private/account@3e79647` -- **neither is an ancestor of that submodule's own `origin/main`**, and **neither `rediacc/renet` nor `rediacc/account` has a remote branch literally named `0923-1`**. Reading `submodule_branches.py`'s own `main()`, this is exactly the shape that produces `"has pointer changes but branch '%s' not found"` -- the gate looks up a submodule's coordinating PR **by the console PR's own branch name**, and finds no PR named `0923-1` in either submodule repo (`#111` is on `0914-1`, `#87` is on `0914-1`). CI hasn't actually rendered this verdict yet (an unrelated `Initialize` failure blocked that job from running), so this is a prediction from the code, not an observed red -- **verify it live before acting**. If confirmed, the fix is **not** a rename: it's to let `#111`/`#87` merge and re-point console's pointers to the merged commits, or to accept and clearly document the red until then. Do not try to force a pass by pushing a decoy `0923-1` branch/PR into `renet`/`account` -- that either produces an orphan branch with no PR (still an error) or a second open PR (hook-blocked).

In short: the operator's "rename the mismatched branches" instinct targets a symptom that is actually two more specific, already-correctly-handled situations (a live PR carried forward under an old name; a deliberately-withheld competing branch), plus one real but different problem (a name-lookup gap between two enforced rules) that a rename cannot fix and that self-resolves when the upstream PRs merge.

## Finding

The operator's report ("submodules have different branch names than the parent repo") is true as a literal description of `git submodule status` but conflates three distinct situations that need three distinct answers:

- **(a) A local checkout is on a stale branch name.** Not actually true here -- verified `private/renet` and `private/account` are on `0914-1` because that's where the *real, currently pushed, PR-carrying* work lives, not because nobody moved them.
- **(b) A submodule's coordinating PR is riding an older branch name than console's current one.** True, and it's the ONE-OPEN-PR rule working as designed.
- **(c) The `Submodule Branches` CI gate's own name-lookup can't find a PR under an older name.** True, and it's a real gap between two independently-correct, independently-enforced rules. This is the actionable finding, and it is what the new guard has to be careful not to make worse by mirroring the CI gate too literally.

## 0. What already exists that this must not duplicate or contradict

- **`.ci/rediacc_ci/quality/submodule_branches.py`** -- the real, already-enforced CI gate (`.github/workflows/ci-quality.yml:656`, `quality-submodule-branches` job). Its rule, precisely: for each submodule whose committed pointer differs from that submodule's own `origin/main`, if the pointed-at commit is already an ancestor of `origin/main` it passes automatically; otherwise it requires a branch named like console's *current* branch to exist in the submodule's remote, an open PR for it, that PR linked in the console PR body, and its review comments/report answered. Submodules with no pointer change are expected to sit on `main`. Key functions to reuse rather than re-derive: `gitlink_at`, `submodule_has_pointer_changes`, `SUBMODULE_ORDER`/`SUBMODULE_REPOS`, the `merge-base --is-ancestor` check, `submodule_branch`, `branch_exists_in_remote`, `get_pr_for_branch`.
- **`CLAUDE.md:19-20` + `.claude/rediacc_hooks/guards/block_second_open_pr.py`** -- ONE OPEN PR AT A TIME, hook-enforced (`pre-bash`, `ORDER = 25`, fails closed on an unreadable PR list). This is the rule the operator's ask must not be allowed to contradict: a guard that blocks a submodule branch merely for not matching console's current name would be blocking the exact behavior this hook mandates.
- **`.claude/commands/pr-babysit.md:58-59`** -- states the same rule in prose, including the "stacking is the exception, not the default, and needs the operator's say-so" carve-out.
- **`.claude/rediacc_hooks/guards/block_nonstandard_branch_name.py`** (`ORDER=17`) and **`block_stale_pr_branch_date.py`** (`ORDER=24`) -- the two existing, TWIN'd branch-name guards. `block_stale_pr_branch_date` is the closest sibling in spirit: it blocks `gh pr create` from a branch whose *date* doesn't match today, gives a ready-to-run fix command rather than mutating git state itself, and ships an escape hatch env var (`PR_BRANCH_DATE_OK=1`) for a deliberately long-lived branch. This repo already has a case where an "old date on a branch" is sometimes legitimate, and it chose WARN-with-escape-hatch over an unconditional block for exactly that reason.
- **`.claude/rediacc_hooks/guards/block_untagged_commit.py`, `block_pathspecless_git_commit.py`** -- the pattern for a `pre-bash` guard firing at `git commit`: resolve the real target repo root via `shellscan.target_root` plus the tool call's own `cwd` field (the latter fix landed *this session*). The new guard must reuse this same two-signal resolution.
- **`.claude/rediacc_hooks/guards/block_prose_style_commit.py:164-175`** -- the precedent for importing a `.ci/rediacc_ci` module from a `pre-bash` guard via a scoped `sys.path` insert/remove. This is the mechanism that lets the new guard literally reuse `submodule_branches.py`'s own functions instead of re-implementing the ancestor check and branch/PR lookup a second time.
- **`.claude/rediacc_hooks/guards/warn_submodule_deletions.py`** -- precedent for a guard that inspects submodule state at commit time and chooses WARN over BLOCK specifically because the common case is legitimate.
- **Guard-authoring convention for a brand-new (non-ported) guard**: `TWIN = None` sentinel, a dedicated `test-block_<name>.py` standing in for the missing bash oracle, a `DEFECT` tuple the differential plants to prove the test can fail, `EDGE_CASES` tuples for named scenarios.
- **Already-tracked, correct state**: worklist entries `#45b9e3df` (renet), `#6f6c87e0`/`#cb82a5ca` (account), and the operator's own request logged at `#f8609a14`. This plan must not re-litigate `#6f6c87e0`'s decision; it belongs to the operator.

## 1. Diagnosis -- why `0914-1` survived instead of `0923-1`

Not drift. `0914-1` is the branch name of two still-open submodule PRs (`renet#111`, `account#87`) that predate console's `0923-1` wave. The ONE-OPEN-PR hook makes "push new unrelated work onto the existing open PR's branch" the mandatory default, not a fallback; console itself is allowed to advance branch names wave-over-wave only because console has no equivalent "one PR" constraint. Submodule repos do have that constraint, so their branch names lag behind console's by design whenever their existing PR hasn't merged yet.

## 2. Is renaming safe or even meaningful right now?

No, on both counts.

- **Mechanically**: GitHub does not offer a "rename this open PR's head branch" operation. The only real moves are force-push the same name (not a rename), push a new-named branch and either leave the old one attached (looks abandoned) or close/reopen (destroys review threads), or leave it.
- **Substantively**: even if a mechanical rename existed, there is nothing to fix -- `0914-1` is exactly where the work and its PR live.

## 3. "Wrong branch checked out locally" vs. "PR-branch identity should change"

- **Local checkout switch** (`git -C private/renet checkout <name>`) is cheap, safe, touches nothing remote, and is the right tool only when the checkout genuinely doesn't match any live coordinating branch. Not the case here.
- **Renaming a branch with a live PR attached** is expensive, has no clean mechanism, and was never actually called for once the diagnosis above is understood.

## 4. The `private/account` tangle

Verified by direct commit comparison: `0914-1` and `fix/deps-freshness-console-ci` share an ancestor in private/account (`git -C private/account merge-base 0914-1 fix/deps-freshness-console-ci`) and then diverge into different, non-identical work -- `0914-1` carries a review/secrets fix, a void-arrow fix, and a zod-pin+lockfile fix, tied to open PR `#87`; `fix/deps-freshness-console-ci` carries nine separate freshness bumps and a different lockfile reconcile, tied to the main-CI-fix effort and not yet PR'd. They are not duplicates, but they touch adjacent files and will conflict if both eventually merge independently. This is already the exact subject of the open, correctly-parked `[?]` `#6f6c87e0`; nothing in this plan should override that.

## 5. The forward-looking guard

Cannot be a naive mirror of `submodule_branches.py`'s name-equality rule as an unconditional BLOCK, because that rule, applied verbatim at commit time, would refuse the exact commit sequence ONE-OPEN-PR mandates. The honest design keeps the CI gate's real distinction (ancestor-of-main vs. genuinely new work) and adds a second distinction the CI gate itself doesn't currently make: "no coordinating PR exists anywhere" (safe to block) vs. "a coordinating PR exists, just under an older name" (must only warn).

Proposed guard: **`.claude/rediacc_hooks/guards/block_uncoordinated_submodule_pointer.py`**

- `CHAIN = "pre-bash"`, `ORDER` -- next free slot (verified live max is 45 as of this investigation; re-check at implementation time).
- `TWIN = None` (fresh, non-ported guard). Its own `test-block_uncoordinated_submodule_pointer.py` stands in for the missing differential, with its own `DEFECT` tuple.
- **Reuses, does not reimplement, the CI gate's logic** via the scoped-import mechanism `.claude/rediacc_hooks/guards/block_prose_style_commit.py:164-175` establishes: `sys.path.insert(0, str(root / ".ci"))`, `from rediacc_ci.quality import submodule_branches as sb`, restore `sys.path` in a `finally`. Pull `sb.gitlink_at`, `sb.submodule_has_pointer_changes`, `sb.SUBMODULE_ORDER`/`sb.SUBMODULE_REPOS`, and the `merge-base --is-ancestor` check directly.
- **Trigger**: `git commit` at command position in the console repo (mirror `block_untagged_commit.py`'s two-signal root resolution).
- **Per submodule with a staged pointer change** (compare the staged gitlink against `HEAD`'s gitlink):
  1. New pointer is an ancestor of that submodule's `origin/main` -> **ALLOW**, silently.
  2. Else, submodule's own branch is `main` or detached -> **BLOCK** (a genuinely diverged, unmerged pointer with no branch coordinating it at all).
  3. Else (a real branch name exists): check whether an open PR exists for that branch.
     - **No open PR at all** -> **BLOCK**. Nobody is coordinating this divergence anywhere.
     - **Open PR exists, branch name equals console's current branch** -> **ALLOW**, silently.
     - **Open PR exists, branch name does NOT equal console's current branch** (today's live case) -> **WARN, never BLOCK** -- naming the exact interaction found in section 0(c): a real, linked PR predating this wave is fine under ONE-OPEN-PR, but the CI gate's own name lookup will likely still redden until that PR merges and the pointer is re-pointed.
  4. **Escape hatch**: an env var (e.g. `SUBMODULE_POINTER_OK=1`), matching `block_stale_pr_branch_date.py`'s convention, for a session that has already made the tradeoff in the warn arm consciously.
- **`EDGE_CASES`**: clean pointer-bump-to-merged-main (allow); diverged pointer with submodule on `main` (block); diverged pointer on a named branch with no PR (block); diverged pointer on a branch matching console's current name with an open PR (allow); today's live shape -- diverged pointer on an older-named branch with its own open PR (warn, not block); the scratch-clone `cwd` case (must resolve to the scratch tree, not this one); a `git -C /tmp commit` (out of scope, allow); prose merely mentioning "git commit" (not a target, allow).
- **`DEFECT`**: dropping the "no open PR at all" branch's distinction from the "open PR under a different name" branch -- collapsing them into one code path is exactly the naive-blanket-rule mistake this plan exists to avoid.

**A companion note, not a mandated box**: the real, durable fix for finding (c) -- the CI gate itself never accepting a correctly-linked PR under an older name -- lives in `submodule_branches.py`, not in this new guard. That file is already enforced, not a proposal, so changing its behavior is a separately-scoped decision. This plan surfaces the gap and lets the guard warn about it; closing it at the CI layer is optional follow-up work, not a box here.

## 6. Docs cross-reference

`pr-babysitter.md` already names the `Submodule Branches` gate three times but never states the interaction found above (that a submodule's carried-forward PR name can make the gate red through no fault of the session). Recommend a short addition near where the gate is first explained, rather than rewriting the doc: one sentence naming the interaction and pointing at the new guard's warning as the place a session will actually see it. `.claude/commands/pr-babysit.md`'s ONE OPEN PR rule itself is otherwise complete and correct and should not be touched.

## Boxes

- [ ] Re-verify live (this tree moves fast): `git submodule status`, `private/renet`/`private/account` branch names, and whether PR #590's `Submodule Branches` check has actually run and rendered a verdict yet.
- [ ] If confirmed red on `Submodule Branches` for #590: do not force a pass; either wait for `renet#111`/`account#87` to merge and re-point, or get explicit operator sign-off to treat it as a documented, expected red in the interim.
- [ ] Add `.claude/rediacc_hooks/guards/block_uncoordinated_submodule_pointer.py`: `TWIN = None`, `CHAIN = "pre-bash"`, next free `ORDER` slot (verify live, candidate 46), scoped `sys.path` import of `submodule_branches.py` per `.claude/rediacc_hooks/guards/block_prose_style_commit.py:164-175`'s pattern, the four-way decision tree in section 5, the `SUBMODULE_POINTER_OK` escape hatch.
- [ ] Add `.claude/rediacc_hooks/guards/test-block_uncoordinated_submodule_pointer.py`: hermetic scratch-repo fixtures covering every EDGE_CASES row, `gh` stubbed per this repo's existing convention, and the planted DEFECT proving the block-vs-warn distinction is load-bearing.
- [ ] Register the guard (no registry edit needed per the directory-scan design) and run the hook-integrity check to confirm it's picked up.
- [ ] Add the one cross-reference sentence to `.claude/agents/pr-babysitter.md`; do not touch `.claude/commands/pr-babysit.md`.
- [ ] Leave `#6f6c87e0` (account PR #87's fate) and every submodule branch/checkout exactly as found -- no rename, no local checkout switch, pending operator action per the Immediate recommendation.
- [ ] File the CI-gate-lookup-gap (section 5's companion note) as its own future consideration, explicitly not as a box in this plan, since it changes an already-enforced gate and needs its own scoping.

## Critical files

- `.ci/rediacc_ci/quality/submodule_branches.py`
- `.claude/rediacc_hooks/guards/block_second_open_pr.py`
- `.claude/rediacc_hooks/guards/block_stale_pr_branch_date.py`
- `.claude/rediacc_hooks/guards/block_untagged_commit.py`
- `.claude/rediacc_hooks/guards/block_prose_style_commit.py`
- `.claude/agents/pr-babysitter.md`
- `agent/worklist/d778be9d.jsonl` (entries `#45b9e3df`, `#6f6c87e0`, `#cb82a5ca`)

Design produced by a dispatched Plan agent (2026-09-23), grounded in live verification of the current submodule/PR state rather than assumption. Its headline conclusion overturns the operator's own proposed action (rename): the current branch state is correct, not drifted, and nothing should be renamed.
