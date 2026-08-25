#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The one-section-per-stop report queue (FIFO, priority, one-shots), the judge stamp, poll baselines, and the quiet-wake collapse.

# Operator, 2026-07-31: the allow report still emitted every fired section at
# once. It now releases WORKLIST_REPORT_PER_STOP of them, highest priority
# first, and the tail states how many are waiting -- a silent cap reads as
# "that is everything", the same argument the guide's own truncation carries.
outq_fixture() { # four class-2 sections firing on one stop
    say "done for now"
    brief_now
    hand_now
    brief_other cafe1234
    # An orphan needs a dead owner: a transcript for cafe1234 older than
    # WORKLIST_DEAD_HOURS but younger than WORKLIST_ARCHIVE_HOURS.
    touch -d '-48 hours' "$BASE/cafe1234.jsonl"
    echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
}
outq_seen() { # count the four section headers present in $1
    local out="$1" n=0 needle
    for needle in "INBOX HAS BEEN QUIET" "Other sessions in this worktree" \
        "ORPHANED item(s)" "nothing open for this session"; do
        grep -qF "$needle" <<<"$out" && n=$((n + 1))
    done
    echo "$n"
}
setup
outq_fixture
OUT="$(run)"
# FOUR, not three: an orphaned item is by construction another session's OPEN
# item, so it always drags the other-session count along with it.
if [[ "$(outq_seen "$OUT")" -eq 1 ]] &&
    grep -qF "(3 more report section(s) queued" <<<"$OUT"; then
    pass "173: exactly one of four sections is released, and the tail counts the rest"
else
    fail "173: released $(outq_seen "$OUT") section(s), or the queued count is wrong: ${OUT:0:400}"
fi
# CONTROL: one planted fact differs, the per-stop budget. All four land and
# nothing claims a queue, so the cap is the only thing the FIRE leg measured.
setup
export WORKLIST_REPORT_PER_STOP=4
outq_fixture
OUT="$(run)"
if [[ "$(outq_seen "$OUT")" -eq 4 ]] && ! grep -qF "more report section(s) queued" <<<"$OUT"; then
    pass "173 CONTROL: a wide drain emits all four and claims no queue"
else
    fail "173 CONTROL: released $(outq_seen "$OUT") of 4: ${OUT:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 174. FIFO inside a priority class; changed content goes to the BACK =="
# All four sections above are class 2, so nothing outranks anything here and
# the only thing deciding the order is the sequence number each entry earned
# when it was first queued.
outq_fill() { # queue the four, one stop at a time, emitting nothing
    export WORKLIST_REPORT_PER_STOP=0
    say "done for now"
    brief_now
    hand_now
    run >/dev/null # the poll-backoff tip is alone on this stop
    brief_other cafe1234
    newturn
    say "done for now"
    run >/dev/null # the other session's brief joins it
    touch -d '-48 hours' "$BASE/cafe1234.jsonl"
    echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
    newturn
    say "done for now"
    run >/dev/null # the orphan and its item count join
}
outq_order() { # drain four stops at one section each, printing the order
    export WORKLIST_REPORT_PER_STOP=1
    local order="" out
    for _ in 1 2 3 4; do
        newturn
        say "done for now"
        out="$(run)"
        grep -qF "INBOX HAS BEEN QUIET" <<<"$out" && order="$order backoff"
        grep -qF "Other sessions in this worktree" <<<"$out" && order="$order others"
        grep -qF "ORPHANED item(s)" <<<"$out" && order="$order orphans"
        grep -qF "nothing open for this session" <<<"$out" && order="$order items"
    done
    echo "$order"
}
setup
outq_fill
GOT="$(outq_order)"
if [[ "$GOT" == " backoff others orphans items" ]]; then
    pass "174: one priority class drains in the order it was enqueued"
else
    fail "174: drain order was '$GOT'"
