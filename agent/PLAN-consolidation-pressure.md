# PLAN: Agreement detection and proof obligations for bulk change
Status: executing
Owner: d778be9d
Updated: 2026-09-17

Scope: `.claude/rediacc_hooks`, `.claude/hooks/stop`, `.claude/hooks/pre-bash`, `scripts/gates`, `docs/agent-reference`.

The operator wants DRY, consolidation and de-duplication enforced rather than aspired to, cleanup pressure applied at commit time, larger batch refactors encouraged over a trickle of small ones, and sub-agents doing the investigation and refactoring so the lead's context stays clean.

## What the first draft of this plan got wrong

The first draft was built on a premise this repository's own main plan contradicts, and the correction is recorded here rather than silently dropped, because the same premise will look plausible to the next reader.

THE TWINS ARE NOT BEING DELETED NOW. `agent/PLAN-tooling-transformation.md` is the main plan, 141 boxes ticked and 13 open, and its headline reads "0 of 521 bash files deleted, 23% twinned, 2 of 12 milestones". Deletion is one box, `W7P5-c`, still open, carrying three verified blockers against a single file. Invariant 5 forbids deleting a twin in the change that ports it. Any
design that treats the differential as dying machinery to be replaced is solving a problem that does not exist yet.

This is better news than the premise it replaces. `test_guards_differential.py` is alive, so the agreement harness this plan needs can EXTEND it rather than reconstruct it after a loss.

THE DUPLICATION FAMILY WIDENING IS ALREADY PLANNED AND IN FLIGHT. `agent/PLAN-extension-shaped-matchers.md` is `Status: executing`, commits 1 and 2 landed, and commit 3 is exactly the widening of `check-shape-duplication.ts` by the two Python families. The gate's own header at `:99-102` names that plan and says the two rows arrive in its commit 3, after an extraction.

The figures the first draft asked the operator to rule on are stale, and that plan says so itself: the 44-copy span is a single shared `sys.path` scaffold rather than 44 defects, PRE-A1 already took it from 44 to 36 by another route, the corpus moved twice on 2026-09-09, and "nothing measured before 2026-09-09 survives either change". Asking whether to seed or drain 76 spans was a
false choice built on numbers the owning plan had already retired.

A plan about eliminating duplication had duplicated an existing plan. The rule that would have caught it is the one already written down: search first.

## Tasks

- [x] Fold the family-widening question into agent/PLAN-extension-shaped-matchers.md commit 3 and remove it from this plan's scope
- [x] Build the sibling-differential harness by generalising the corpus and compare halves of test_guards_differential.py, which stays alive
- [x] Register the prose-decision pair as its first entry: python_comment_lines against _python_reflow_lines
- [ ] Register the C-style pair beside it: cstyle_comment_lines against the `.ts`/`.js`/`.go` segment path, which has no region-kind axis and so needs a different coverage signal
- [x] Add a per-family COUNT floor to the pair registry so an unregistered new sibling fails rather than going quiet
- [x] Write the shape-cluster diff as a reusable script: normalise every changed line to its shape, cluster, diff per-cluster counts against HEAD
- [x] Wire the missing-proof refusal into the stop judge, matching the enforcement shape wl_classsweep.py already uses
- [ ] Wire the same refusal into the pre-bash commit, push and gh guards, so the proof is demanded where the change leaves the tree
- [ ] Add the pre-bash staged-files-only duplication probe against a cached index, budget 200ms, failing OPEN and LOUD when the cache is stale
- [ ] Record the batch-size-scales-with-proof rule in docs/agent-reference/TRAPS.md with a Trap-Id and an Enforced-By pointer
The two family-widening boxes this plan started with are GONE rather than ticked-by-doing, and that is the fold. `agent/PLAN-extension-shaped-matchers.md` owns commit 3, has re-checked its sequencing three times, and has deliberately not started it; carrying a duplicate box here would be this plan committing the defect it was written to detect. The operator's question about
seeding versus draining belongs to that plan and to the numbers it re-measures, not to this one.

## The four incidents this answers to

All four are measured fact from one session, and every gate was green throughout all of them.

