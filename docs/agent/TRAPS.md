# Traps

Ways a session gets *fooled* — as opposed to ways it gets *blocked*. Each entry
cost real time on a real wave, and each is written so the next reader can
recognise the shape before paying for it again.

Mechanics of a specific subsystem do not belong here. CI behaviour (watchdog
semantics, job-roster growth, run-selection, gate quick-fixes) lives in
[ci-gates.md](ci-gates.md); escape hatches and their `BLOCKER:` reasons live in
[suppressions.md](suppressions.md). This file is about judgement.

---

## A wrong comment is more dangerous than a wrong commit message

A commit message ages into the log. **An in-code comment is what the next person
reads immediately before deciding whether to change the line it describes.**

Found 2026-08-04. A line read `${DRILL_KEEP_WORK:-0}` inside an EXIT trap. It
looked redundant, and a comment was written calling it "dead code and, worse, a
lie". Both the comment and the reasoning behind it were wrong: the default
expansion is cheap insurance that keeps the trap from aborting under `set -u`
if the source-then-init order ever changes. Had that comment shipped, the next
reader would have deleted a defensive line **on the authority of the comment
itself**, and the teardown would have died half-way, stranding a gateway and a
sandbox.

So:

- Overstating in a comment is not a style problem. It is a future defect with a
  delay fuse, and the fuse is lit by someone who trusts you.
- When a line looks redundant, the comment's job is to say *why it is not*, or
  to say plainly that nobody has checked. "This looks removable and is not,
  because X" is worth more than any confident-sounding claim.
- If you catch a wrong comment before it ships, fix it forward as its own
  change. It is cheaper than the incident it prevents.

## A check that cannot fail is not evidence

Before believing a clean result, make the check produce a RED on known-bad input
**through the same path**. An empty result and a skipped result are
indistinguishable from the outside.

Three real examples from one wave, all caught only because a control was run:

- A `git archive` silently extracted nothing, so a `[ a -nt b ]` staleness test
  compared two *absent* files and returned false — which looks exactly like a
  genuine "not stale" answer.
- A deliberately restricted `PATH` also hid `bash` itself, so the command under
  test executed **neither** branch while appearing to run.
- A log-collector script was written to gather diagnostics from a directory that
  the tool being diagnosed **deletes on exit**. It would have collected nothing,
  every time, and reported success.

This applies recursively: to the check, and to the check of the check.

## A ruling from an artifact is a hypothesis, whoever issued it

A briefing, a config file, a diff, or a teammate's message describes what someone
*believed* when they wrote it. When the claim is checkable, check it, then act.

Two from the same wave, in opposite directions:

- A validator's suggestion text read "Sections added (translate and add these)".
  It describes the **English** delta and never inspects the translation at all.
  Taken at face value it would have caused twelve already-correct professional
  translations to be rewritten.
- A colleague's correction invented a failure window ("the trap can fire before
  the variable is set") that could not occur, because the trap is installed
  inside a function called long after the assignment runs. The *conclusion* was
  still right; the *mechanism* was not. Both halves matter, because the next
  decision is made on the mechanism.

Report the refutation with the evidence, and say plainly that the ruling was
wrong. Someone who is only ever agreed with is a single point of failure.

## Errors stack: fixing the first one promotes the second

Clearing a build error does not reveal the next one, it *makes the next one
reachable*. A drills leaf failed on a missing `llvm-strip`; with that fixed the
same job failed again, on a different step entirely, for an unrelated reason.
The red looked identical from the run summary both times.

After fixing a blocking error, re-run the thing it was blocking. Clearing the
first error is not progress until you have.
