# RULES: branch 0808-5

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch; edit in place when one proves wrong.

Sharpened 2026-08-08 by session 2fd369e0 from `.agent/main/RULES.md` at
babysit start. Rules scoped to other branches were dropped; what remains is
verified on this branch.

## What this branch is

The phase-2 post-merge wave of the 2026-08-05/08 CI-overhaul follow-up:
profiler wired fleet-wide via setup-workspace, fixture-race fix, autopilot
loose ends (ALLOW_MODEL rename), install-methods channel-less guards, docs.
One snapshot commit `32d906f59`; PR #560 (draft). No submodule changes.
Babysit round log (the real state):
`~/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0808-5.md`
— read its wave header + STATUS before touching anything.

## Do not re-litigate

- **Install-methods empty REPO_CHANNEL must NOT default to `stable`.** The
  two signals (main-broke vs release-broke) must not be conflated; the fix is
  the return-77 guard, and `test-installmethods-args.sh` enforces it. The
  wrong default was tried and caught this session.
- **The AUTOPILOT_MODEL → AUTOPILOT_ALLOW_MODEL rename is deliberate.** The
  old name survives only in the dated note in
  `docs/ci-overhaul/03-v2-autonomy.md` — do not "fix" it back either way.
- **The profiler coverage ledger only shrinks.** Re-adding a burned line is
  refused by `check-profiler-coverage.sh` (planted-defect proven). Wiring a
  job REQUIRES deleting its ledger line in the same change.
- **Autopilot S1 is armed** (repo vars AUTOPILOT_ENABLED=true,
  AUTOPILOT_AUTHOR_ALLOWLIST=mfbayraktar, set 2026-08-08 on operator's go).
  Shadow only: all write-stage flags absent = off. Do not flip more flags.
- **docs.appimage.org is unreachable upstream** (curl 000, 2026-08-08). An
  external-links red on it is drift, not ours; on PRs the sanctioned move is
  the skip label, never editing the gate or the link.

## Standing constraints (repo-wide, verified live)

- Babysit mechanics come from `.claude/agents/pr-babysitter.md` — the ONE
  sanctioned CI watch is the terminal-state poll in background; `gh run
  watch` drops silently. Hooks block: non-draft console PR create, premature
  ready, admin merge, sleep-then-poll patterns, shell-`&` waiters
  (use run_in_background), empty retrigger commits, commit-meta trailers.
- Never `git add -A` after the snapshot; never restore/reset/stash; never
  push main; never merge. `private/growth` and `private/generative` are
  non-submodule gitignored repos — never staged.
- PR-Description gate reads `lastEditedAt`, not `updatedAt`: the body must
  genuinely change on every push.
