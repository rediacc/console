# STATE — TWO LIVE SESSIONS SHARE THIS BRANCH. Both blocks are current.
# MERGE, never rewrite: a plain rewrite destroyed B's block twice. Cap is 4000
# PER `## SESSION` block, so there is room to merge honestly.
#
# NOTE ON B'S BLOCK BELOW, added by A without editing its content: it is
# stamped 11:50Z, now ~8.5h old, and the head it names is long superseded.
# Read it for B's intent, never for its facts; re-derive head from git.

## SESSION A (2fd369e0) — ~20:15Z — IDLE, NOTHING IN FLIGHT
All of A's work is COMMITTED AND PUSHED. No path held, no agent running, no
worklist item open, no request unanswered. Teammate roster reaped (8 retired).
B is pushing frequently: head was d04b1f564, then 798e93121, now 37fc70674.
A's tree is CLEAN throughout, because A and B SHARE this worktree, so B's
commits move A's HEAD. That is why A never committed anything itself.

WHAT A LANDED (each verified against artifacts, NOT from agent reports -- five
of six writers finished without messaging, and one report that did exist was
only found later in the durable inbox):
the 5-item plan (external_quality 3-state flag + run-external-gate.sh, since
continue-on-error is banned repo-wide; the label chain code->declared->exists->
shown-on-every-PR; the autopilot dispatch campaign; the PR label-guide comment;
worklist CLI cap, hook-wiring assertion, renet GPG retry) and the CI runner
profiler on the operator's ENVIRONMENTAL framing (runners are free on this
public repo, so the case is that a job using ~1 core on a 4-vCPU VM burns ~4x
the core-minutes it needs).

FIVE DEFECTS FIXED, THREE OF THEM A'S OWN. Carry these forward:
 - check-dead-case-arms.sh was BLIND TO ITS OWN FOUNDING DEFECT: its header
   comment mentioned `cores=`, key_is_live grepped comments, so the tree's only
   occurrences were its own prose and it ruled the dead arm live. GENERAL FORM:
   any script documenting a bad pattern in prose vaccinated the whole tree
   against detecting it. Fixed, pinned by a permanent `cores=` fixture.
 - MISLABEL vs HOST_LEAK in report.awk PARTITION the space and must NOT be
   merged. Do-not-fix; both have firing proofs with controls.
 - B caught a defect A missed: test-profiler-report.sh INHERITED
   GITHUB_STEP_SUMMARY, which Actions always sets, so panel.sh wrote to the
   summary file while the test read stdout -- green locally, red on every
   runner. Now pinned at the seam. A re-ran it under the CI condition: exit 0.

NOT TEST-PROTECTED, never repeat as if guarded: the "2.7s on 1 vCPU, bare
image" overhead figure is ad-hoc; and PROC_HOST + non-slim label + UNKNOWN
fingerprint is caught by neither guard, ACCEPTED as inherent to a heuristic.

MESSAGING, learned the hard way today: the waiter must run as a REAL
background task (nohup is not enough; a PostToolUse hook says NOT LISTENING)
and must be RELAUNCHED every time it fires. B was deaf for an hour because it
SENT as 4c3e095a while its cron and waiter ran as d136ac61 -- different
inboxes, completely silent failure. B's own follow-up found the fix:
CLAUDE_CODE_SESSION_ID is the one reliable portable identity source.

## Next action
A: nothing queued. Two items belong to the OPERATOR:
 1. Dispatch .github/workflows/profiler-probe.yml once 0804-1 reaches main. It
    settles whether GitHub's UNPRIVILEGED slim container exposes /sys/fs/cgroup
    the way local docker does, and whether a JS action's post: hook fires when
    nested inside a composite -- that second answer decides whether wiring the
    profiler is ONE line in setup-workspace or 26 explicit edits.
 2. The PR review itself.
If woken by the waiter: read the body, RELAUNCH THE WAITER, then act.

