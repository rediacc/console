# PLAN: lessons-registry follow-ups, the two deferred boxes L10 and L11

Status: draft -- carried from agent/plans/PLAN-lessons-registry.md on 2026-10-09, executing each box's recorded DEFAULT (defer)
Depends-On: no-dep -- agent/plans/PLAN-lessons-registry.md (every other box ticked) built the registry these extend
Owner: d778be9d
First-Seen: 2026-10-09
Priority: P3 -- both are hardening of a registry that already gates; neither blocks work
Concurrency: parallel -- the files under Owns
Owns: .ci/rediacc_ci/anchors.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/HINTS.md, .claude/rediacc_hooks/guards/block_short_wake_timeout.py

## Why

PLAN-lessons-registry closed every box but these two, which its author parked as `[?]` with DEFAULT: defer, each with its WHY. They are kept byte-identical here so the decision and the reasons travel with them.

## Boxes

- [?] L10 DEFAULT: defer. Move the shared resolver to `.ci/rediacc_ci/anchors.py` and teach `wl_planrec.resolve` the `text`/`doc`/`box` kinds through `wl_gh.import_ci` (the same pattern as `shacite`, `.claude/hooks/stop/wl_planrec.py:298-302`). Then migrate the 9 `file:CLAUDE.md:<N>` Sources in HINTS.md. WHY defer: it touches `.claude/hooks/stop` and HINTS.md's corpus gate, and the operator's request is met without it. HOW to undefer: operator says yes.
- [?] L11 DEFAULT: defer. A pre-bash guard that reads `tool_input.timeout` on a `wl_wake.py` call and refuses one below `harness_timeout_ms` (`.claude/hooks/stop/wl_wake.py:115`). Doing this turns seed S1 from Residue into enforcement. WHY defer: it adds a new guard, and S1 is already documented and its anchor checked.
