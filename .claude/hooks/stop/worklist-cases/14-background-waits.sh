#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Background waiting: check-ins, impure waits, drained waiters, roster reaping, and the transcript join that finds the task store.

echo "== 161. an OPEN operator request suppresses the stuck exempt-overrun =="
# Terminal-hold shape: all work done, the one question posted to the operator
# with DEFAULT: hold, long-lived teammate tasks keeping live_bg nonempty. The
# ball is verifiably out of this session's court, so the overrun must not
# nag it into fake motion; the suppression lifts when the request resolves.
setup
brief_now
hand_now
export WORKLIST_STUCK_ROUNDS=1
task 7 pending "operator-gated decision"
reqcli --ask deadbeef operator "merge the green PR? DEFAULT: hold and do not merge" >/dev/null
BG='[{"id":"tz1","type":"teammate","status":"running","description":"long-lived teammate"}]'
FIRED=0
for i in 1 2 3 4 5 6; do
    newturn
    say "answer

## Remaining
- #7 operator-gated decision (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
if [[ "$FIRED" == 0 ]]; then
    pass "161: waiting on an open operator question is not stuck"
else
    fail "161: the hold state was nagged as stuck: ${OUT:0:250}"
fi
# CONTROL: the same shape WITHOUT the operator request still overruns.
setup
brief_now
hand_now
task 7 pending "operator-gated decision"
BG='[{"id":"tz1","type":"teammate","status":"running","description":"long-lived teammate"}]'
FIRED=0
for i in 1 2 3 4 5 6; do
    newturn
    say "answer

## Remaining
- #7 operator-gated decision (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
unset WORKLIST_STUCK_ROUNDS
BG='[]'
if [[ "$FIRED" == 1 ]]; then
    pass "161 CONTROL: without the request the exempt-overrun still fires"
else
    fail "161 CONTROL: the overrun never fired: ${OUT:0:250}"
fi

echo "== 163. v15: pure background wait gets a 15-min check-in, not make-work =="
# The state: live background jobs, no open items, no expired deferral. The
# hook recognizes it as legitimate and demands only a bounded check-in whose
# worker facts it gathered itself from the output streams.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
# v19: an UNBLOCKED pending task now (correctly) makes the wait impure, so this
# case's parked task is in_progress -- the state a watched-by-this-session job
# actually has. The unblocked-pending behavior gets its own case 163y below.
task 7 in_progress "waiting on the nightly"
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
# Stop 1 SEEDS the wait clock silently: the check-in means "you have been
# waiting 15 minutes", never "you started waiting".
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163 seed: first sight of the wait state does not fire"
else
    fail "163 seed: fired on first sight: ${OUT:0:250}"
fi
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT" && grep -qF "bw1 (long CI watch)" <<<"$OUT" &&
    grep -qF "output last grew" <<<"$OUT"; then
    pass "163: after 15 waited minutes the check-in fires with the hook's own stream facts"
else
    fail "163: check-in wrong: ${OUT:0:300}"
fi
# CONTROL: inside the window it does not repeat (latched on fire).
newturn
say "bw1 confirmed: the long CI watch stream matches; nothing stuck.

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163 CONTROL: no second check-in inside the 15-minute window"
else
    fail "163 CONTROL: the check-in drumbeat: ${OUT:0:250}"
fi

echo "== 163y. v19: an unblocked pending task makes the wait IMPURE and gets named =="
# Operator, 2026-08-08: a session idled for hours in "pure background wait"
# beside a fully planned, unblocked pending task; the check-in kept certifying
# the wait because it never consulted the harness queue. Now: pending with no
# unresolved blocker -> the check-in fires as WORKABLE-TASKS and names it;
# pending with a live blocker -> the wait stays pure (the control).
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
task 7 pending "fully planned and unblocked"
say "answer

## Remaining
- #7 fully planned and unblocked (pending)"
OUT="$(run)" # seed the clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 fully planned and unblocked (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #7 fully planned and unblocked" <<<"$OUT" &&
    ! grep -qF "not a demand for other work" <<<"$OUT"; then
    pass "163y: the check-in names the unblocked pending task instead of certifying the wait"
else
    fail "163y: workable task not named: ${OUT:0:300}"
fi
# CONTROL: the same task behind a LIVE blocker keeps the wait pure.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
task 6 pending "the prerequisite"
task 7 pending "parked behind 6" 6
say "answer

