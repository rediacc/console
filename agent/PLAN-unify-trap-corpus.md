# PLAN: Unify the trap corpus
Status: compacted Owner: 99ccf057 Full-Text: f7a5351a9 agent/PLAN-unify-trap-corpus.md Full-Text-Blob: 477232b48be389ccf464567572800f6dde8b0d5a Record-Sig: 4dd2aa8b

## Why
The repo kept two trap documents, a gitignored `.agent/TRAPS.md` that the Stop hook read and a tracked one that it did not, each blind to the other. The plan wanted one corpus at a tracked path, read by the hook and pointed at by CLAUDE.md, with a gate that reds if a second one ever appears.

## Outcome
PARTIALLY SHIPPED, and `Status: superseded` UNDERSTATES it. The successor named in the header exists and its first wave landed, but a reader taking "superseded" to mean "nothing here shipped" would be wrong. Measured 2026-09-06: the merge landed in e0ad8e6c2, which also performed the docs rename; `git ls-files` finds exactly ONE tracked TRAPS.md, at `docs/agent-reference/TRAPS.md`,
now 75 `## ` headings; the Stop hook's traps path at `.claude/hooks/stop/wl_store.py:364` points there; no `.agent` directory remains on disk; and the heading cap with its visible overflow sentinel landed in c9380778e. NOT SHIPPED: the anti-resplit gate this plan named was never built, and the differently scoped registry gate that replaced it in 126c8c2f1 asserts only a ratcheting
floor, not the one-corpus, no-gitignored-file, no-stale- reference or hook-agreement assertions. The loudness redesign does not exist at all, and two renderers still duplicate the `(none recorded)` fallback. The demanded rename of the traps-path helper did not happen either, which is the exact wrong-comment hazard the plan flagged.

## Lessons
- "Superseded" is a fact about authorship, not about delivery. Half of this plan
is in the tree today and the header does not say so.
- The invariant the plan wanted a gate for holds right now and is asserted by
nothing, so it holds by luck. That is the difference between a fixed day and a fixed slope.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted Prior-Status: superseded Compacted-By: 8f55d4f0 Compacted-At: 2026-09-06T17:08:54Z Boxes: 0 attested, 0 open, 0 abandoned Epics: none Touched: .gitignore, CLAUDE.md, .ci/scripts/quality/check-probe-parity.sh, docs/agent-reference/TRAPS.md, .claude/settings.json, .claude/hooks/pre-edit/block-agent-state-shape.sh Gates: check:ci-dead-bash,
check:ci-gate-id-convention, check:ci-gate-reachability-coverage, check:ci-probe-parity, check:ci-shell-format Why-Source: author Read-History: `git show 477232b48be389ccf464567572800f6dde8b0d5a` recovers the text; `git log --find-object=477232b48be389ccf464567572800f6dde8b0d5a --all` names the commit

## History
- 2026-09-06T17:08:54Z compacted by 8f55d4f0 from `superseded` (record-sig 4dd2aa8b)