1. TWO IMPLEMENTATIONS OF ONE DECISION. `python_comment_lines` read comments AND docstrings while `_python_reflow_lines` read comments only. Not duplicated text, different code making one decision and disagreeing. 9,932 narrow docstring paragraphs across 1,021 of 1,024 files were invisible to R19 and to the reflow.
2. CORRECT POLICY A SIBLING NEVER CONSULTED. `REFLOW_STOP` protected rule-line banners in markdown from the start; the comment path never applied it. 838 banners destroyed across 161 files, with an AST-equality proof passing, because AST-diff cannot see prose structure.
3. A FIX THAT COVERED ONE LANGUAGE. The Python fix left `_cstyle_reflow_lines` untouched: 32 banners, 19 list items and 3 headings still absorbed.
4. A FIX THAT COVERED ONE CALL SITE. One guard learned a PR-body form it was blind to; three siblings had the identical blind spot until a stop-gate judge demanded the class sweep.

The through-line: a policy existed in one place and was silently absent from its sibling, and no line-level or diff-level metric could see it.

## Why duplication detection is the wrong instrument, and agreement detection is the right one

`scripts/gates/check-shape-duplication.ts` is 1,553 lines hashing 5-line windows across four families with a seeded baseline and per-family floors, and `.claude/hooks/stop/wl_shapedup.py` is 403 lines routing its findings into the stop judge. That machinery exists and works, so proposing a third-party clone detector beside it would be a second implementation of a question this tree
already answers, which is incident 1 in miniature.

It would also not have caught any of the four. It strips comments and literals and does not normalise identifiers, so two functions with different bodies making one decision produce no matching window. The gap is not duplication, it is AGREEMENT: two consumers of one policy, or two implementations of one decision, with nothing comparing their answers.

A DECLARATIVE AGREEMENT REGISTRY IS THE WRONG SHAPE, and the honesty question answers itself. This tree has no declarative agreement file. It has roughly twelve EXECUTABLE parity gates that recompute both sides and compare, and that form is honest by construction: a stale entry cannot go quiet because both sides are recomputed on every run, a renamed path fails resolution with no
allowlist to hide in, and an unregistered sibling is caught by a per-family COUNT floor. A declarative file has none of those three properties, so this plan adds pairs of CALLABLES with a shared corpus, never a list of paths that claim to agree.

ONE HOME WAS ALREADY TRUE AND WAS NOT THE DEFECT. `REFLOW_STOP` is a single tuple at `prose_style.py:864`. The failure was that a consumer never consulted it, and a single home does not make anyone read it. Only a differential BETWEEN consumers catches a consumer that does not consult.

## Layer assignment, and where the refusal lives

PRE-BASH blocks the command. Synchronous, sees the command line plus the staged index, bypassable by an operator's own `!` command. The operator's ruling is that the proof obligation is demanded HERE as well as at the stop, on commit, on push and on the `gh` write path, because those are the three points where a change leaves the tree.

STOP blocks ending a turn. It already owns the consolidation questions through `wl_classsweep.py` and `wl_shapedup.py`, and expensive corpus work belongs here because a stop is rare and already costs a model call.

CI owns whole-tree census and floors. Nothing taking more than about a second per invocation belongs anywhere else.

## No automated cleanup on commit, and what the proof cannot see

An automatic cleanup pass on every commit is itself a mechanical bulk transform, which is the exact operation that destroyed 838 banners while reporting success. This plan proposes no automated rewrite at commit time. What it proposes is a PROOF OBLIGATION on any bulk transform: a shape-cluster diff, where every changed line is normalised to its shape, clustered, and the
per-cluster counts diffed against HEAD. That is the check that actually caught incident 2 while the AST proof attached to it passed.

Its blind spot is stated in the same breath, because a proof whose limits go unstated is how incident 2 shipped. A shape-cluster diff cannot see a change that preserves the shape distribution while altering meaning, and cannot see loss INSIDE a line whose shape is unchanged. Neither can it see a COLUMN, which is how a list item's continuation was flattened to column 0 while a
fence, heading, table and list-marker check all passed. What covers the remainder: re-running the sweep against the scopes NOT yet rewritten, which is what found incident 3, plus reading one sampled file per cluster across both revisions.

## Batch size scales with proof, not ambition

The 884-file batch was cheap to revert only because it was uncommitted. A batch may cover as many files as the available mechanical proof can cluster and diff. With a shape-cluster diff plus an untouched-scope sweep, tree-wide is allowed. With only an AST proof, the cap is the scope one read can verify. With neither, one file.

## The sub-agent contract

Beyond "tests pass" a refactoring sub-agent returns: the exact file set it owns plus a statement that it touched nothing else; the shape-cluster diff against HEAD with per-cluster counts; the sweep result over the scopes it did NOT rewrite; and the gates that ran by name. Required: `npm run ci:quick` plus targeted pytest for any touched Python module. Advisable: `npm run ci`. The
caveat stays in the contract, because every gate was green through all four incidents: a green proves code correctness and never feature correctness.