## Remaining
- #6 the prerequisite (pending)
- #7 parked behind 6 (pending)"
OUT="$(run)" # seed
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #6 the prerequisite (pending)
- #7 parked behind 6 (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #6 the prerequisite" <<<"$OUT" &&
    ! grep -qF "task #7 parked behind 6" <<<"$OUT"; then
    pass "163y CONTROL: the blocked task stays unnamed; its live blocker is the one named"
else
    fail "163y CONTROL: blocker logic wrong: ${OUT:0:300}"
fi

echo "== 163x. v19: the transcript join finds a renamed task store; ambiguity refuses =="
# Review finding on #559: the fallback in _resolve_tasks_dir had no committed
# coverage (the original proof ran as ephemeral scratchpad python). This case
# drives it through the REAL hook: the primary session-deadbeef dir is EMPTY
# (setup creates it bare), the actual tasks live under a differently-named
# session-* dir, and the only join evidence is a TaskCreate result line in the
# transcript tail. The workable-tasks check-in naming the task proves the
# whole chain: resolve -> actionable -> fire.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
mkdir -p "$BASE/tasks/session-teamzzzz"
printf '{"id":"21","status":"pending","subject":"the mismatch fixture task","blockedBy":[]}\n' \
    >"$BASE/tasks/session-teamzzzz/21.json"
say "Task #21 created successfully: the mismatch fixture task"
say "answer

## Remaining
- #21 the mismatch fixture task (pending)"
OUT="$(run)" # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #21 the mismatch fixture task (pending)"
OUT="$(run)"
if grep -qF "WORKABLE TASKS" <<<"$OUT" && grep -qF "task #21 the mismatch fixture task" <<<"$OUT"; then
    pass "163x: the join resolved the renamed store off the transcript and named its task"
else
    fail "163x: fallback resolution failed: ${OUT:0:300}"
fi
# CONTROL: TWO dirs matching the same TaskCreate line -> the join refuses, no
# task is named, the wait stays pure. Fresh setup so the durable resolution
# cache from the fire case cannot leak in.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
BG='[{"id":"bw1","type":"shell","status":"running","description":"long CI watch"}]'
for d in teamzzzz teamyyyy; do
    mkdir -p "$BASE/tasks/session-$d"
    printf '{"id":"21","status":"pending","subject":"the mismatch fixture task","blockedBy":[]}\n' \
        >"$BASE/tasks/session-$d/21.json"
done
say "Task #21 created successfully: the mismatch fixture task"
say "answer

## Remaining
(nothing tracked here)"
OUT="$(run)" # seed
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
(nothing tracked here)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT" && ! grep -qF "task #21" <<<"$OUT"; then
    pass "163x CONTROL: two candidate dirs refuse the join; no manufactured task, wait stays pure"
else
    fail "163x CONTROL: ambiguity did not refuse: ${OUT:0:300}"
fi

echo "== 163z. v18: a CONFIRMED inbox waiter owes no check-in and needs no poll cron =="
# The waiter blocks until something new arrives for this session and then EXITS,
# and its exit is the harness notification that wakes the session. Its liveness
# IS its report, so the two supervision demands that exist to make a session
# account for a silent background job do not apply to it. Both relaxations are
# keyed on `confirmed` and on nothing weaker.
#
# A REAL wl_wait.py process, not a fake command string: `confirmed` means the OS
# can see a live descendant carrying the command, so a fixture that only claims
# the command would prove the string match and not the verdict.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
WAITER_CMD="python3 $(dirname "$HOOK")/wl_wait.py deadbeef --timeout 3"
TMPDIR="$BASE/waittmp" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
WAITER_PID=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter"}]))
PYEOF
)"
# Premise, asserted rather than assumed: if the verdict is not `confirmed` this
# whole case is vacuous and would "pass" for the wrong reason.
VERDICT=$(
    cd "$BASE" && python3 - "$(dirname "$HOOK")" "$WAITER_CMD" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
bg = [{"id": "wt1", "type": "shell", "status": "running", "command": sys.argv[2]}]
print(L.verify_background(bg, ancestors={int(os.environ["WORKLIST_HARNESS_PID"])}).get("wt1"))
PYEOF
)
if [[ "$VERDICT" == "confirmed" ]]; then
    pass "163z premise: the live waiter verifies as confirmed"
else
    fail "163z premise: waiter verdict is '$VERDICT', not confirmed -- this case is vacuous"
