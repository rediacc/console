# STATE — TWO LIVE SESSIONS SHARE THIS BRANCH. Both blocks are current.
# MERGE, never rewrite (0804-1 convention). Cap scales per `## SESSION` block.

## SESSION B (d136ac61) — carried forward verbatim below (was a single-block doc)

**AUTOPILOT.** Operator invoked `/pr-merge` then slept. The 0807 wave is fully
merged AND released; this branch is a follow-up gate found via #556's review.

## Done

```
console main = c3428568b   v1.2.19 RELEASED (edge deployed, all 6 install
                           platforms green, Tag & GitHub Release cut)
renet  main = 2a8ec0d15
merged: console #552 #554 #555 #556, account #77, renet #100 #101
closed: renet #99 (verified duplicate), console #553 (superseded)
```

## Next action

1. **Watch `b56onktrp`** — Console CI on main for `c3428568b`. On green it
   dispatches `cd-v2.yml` (tag -> GitHub Release -> R2 -> deploy edge).
   **WATCH THAT RELEASE JOB-BY-JOB, not just its conclusion.** The 1ebd8aff4
   release reported success on every deploy job while silently skipping
   `Tag & GitHub Release`, leaving no tag.
2. **Then the MANDATORY resync** (step 6, not optional): `git fetch origin
   --prune && git merge --ff-only origin/main && git submodule update --init
   --recursive`. CD pushes TWO commits back to main every release. If a submodule
   shows dirty, decide by which commit is NEWER: worktree BEHIND the record means
   a stale checkout -> update, COMMIT NOTHING.
3. **Open the PR for 0808-2** (`--draft`, hook-enforced) -> CI -> `gh pr ready`
   -> review -> resolve threads AND answer the summary -> merge.
4. **Then the known gap, its own PR:** console main records renet `325905214`
   but renet main is `2a8ec0d15`. Bump it alone; never bolt a submodule pointer
   onto an unrelated PR.
5. **Hand back:** the checkout must not be left parked on `main`. Say so in the
   report, and do NOT pre-create the next branch.

## Operator-only

- Re-cutting any release. `/pr-merge` step 5 is explicit.
- `private/growth` holds 1 uncommitted path from ANOTHER session. Reported, not
  touched. `private/generative` is clean. Both are GitLab-hosted, gitignored.

## Live workers

`b56onktrp` (Console CI on main). Waiter `bstmm1rph`.
Crons: work `c73f29b8`, poll `1e8a7aff`.
