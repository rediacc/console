## SESSION b7baf3ee 2026-08-24T09:08:16Z

## Where things stand

Branch `0823-1`, **PR #571 open and READY**. ONE PR -- never `gh pr create`.
**Do NOT merge; `/pr-merge` is the operator's.** Pushed through `3771a92f`.

## Open worklist

- `#0ae213d7` reggate rewrite: HALF DONE. Surface routing and one-fix-per-stop
  are shipped; what remains is whatever the design in
  `agent/PLAN-test-advisor.md` still calls for.
- `#7d3c6a7d` move the video-language switch INTO the Plyr settings menu beside
  Captions/Speed, switching the VIDEO not just captions
  (`/tmp/Screenshot 2026-08-24 110222.png`). Agent `plyr-lang` is assessing
  feasibility; do NOT start implementing before its verdict.

## Two agents in flight

- **`plyr-lang`** (opus): feasibility for `#7d3c6a7d`. The hard part it is
  checking: a language change currently remounts the whole subtree via `key`,
  because `Plyr.destroy()` returns a CLONE, and the menu entry would live inside
  the DOM that remount destroys.
- **`skill-probe`** (sonnet): ran `skill-test-iterate` against
  `.claude/skills/testing/`. Asked twice, has not reported. If it stays silent,
  re-run the probe rather than assuming the docs are clean.

## Background

Full worklist suite re-running; log at
`/tmp/claude-1000/-home-muhammed-console/b7baf3ee-5a1d-41f1-8bcf-7c6e4026508e/scratchpad/wl-suite2.log`.
The previous run was 781 passed / 4 failed and all four are fixed in `3771a92f`.

## What landed this round

Per-unit code copy, sr-only tally, heading alignment, category-flash fix, one
video player (`SolutionVideoPlayer.tsx` deleted), the context budget aligned with
`/context` (window is the PIN, margin 33,000), four new gates
(`check:ci-docs-copy-units`, `check:ci-docs-browse-invariants`,
`check:ci-skill-size`, plus the reggate surface work), and
`.claude/skills/testing/` + `.claude/agents/test-advisor.md`.

## Operator corrections to honour

- **ops/KVM is NOT unwatched.** The machines the ops workflow provisions are
  exercised by the E2E suites (Tests + Infra). Provisioning behaviour is an ops
  step; anything happening ON a machine is an E2E case.
- Reggate rules: only code-touching ticks are asked, haiku may overrule the
  session's "not worth it" and must justify it, block one at a time.
- Sharper and shorter beats longer. Skills are capped at 60 lines by a gate.

## Environment

- Dev server RUNNING at :4321. `/en` works, `/en/` 404s.
- `agent-browser`: `open <url>` FIRST, then `eval <js>`; `set viewport <w> <h>`.
- `plyr` reads `document` at module scope, so the player can NEVER be an Astro
  island; it mounts from a dynamic import in `src/scripts/tutorial-video-hydrate.ts`.
- Do NOT run `build:www` here. `npm run check:format` is biome; Python is
  `.ci/scripts/quality/check-python-lint.sh`.

## Next action

1. Read `plyr-lang`'s verdict, relay it to the operator, then act on it.
2. Chase or re-run `skill-probe`; apply its findings to the testing skill.
3. Finish `#0ae213d7` against `agent/PLAN-test-advisor.md`.
4. CONDITION, not an action: CI runs on each push and the review re-fires when
   the head moves. On red, fix; on the review, answer it.
5. NEVER merge, NEVER push main, NEVER a second PR.