fi
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
task 7 in_progress "waiting on the inbox"
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}  # 15 minutes overdue
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z: an overdue check-in is SUPPRESSED when the only live task is a confirmed waiter"
else
    fail "163z: the check-in fired at a waiter: ${OUT:0:250}"
fi
# The needle is lifted VERBATIM from V_NO_POLL_CRON. The first draft of this
# line grepped for "no inbox poll" and "poll cron", neither of which appears in
# that message at all -- so the assertion could never fail and passed for a
# reason unrelated to the waiter.
if ! grep -qF "NOTHING LISTENING FOR CROSS-SESSION MAIL" <<<"$OUT"; then
    pass "163z: a work cron with NO poll cron is accepted beside a confirmed waiter"
else
    fail "163z: no-poll fired despite the waiter: ${OUT:0:250}"
fi
kill "$WAITER_PID" 2>/dev/null
wait "$WAITER_PID" 2>/dev/null

echo "== 163q. v20: a DRAINED session is told to STOP its waiter =="
# THE OTHER HALF OF 163z/163w. Those two force a session with work to LISTEN;
# nothing ever told a finished one to stop, so a drained session held a process
# for up to an hour and was nagged on every tool call to relaunch it. Observed
# live 2026-08-19: zero open items, zero background jobs, VMs torn down, and
# still "NOT LISTENING".
#
# A REAL wl_wait.py process again, for 163z's reason: the advice is keyed on
# `confirmed`, so a fixture that only claims the command would prove the string
# match and not the verdict.
drained_waiter() { # a live waiter + the BG row that declares it; sets BG
    WAITER_CMD="python3 $(dirname "$HOOK")/wl_wait.py deadbeef --timeout 3"
    TMPDIR="$BASE/waittmp" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
    WAITER_PID=$!
    export WORKLIST_HARNESS_PID=$$
    sleep 1
    BG="$(
        python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt9", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter"}]))
PYEOF
    )"
}
stop_waiter() {
    kill "$WAITER_PID" 2>/dev/null
    wait "$WAITER_PID" 2>/dev/null
}
drained_setup() { # the common fixture: fresh world, waiter running, queue drainable
    setup
    brief_now
    hand_now
    mkdir -p "$BASE/bgout"
    export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
    # The advice is a QUEUED REPORT, not a violation, and OUTQ_PER_STOP is 1 by
    # default -- so without this the case would be measuring queue position
    # rather than the check.
    export WORKLIST_REPORT_PER_STOP=6
}
DRAINED_MSG="all of it is finished and the tree is clean

## Remaining
- nothing open, nothing in flight, no pending task"
drained_setup
drained_waiter
# Premise, asserted rather than assumed, exactly as 163z does: an unconfirmed
# waiter makes every assertion below vacuous and green.
VERDICT=$(
    cd "$BASE" && python3 - "$(dirname "$HOOK")" "$WAITER_CMD" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
bg = [{"id": "wt9", "type": "shell", "status": "running", "command": sys.argv[2]}]
print(L.verify_background(bg, ancestors={int(os.environ["WORKLIST_HARNESS_PID"])}).get("wt9"))
PYEOF
)
if [[ "$VERDICT" == "confirmed" ]]; then
    pass "163q premise: the live waiter verifies as confirmed"
else
    fail "163q premise: waiter verdict is '$VERDICT', not confirmed -- this case is vacuous"
fi
say "$DRAINED_MSG"
OUT="$(run)"
if grep -qF "DRAINED, AND STILL HOLDING A WAITER" <<<"$OUT"; then
    pass "163q: a drained session is told to stop its waiter"
else
    fail "163q: no advice for a drained session holding a waiter: ${OUT:0:300}"
fi
# The remedy must name the task's OWN id. One that does not is a remedy the
# reader has to guess at, and there is nothing on a Stop event to guess from.
if grep -qF "TaskStop wt9" <<<"$OUT"; then
    pass "163q: it names the exact TaskStop command for that task id"
else
    fail "163q: the advice carries no TaskStop for wt9: ${OUT:0:300}"
fi
# GUIDANCE, NEVER A BLOCK. A stop that blocked on this would keep the session
# alive to argue about the process it is being told to shut down.
DEC=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$DEC" != "block" ]]; then
    pass "163q: the advice does not block the stop"
else
    fail "163q: a drained session was BLOCKED over its waiter: ${OUT:0:300}"
fi
stop_waiter

