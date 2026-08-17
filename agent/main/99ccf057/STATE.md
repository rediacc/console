

## SESSION 99ccf057 2026-08-10T05:26:58Z

Trap-enforcement program: converting traps that lived only in markdown into mechanical
instruments, after the operator ruled that a doc an agent can skip reading is not a
control.

ALL FOUR PRs ARE GREEN, REVIEWED, AND WAITING ON THE OPERATOR'S /pr-merge. DO NOT MERGE.
DO NOT PUSH MAIN. Stacked, each based on its predecessor's branch, so merge order
matters: #563 (handoff CHECKLIST gate) -> #565 (STATE.md one owned section per session)
-> #566 (block-blanket-git-add.sh) -> #567 (trapguard rules + judge order filter +
dead-worker remedy). #567 is branch 0809-5 at head 12bd20ec8, verified 45 SUCCESS /
39 SKIPPED / zero anything else, not draft, MERGEABLE, three review passes each answered
with its own reply.

NOTHING OF MINE IS UNCOMMITTED for those PRs. The M markers on .claude/hooks/stop/*.py
are expected: HEAD sits on main while the work lives on the branch.

ONE ITEM STILL OPEN, #941ffc9f, and it is NOT part of any PR yet. Two new files exist
UNCOMMITTED and on no branch:
  docs/agent/main/PLAN-promote-mutation-runner.md  (Status: executing)
  .ci/scripts/test/mutate-check.sh                 (implemented, shellcheck clean)
The tool runs a suite twice, mutant then baseline, and exits 0 only when the mutant is
RED on the named cases and the baseline is GREEN. Its whole reason to exist is the
verdict PROVED NOTHING, for when both directions are red, because a case that can never
pass goes red under every mutation including a no-op one.

THE TOOL HAS BEEN WRONG TWICE, BOTH MY DESIGN, BOTH NOW FIXED. First it blamed the check
when the real cause was that I passed pass()-branch prose while the mutant emits
fail()-branch wording. Then, worse, it matched the same pattern against FAIL lines in the
mutant and PASS lines in the baseline, so the interface could never be satisfied and it
issued PROVED NOTHING about a case behaving perfectly. --expect-red now takes a CASE ID,
checked as FAIL:<id> in the mutant and PASS:<id> with no FAIL:<id> in the baseline.

KNOWN AND ACCEPTED: case 191 (test-worklist-v5.sh:8607, assertion :8664) reds inside the
out-of-repo sandbox because it asserts the anchor is the hook file's own repo. The tool
NAMES it rather than filtering it, deliberately.

## Next action

Read the third mutate-check run (background task bnup18rov). Expect mutant RED on 208,
baseline GREEN, exit 0. Verify by running the command yourself if the log is ambiguous:

  bash .ci/scripts/test/mutate-check.sh --file .claude/hooks/stop/wl_checks.py \
    --from "    if ladder_gone:" --to "    if False:" --expect-red 208

Each run takes 8+ minutes (two full suite passes), so run it with run_in_background.

When it exits 0, the tool is proven and #941ffc9f can be ticked. Then decide packaging
and ASK rather than assume: these two files could ride a fifth stacked PR on 0809-5, or
wait for the operator to merge the stack first. Do not open a fifth PR without asking,
because four unmerged PRs already await a decision and a fifth deepens a stack nobody has
merged yet. Never edit .claude/hooks/stop/*.py while any suite run is in flight: every
suite call re-imports those modules, so mid-run edits contaminate the results silently.
