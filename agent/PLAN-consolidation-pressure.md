# PLAN: Consolidation pressure that outlives the guard twins
Status: draft
Owner: d778be9d
Updated: 2026-09-17

Scope: `.claude/rediacc_hooks`, `.claude/hooks/stop`, `scripts/gates`, `.ci/rediacc_ci`, `docs/agent-reference`.

The operator wants DRY, consolidation and de-duplication enforced rather than aspired to, cleanup pressure applied at commit time, larger batch refactors encouraged over a trickle of small ones, and sub-agents doing investigation and refactoring so the lead's context stays clean.

## The four incidents this must answer to

All four are measured fact from one session, and every gate was green throughout all of them.

1. TWO IMPLEMENTATIONS OF ONE DECISION. `python_comment_lines` read comments AND docstrings while `_python_reflow_lines` read comments only. Not duplicated text, different code making one decision and disagreeing. 9,932 narrow docstring paragraphs across 1,021 of 1,024 files were invisible to R19 and to the reflow. Caught by the operator asking why two code paths existed.
2. CORRECT POLICY A SIBLING NEVER CONSULTED. `REFLOW_STOP` protected rule-line banners in markdown from the start; the comment path never applied it. 838 banners destroyed across 161 files, with an AST-equality proof passing, because AST-diff cannot see prose structure.
3. A FIX THAT COVERED ONE LANGUAGE. The Python fix left `_cstyle_reflow_lines` untouched: 32 banners, 19 list items and 3 headings still absorbed. Found only by re-sweeping the scopes not yet rewritten.
4. A FIX THAT COVERED ONE CALL SITE. One guard learned a PR-body form it was blind to; three siblings had the identical blind spot until a stop-gate judge demanded the class sweep.

The through-line: a policy existed in one place and was silently absent from its sibling, and no line-level or diff-level metric could see it.

## Tasks

- [ ] Enumerate in a gate test the properties test_guards_differential.py enforces, marking which survive oracle removal
- [ ] Repoint test_every_guard_discriminates at a Python-only reference so it does not die with bash_results
- [ ] Re-express COMMENT_RATIO_FLOOR and the ARCHAEOLOGY rule against git show HEAD:<path> instead of the oracle
- [ ] Write a test-<stem>.py suite for the ~41 guards that have none, in waves, before any oracle is deleted
- [ ] Build the sibling-differential harness by generalising the corpus and compare halves of test_guards_differential.py
- [ ] Register the prose-decision family as its first pair set, with a per-family count floor
- [ ] Add the shape-cluster diff as a reusable script and require it in the refactoring sub-agent contract
- [ ] Widen check-shape-duplication.ts by one family, measure the seed cost, record it
- [ ] Add a pre-bash staged-files-only duplication probe reading a cached index, budget 200ms, failing OPEN and LOUD on a stale cache
- [ ] Record the batch-size-scales-with-proof rule in docs/agent-reference/TRAPS.md with a Trap-Id

## What the twins take with them

`.claude/rediacc_hooks/tests/test_guards_differential.py` is the only thing in this tree proving two implementations of one decision agree. Removing the oracles kills `test_guard_matches_bash`, kills the `COMMENT_RATIO_FLOOR = 0.90` archaeology check at `:78` and `:822`, and kills the staleness detector on declared divergences. It orphans `test_every_guard_discriminates`, which
reads `bash_results` and needs a Python-only reference instead.

What survives is the foundation to build on: `test_the_differential_can_fail` compares each port against ITSELF-WITH-A-DEFECT and never touches bash, and the corpus harvester reads `.claude/hooks/test-hooks.sh` rather than the oracles.

The sharp cost is the present-twin rule's second arm, which requires a `test-<stem>.py` beside any guard declaring `TWIN = None`. Measured here: 47 twinned guards, 1 untwinned and 6 `test-block_*.py` suites, so roughly 41 guards become rule violations the moment the oracles go. A design agent counting the same thing reported 43, and the discrepancy is in how a multi-line or
docstring-mentioned `TWIN` is counted; it does not change the conclusion, which is that the suites must be written in waves BEFORE deletion rather than after.

## Layer assignment

