# STATE: branch 0807-4 — PR #555, the last PR of the 0807 wave

**AUTOPILOT.** Operator invoked `/pr-merge` then went to bed: "when I came this
morning, all the issues should be fixed and merged all the PRs."

## Landed already

```
renet   #100  MERGED -> renet main   325905214
console #552  MERGED -> console main e4cd1fd2d
account #77   MERGED -> account main e75e295a9
console #554  MERGED -> console main 1ebd8aff4   (the deadlock breaker)
renet   #99   CLOSED  (verified duplicate of #100, blobs byte-identical)
console #553  SUPERSEDED by #555 — unmergeable, see RULES.md
```

## Next action

1. Watch `bzysuwvgq` (Console CI for #555 at `c70070304`, after the knip bump).
2. On green: `gh pr ready 555`. The review WILL likely starve — the diff is
   ~3000 lines and `main` still carries the OLD 50-turn budget (the fix is in
   THIS branch's content, but reviews run the DEFAULT-BRANCH copy). Expect three
   `error_max_turns` attempts posting nothing, then the deadlock guard on main
   clears `Review Complete` legitimately. That is not a failure to diagnose.
3. `gh pr merge 555 --repo rediacc/console --rebase --auto`. This branch is
   LINEAR so rebase-merge works, unlike #553.
4. Close #553 with a comment pointing at #555.
5. **W4:** the merge to main IS the edge release. Watch Console CI on main (real
   Docker build+push), then the Release run it dispatches (tag -> GitHub Release
   -> R2 -> deploy edge). Classify any red: did that job run and pass on the PR
   run? passed-there = transient, the watchdog auto-retries, DO NOTHING;
   never-ran-there = main-only, which licenses a direct fix on main.
   Then `git fetch && git merge --ff-only && git submodule update --init
   --recursive` — CD pushes 2 commits back to main EVERY time.
6. **W5:** renet overlayfs fix. `finalizeMachinePush`
   (`private/renet/cmd/renet/backup_push.go:650`) runs
   `sudo -u rediacc rsync -a --delete`, which cannot opendir containerd's
   overlayfs `work/work` (mode 000, root-owned) and exits 23. STATE-DEPENDENT,
   so a green retry does NOT disprove it. Own renet branch + PR; CI is the
   verification since bridge/kube tests cannot run locally.

## Live workers

Watch `bzysuwvgq`. Waiter `bb51nfpv9`. Crons: work `c73f29b8`, poll `1e8a7aff`.

## Do not be fooled

- To ask "did the review run?", query the WORKFLOW
  (`gh run list --workflow claude-review.yml`), NEVER `--branch`: a
  `workflow_run` event reports the DEFAULT BRANCH's SHA, so a PR's review shows
  as `branch=main`. Also raise `--limit`: review workflows flood the list and
  truncated it past the Console CI run once.
- `per_page=30` silently truncates these ~95-job runs. Always `per_page=100`.
- A run reports `queued` while ANY job waits for a runner. Read JOB counts.
- `check:deps` reads node_modules, so it looks red locally until you install;
  CI installs from the lockfile, which is what decides there.
