#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Handoff checklists: zero overhead when absent, missing deliverables, foreign and door-parked waves, ticks, statuses, the shape gate.

echo "== 191. root resolution must not walk into a repo NESTED in the repo =="
# THE DEFECT, measured live on 2026-08-06: the Stop event's cwd is wherever the
# session last worked, and this tree holds repos INSIDE the repo -- submodules
# (private/renet) and gitignored non-submodule siblings (private/growth). Every
# root resolution started from that cwd, so project_root() stopped at the NESTED
# repo and the branch check read ITS branch: a session on 0804-1 was ordered to
# bootstrap agent/main/ because private/growth happened to be on main.
#
# CONTROL FIRST, and it is the pre-fix expression itself rather than a mutation:
# if `event.cwd or getcwd()` does NOT resolve to the nested repo on this
# fixture, the fixture is not reproducing the bug and the FIRE below proves
# nothing.
setup
NESTBASE="$BASE/nesting"
rm -rf "$NESTBASE"
mkdir -p "$NESTBASE/outer/.claude/hooks/stop" "$NESTBASE/outer/nested"
: >"$NESTBASE/outer/.git" # a FILE, as a worktree or submodule writes it
: >"$NESTBASE/outer/nested/.git"
OUT=$(
    export CLAUDE_PROJECT_DIR="$NESTBASE/outer" HOOKDIR
    HOOKDIR="$(dirname "$HOOK")"
    export NESTBASE
    python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
import wl_core as C

base = os.environ["NESTBASE"]
nested = os.path.join(base, "outer", "nested")
event = {"cwd": nested}
print("CONTROL", C.project_root(event.get("cwd") or os.getcwd()))
print("FIRE", C.project_root(C.project_start(event)))
# Rung 2: with no CLAUDE_PROJECT_DIR at all, a CLI run must anchor on the hook
# FILE's own repo, not on wherever the shell happens to be standing.
del os.environ["CLAUDE_PROJECT_DIR"]
os.chdir(nested)
print("CLI", C.project_start(), C.hook_repo_root())
PYEOF
)
if grep -qF "CONTROL $NESTBASE/outer/nested" <<<"$OUT"; then
    pass "191 CONTROL: the pre-fix ladder does resolve to the nested repo"
else
    fail "191 CONTROL: fixture does not reproduce the bug, so FIRE proves nothing: ${OUT:0:300}"
fi
if grep -qF "FIRE $NESTBASE/outer" <<<"$OUT" && ! grep -qF "FIRE $NESTBASE/outer/nested" <<<"$OUT"; then
    pass "191 FIRE: project_start anchors on the outer repo, not the nested one"
else
    fail "191 FIRE: still resolving into the nested repo: ${OUT:0:300}"
fi
CLI_LINE=$(grep "^CLI " <<<"$OUT")
CLI_START=$(awk '{print $2}' <<<"$CLI_LINE")
CLI_HOOK=$(awk '{print $3}' <<<"$CLI_LINE")
if [[ -n "$CLI_HOOK" && "$CLI_START" == "$CLI_HOOK" ]]; then
    pass "191 FIRE: with no CLAUDE_PROJECT_DIR the anchor is the hook file's repo"
else
    fail "191 FIRE: a CLI run still anchors on cwd (start=$CLI_START hook=$CLI_HOOK)"
