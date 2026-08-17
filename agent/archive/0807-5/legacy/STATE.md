# STATE: branch 0807-5 — the edge smoke-test retry + its PR-time gate

**AUTOPILOT.** Operator invoked `/pr-merge` then went to bed. The whole 0807 wave
is MERGED; this branch is a follow-up defect found while watching the release.

## The wave is done

```
renet   #100  MERGED    renet   #99   CLOSED (verified duplicate)
account #77   MERGED    console #552  MERGED
console #554  MERGED    console #553  CLOSED (superseded by #555)
console #555  MERGED -> console/main 753a2f48f
```

## Next action

1. **Open the PR for 0807-5** (`--draft`, hook-enforced), then the usual finish
   line: CI green -> `gh pr ready` -> review -> resolve threads AND **answer the
   top-level summary** -> `gh pr merge --rebase --auto`.
   Diff is ~170 lines, so the review will NOT starve.
2. **Console CI on main run 31237968227** (watch `bl2bb3igo`) was at 77/78 with
   only `Validate Promotion` left. When it goes green it dispatches `cd-v2.yml`.
   **WATCH THAT RELEASE.** Not watching #554's is how the v1.2.19 gap happened.
3. **Then the mandatory resync**: `git fetch origin --prune && git merge --ff-only
   origin/main && git submodule update --init --recursive`. CD pushes TWO commits
   back to main on every release (homebrew-tap pointer, contract floor).
   If a submodule shows dirty, decide by which commit is NEWER, never by whose
   work it looks like: worktree BEHIND the record = stale checkout -> update,
   COMMIT NOTHING.
4. **W5, the last open finding:** renet `finalizeMachinePush`
   (`private/renet/cmd/renet/backup_push.go:650`) runs
   `sudo -u rediacc rsync -a --delete`, which cannot opendir containerd's
   overlayfs `work/work` (mode 000, root-owned) and exits 23. STATE-DEPENDENT — a
   green retry does NOT disprove it. Own renet branch + PR; CI is the verification
   since bridge/kube suites cannot run locally.

## Operator-only, do NOT do these

- **Re-cutting the v1.2.19 release.** Run 31234422166 deployed edge fine but
  skipped `Tag & GitHub Release`, so there is no v1.2.19 tag and no GitHub
  Release. `/pr-merge` step 5 says re-dispatching is the operator's call.
- The two stashes in `git stash list` belong to OTHER sessions. Leave them.

## Live workers

Watch `bl2bb3igo` (Console CI on main). Waiter `bp7wt40d5`.
Crons: work `c73f29b8`, poll `1e8a7aff`.