PRE-BASH blocks the commit command. Synchronous, sees the command line plus the staged index, bypassable by an operator's own `!` command. Only cheap staged-scoped checks belong here.

STOP blocks ending a turn. It already owns the consolidation questions, and expensive corpus work belongs here because a stop is rare and already costs a model call.

CI owns whole-tree census and floors. Nothing taking more than about a second per invocation belongs anywhere else.

## No automated cleanup on commit, and why

An automatic cleanup pass on every commit is itself a mechanical bulk transform, which is the exact operation that destroyed 838 banners while reporting success. This plan proposes no automated rewrite at commit time. What it proposes instead is a PROOF OBLIGATION on any bulk transform: a shape-cluster diff, where every changed line is normalised to its shape, clustered, and the
per-cluster counts diffed against HEAD. That is the check that actually caught incident 2 while the AST proof attached to it passed.

Its blind spot is stated in the same breath, because a proof whose limits go unstated is how incident 2 shipped. A shape-cluster diff cannot see a change that preserves the shape distribution while altering meaning, and cannot see loss INSIDE a line whose shape is unchanged. Neither can it see a column, which is how a list continuation was flattened to column 0 under a passing
structural check. What covers the remainder: re-running the sweep against the scopes NOT yet rewritten, which is what found incident 3, plus reading one sampled file per cluster across both revisions.

## Batch size scales with proof, not ambition

The 884-file batch was cheap to revert only because it was uncommitted. A batch may cover as many files as the available mechanical proof can cluster and diff. With a shape-cluster diff plus an untouched-scope sweep, tree-wide is allowed. With only an AST proof, the cap is the scope one read can verify. With neither, one file.

## The sub-agent contract

Beyond "tests pass" a refactoring sub-agent returns: the exact file set it owns plus a statement it touched nothing else; the shape-cluster diff against HEAD with per-cluster counts; the sweep result over the scopes it did NOT rewrite; and the gates that ran by name.
Required: `npm run ci:quick` plus targeted pytest for any touched Python module. Advisable: `npm run ci`.
The caveat stays in the contract, because every gate was green through all four incidents: a green proves code correctness and never feature correctness.

## Corrections this design made to its own brief

The brief asked for a duplication detector and a declared-agreement registry. Both were wrong, and the reasons are the most useful part of the design.

THE COUNTER ALREADY EXISTS. `scripts/gates/check-shape-duplication.ts` is 1,553 lines hashing 5-line windows across four families with a seeded baseline and per-family floors, and `.claude/hooks/stop/wl_shapedup.py` is 403 lines routing its findings into the stop judge. Proposing a third-party clone detector here would have been a second implementation of a question this tree
already answers, which is incident 1 exactly.

THE COUNTER WOULD NOT HAVE CAUGHT ANY OF THE FOUR. It strips comments and literals and does not normalise identifiers, so two functions with different bodies making one decision produce no matching window. The gap is not duplication detection, it is AGREEMENT detection, and the only agreement harness in the tree is the one the twins are about to take with them.

A REGISTRY IS THE WRONG SHAPE, and the honesty question answers itself. This tree has no declarative agreement file; it has roughly twelve EXECUTABLE parity gates that recompute both sides and compare. That is honest by construction: a stale entry cannot go quiet because both sides are recomputed on every run, a renamed path fails resolution with no allowlist to hide in, and an
unregistered sibling is caught by a per-family COUNT floor. A declarative registry has none of those three properties, so by the brief's own standard it is not worth adding, and this plan does not add one.

ONE HOME WAS ALREADY TRUE AND WAS NOT THE DEFECT. `REFLOW_STOP` is a single tuple at `prose_style.py:864`. The failure was that a consumer never consulted it, which no registry prevents: a single home does not make anyone read it. Only a differential BETWEEN the consumers catches a consumer that does not consult.

TWO FACTUAL CORRECTIONS. `npm run quick` does not exist; the script is `ci:quick`. And `COMMENT_RATIO_FLOOR` is not a comment density rule: it compares the port's comment BYTES against its bash original's, so its replacement must be HEAD-relative rather than absolute, or it creates exactly the pressure to pad prose that the differential itself warns about.
