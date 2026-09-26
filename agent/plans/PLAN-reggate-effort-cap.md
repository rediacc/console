# PLAN: a bounded-effort cap for the stop-gate's regression-gate demands
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: 687dd4b63bfe7725667ff76f0a23cde9f613bd56
Record-Sig: 54d86dd4

## Why
The regression-gate judge had no termination condition. When a fix landed without protection from a regression gate, the judge would block; each gate-demand to resolve that block often produced new findings that themselves demanded gates. This created a self-generating loop visible in session [unresolved] (branch 0903-1, 2026-09-04/05): eight consecutive rounds, each costing ~15
minutes of CI, on a PR already green, reviewed, and resolved. No single demand was wrong; the defect was structural.

## Outcome
Designed 2026-09-05 by Plan agent, verified by [unresolved]. Stratified into three layers: (1) precision via prompt enhancement to detect gate-artifacts, (2) cap-and-budget system converting excess demands to debts, (3) debt materialization when due. Ledger file `agent/reggate/<branch-slug>.jsonl` exists per design and is actively modified on current branch, indicating
implementation is deployed and in use.

## Lessons
- A cap that fires after the cost is already paid is a historical record, not a limit. The bound must lower once work is otherwise done, shifting the constraint from 'avoid N rounds' to 'avoid N wasteful rounds.'
- Per-session budgets evaporate at compaction. Branch-scoped budgets survive the session boundary; the cost is borne by the PR, not the session.
- Layer 1 (precision via artifact detection) removes most of the loop before any capping mechanism exists, proving that separation of concerns yielded an independent, measurable win.
- The ledger cannot live in the event store; compaction silently destroys novel event kinds. A sidecar under `agent/reggate/` survives both compaction and machine boundaries.
- Discharging requires artifacts, never ticking. A cap that can be self-served by hand-written tokens is an escape hatch masquerading as a safeguard.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: designed
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:58:40Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: none
Gates: check:ci-gate-manifest, check:ci-shape-duplication
Why-Source: model
Read-History: `git show 687dd4b63bfe7725667ff76f0a23cde9f613bd56` recovers the text; `git log --find-object=687dd4b63bfe7725667ff76f0a23cde9f613bd56 --all` names the commit

## History
- 2026-09-20T17:58:40Z compacted by d778be9d from `designed` (record-sig 54d86dd4)
