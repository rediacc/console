## SESSION e6500e92 2026-08-20T15:08:27Z

## What is true right now

Branch `0818-1`, PR **#569 OPEN, READY, non-draft**. Pushed: `origin/0818-1` == `61dc7d71d`.
CI run `32383638044` queued on it.

**CI REACHED FULLY GREEN** two heads ago on `b3d59b71d` (run `32376107783`): conclusion
`success`, **78 success, 20 skipped, ZERO failures, ZERO cancelled, ZERO neutral.** The zeros
are the point; earlier runs looked similar while up to 24 jobs had been cancelled without
reporting.

Three PRs open, all linked in #569's body (the submodule gate REQUIRES the link): console
**#569**, account **#80** (`3cd870b`), renet **#104** (`f3fcf78`). All four submodules CLEAN.

## Uncommitted right now, and what to do with each

- `.claude/hooks/test-hooks.sh` -- peer session's hardening: the per-suite counter now REFUSES
  a zero case-count (it had shipped one run reporting "0 case(s) passed" and still exiting ok).
  **Commit it, but only after `bash .claude/hooks/test-hooks.sh` passes** (~6 min, expect
  PASS=1168 FAIL=0). A waiter is armed.
- `agent/e6500e92/STATE.md` -- mine, commit with it.
- `package-lock.json` -- if it shows ONLY `"dev": true` deletions it is the cosmetic npm11
  flip. Restore with `npx -y npm@10 install --package-lock-only --ignore-scripts`. NEVER
  commit it.
- **`private/growth` has ONE modified file, `corporate/legal-tax/maasikas.emta.ee`.** That is a
  SEPARATE GitLab repo, not a submodule: it cannot enter the console PR, it is unrelated to
  this wave, and committing there needs an explicit operator request. **ASKED, not assumed.**

## Done, do not re-open

- **console#440 was NEVER regressed.** Two withhold paths; `repo up` routes through the DAEMON,
  not `local-executor`. Pinned by `check:ci-guard-mutations`.
- **Ceph** was an unpinned floating container tag rebuilt in place upstream on 2026-08-19.
  Pinned `v19.2.3-20250717` (renet `f3fcf78`). **The image must match the host's ceph-common
  EXACTLY; major-line matching was MY hypothesis and a live 6-VM fleet disproved it.**
- **`no-media-quality` stays declared and live, and stays OFF #569.** I deleted it once;
  `test-label-references.sh` refused a label referenced by code but not declared, so `046303fe5`
  was reverted in `fa9894881`. An unapplied label is the NORMAL state for a hold.
- `docs/ci-overhaul/06-progress.md` updated for this wave.

## Two constraints that are NOT mine to act on

- **A 6-VM KVM fleet is running, ~21.5 GB.** **Do NOT run `./rdc.sh ops down`: releasing it is
  RESERVED TO THE OPERATOR** and the stop gate rejects it as an action. Report it only.
- Never merge, never push `main`.

## Next action

1. Read the hooks-suite waiter, then commit the two console files above (#4179d239).
2. Then a **FRESH Claude review**: the head has moved many times, the
   `<!-- claude-reviewed: <sha> -->` marker no longer matches, and `Review Complete` currently
   FAILS for exactly that reason. That failure is expected and the review is its fix. Then
   resolve EVERY thread.
3. Then `CronDelete 7cb9b31f` and say so in the final report.

**If CI reds:** read the CONSOLE CI run by workflow NAME (the newest run is usually a
`Watchdog:` run), count `cancelled` AND `neutral` as DID NOT REPORT, and do NOT push while
waiting on a specific job -- a push auto-cancels the run, which cost five consecutive verdicts
earlier in this wave.
