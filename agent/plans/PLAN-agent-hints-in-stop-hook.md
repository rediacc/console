# PLAN: Agent hints in the stop hook
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-agent-hints-in-stop-hook.md
Full-Text-Blob: 1cc03bcbe8b95625789dabc41f2c5b84b83dd032
Record-Sig: 0c31fe11

## Why
The stop hook could not notice, unprompted, that the work in hand matched a specialist under `.claude/agents/`, so sessions kept not using them and the operator had to point at them by hand. This file carries the INVESTIGATION half of that work: how the hook's emission paths work, why `vadd` is the wrong channel, what the Haiku judge already costs per stop (which is the evidence a
second model call was refused on), and a prototype matcher measured over synthetic one-line haystacks. It also carries a design half its own author labelled unreviewed, because the brief was corrected mid-task: investigation and design were meant to be separate steps and only the investigation was in scope.

## Outcome
THE HEADER SAYS `Status: SUPERSEDED`, AND THIS IS THE ONE PLAN IN THIS BATCH WHERE THE TREE AGREES WITH THE HEADER. Measured 2026-09-06.

Its investigation half was consumed by `agent/plans/PLAN-agent-hints-implementation.md`, which SHIPPED. Its design half did not land, and three specifics prove it rather than assert it:

- The gate filename this plan proposed, `.ci/scripts/quality/check-agent-hint-liveness.py`
with hyphens, does not exist. What exists is the underscore form `.ci/scripts/quality/check_agent_hint_liveness.py`, which is exactly the correction the implementation plan's section 1 made to this file.
- Its section 6 thresholds, "threshold 2, margin 2", are not what shipped:
`.claude/hooks/stop/wl_agents.py:51,57` default MIN_SCORE 2 and MIN_MARGIN 1, and the running gate prints `MIN_SCORE=2 MIN_MARGIN=1`.
- Its core verdict did ship, but through the other plan's implementation: a
deterministic description matcher on the advisory queue, no second model call (`.claude/hooks/stop/wl_checks.py:2011`).

Both files were committed in the same console commit, 120cd9e73, so the superseded design and its replacement landed together as history rather than as two competing live proposals.

## Lessons
- A prototype measured on synthetic one-line haystacks produces thresholds that do
not survive real session text. This plan said so about itself, and the recalibration moved the margin from 2 to 1.
- The miss it diagnosed, `config-universe` losing because `licensing-ops`'s
description literally contains the string "config-universe", was fixed structurally by discrimination weighting rather than by tuning a number. Tuning would have moved the failure somewhere else.
- A superseded plan is still worth keeping and worth reading: its verified facts were
the input to the plan that shipped, and its corrected proposals are the record of why the shipped shape is not the obvious one.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: superseded
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:10Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: .claude/settings.json, package.json, scripts/ci-runner/manifest.ts, .ci/scripts/test/gates/test-worklist-hooks.sh, .ci/scripts/quality/lint-rule-liveness.mjs, scripts/gates/check-ci-parity.ts, .ci/scripts/test/mutate-check.sh
Gates: check:ci-agent-hint-liveness, check:ci-hook-worklist-suite
Why-Source: auto
Read-History: `git show 1cc03bcbe8b95625789dabc41f2c5b84b83dd032` recovers the text; `git log --find-object=1cc03bcbe8b95625789dabc41f2c5b84b83dd032 --all` names the commit

## History
- 2026-09-06T17:06:10Z compacted by 8f55d4f0 from `superseded` (record-sig 0c31fe11)