fi
# CONTROL: the operator's "changed content re-enqueues at its priority",
# proven rather than asserted. Touch the SECOND section's body and it loses
# the position it had earned instead of keeping it.
setup
outq_fill
printf '%s %s %s\n' "cafe1234" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "pivoted to the deploy fix" >>"${WL%.md}.sessions"
newturn
say "done for now"
run >/dev/null
GOT="$(outq_order)"
if [[ "$GOT" == " backoff orphans items others" ]]; then
    pass "174 CONTROL: a changed section goes to the back of its own class"
else
    fail "174 CONTROL: drain order was '$GOT'"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 175. priority beats FIFO: an actionable CI note passes an older advisory =="
# PLANTED DEFECT, run 2026-07-31: outq_drain's sort key was changed from
# (prio, seq) to (seq,). Both legs failed, the first with
#   FAIL: 175: priority did not beat FIFO: {"systemMessage": "WORKLIST GUIDE:
#   ... \n\nWorklist: nothing open for this session.\n  1 open item(s) owned
#   by session cafe1234\n\n(1 more report section(s) queued; ...
# which is the inversion exactly: the older class-2 advisory took the slot and
# the CI note was the one left queued. 173 and 174 stayed green throughout. A
# priority ladder nobody has watched invert is a ladder nobody knows is wired
# up.
ci_setup
# The older advisory is another session's item count, NOT its brief:
# ci_trouble returns "multi-session" the moment a second brief is live, and a
# fixture that quietly switches off the check it is racing proves nothing.
echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
export WORKLIST_REPORT_PER_STOP=0
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
ci_run >/dev/null # the class-2 advisory is queued first, and waits
export WORKLIST_REPORT_PER_STOP=1
ci_rollup PENDING "[$(ci_job "E2E / opensuse" FAILURE), $(ci_running "E2E / ubuntu")]"
out="$(ci_run)"
if grep -qF "retry allowlist" <<<"$out" && ! grep -qF "nothing open for this session" <<<"$out"; then
    pass "175: the class-0 CI note is released ahead of the older class-2 advisory"
else
    fail "175: priority did not beat FIFO: ${out:0:400}"
fi
# CONTROL: with the run green there is no class-0 section, and the advisory
# that was passed over is released on the very next stop. It is also what
# makes the leg above non-vacuous: the section really was queued and waiting.
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
if grep -qF "nothing open for this session" <<<"$out"; then
    pass "175 CONTROL: the passed-over advisory drains once nothing outranks it"
else
    fail "175 CONTROL: the advisory was lost, not delayed: ${out:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 176. a ONE-SHOT is never dropped, only delayed =="
# The property that decides the whole design, so the fixture is built to make
# the one-shot LOSE its first stop. wl_email.pump spends its budget at compute
# time: it appends the ledger and sends. Nothing can regenerate that note, so
# a report with no room for it has to keep it.
#
# PLANTED DEFECT, run 2026-07-31: outq_drain's per-entry removal was replaced
# with `q["items"][:] = []` (a plausible "reset the queue after draining"
# bug). Leg 2 failed with
#   FAIL: 176: the one-shot was DROPPED, not delayed (mail=1):
#   {"systemMessage": "WORKLIST GUIDE: ... \n\nRequests you posted, still
#   OPEN (they block their recipients, never you): ...
# The digest note was gone for good and a class-2 advisory took its place,
# while the mail count proves no second send could ever bring it back. 173
# also went red on that run (its queued count read 0 instead of 3), but only
# this case says what was LOST rather than that a number was wrong.
ci_setup
mail_fixture
export WORKLIST_REPORT_PER_STOP=1
askid deadbeef operator 'which tier map? DEFAULT: ship the draft map' >/dev/null
ci_rollup PENDING "[$(ci_job "E2E / opensuse" FAILURE), $(ci_running "E2E / ubuntu")]"
out="$(ci_run)"
if grep -qF "retry allowlist" <<<"$out" && ! grep -qF "OPERATOR EMAILED" <<<"$out" &&
    [[ "$(mailcount)" == "1" ]]; then
    pass "176: the class-0 CI note takes stop 1 although the digest has already gone"
else
    fail "176: leg 1 shape wrong (mail=$(mailcount)): ${out:0:400}"
