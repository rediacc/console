# PLAN: runtime caller-identity awareness for the worklist CLI
Status: compacted
First-Seen: 2026-09-17
Full-Text: f7a5351a9 agent/PLAN-runtime-caller-identity.md
Full-Text-Blob: 61d22f80a7aa9243a0363a1e1245cd4ff7e3558a
Record-Sig: 21a88cb5

## Why
Every `<me>` in the worklist CLI was accepted on SHAPE alone; nothing had ever compared one to reality, and an agent-namespace token copied out of a Task-spawn result had been frozen as a hand-typed `<me>` and accepted. The framing handed to the planner blamed compaction rotating the session id. That is false, and the plan disproved it twice inside one transcript. The real finding:
the session id is live in every Bash-tool child, so the CLI can warn AT THE CALL rather than at the next stop.

## Outcome
SHIPPED IN FULL, AND THE HEADER IS WRONG. It still reads `Status: DESIGN`, i.e. nothing built; the tree shows the entire three-layer design landed in 626efcb26 on the same day the plan was written. Measured 2026-09-06: `.claude/hooks/stop/wl_core.py:261` is `resolve_session_id()` and `:293` is `check_me()`; the report reader was refactored onto that shared resolver; the
`_identity_or_die` helper is called at 15 `<me>` parse sites, WIDER than the 13 the plan enumerated, with direct `check_me` calls in the requests, wait and report modules besides. The report-only phantom backstop with its blindness control, `--reassign` as an appended event rather than a rewrite, the `--ask` roster check, the ambient-env scrub in the suite, and the anti-vacuity
case that DERIVES the me-taking verb list from the dispatch source all exist. Do not record this plan as unimplemented.

## Lessons
- A plan written by a planning sub-agent can be executed within hours and never
have its own header touched. `Status: DESIGN` is a fact about authorship, not about delivery.
- The defect's shape was "a rule applied to some call sites and not others",
which is why the suite derives the verb list from the source instead of listing it. Verb 16 cannot silently reopen the hole.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: design
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:53Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: none
Gates: none
Why-Source: author
Read-History: `git show 61d22f80a7aa9243a0363a1e1245cd4ff7e3558a` recovers the text; `git log --find-object=61d22f80a7aa9243a0363a1e1245cd4ff7e3558a --all` names the commit

## History
- 2026-09-06T17:08:53Z compacted by 8f55d4f0 from `design` (record-sig 21a88cb5)