fi
# The store path is the thing a wrong root DESTROYS: it is slugged from the
# root, so a root that moves orphans every open item in the old file. Pin it.
PATH_OUTER=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$NESTBASE/outer" python3 "$HOOK" --path)
PATH_NESTED=$(cd "$NESTBASE/outer/nested" && TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$NESTBASE/outer" python3 "$HOOK" --path)
if [[ "$PATH_OUTER" == "$PATH_NESTED" ]]; then
    pass "191 FIRE: --path is identical from the outer repo and from inside the nested one"
else
    fail "191 FIRE: --path moved with cwd ($PATH_OUTER vs $PATH_NESTED)"
fi

# ---------------------------------------------------------------------------
# 192 an hourly poll cron parked off :00 is still a poll cron
#
# THE INCIDENT (2026-08-07): CronCreate tells every session to avoid the :00 and
# :30 marks so the fleet does not hit the API on one instant, and offers
# "hourly -> 7 * * * *" as its example. is_poll_cron knew the hourly rung only
# as `0 * * * *`, so a session obeying both instructions had its poll cron
# counted as a second WORK cron, and the next stop ordered it to CronDelete the
# cron the previous stop had ordered it to create.
#
# THE FIRST FIX WAS WRONG and this case exists to keep it wrong: widening the
# schedule regex to any `<minute> * * * *` took this harness from 1 failure to
# 168, because an hourly WORK cron is indistinguishable from an hourly poll by
# schedule alone. Hence the negative assertions below -- they are not padding,
# they are the guard rail that reverted change would trip.
OUT=$(
    cd "$(dirname "$HOOK")" && python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
import wl_checks as W

POLL = {"schedule": "37 * * * *", "prompt": "run .claude/hooks/stop/worklist.py --poll d136ac61"}
WORK = {"schedule": "17 * * * *", "prompt": "pr-babysit HEARTBEAT: check CI, fix reds"}

checks = {
    "poll-offminute": W.is_poll_cron(POLL) is True,
    "work-hourly-not-poll": W.is_poll_cron(WORK) is False,
    "shape-still-sufficient": W.is_poll_cron({"schedule": "*/5 * * * *"}) is True,
    "shape-zero-still-works": W.is_poll_cron({"schedule": "0 * * * *"}) is True,
    "no-prompt-degrades": W.is_poll_cron({"schedule": "37 * * * *"}) is False,
    "daily-not-poll": W.is_poll_cron({"schedule": "0 9 * * *"}) is False,
}
bad = [k for k, v in checks.items() if not v]
print("CLASSIFY", "OK" if not bad else "BAD:" + ",".join(bad))
print("CANON", W.canonical_poll_schedule("37 * * * *"))
print("TIP", repr(W.poll_backoff_tip([POLL], 9999, False)))
PYEOF
)
if grep -q "^CLASSIFY OK$" <<<"$OUT"; then
    pass "192: an off-minute hourly POLL is recognised; an hourly WORK cron still is not"
else
    fail "192: poll-cron classification wrong: $(grep '^CLASSIFY' <<<"$OUT")"
fi
if grep -q "^CANON 0 \* \* \* \*$" <<<"$OUT"; then
    pass "192: an off-minute hourly poll canonicalises onto the ladder's top rung"
else
    fail "192: canonical_poll_schedule did not map :37 to the hourly rung: ${OUT:0:200}"
fi
if grep -q "^TIP ''$" <<<"$OUT"; then
    pass "192: the backoff ladder treats an off-minute hourly poll as capped, not unknown"
else
    fail "192: poll_backoff_tip mis-handled an off-minute hourly poll: $(grep '^TIP' <<<"$OUT")"
fi

# ---------------------------------------------------------------------------
# 193-203 v20: the /handoff checklist gate (agent/programs/<slug>/CHECKLIST.md).
#
# THE GAP THESE PIN: /handoff wrote a design suite and then TOLD the next
# session, in prose inside PROMPT.md, to seed the worklist. Prose gates
# nothing, so a handoff whose PROMPT.md was ignored or compacted away dropped
# program work silently. CHECKLIST.md is the machine-readable half, and its
# two halves are enforced by DIFFERENT means: deliverables are FILE-VERIFIED
# (the tick is bookkeeping, the file is the truth) while waves are
# tick-on-trust with store linkage through the `cl:<slug>/<wN>` token. Every
# case below is paired with a clean-fixture control, because a gate nobody has
# watched stay silent is a gate nobody knows fires for the right reason.

clfile() { # clfile <slug>  -- body on stdin, written to agent/programs/<slug>/CHECKLIST.md
    # Follows wl_checklist.py's glob, which moved out of docs/ with the rest of
    # the agent working tree. Left behind, these fixtures write somewhere the
    # gate no longer looks and every case below passes over an empty scan --
    # which is why case 193 exists to prove the silence is cheap, not dead.
    mkdir -p "$BASE/proj/agent/programs/$1"
    cat >"$BASE/proj/agent/programs/$1/CHECKLIST.md"
}

cldeliver() { # cldeliver <relpath> [content] -- a deliverable file under the repo
    mkdir -p "$BASE/proj/$(dirname "$1")"
    printf '%s' "${2-x}" >"$BASE/proj/$1"
}

echo "== 193. ZERO OVERHEAD: a repo with no checklist never hears the word =="
# The cost claim in wl_checklist's docstring is that a repo keeping no
# handoffs pays one glob and says nothing. That is only half a control: a
# silent gate and a dead gate look identical from here, so the second leg
# plants one checklist into the SAME fixture and demands the words appear.
setup
say "done for now"
brief_now
hand_now
OUT="$(run)"
if ! grep -qi "handoff" <<<"$OUT" && ! grep -qF "CHECKLIST" <<<"$OUT"; then
    pass "193: no agent/programs/<slug>/CHECKLIST.md means not one word about handoffs"
else
    fail "193: the gate talked about checklists that do not exist: ${OUT:0:300}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: deadbeef

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "agent/programs/demo/CHECKLIST.md" <<<"$OUT" && grep -qi "handoff" <<<"$OUT"; then
    pass "193 CONTROL-FOR-THE-CONTROL: one planted checklist and the same fixture speaks"
else
    fail "193 CONTROL: the silence above was a DEAD gate, not a cheap one: ${OUT:0:300}"
fi

echo "== 194. producing + a missing deliverable blocks its OWNER =="
setup
say "done for now"
brief_now
hand_now
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: deadbeef

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "DO NOT VERIFY" <<<"$OUT" && grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT"; then
    pass "194: the producing owner is blocked, and the row names the file and the verdict"
else
    fail "194: the producing block did not name the missing deliverable: ${OUT:0:400}"
fi
check "194: and the decision is block, not a note on an allowed stop" block "0 of 1 are present"

echo "== 194b. producing + everything verified: ONE step left, and it is the flip =="
cldeliver docs/demo/README.md "the readme"
OUT="$(run)"
if grep -qF "ONE step remains and it is the flip" <<<"$OUT" &&
    grep -qF "'Status: producing' to 'Status: executing'" <<<"$OUT" &&
    ! grep -qF "DO NOT VERIFY" <<<"$OUT"; then
    pass "194b: a verified producing checklist demands the status flip, nothing else"
else
    fail "194b: the flip demand is wrong: ${OUT:0:400}"
fi

echo "== 195. a FOREIGN producing checklist is reported, never blocked on =="
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile demo <<'MD'
# Handoff checklist: demo
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF '"decision": "block"' <<<"$OUT" &&
    grep -qF "that session's to finish" <<<"$OUT"; then
    pass "195: another session's producing handoff rides the report and blocks nobody"
else
    fail "195: a foreign producing checklist was mis-adjudicated: ${OUT:0:400}"
fi
if ! grep -qF "adopt it by editing" <<<"$OUT"; then
    pass "195 CONTROL: a LIVE owner gets no adoption hint (that would be a land grab)"
else
    fail "195 CONTROL: the adoption hint fired on a live owner: ${OUT:0:400}"
fi

echo "== 195b. the same checklist, owner's transcript DEAD: adopt or supersede =="
# projects_dir is the transcript's own directory (wl_checks.py:1678), so an
# aged cafe0000*.jsonl beside the fixture transcript is exactly what
# owner_age_hours reads. Planted rather than mocked, for that reason.
touch -d '-48 hours' "$BASE/cafe0000-dead.jsonl"
OUT="$(run)"
if grep -qF "adopt it by editing the 'Owner:' line" <<<"$OUT" &&
    grep -qF "agent/programs/demo/CHECKLIST.md" <<<"$OUT" && grep -qF "superseded" <<<"$OUT"; then
    pass "195b: a dead owner turns the advisory into an adoption offer"
else
    fail "195b: no adoption hint for an abandoned handoff: ${OUT:0:500}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 196. TICKED but missing: the file is the truth, the tick is bookkeeping =="
# The wave is claimed by a peer rather than ticked, so the deliverable check
# is the ONLY thing that can speak here and the control below is a real allow
# instead of a different violation wearing the same fixture.
setup
say "done for now"
brief_now
hand_now
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT"; then
    pass "196: a ticked box does not save a deliverable that is not on disk"
else
    fail "196: the ticked-but-missing deliverable passed: ${OUT:0:400}"
fi

echo "== 196b. EMPTY is not MISSING, and the row says which =="
cldeliver docs/demo/README.md ""
OUT="$(run)"
if grep -qF "d1 docs/demo/README.md -- EMPTY" <<<"$OUT" &&
    ! grep -qF -- "-- MISSING" <<<"$OUT"; then
    pass "196b: a 0-byte deliverable reads as EMPTY, distinctly from MISSING"
else
    fail "196b: the truncated deliverable was mis-named: ${OUT:0:400}"
fi
cldeliver docs/demo/README.md "the readme"
check "196b CONTROL: a non-empty file clears the check entirely" allow ""

echo "== 197. an UNCOVERED wave blocks, and carries its own one-command exit =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "w1 UNCOVERED" <<<"$OUT" && grep -qF "cl:demo/w1" <<<"$OUT" &&
    grep -qF -- "--add deadbeef 'cl:demo/w1 Wave A: wire the thing'" <<<"$OUT"; then
    pass "197: the uncovered wave names its token and the exact --add that claims it"
else
    fail "197: the uncovered wave has no runnable exit: ${OUT:0:500}"
fi

echo "== 197b. claiming it with --add moves the work into the ORDINARY open-items check =="
# DISJOINTNESS, not merely absence: the cl-waves needle must go while the
# open-item it created appears, because a gate that stopped firing AND took
# the work with it would look identical from a one-needle assertion.
reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" >/dev/null
export WORKLIST_FOCUS=off
OUT="$(run)"
if ! grep -qF "UNCOVERED" <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT" &&
    grep -qF "cl:demo/w1" <<<"$OUT"; then
    pass "197b: a claimed wave stops blocking as a wave and starts blocking as an item"
else
    fail "197b: coverage either did not register or swallowed the work: ${OUT:0:500}"
fi
unset WORKLIST_FOCUS

echo "== 197c. a PEER's item covers the wave for everybody, which is the point =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "UNCOVERED" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "197c: once ANY session claims the wave, the redundant block on the others lifts"
else
    fail "197c: a peer-claimed wave still blocked this session: ${OUT:0:400}"
fi

echo "== 198. DONE-BUT-UNTICKED: the store settled it, the box did not =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "wave A landed, suite run green, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT" && grep -qF "#$IID" <<<"$OUT" &&
    grep -qF "tick '- [x] w1' in agent/programs/demo/CHECKLIST.md" <<<"$OUT"; then
    pass "198: a ticked store item with an unticked box is called out with the box to tick"
else
    fail "198: the settled wave did not demand its tick: ${OUT:0:500}"
fi

echo "== 198c. a wave closed through a DOOR must NOT be told to tick its box =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: set the production secrets and cut over
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: set the production secrets and cut over" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "door:operator-only - needs secrets no session holds; brief at docs/demo/RUNBOOK.md:12" >/dev/null
OUT="$(run)"
if ! grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT"; then
    pass "198c: a door-closed wave is covered and correctly unticked, not demanded as done"
else
    fail "198c: the gate demanded a FALSE tick for work no session did: ${OUT:0:500}"
fi

echo "== 198d. control: the same wave WITHOUT a door still demands its tick =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: set the production secrets and cut over
MD
IID=$(reqcli --add deadbeef "cl:demo/w1 Wave A: set the production secrets and cut over" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "cut over on host-1, verified, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "w1 DONE-BUT-UNTICKED" <<<"$OUT"; then
    pass "198d: control fires -- 198c passes because of the door, not because the check went silent"
else
    fail "198d: the door exemption swallowed a genuinely settled wave: ${OUT:0:500}"
fi

echo "== 198b. every box ticked under 'executing' means the status is stale =="
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "everything is settled; set 'Status: done'" <<<"$OUT"; then
    pass "198b: an all-settled executing checklist is asked for the last edit it needs"
else
    fail "198b: a finished program was left at executing forever: ${OUT:0:400}"
fi

echo "== 199. 'done' is INACTIVE, and is gated on being honestly done =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "CHECKLIST" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "199: a genuinely done handoff costs a later session nothing at all"
else
    fail "199: a done checklist is still talking: ${OUT:0:400}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "wave w1 is not ticked, yet the checklist claims done" <<<"$OUT"; then
    pass "199: 'done' with an unticked wave is a lie the next session would believe"
else
    fail "199: a dishonest done header passed: ${OUT:0:400}"
fi

echo "== 199b. 'superseded' is the terminal escape and adjudicates nothing =="
clfile demo <<'MD'
# Handoff checklist: demo
Status: superseded

## Deliverables
- [ ] d1 file:docs/demo/GONE.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "CHECKLIST" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "199b: an abandoned program stops costing anything the moment it says so"
else
    fail "199b: superseded still adjudicated: ${OUT:0:400}"
fi

echo "== 200. the SHAPE gate collects every defect, and scopes itself to the bad file =="
# One error per stop would cost one turn per typo, so the parser collects them
# all. The clean checklist alongside is the control: a malformed file must not
# smear its verdict over its neighbours.
setup
say "done for now"
brief_now
hand_now
cldeliver docs/good/README.md "the readme"
clfile good <<'MD'
# Handoff checklist: good
Status: done

## Deliverables
- [x] d1 file:docs/good/README.md

## Waves
- [x] w1 Wave A: the finished one
MD
clfile broken <<'MD'
# Handoff checklist: broken
Owner: deadbeef

## Deliverables
- [ ] d1 nothing verifies this one
- [ ] d1 file:docs/broken/README.md
- [ ] w9 a wave id under the deliverables

## Waves
- [z] w1 a state character that does not exist
MD
OUT="$(run)"
NROWS=0
for needle in "no 'Status:' line in the first 10 lines" \
    "does not belong under that section" \
    "carries no 'file:<path>' token" \
    "duplicate id 'd1'" \
    "not a checklist item"; do
    grep -qF "$needle" <<<"$OUT" && NROWS=$((NROWS + 1))
done
if grep -qF "is MALFORMED" <<<"$OUT" && [[ "$NROWS" -ge 3 ]]; then
    pass "200: the malformed checklist blocks and reports $NROWS defects in one pass"
else
    fail "200: shape diagnosis is thin (rows=$NROWS): ${OUT:0:600}"
fi
if grep -qF "agent/programs/broken/CHECKLIST.md is MALFORMED" <<<"$OUT" &&
    ! grep -qF "agent/programs/good/CHECKLIST.md" <<<"$OUT"; then
    pass "200 CONTROL: the clean checklist beside it is never mentioned"
else
    fail "200 CONTROL: the shape verdict smeared onto a healthy file: ${OUT:0:600}"
fi

echo "== 201. the poll fast path FORFEITS on a live checklist, stat-only =="
# The banked pollbase carries clsig and cl_live (wl_checks.bank_pollbase).
# Leg 1 banks a LIVE-but-non-blocking world (wave claimed by a peer), so
# cl_live=1 with an unchanged signature -- which is the only thing that can
# make the silent path forfeit here. Legs 2 and 3 are the controls: the same
# dance with no checklist at all, and with a settled one, must stay silent.
setup
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
as_peer cafe0000 reqcli --add cafe0000 "cl:demo/w1 Wave A: wire the thing" >/dev/null
say "answer

## Remaining
- nothing of mine"
check "201: the full stop allows and banks the checklist world" allow ""
BANK="$(cat "${WL%.md}.pollbase-deadbeef")"
if grep -qF '"cl_live": 1' <<<"$BANK" && grep -qE '"clsig": "[0-9a-f]{16}"' <<<"$BANK"; then
    pass "201: the pollbase banks the live count beside a stat-only signature"
else
    fail "201: the checklist world was not banked: $BANK"
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "201: a live checklist forfeits the silent poll even with an unchanged world"
else
    fail "201: the poll went silent while a live handoff was outstanding"
fi
setup
brief_now
hand_now
say "answer

## Remaining
- nothing of mine"
check "201 CONTROL: baseline stop with no checklist at all" allow ""
if grep -qF '"cl_live": 0' <<<"$(cat "${WL%.md}.pollbase-deadbeef")"; then
    pass "201 CONTROL: a repo with no handoffs banks cl_live=0, which is what keeps polls free"
else
    fail "201 CONTROL: an empty repo banked a live count: $(cat "${WL%.md}.pollbase-deadbeef")"
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "201 CONTROL: with no checklist the poll stop is still perfectly silent"
else
    fail "201 CONTROL: the gate broke the silent path for everyone: rc=$RC '${OUT:0:200}'"
fi
setup
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
say "answer

## Remaining
- nothing of mine"
check "201 CONTROL: baseline stop with a SETTLED checklist" allow ""
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "201 CONTROL: a done program costs polls nothing, exactly as promised"
else
    fail "201 CONTROL: a settled checklist still charged the poll: rc=$RC '${OUT:0:200}'"
fi
# The banked cl_live is still 0, so the ONLY thing that can forfeit the silent
# path on the next poll is the moved signature -- and the battery it pays for
# is what catches the un-tick this edit smuggled in.
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if grep -qF "reality disagrees" <<<"$OUT"; then
    pass "201: a MOVED signature forfeits too, so an edited checklist cannot hide behind a poll"
else
    fail "201: an edited checklist slipped past the poll fast path: '${OUT:0:200}'"
fi

echo "== 202. checklists_sig() is STAT-ONLY, and the unreadable file proves it =="
# A contract, not an optimisation: the poll path compares this value, and a
# version that opened files would pay exactly the cost the fast path exists to
# avoid. A chmod-000 checklist is the instrument -- stat still answers where
# read cannot, so the signature must come back while the ADJUDICATION (which
# does read) fails closed into the ALWAYS-tier unreadable violation. The key
# it fails closed UNDER is asserted too, and it is per-slug (`cl-shape:locked`)
# for the reason case 204 pins: one unreadable checklist must not evict a
# second one from the rotation.
setup
mkdir -p "$BASE/proj/agent/programs/locked"
printf 'Status: executing\n' >"$BASE/proj/agent/programs/locked/CHECKLIST.md"
chmod 000 "$BASE/proj/agent/programs/locked/CHECKLIST.md"
OUT=$(
    cd "$(dirname "$HOOK")" && CLROOT="$BASE/proj" python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, ".")
import wl_checklist as CL

root = os.environ["CLROOT"]
path = os.path.join(root, "agent", "programs", "locked", "CHECKLIST.md")
try:
    open(path).read()
    print("READABLE yes")
except OSError:
    print("READABLE no")
print("SIG", CL.checklists_sig(root))
v, a, live = CL.checklist_findings(root, None, "deadbeef-1111", "")
print("V", v[0][0], v[0][1], live)
print("TEXT", "THIS IS A HOOK BUG" in v[0][2])
PYEOF
)
chmod 644 "$BASE/proj/agent/programs/locked/CHECKLIST.md"
if grep -q "^READABLE no$" <<<"$OUT"; then
    pass "202 CONTROL: the fixture really is unreadable, so the leg below means something"
else
    fail "202 CONTROL: chmod 000 did not deny this process (running as root?): ${OUT:0:200}"
fi
if grep -qE "^SIG [0-9a-f]{16}$" <<<"$OUT"; then
    pass "202: checklists_sig returns a signature for a file it may not open"
else
    fail "202: the stat-only signature raised or came back malformed: ${OUT:0:300}"
fi
if grep -q "^V cl-shape:locked True 1$" <<<"$OUT" && grep -q "^TEXT True$" <<<"$OUT"; then
    pass "202: and the reading half fails CLOSED, ALWAYS-tier, naming itself a hook bug"
else
    fail "202: an unreadable checklist did not fail closed: ${OUT:0:300}"
fi
rm -f "$BASE/proj/agent/programs/locked/CHECKLIST.md"

echo "== 203. SessionStart hands a new session the live checklists =="
setup
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
- [ ] w2 Wave B: land the rest
MD
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "LIVE HANDOFF CHECKLISTS" <<<"$out" &&
    grep -qF "agent/programs/demo/CHECKLIST.md [executing] owner=cafe0000 deliverables 1/1 verified, waves 1/2 settled" <<<"$out"; then
    pass "203: the listing carries status, owner and both progress fractions"
else
    fail "203: SessionStart did not hand back the live checklist: ${out:0:400}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if ! grep -qF "LIVE HANDOFF CHECKLISTS" <<<"$out"; then
    pass "203 CONTROL: a settled checklist is not context anyone needs handed back"
else
    fail "203 CONTROL: the listing surfaced a done handoff: ${out:0:400}"
fi

# ---------------------------------------------------------------------------
# 204-206 v20b: ONE KEY PER CHECKLIST, and an advisory that gives no orders.
# Both gaps were found by the automated review on PR #563, and both are about
# a second concurrent handoff, which this repo ran two of on the day they
# landed.
#
# 204/205 pin the KEY. Every checklist finding used to be pushed under a fixed
# string -- "cl-waves", "cl-foreign" and friends -- while two things downstream
# read that string as an IDENTITY. The focused block's rotation builds its tie
# breaker with `order = {v[0]: i for ...}`, a dict comp in which duplicate keys
# COLLAPSE, so two violations sharing a key get identical sort tuples and `min`
# returns the first one forever; and outq_add finds a non-sticky entry by key
# alone, so the second advisory OVERWRITES the first rather than queueing
# beside it. The second handoff was therefore starved permanently, not for a
# stop or two, and only ever showed up inside the "N more outstanding" count.
#
# 206 pins the AUDIENCE. The drift text was built once and routed either to a
# blocking violation (owner) or to the advisory (non-owner), so a session that
# does not own the handoff was told to restore the artifacts "in this turn".
# Acting on that means editing another session's header or its files, which is
# how a peer's shared STATE.md was destroyed here.