# CONTROL 1: WORK OUTSTANDING, same live waiter -- the advice must not fire.
# A pending harness task rather than an open item, deliberately: an open item
# BLOCKS, and an absence asserted on a blocking stop proves nothing, because
# the report queue is not drained on that path.
drained_setup
drained_waiter
task 9 in_progress "still doing the thing"
say "still working

## Remaining
- #9 still doing the thing (in_progress)"
OUT="$(run)"
if ! grep -qF "DRAINED, AND STILL HOLDING A WAITER" <<<"$OUT"; then
    pass "163q-c1 CONTROL: a session with a pending task keeps its waiter"
else
    fail "163q-c1 CONTROL: told to stop listening while work was pending: ${OUT:0:300}"
fi
stop_waiter

# CONTROL 2: drained, but holding NO waiter. There is nothing to stop, and an
# advisory that fired here would be telling every finished session in the repo
# to kill a process it does not have.
drained_setup
BG='[]'
say "$DRAINED_MSG"
OUT="$(run)"
if ! grep -qF "DRAINED, AND STILL HOLDING A WAITER" <<<"$OUT"; then
    pass "163q-c2 CONTROL: a drained session with no waiter is told nothing"
else
    fail "163q-c2 CONTROL: advice fired with no waiter to stop: ${OUT:0:300}"
fi

# CONTROL 3: a waiter BESIDE another live background job. That job's report
# arrives through this very channel, so telling the session to stop listening
# would make it deaf to the worker it is supervising. This is what
# `_only_waiters` guards, and it is the assertion that goes red without it.
drained_setup
drained_waiter
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([
    {"id": "wt9", "type": "shell", "status": "running",
     "command": sys.argv[1], "description": "inbox waiter"},
    {"id": "job1", "type": "teammate", "status": "running",
     "description": "a writer sub-agent still running"},
]))
PYEOF
)"
say "waiting on the worker

## Remaining
- job1 is still running; its report is what I am waiting for"
OUT="$(run)"
if ! grep -qF "DRAINED, AND STILL HOLDING A WAITER" <<<"$OUT"; then
    pass "163q-c3 CONTROL: a waiter beside a live worker is kept"
else
    fail "163q-c3 CONTROL: told to stop listening while a worker was running: ${OUT:0:300}"
fi
stop_waiter
unset WORKLIST_REPORT_PER_STOP WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID

echo "== 163v. a roster the session cannot verify is reaped, but only where certain =="
# THE BUG: after a compaction, or an operator reopening the session, the harness
# still reports every teammate ever spawned as `running`. Measured live: 20
# claimed, exactly 1 transcript still growing. That roster drives _in_pure_wait,
# the 15-minute check-in and confirmed_waiters, so a stale one means a session is
# told it supervises twenty workers forever and confirms phantoms every quarter
# hour.
#
# There is NO JOIN from a task id to an agent -- a task carries only {id, type,
# status, description}, the description is the prompt truncated to ~50 chars, and
# that prefix is provably not unique (10 of 19 collided on a live roster). So the
# automatic reap fires only where it is a CERTAINTY: not one teammate transcript
# fresh means every teammate task is dead, whatever its id.
setup
brief_now
hand_now
# A projects store with a teammate transcript that is STALE (hours old).
python3 - "$BASE" "$SID" <<'MKSTORE'
import json, os, pathlib, re, sys, time
B = pathlib.Path(sys.argv[1])
SID = sys.argv[2]
root = B / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(B / "proj"))
def mate(sess, name, age_min):
    d = root / sess / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    aid = "a%s-1111222233334444" % name
    (d / ("agent-%s.meta.json" % aid)).write_text(json.dumps(
        {"agentType": name, "name": name, "taskKind": "in_process_teammate"}))
    j = d / ("agent-%s.jsonl" % aid)
    j.write_text(json.dumps({"type": "assistant", "message": {"content": []}}) + "\n")
    old = time.time() - age_min * 60
    os.utime(j, (old, old))
