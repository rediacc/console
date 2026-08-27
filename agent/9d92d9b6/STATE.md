## SESSION 9d92d9b6 2026-08-27T11:22:08Z

## Where things stand

Branch `0826-3`, 25 commits, **nothing pushed, no PR**. #577 (`0826-2`) is the
only open PR and must stay so. Recovery tags: `preredo-0826`=3ced1a4d8,
`prerebase-0826`=9f3cb9f8c, `private/account` `prerebase-0826`=3e79b39.

The working tree holds ONE uncommitted wave: a hook-guard sweep. Nothing is
half-applied; every file is syntactically valid, and the hook suite passes
**1464 cases / 0 failures** on exactly these bytes.

## What this wave did

`check:ci-hook-integrity` had `GUARD_DIR` hard-wired to `pre-bash`, so
`pre-edit/` and `pre-ask/` sat outside BOTH assertions. It also grepped only the
literal `check 2 <guard>`, missing helper-driven cases. Widened to all three
chains with chain-qualified keys; helper wrappers resolved by reading which
single guard a function body names. **The coverage baseline went 8 grandfathered
gaps to 0** — all 35 guards now have a case in each direction.

Twelve guards matched MENTION rather than execution intent. Nine live refusals
this session, including `block-suppressions` refusing its own repair and
`block-bash-write-to-running-script` refusing four commands because a chain
SIBLING is always "running". Fixed by routing through
`.claude/hooks/pre-bash/lib/command-scan.sh` where safe.

**SIX WERE REVERTED under the operator's 2026-08-25 ruling.** `block-ci-polling`,
`block-ci-reverse-poll` and `block-long-sleep` keep their prose false positive:
it fails LOUDLY while every narrowing fails SILENTLY, and the ruling names
heredoc exemption as the worst option — exactly what `hook_scan_target` does.
Two pinned suite cases caught the narrowing and reverted it. Those three guards'
code is byte-identical to HEAD. **Do not re-narrow them.**

`npm run ci` was 283 ok / 26 failed. Seven were real and are fixed: shell-format,
profiler-coverage, native-rebuild (a rebase left TWO `npm install` calls in
`ensure_deps`), shrink-only-composition, run-all-parallel (`date +%s%3N` returns
NANOSECONDS under uutils coreutils), mark-production and nightly-retry-filters
(both called `require_cmd` inside the fallback for `require_cmd` being missing).

## Not mine, shown rather than asserted

`private/account/node_modules` is EMPTY (0 entries) — one fact behind ~17
failures (`check:types` on `@cloudflare/workers-types`, `check:deps`,
`ci-account-*`, `ci-peer-deps`). `ruff` and `aws` are absent, so
`check:ci-python-lint` and `gate-test:scrub-sentinel-empty` cannot run; both
correctly refuse to skip. Do NOT run `npm install` unasked — npm 11 rewrites
`package-lock.json` here.

`check:ci-pr-task-trailers` stays RED by operator ruling: wait for #577 to merge,
re-rebase onto `origin/main`, base the PR there. Do not weaken it, do not stack a PR.

`packages/www/--full-page` is a stray 97KB PNG from ANOTHER session in this
shared worktree. Leave it.

## Next action

1. Commit the wave with a `PR-TASK: f2757830` trailer. Do NOT push, do NOT open a
   PR. Message draft: `<scratchpad>/commitmsg.txt`, where `<scratchpad>` is
   /tmp/claude-1000/-home-developer-console/9d92d9b6-77d0-4b72-a748-6b8a129d5338/scratchpad
2. Item `#051bce55`: the resumable rebase executor, steps 4-5 (registry
   invariants, then the continue loop) per
   `agent/PLAN-resumable-rebase-executor.md`. Steps 1-3 already shipped.
3. Re-run `npm run ci` to confirm the residual failure set is only the
   environmental one above plus `pr-task-trailers`. No run is currently in
   flight; the hook suite finished green.