fi
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
# The mail count is the proof: pump() sends nothing on this stop, because its
# ledger already holds the digest, so the text can only have come from the
# queue.
if grep -qF "OPERATOR EMAILED" <<<"$out" && [[ "$(mailcount)" == "1" ]]; then
    pass "176: the send note arrives on stop 2 from the queue, with no second send"
else
    fail "176: the one-shot was DROPPED, not delayed (mail=$(mailcount)): ${out:0:400}"
fi
out="$(ci_run)"
out="$(ci_run)"
if ! grep -qF "more report section(s) queued" <<<"$out"; then
    pass "176: the queue empties instead of holding drained entries forever"
else
    fail "176: entries still queued after every section was released: ${out:0:400}"
fi
# CONTROL: the same fixture with no CI trouble at all. The digest note lands
# on stop 1, which is what makes stop 2 above a DELAY rather than the normal
# path.
ci_setup
mail_fixture
askid deadbeef operator 'which tier map? DEFAULT: ship the draft map' >/dev/null
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
out="$(ci_run)"
if grep -qF "OPERATOR EMAILED" <<<"$out"; then
    pass "176 CONTROL: with nothing outranking it the digest note lands on stop 1"
else
    fail "176 CONTROL: the note did not land unopposed either: ${out:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 177. the judge line is a STAMP unless the context is fresh or the reason changed =="
# Operator, 2026-07-31: the approval reason was reprinted on every stop. It
# now rides a stop whose context was just rebuilt (SessionStart, PostCompact)
# or whose reason genuinely changed, and every other stop gets the bare stamp.
# The verdict cache is pinned OFF so every stop pays a fresh call: a cached
# verdict would make the cache, not the signature latch, the thing under test.
ctx_event() { # drive a context-rebuilding hook mode: ctx_event --session-start
    printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" "$1" >/dev/null 2>&1
}
judge_turn() { # a fresh turn whose message satisfies the Remaining demand
    newturn
    say "answer

## Remaining
| #7 | merge the chain | pending, you |"
}
setup
export WORKLIST_JUDGE_CACHE_MIN=0
# Six stops on an unchanged world would otherwise trip stuck detection, which
# has nothing to do with what this case measures.
export WORKLIST_STUCK_ROUNDS=99
brief_now
hand_now
task 7 pending "merge the chain"
judge_turn
shim_judge_out '{"verdict":"stop","reason":"MARKER_REASON_ONE waiting on the run","next_action":"none"}'
ctx_event --session-start
out="$(runj)"
if grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177: a context-fresh session gets the judge's full approval reason"
else
    fail "177: the fresh-context reason was withheld: ${out:0:400}"
fi
judge_turn
out="$(runj)"
if grep -qF "Stop-gate judge" <<<"$out" && ! grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177 CONTROL: an ordinary stop gets the stamp alone"
else
    fail "177 CONTROL: the reason was reprinted on an ordinary stop: ${out:0:400}"
fi
# PostCompact is the case the marker is load-bearing for: the state doc
# SURVIVES a compaction, so the reason signature still matches and only the
# marker can bring the full statement back.
ctx_event --post-compact
judge_turn
out="$(runj)"
if grep -qF "MARKER_REASON_ONE" <<<"$out"; then
    pass "177: PostCompact restores the full reason on the next judged stop"
else
    fail "177: a compacted session got the bare stamp: ${out:0:400}"
fi
# The signature arm on its own: no marker anywhere, but a genuinely different
# reason still fires, and a repeat of it does not.
shim_judge_out '{"verdict":"stop","reason":"MARKER_REASON_TWO the gate changed","next_action":"none"}'
judge_turn
out="$(runj)"
if grep -qF "MARKER_REASON_TWO" <<<"$out"; then
    pass "177: a changed reason fires with no context marker at all"
else
    fail "177: a new reason was swallowed by the latch: ${out:0:400}"
fi
judge_turn
out="$(runj)"
if grep -qF "Stop-gate judge" <<<"$out" && ! grep -qF "MARKER_REASON_TWO" <<<"$out"; then
    pass "177: and repeating that reason drops back to the stamp"
