# STATE: branch 0807-3 — PR #554, the deadlock breaker

**AUTOPILOT.** Operator invoked `/pr-merge` then went to bed: "when I came this
morning, all the issues should be fixed and merged all the PRs."

## Where this sits in the chain

```
W1a renet #100        MERGED  -> renet main 325905214
W1c console #552      MERGED  -> console main e4cd1fd2d
W2  console #554      <== YOU ARE HERE (branch 0807-3, CI in flight)
W3  renet #99 + account #77 -> rebase 0807-2 -> land #553
W4  release watch + main resync
W5  renet overlayfs work/work fix
```

## Next action

1. Watch `bgpbnp9vw` (Console CI for #554). On green: `gh pr ready 554`.
2. Review posts (tiny diff, will NOT starve). Resolve threads AND **answer the
   top-level summary comment** — a summary has no thread, and an unanswered one
   kept #552 red for two rounds. `review-findings: []` does NOT exempt it.
3. `gh pr merge 554 --repo rediacc/console --rebase --auto`.
4. **Then the payoff:** `gh workflow run review-status.yml --repo rediacc/console
   --ref 0807-2 -f pr_number=553`. With the fix on main the guard sees 3/3 and
   passes loudly; #553 goes CLEAN with no bypass.
5. W3: merge renet #99 + account #77 (both UNSTABLE — verify the failing context
   is `isRequired:false`; it is the known org-secret Claude Review failure, see
   account#76). Then rebase 0807-2 onto main: it conflicts with #552 on SEVEN
   files (`ci-quality.yml`, `docs/ci-overhaul/06-progress.md`, `package.json`,
   `package-lock.json`, `packages/www/package.json`,
   `scripts/ci-runner/manifest.ts`, `private/renet`). **Resolve by KEEPING BOTH
   waves' entries** — both add manifest gates and workflow steps; dropping either
   silently unwires gates.

## Live workers

- Watch `bgpbnp9vw` (#554 CI). Waiter `b2zqbrgwf` (tracked; a shell `&` is NOT).
- Crons: work `c73f29b8`, poll `1e8a7aff` (`*/40` — `:37` reads as a second WORK
  cron on branches predating the prompt-based `is_poll_cron` fix).

## Do not be fooled

- To ask "did the review run?", query the WORKFLOW
  (`gh run list --workflow claude-review.yml`), never `--branch`: a
  `workflow_run` event reports the DEFAULT BRANCH's SHA, so a PR's review shows
  as `branch=main`. Filtering by branch once cost a duplicate dispatch.
- #553's review cap is EXHAUSTED (3/3, none posted). It cannot be re-reviewed.
  Its content was gate-verified locally, and #552's reviewer independently
  verified the overlapping hook work.
- The `E2E Migrate` red is a REAL renet defect (overlayfs `work/work`, exit 23),
  state-dependent — a green retry does NOT disprove it. That is W5.