# THIS session's own teammate, stale by hours: the roster is genuinely dead.
# The directory is named for the SESSION ID, which is the real convention --
# it used to be a literal "s1", which meant the scoped lookup could not resolve
# and the case was really exercising the unscoped glob.
mate(SID, "oldmate", 600)
# A DIFFERENT session in the same project, with a FRESH teammate. This is the
# cross-session contamination the review found: unscoped, this one transcript
# made fresh > 0 for EVERY session in the project, so a session whose own roster
# was 100% phantom was told it still had live workers and the auto-reap never
# fired. Concurrent sessions in one tree are routine here, so this was the
# common case rather than an edge one.
mate("bystander-9999-8888-7777-666666666666", "freshmate", 0)
MKSTORE
export CLAUDE_CONFIG_DIR="$BASE/claude"
BG='[{"id":"tm1","type":"teammate","status":"running","description":"You are an Opus writer sub-agent in /home..."},{"id":"tm2","type":"teammate","status":"running","description":"You are an Opus writer sub-agent in /home..."}]'
task 7 in_progress "waiting on the teammates"
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
run >/dev/null # establishes the state doc
# THE CLOCK MUST BE OVERDUE BEFORE THIS PROVES ANYTHING. Asserting on a seeding
# stop is vacuous: the check-in does not fire on first sight of the wait state
# whether or not the roster was pruned, so the assertion passed with the pruning
# removed entirely (mutation Mk). With the clock overdue the two cases diverge:
# pruned -> the roster is empty, so it is not a pure wait and nothing is owed;
# unpruned -> the check-in fires for two phantoms.
python3 - "$WL" <<'SEED0'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
d = json.loads(p.read_text()) if p.exists() else {}
d["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(d))
SEED0
newturn
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v: with zero fresh transcripts the phantom roster is dropped"
else
    fail "163v: still supervising phantoms: ${OUT:0:250}"
fi
# CONTROL: make one transcript FRESH and the same roster is kept -- the drop is
# the certainty branch, not a blanket "teammates never count".
python3 -c '
import glob, os, sys, time
# THIS SESSIONS OWN transcript, not glob()[0]. With a bystander session in the
# fixture, [0] could pick the other sessions file -- which is already fresh --
# leaving this sessions mate stale, so the control would silently assert the
# opposite of what it means.
hits = glob.glob(sys.argv[1] + "/claude/projects/*/" + sys.argv[2] + "/subagents/*.jsonl")
assert hits, "control fixture missing: no transcript for this session"
os.utime(hits[0], (time.time(), time.time()))' "$BASE" "$SID"
python3 - "$WL" <<'SEED'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
d = json.loads(p.read_text()) if p.exists() else {}
d["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(d))
SEED
newturn
say "answer

## Remaining
- #7 waiting on the teammates (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v CONTROL: one fresh transcript keeps the roster and the check-in"
else
    fail "163v CONTROL: a live teammate was reaped: ${OUT:0:250}"
fi
# ...and because 2 are claimed while only 1 is fresh, the overclaim is REPORTED
# rather than guessed at.
if grep -qF "ROSTER OVERCLAIMS" <<<"$OUT"; then
    pass "163v: the unresolvable remainder is surfaced, not silently kept"
else
    fail "163v: the overclaim was hidden: ${OUT:0:300}"
fi
unset CLAUDE_CONFIG_DIR

echo "== 163v-c1. --reap retires an id, and refuses one the hook never saw =="
setup
brief_now
hand_now
BG='[{"id":"tm1","type":"teammate","status":"running","description":"a teammate"}]'
task 7 pending "waiting"
say "answer

## Remaining
- #7 waiting (pending)"
run >/dev/null # banks the lastevent the CLI validates against
if reqcli --reap deadbeef nosuchid >/dev/null 2>"$BASE/reap.err"; then
    fail "163v-c1: an unknown task id was accepted"
else
    if grep -qF "not in the last background-task list" "$BASE/reap.err"; then
        pass "163v-c1: an id the hook never saw is REFUSED, not recorded"
    else
        fail "163v-c1: refusal was unclear: $(head -c 120 "$BASE/reap.err")"
    fi
fi
if [ ! -f "${WL%.md}.reaped-deadbeef" ]; then
    pass "163v-c1: the refused reap wrote nothing"
else
    fail "163v-c1: a rejected reap still recorded an id"
fi
# CONTROL: a REAL id from that same roster is accepted and takes effect.
OUT="$(reqcli --reap deadbeef tm1 2>&1)"
assert_c1=$?
if grep -qF "reaped 1 task" <<<"$OUT"; then
    pass "163v-c1 CONTROL: a known id is accepted"
else
    fail "163v-c1 CONTROL: a valid reap was refused: ${OUT:0:150}"
fi
newturn
say "answer

## Remaining
- #7 waiting (pending)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163v-c1: the reaped task no longer counts as running"
else
    fail "163v-c1: the reap had no effect: ${OUT:0:200}"
fi

echo "== 163w. v18: a session that IGNORES the waiter nudges is blocked =="
# The operator asked to "force contexts to run in background". The trigger is
# deliberately NOT "no confirmed waiter right now": a waiter EXITS every time it
# fires, so that condition is true in exactly the window the session is supposed
# to be in, and keying on it blocked correct behaviour and broke 16 cases here.
# It keys on the count of PostToolUse nudges the session has been given and not
# acted on, which only grows over half an hour of being asked.
setup
brief_now
hand_now
brief_other peer1234
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer"
# Below the grace threshold: asked twice, not yet blocked.
printf '2 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w: under the grace count the session is not blocked yet"
else
    fail "163w: blocked too early: ${OUT:0:200}"
fi
# At the threshold: three unheeded nudges is half an hour of being asked.
printf '3 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
OUT="$(run)"
if grep -qF "AND IS NOT LISTENING" <<<"$OUT" && grep -qF "wl_wait.py" <<<"$OUT"; then
    pass "163w: three ignored nudges blocks, and the block carries the command"
else
    fail "163w: did not block at the threshold: ${OUT:0:250}"
fi

echo "== 163w-c1. CONTROL: a CONFIRMED waiter silences it =="
# Same ignored count, same peer, same loop -- only a live waiter differs.
setup
brief_now
hand_now
brief_other peer1234
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
WAITER_CMD="python3 $(dirname "$HOOK")/wl_wait.py deadbeef --timeout 3"
TMPDIR="$BASE/wt1" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
W163W=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '9 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c1 CONTROL: a confirmed waiter silences it even at nine ignored nudges"
else
    fail "163w-c1 CONTROL: blocked despite a live waiter: ${OUT:0:250}"
fi
kill "$W163W" 2>/dev/null
wait "$W163W" 2>/dev/null

echo "== 163w-c2. CONTROL: an UNVERIFIABLE waiter does NOT satisfy it =="
# The case that could silently pass for the wrong reason. Same command string,
# dead process, so the verdict is `suspect` rather than `confirmed`. A waiter
# nobody can see on the OS is worth nothing: the whole argument is that its EXIT
# wakes you.
setup
brief_now
hand_now
brief_other peer1234
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
export WORKLIST_HARNESS_PID=$$
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter (dead)"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '3 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c2 CONTROL: a dead (unverifiable) waiter still blocks"
else
    fail "163w-c2 CONTROL: an unseeable waiter satisfied the check: ${OUT:0:250}"
fi
unset WORKLIST_HARNESS_PID

echo "== 163w-c3. CONTROL: no live peer, no block =="
# The harm of not listening is TO SOMEBODY. With no peer there is nobody whose
# request could go unseen, so the check has no victim and must stay silent --
# this is the condition that makes blocking safe at all.
setup
brief_now
hand_now
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
printf '9 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "AND IS NOT LISTENING" <<<"$OUT"; then
    pass "163w-c3 CONTROL: with no live peer the check stays silent"
else
    fail "163w-c3 CONTROL: blocked with nobody to hear from: ${OUT:0:250}"
fi

echo "== 163w-c4. THE TOMBSTONE: a LAPSED waiter blocks with ZERO ignored nudges =="
# THE PERVERSE INCENTIVE THIS CLOSES. wait() used to `hb.unlink()` on BOTH of
# its exits, so a waiter that had died left exactly what a session that never
# listened leaves: nothing. Combined with nudge()'s counter RESET, arming a
# single 60-minute waiter therefore bought 30+ minutes of guaranteed silence
# after it lapsed -- the cheapest way to be left alone was to arm one waiter
# every few hours and never relaunch it.
#
# Zero nudges here, deliberately: the ignored-count grace is for a session that
# merely COULD receive work. A session whose waiter exited already volunteered,
# was told on the way out to relaunch, and did not.
setup
brief_now
hand_now
brief_other peer1234
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
rm -f "${WL%.md}.waiternudge-deadbeef"
printf 'EXPIRED 2026-01-01T00:00:00Z timeout\n' >"${WL%.md}.waiter-deadbeef"
# Aged past HEARTBEAT_STALE_S so the marker is a lapse rather than a waiter that
# exited seconds ago and is about to be relaunched in the same turn.
touch -d '-10 minutes' "${WL%.md}.waiter-deadbeef"
say "answer"
OUT="$(run)"
if grep -qF "YOUR WAITER LAPSED" <<<"$OUT" && grep -qF "timeout" <<<"$OUT"; then
    pass "163w-c4: a lapsed waiter blocks at once, and the block names WHICH exit it was"
else
    fail "163w-c4: the lapse was invisible: ${OUT:0:350}"
fi

echo "== 163w-c5. CONTROL: NEVER ARMED, zero nudges, is silent =="
# The whole point of the tombstone is that these two states are different. If
# this fires too, the change has bought nothing -- it has just made the hook
# harsher at everybody.
setup
brief_now
hand_now
brief_other peer1234
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
rm -f "${WL%.md}.waiternudge-deadbeef" "${WL%.md}.waiter-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "YOUR WAITER LAPSED" <<<"$OUT"; then
    pass "163w-c5 CONTROL: a session that never armed one is not accused of losing one"
else
    fail "163w-c5 CONTROL: never-armed and lapsed are still indistinguishable: ${OUT:0:350}"
fi

echo "== 163w-c6. CONTROL: a LIVE heartbeat is not a tombstone =="
# _is_tombstone reads the CONTENT, because a tombstone is a WRITE and therefore
# looks `fresh` for its first HEARTBEAT_STALE_S seconds. A live pulse must never
# be mistaken for one.
setup
brief_now
hand_now
brief_other peer1234
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
rm -f "${WL%.md}.waiternudge-deadbeef"
printf '2026-08-28T10:00:00Z\n' >"${WL%.md}.waiter-deadbeef"
touch -d '-10 minutes' "${WL%.md}.waiter-deadbeef"
say "answer"
OUT="$(run)"
if ! grep -qF "YOUR WAITER LAPSED" <<<"$OUT"; then
    pass "163w-c6 CONTROL: a stale ordinary heartbeat is not read as a lapse"
else
    fail "163w-c6 CONTROL: an ordinary heartbeat was read as a tombstone: ${OUT:0:350}"
fi

echo "== 163w-c7. THE NUDGE DECAYS BY ONE, it does not reset to zero =="
# The counter used to be UNLINKED the moment a heartbeat looked fresh, which
# made it resettable BY THE FAILURE: arming one waiter zeroed it, so when that
# waiter lapsed the Stop-side backstop had to climb from zero over another half
# hour of nudges. Decay keeps it a measure of recent behaviour without letting
# one act of compliance erase a history of ignoring it.
setup
printf '3 2026-01-01T00:00:00Z\n' >"${WL%.md}.waiternudge-deadbeef"
# Backdated past NUDGE_EVERY_S, or the throttle returns before the decay.
touch -d '-30 minutes' "${WL%.md}.waiternudge-deadbeef"
printf '2026-08-28T10:00:00Z\n' >"${WL%.md}.waiter-deadbeef"
printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","tool_name":"Bash"}' \
    "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        python3 "$(dirname "$HOOK")/wl_wait.py" --nudge >/dev/null 2>&1
N163C7="$(cut -d' ' -f1 <"${WL%.md}.waiternudge-deadbeef" 2>/dev/null || echo GONE)"
if [[ "$N163C7" == "2" ]]; then
    pass "163w-c7: three ignored nudges decay to two on compliance, not to zero"
else
    fail "163w-c7: the counter went to '$N163C7' instead of 2"
fi

echo "== 163w-c8. CONTROL: complying repeatedly still walks it all the way down =="
# Decay must not become a counter that can never be cleared: a session doing the
# right thing for long enough gets back to zero, which is what the reset was
# rightly for.
for _i in 1 2; do
    touch -d '-30 minutes' "${WL%.md}.waiternudge-deadbeef" 2>/dev/null
    printf '2026-08-28T10:00:00Z\n' >"${WL%.md}.waiter-deadbeef"
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","tool_name":"Bash"}' \
        "$SID" "$BASE/proj" "$BASE/t.jsonl" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            python3 "$(dirname "$HOOK")/wl_wait.py" --nudge >/dev/null 2>&1
done
if [[ ! -f "${WL%.md}.waiternudge-deadbeef" ]]; then
    pass "163w-c8 CONTROL: two more compliant windows clear the counter entirely"
else
    fail "163w-c8 CONTROL: the counter is stuck at $(cut -d' ' -f1 <"${WL%.md}.waiternudge-deadbeef")"
fi