else
    fail "177: the changed reason kept reprinting: ${out:0:400}"
fi
unset WORKLIST_JUDGE_CACHE_MIN WORKLIST_STUCK_ROUNDS

echo "== 178. v17: the poll baseline is SESSION-scoped, not repo-scoped =="
# THE BUG this fixes: world_sig hashed the BYTES of the shared markdown, event
# log and requests file, so one teammate's --add broke every other session's
# baseline and forfeited their silent poll. Measured on the live store before
# the fix: 32 of 32 events in a 3-hour window were foreign, polluting 18 of 36
# five-minute windows.
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "178 baseline: the full stop banks the poll baseline" allow "operator may answer"
# A DIFFERENT session tracks its own work. Nothing about this session moved.
as_peer cafe1234 reqcli --add cafe1234 "a teammate's own finding" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "178: another session's worklist event does NOT forfeit the silent poll"
else
    fail "178: a foreign event paid the full battery: ${OUT:0:200}"
fi
# CONTROL: the signature is not simply dead -- this session's OWN store write
# still forfeits, which is the whole point of having a baseline.
reqcli --add deadbeef "my own new finding" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "178 CONTROL: this session's own store write still forfeits the silence"
else
    fail "178 CONTROL: an own item went silent: ${OUT:0:200}"
fi

echo "== 178b. a foreign REQUEST to someone else is invisible; to me it is not =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "178b baseline" allow "operator may answer"
askid_as cafe1234 beefcafe "a question between two OTHER sessions" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "178b: a request between two other sessions keeps the silence"
else
    fail "178b: a foreign request forfeited: ${OUT:0:200}"
fi
askid_as cafe1234 deadbeef "please rebuild the docs index" >/dev/null
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "rebuild the docs index" <<<"$OUT"; then
    pass "178b CONTROL: a request addressed to ME still forfeits and delivers"
else
    fail "178b CONTROL: a request to me was swallowed: ${OUT:0:200}"
fi

echo "== 179. v17: the bgwait latch RESETS when the wait ends =="
# THE BUG: the clock was only written inside the wait state, so leaving it
# froze the stamp. Re-entering an hour later found it 60 minutes old and fired
# the roster demand on the FIRST stop back -- "you started waiting, report",
# the exact thing the silent seed exists to prevent.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bw9.output"
BGON='[{"id":"bw9","type":"shell","status":"running","description":"long watch"}]'
BG="$BGON"
task 7 in_progress "waiting on the nightly"
say "answer

## Remaining
- #7 waiting on the nightly (in_progress)"
run >/dev/null # seeds the wait clock
age_bgwait() {
    python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc.setdefault("bgwait", {})["at"] = "2026-01-01T00:00:00Z"
p.write_text(json.dumps(doc))
PYEOF
}
has_bgwait() {
    python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
try:
    doc = json.loads(p.read_text())
except OSError:
    doc = {}
print("present" if doc.get("bgwait") else "absent")
PYEOF
}
age_bgwait
# The wait ENDS: the workers are gone.
BG='[]'
newturn
say "the watch finished

## Remaining
- #7 waiting on the nightly (in_progress)"
run >/dev/null
if [[ "$(has_bgwait)" == "absent" ]]; then
    pass "179: leaving the wait state clears the check-in clock"
else
    fail "179: the stale clock survived the end of the wait"
fi
# And a LATER wait re-seeds silently instead of firing on arrival.
BG="$BGON"
newturn
say "started a new watch

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "179: re-entering a wait re-seeds the clock instead of firing on arrival"
else
    fail "179: the check-in fired on the first stop of a NEW wait: ${OUT:0:250}"
fi
# CONTROL: the latch is not simply disabled -- aged INSIDE a live wait it fires.
age_bgwait
newturn
say "still waiting

## Remaining
- #7 waiting on the nightly (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "179 CONTROL: aged inside a live wait, the check-in still fires"
else
    fail "179 CONTROL: the check-in never fires at all now: ${OUT:0:250}"
