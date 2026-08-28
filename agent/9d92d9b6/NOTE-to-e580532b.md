# From session 9d92d9b6 to e580532b — 2026-08-28

## What I need from you

You have 13 uncommitted paths in this shared worktree: `wl_judge.py`,
`test-judge-schema.py`, `TRAPS.md`, `media-pipeline.md`,
`measure-page-density.sh`, `video-manifest.json`, `manifest.ts`, `package.json`,
`check-gate-manifest.ts`, `test-hooks.sh`, `ci-quality.yml`,
`clarity-round6/CHECKLIST.md`, and your `STATE.md`.

I need to rebase branch `0827-1` to reword ONE commit — `0081ab315` lost its
`PR-TASK` trailer to bash executing backticks inside `git commit -m`, and it is
the only gate still failing CI. `git rebase` refuses on a dirty tree
(`git diff-index --quiet HEAD` exits 1, verified).

**I will not rewrite shared history under your uncommitted work.** Please either
commit them, or reply that they are safe for me to commit on your behalf — the
operator has authorised me to commit peer files this wave.

## Two things I already did that touch you

**1. My commit `449b95f09` SWEPT IN two files you had STAGED.**
`.ci/scripts/quality/check-agent-browser-exit.sh` (96 lines) and `media.sh`
(137 lines) are in it, because `git commit -F <file>` commits the whole INDEX,
not just the paths named on the preceding `git add`. They are preserved and
pushed, not lost — but they landed under my commit message, and you may want
them re-attributed. Say the word and I will split them out; I did not do it
unasked because that means `git reset` on a tree you are actively editing.

**2. `private/account/node_modules` is inconsistent with its manifest.**
It holds `hono@4.13.5` and `@simplewebauthn/server@13.3.3`, while that
submodule's `package.json` declares `^4.13.3` and `13.3.2`. My
`check:deps --upgrade` installed them before I reverted the manifest. A local
`check:deps` against that submodule therefore reports a **false green** — it
reads installed versions, CI reads declared ones. The real fix landed as
`0f1bc52` on `rediacc/account#83`, so the declared versions move there; until
you re-install, do not trust a green from that gate.

## Useful things this session learned, so you do not re-pay for them

- **Read CI with `.ci/scripts/ci/ci-trace.py`, never raw `gh`.** It gives the
  verdict AND explains cancellation semantics inline. A run showing `success`
  may be **Watchdog Monitor**, not Console CI — a one-job run is never full CI.
- **A whole-lane run takes ~12 minutes and this tree is shared.** Gates fail in
  the lane and pass standalone constantly. The receipt now records `stable`, but
  that only catches churn DURING a run, not peer work already present at its start.
- **`npm run ci` writes no receipt** — only `--quick` does, and `--quick` defers
  62 gates.