fi
# v17 requirement 3: the bound is VISIBLE, so a reader can verify the latch
# from the message alone.
if grep -qF "Last delivered:" <<<"$OUT" && grep -qF "Next one no earlier than" <<<"$OUT"; then
    pass "179: the check-in carries its last-fired and next-earliest stamps"
else
    fail "179: the check-in still only CLAIMS a bound: ${OUT:0:300}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180. v17: three no-op wakes collapse the whole stop to ONE line =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwq.output"
BG='[{"id":"bwq","type":"shell","status":"running","description":"long watch"}]'
task 7 in_progress "waiting on the nightly"
# A real deferral, so the NON-collapsed report has a guide in it. Since v18 an
# empty guide is silent, and the reset control below needs a full report it can
# actually see coming back.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
quiet_turn() {
    newturn
    say "still waiting on the nightly

## Remaining
- #7 waiting on the nightly (in_progress)
- the flag decision, deferred with a default"
}
quiet_turn
OUT1="$(run)"
quiet_turn
OUT2="$(run)"
quiet_turn
OUT3="$(run)"
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT3"; then
    pass "180: the third consecutive no-op wake fires the reschedule message"
else
    fail "180: no collapse after three quiet wakes: ${OUT3:0:300}"
fi
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT1" && ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT2"; then
    pass "180: and NOT before three (one quiet wake proves nothing)"
else
    fail "180: fired too early: 1='${OUT1:0:120}' 2='${OUT2:0:120}'"
fi
if grep -qF '*/10 * * * *' <<<"$OUT3"; then
    pass "180: it names the next rung up from */5"
else
    fail "180: no next rung in the message: ${OUT3:0:300}"
fi
# THE FOCUS REQUIREMENT: this is the ENTIRE output. The worker roster, the
# guide and the advisory sections are all gone.
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT3" &&
    ! grep -qF "bwq (long watch)" <<<"$OUT3" &&
    ! grep -qF "WORKLIST GUIDE" <<<"$OUT3"; then
    pass "180: the quiet wake emits ONLY the one-liner (no roster, no guide)"
else
    fail "180: the collapsed stop still carried other sections: ${OUT3:0:400}"
fi
# CONTROL: a real event -- new bytes on a worker's stream -- resets the streak.
printf 'the worker printed something new\n' >>"$BASE/bgout/bwq.output"
quiet_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT" && grep -qF "WORKLIST GUIDE" <<<"$OUT"; then
    pass "180 CONTROL: new worker output resets the streak and restores the full report"
else
    fail "180 CONTROL: the collapse survived a real event: ${OUT:0:300}"
fi
# ... and the count starts again from zero rather than resuming where it was.
quiet_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180 CONTROL: the streak restarts from zero, it does not resume"
else
    fail "180 CONTROL: the streak resumed after a real event: ${OUT:0:300}"
fi

echo "== 180b. a HARD check is never suppressed by the quiet collapse =="
# The whole risk of collapsing output is hiding something that matters. Get a
# session into the collapsed state, then plant an open item: it must BLOCK.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwh.output"
BG='[{"id":"bwh","type":"shell","status":"running","description":"long watch"}]'
task 7 pending "waiting"
for _ in 1 2 3; do
    newturn
    say "still waiting

## Remaining
- #7 waiting (pending)"
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180b setup: the session is in the collapsed quiet state"
else
    fail "180b setup: never reached the collapsed state: ${OUT:0:250}"
fi
echo '- [ ] (deadbeef) a real finding that must not be swallowed' >>"$WL"
newturn
say "still waiting

## Remaining
- #7 waiting (pending)"
check "180b: an open item BLOCKS even from inside the quiet collapse" block "OPEN worklist item"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180c. the rung ladder escalates 5->10->20->40->60 and CAPS =="
OUT=$(
    python3 - "$(dirname "$HOOK")" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import wl_checks as CK
fail = 0
want = [("*/5 * * * *", "*/10 * * * *"), ("*/10 * * * *", "*/20 * * * *"),
        ("*/20 * * * *", "*/40 * * * *"), ("*/40 * * * *", "0 * * * *")]
for cur, nxt in want:
    note = CK.quiet_wake_note([{"id": "p", "schedule": cur}], 3)
    if nxt not in note:
        print("rung %s did not recommend %s: %r" % (cur, nxt, note[:120])); fail += 1
cap = CK.quiet_wake_note([{"id": "p", "schedule": "0 * * * *"}], 9)
if "cap" not in cap or "0 * * * *" in cap.split("cap")[1]:
    print("the top rung did not cap cleanly: %r" % cap[:160]); fail += 1
# No recognisable poll cron -> no collapse at all, so the report is never
# replaced by an instruction the session cannot act on.
for crons in ([], [{"id": "p", "schedule": "*/7 * * * *"}],
              [{"id": "p", "schedule": "*/5 * * * *"}, {"id": "q", "schedule": "*/5 * * * *"}]):
    if CK.quiet_wake_note(crons, 5) != "":
        print("collapsed on an unusable cron shape: %r" % crons); fail += 1
print("ladder failures=%d" % fail)
sys.exit(1 if fail else 0)
PYEOF
)
if [[ $? -eq 0 ]]; then
    pass "180c: every rung recommends the next, the top rung caps, odd shapes decline"
else
    fail "180c: $OUT"
fi

echo "== 180d. this session's OWN progress note is a real event =="
# Found by the suite, not by design: with the streak keyed on item STRUCTURE
# alone, a session dutifully renewing its lease and posting --update notes
# looked quiet, and case 172's advisory got collapsed away. Doing what the
# liveness ladder asks is movement.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bwu.output"
BG='[{"id":"bwu","type":"shell","status":"running","description":"the watch"}]'
UID180=$(reqcli --add deadbeef "carry the CI watch to green" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$UID180" +60 worker:bwu "watching the run" >/dev/null
upd_turn() {
    newturn
    say "watching.

## Remaining
- #$UID180 carry the CI watch to green (in flight)"
}
for _ in 1 2 3; do
    upd_turn
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180d setup: three untouched wakes do collapse"
else
    fail "180d setup: never collapsed: ${OUT:0:250}"
fi
reqcli --update deadbeef "$UID180" "still watching, run pending" >/dev/null
upd_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180d: an --update on this session's own item resets the streak"
else
    fail "180d: a progress note was treated as silence: ${OUT:0:300}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR

echo "== 180e. a worker DYING is never silenced by the streak =="
# The one change a byte-level view cannot see: the stream is identical, the
# event still lists the task as running, and the only difference is that the
# OS process is gone. If the streak counter could hide that, the collapse
# would be actively dangerous rather than merely quiet.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bwd.output"
touch -d '25 minutes ago' "$BASE/bgout/bwd.output"
sleep 3717171718 &
PROBE180E=$!
export WORKLIST_HARNESS_PID=$$
BG='[{"id":"bwd","type":"shell","status":"running","description":"silent watch","command":"sleep 3717171718"}]'
task 7 pending "thing"
dead_turn() {
    newturn
    say "answer

## Remaining
- #7 thing (pending)"
}
for _ in 1 2 3 4; do
    dead_turn
    OUT="$(run)"
done
if grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT"; then
    pass "180e setup: a live, silent worker collapses into the quiet state"
else
    fail "180e setup: never collapsed with a live worker: ${OUT:0:250}"
fi
kill "$PROBE180E" 2>/dev/null
wait "$PROBE180E" 2>/dev/null
# The check-in window is opened too, so this case asserts BOTH halves: the
# streak breaks, AND the report that the break makes room for actually
# carries the accusation. Without the ageing it would only ever prove the
# first half, and a half-proof of a safety property is not one.
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc.setdefault("bgwait", {})["at"] = "2026-01-01T00:00:00Z"
p.write_text(json.dumps(doc))
PYEOF
dead_turn
OUT="$(run)"
if ! grep -qF "CONSECUTIVE QUIET WAKES" <<<"$OUT" && grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT"; then
    pass "180e: the worker's death breaks the streak and delivers the accusation"
else
    fail "180e: a dead worker stayed hidden behind the streak: ${OUT:0:400}"
fi
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID
