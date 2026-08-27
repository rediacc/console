#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Cross-session requests: delivery, answers, declines, broadcasts, escalation to the operator, and the concurrency races.

echo "== 65. v6: a request addressed to ME blocks my stop =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "regenerate the caption media and republish")
check "a direct request to this session blocks" block "waiting on you"

echo "== 65b. the block carries the WHOLE payload, both directions =="
# The motivating failure: a finding parked in a commit message, correct and
# unread, relayed by hand. Delivery must not depend on the recipient choosing
# to read anything (--requests included), so the body and the answer ride
# inside the block untruncated. The crucial detail sits past the 300-char
# mark that an earlier draft truncated at.
setup
say "done for now"
brief_now
LONGASK="$(python3 -c "print('caption combos: ' + 'x' * 320 + ' CRUCIAL-ASK: republish then rerun check:ci-tutorial-caption-sync')")"
RID=$(askid_as cafe1234 deadbeef "$LONGASK")
check "the tail of a long request body survives into the block" block "CRUCIAL-ASK: republish then rerun"
LONGANS="$(python3 -c "print('context: ' + 'y' * 320 + ' CRUCIAL-ANSWER: the media session already republished at 14:02Z')")"
reqcli --answer deadbeef "$RID" "$LONGANS" >/dev/null
out="$(printf '{"session_id":"cafe1234-9999-8888-7777-666666666666","cwd":"%s","transcript_path":"%s","last_assistant_message":"done"}' "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "CRUCIAL-ANSWER: the media session already republished" <<<"$out"; then
    echo "  PASS: the tail of a long answer survives into the asker's block"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the answer was truncated or did not block: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 66. CONTROL: a request between two OTHER sessions never blocks me =="
setup
say "done for now"
brief_now
brief_other cafe1234
askid_as aaaa1111 cafe1234 "please do Y" >/dev/null
check "someone else's request does not block a bystander" allow ""

echo "== 67. CONTROL: my own OPEN request never blocks me, and is reported =="
setup
# The fixture produces TWO class-2 sections (this other session's brief and
# the open request), and the output queue releases one per stop by default.
# This case is about the request being reported at all, not about rationing,
# so it drains wide; cases 173 to 177 own the rationing behaviour.
export WORKLIST_REPORT_PER_STOP=9
say "done for now"
brief_now
brief_other cafe1234
askid deadbeef cafe1234 "please regenerate captions" >/dev/null
check "the asker is never blocked on their own open request" allow "still OPEN"
unset WORKLIST_REPORT_PER_STOP

echo "== 68. answering releases the recipient =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "do X")
check "unanswered, it blocks" block "waiting on you"
reqcli --answer deadbeef "$RID" "done: X is finished, gate green" >/dev/null
check "answered, it releases the recipient" allow ""

echo "== 69. a decline MUST carry a reason; an unanswered ack is refused =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "do X")
if reqcli --decline deadbeef "$RID" >/dev/null 2>&1; then
    echo "  FAIL: a reasonless decline was accepted"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: a reasonless decline is refused (exit nonzero)"
    PASS=$((PASS + 1))
fi
if grep -q '"ev":"decline"' "${WL%.md}.requests"; then
    echo "  FAIL: the refused decline still left an event behind"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: the refusal wrote nothing"
    PASS=$((PASS + 1))
fi
if as_peer cafe1234 reqcli --ack cafe1234 "$RID" >/dev/null 2>&1; then
    echo "  FAIL: acking an unanswered request was accepted"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: acking an unanswered request is refused"
    PASS=$((PASS + 1))
fi

echo "== 70. the ANSWER is delivered to the asker as a block, until ack =="
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "which session owns caption regen")
as_peer cafe1234 reqcli --answer cafe1234 "$RID" "the media session owns it; rerun your gate after publish" >/dev/null
check "an unacked answer blocks the asker WITH the answer text" block "the media session owns it"
reqcli --ack deadbeef "$RID" >/dev/null
check "after --ack the answer never re-blocks" allow ""

echo "== 71. a DIRECT decline resolves it and carries its reason back =="
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "please also do Z")
as_peer cafe1234 reqcli --decline cafe1234 "$RID" "out of scope: Z belongs to the GPU session" >/dev/null
check "the decline reason reaches the asker as a block" block "out of scope: Z belongs to the GPU session"
reqcli --ack deadbeef "$RID" >/dev/null
check "an acked decline is silent" allow ""

echo "== 72. a BROADCAST blocks each live session only until IT responds =="
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 '*' "who owns tutorial caption regeneration")
check "an unanswered broadcast blocks a session that has not responded" block "broadcast"
reqcli --decline deadbeef "$RID" "not my area: I only touch the stop hook" >/dev/null
check "declining a broadcast releases the decliner" allow ""

echo "== 73. a request to a DEAD recipient escalates to an operator [?] once =="
setup
say "done for now"
brief_now
printf '{"ev":"ask","id":"feedc0de","from":"cafe1234","to":"beef9999","at":"%s","body":"republish the caption media"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
check "a dead-recipient request blocks nobody and escalates" allow "ESCALATED"
# v10: the [?] is a store event, not a markdown append; --list renders the
# same line shape the markdown used to carry, so the assertions keep their
# regexes and read the store instead of the file.
LIST="$(reqcli --list)"
if grep -q '\- \[?\] (cafe1234) request #feedc0de' <<<"$LIST" && grep -q 'proceeds without an answer' <<<"$LIST"; then
    echo "  PASS: the [?] item exists, owned by the asker, with a generic DEFAULT"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no operator [?] item was recorded: $LIST"
    FAIL=$((FAIL + 1))
fi
run >/dev/null
if [[ "$(reqcli --list | grep -c 'request #feedc0de')" == "1" ]]; then
    echo "  PASS: a second stop does not escalate it again"
    PASS=$((PASS + 1))
else
    echo "  FAIL: escalation is not idempotent: $(reqcli --list | grep -c 'request #feedc0de') lines"
    FAIL=$((FAIL + 1))
fi

echo "== 74. a broadcast with NO other live session escalates, not black-holes =="
setup
# The [?] lands on the ASKER (deadbeef), so it is a deferred item of ours the
# moment it is appended, and the usual something-remains machinery (handover,
# ## Remaining) applies to this stop. That is intended: the asker must report
# that the question went to the operator.
say "done for now

## Remaining
- the fedora ownership question, escalated to the operator as a [?]"
brief_now
hand_now
askid deadbeef '*' "anyone own the flaky fedora leg? DEFAULT: I quarantine it myself" >/dev/null
check "a broadcast nobody can answer escalates immediately" allow "ESCALATED"
if reqcli --list | grep -q 'DEFAULT: I quarantine it myself'; then
    echo "  PASS: the ask's own DEFAULT: is carried into the [?] item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the ask's DEFAULT was not reused: $(reqcli --list)"
    FAIL=$((FAIL + 1))
fi

echo "== 75. CONTROL: the request block no-ops under GITHUB_ACTIONS =="
setup
say "done for now"
brief_now
askid_as cafe1234 deadbeef "do X" >/dev/null
check "off a runner the request still blocks" block "waiting on you"
GHA=true check "GITHUB_ACTIONS=true never blocks a runner on a request" allow ""

echo "== 76. RACE: concurrent writers lose nothing =="
setup
for i in $(seq 1 16); do
    as_peer "sess000$i" reqcli --ask "sess000$i" cafe1234 "concurrent probe $i" >/dev/null 2>&1 &
done
wait
RQ="${WL%.md}.requests"
OUT=$(python3 -c '
import json, sys
ids, bad, n = set(), 0, 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        bad += 1
        continue
    if ev.get("ev") == "ask":
        n += 1
        ids.add(ev.get("id"))
print("asks=%d ids=%d bad=%d" % (n, len(ids), bad))
' "$RQ")
if [[ "$OUT" == "asks=16 ids=16 bad=0" ]]; then
    echo "  PASS: 16 concurrent asks -> 16 parseable events, 16 distinct ids"
    PASS=$((PASS + 1))
else
    echo "  FAIL: concurrent asks were lost or torn: $OUT"
    FAIL=$((FAIL + 1))
fi
RID=$(python3 -c '
import json, sys
print(sorted(json.loads(l)["id"] for l in open(sys.argv[1]) if l.strip())[0])
' "$RQ")
for i in $(seq 1 8); do
    as_peer "answ000$i" reqcli --answer "answ000$i" "$RID" "answer $i" >/dev/null 2>&1 &
done
wait
NANS=$(grep -c "\"ev\":\"answer\",\"id\":\"$RID\"" "$RQ")
if [[ "$NANS" == "8" ]]; then
    echo "  PASS: 8 concurrent answers to one request all survive"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 8 answer events, found $NANS"
    FAIL=$((FAIL + 1))
fi

echo "== 77. an over-length body is REFUSED, never silently truncated =="
# Silent write-time truncation would be the commit-message defect one layer
# down: the tail (often the crucial part) vanishes while the sender is told
# the payload was delivered.
setup
say "done for now"
brief_now
if as_peer cafe1234 reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1000)")" >/dev/null 2>&1; then
    echo "  PASS: a body exactly at the 1000-char limit is accepted"
    PASS=$((PASS + 1))
else
    echo "  FAIL: an at-limit body was refused"
    FAIL=$((FAIL + 1))
fi
if as_peer cafe1234 reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1100)")" >/dev/null 2>"$BASE/asklen.err"; then
    echo "  FAIL: an over-length ask was accepted"
    FAIL=$((FAIL + 1))
elif grep -qF "REFUSED rather than silently truncated" "$BASE/asklen.err" &&
    [[ "$(grep -c '"ev":"ask"' "${WL%.md}.requests")" == "1" ]]; then
    echo "  PASS: an over-length ask is refused loudly and writes nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: over-length refusal was silent or leaked an event: $(cat "$BASE/asklen.err")"
    FAIL=$((FAIL + 1))
fi
RID=$(reqcli --requests | sed -n 's/^#\([0-9a-f]\{8\}\).*/\1/p' | head -n1)
if reqcli --answer deadbeef "$RID" "$(python3 -c "print('y' * 1100)")" >/dev/null 2>"$BASE/anslen.err"; then
    echo "  FAIL: an over-length answer was accepted"
    FAIL=$((FAIL + 1))
elif grep -qF "REFUSED rather than silently truncated" "$BASE/anslen.err" &&
    ! grep -q '"ev":"answer"' "${WL%.md}.requests"; then
    echo "  PASS: an over-length answer is refused loudly and writes nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: over-length answer refusal was silent or leaked an event"
    FAIL=$((FAIL + 1))
fi

echo "== 78. --compact never touches the requests sidecar; blocking survives it =="
setup
say "done for now"
brief_now
askid_as cafe1234 deadbeef "must survive compaction" >/dev/null
printf -- '- [ ] (deadbeef) live item that must survive compaction, exit 0\n' >>"$WL"
printf -- '- [~] (cafe1234) archived tombstone line\n' >>"$WL"
# Force the EVENTS FILE to exist before compacting: the event-log compaction
# once deadlocked against its own flock (load(sync=True) inside the held
# lock), and this fixture's original shape dodged that path entirely because
# no events file had been created yet. `timeout` turns a regression into a
# failure instead of a hung suite.
reqcli --list >/dev/null
BEFORE=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    timeout 20 python3 "$HOOK" --compact >/dev/null 2>&1 </dev/null || true
if grep -q 'archived tombstone' "$WL"; then
    echo "  FAIL: --compact did not run (tombstone still present), test is vacuous"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: --compact really ran (tombstone dropped)"
    PASS=$((PASS + 1))
fi
if reqcli --list | grep -qF "live item that must survive compaction"; then
    echo "  PASS: the compacted event log still folds the live item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: event-log compaction lost a live item: $(reqcli --list)"
    FAIL=$((FAIL + 1))
fi
AFTER=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "  PASS: the requests sidecar is byte-identical after --compact"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --compact modified the requests sidecar"
    FAIL=$((FAIL + 1))
fi
# FOCUS=off: this fixture has several outstanding checks and the assertion
# is about the request one specifically, not about which check rotation picks.
export WORKLIST_FOCUS=off
check "an open request still blocks after --compact" block "waiting on you"
unset WORKLIST_FOCUS

echo "== 79. requests survive the worklist file being deleted entirely =="
# Deleting the worklist is the hook's documented allow-a-stop residual, but it
# must not delete cross-session obligations: the sidecar is a separate file
# and the request checks run unconditionally, not under worklist.exists().
setup
say "done for now"
brief_now
RID=$(askid_as cafe1234 deadbeef "still here after the worklist dies")
rm -f "$WL"
check "deleting the worklist does not delete the obligation" block "waiting on you"
reqcli --answer deadbeef "$RID" "done regardless of the worklist" >/dev/null
check "and the lifecycle still completes without a worklist file" allow ""

echo "== 80. RACE: concurrent escalators write the [?] exactly once =="
# The double-write question: two sessions escalating the same request in the
# same second. By construction both appends happen INSIDE the non-blocking
# flock and every escalator re-reads AFTER acquiring it, so a racer either
# fails the acquire (skips) or sees the winner's escalate event. This drives
# 8 hook processes at one dead-recipient request to prove it empirically.
setup
say "done for now"
brief_now
printf '{"ev":"ask","id":"feedc0de","from":"cafe1234","to":"beef9999","at":"%s","body":"race the escalators"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
for i in $(seq 1 8); do
    (run >/dev/null 2>&1) &
done
wait
NESC=$(reqcli --list | grep -c 'request #feedc0de')
NEVT=$(grep -c '"ev":"escalate","id":"feedc0de"' "${WL%.md}.requests")
if [[ "$NESC" == "1" && "$NEVT" == "1" ]]; then
    echo "  PASS: 8 concurrent stops produced exactly one [?] item and one escalate event"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 1 [?] item and 1 escalate event, got $NESC and $NEVT"
    FAIL=$((FAIL + 1))
fi

echo "== 81. asking a live peer without a waiter BLOCKS (v21) =="
# THE GAP THIS CLOSES, measured live 2026-08-27. The general NOT LISTENING
# check needs three things before it fires: a live non-poll work cron, a live
# peer, and WAITER_GRACE_NUDGES ignored nudges (half an hour). A session with
# NO cron directory can therefore never trip it -- and one was observed holding
# an open request to a peer seen minutes earlier, with no waiter, about to stop
# and wait forever for an answer it had no way to hear.
#
# Posting a request is the session choosing to depend on a reply, so this arm
# needs no grace period at all: one stop is enough.
setup
# NO POLL CRON. The default fixture carries one, and a 5-minute poll IS a
# listener -- the answer arrives within the rung, so the check correctly stays
# quiet there (case 81b pins that). What this arm models is the session that has
# NEITHER: measured live 2026-08-27, a session with no cron directory at all,
# holding an open ask, about to stop.
# NO CRONS AT ALL, and that is the precise gap. A work cron WITHOUT a poll cron
# trips the existing V_NO_POLL_CRON check ("THIS SESSION HAS A LOOP BUT NOTHING
# LISTENING"), which would block first and mask this one -- the first draft of
# this case did exactly that and reported a block from the wrong check. A
# session with NO loop is outside that check by construction, and is the shape
# actually observed live: no cron directory, an open ask, about to stop.
CRONS='[]'
say "done for now"
brief_now
brief_other cafe1234
askid deadbeef cafe1234 "please format the file that is reddening the lane" >/dev/null
check "an open ask, no waiter and no poll cron, blocks the stop" block "NOT LISTENING FOR THE ANSWER"

echo "== 81b. CONTROL: a POLL CRON is a listener, so the same state is allowed =="
# The distinction the first draft of this check missed, and two existing cases
# caught: a waiter is faster, a cron is slower, both HEAR. Without this control
# the arm above would pass just as well if the check ignored crons entirely.
setup
say "done for now"
brief_now
brief_other cafe1234
askid deadbeef cafe1234 "same state, but this session polls" >/dev/null
check_quiet "an open ask with a live poll cron does not demand a waiter" "NOT LISTENING FOR THE ANSWER"

echo "== 82. CONTROL: an ask to the OPERATOR needs no waiter =="
# A human answers at a shell; there is nothing for a waiter to hear, and
# blocking here would make `--ask operator` unusable.
setup
say "done for now"
brief_now
askid deadbeef operator "which branch should this land on" >/dev/null
check_quiet "an operator ask does not demand a waiter" "NOT LISTENING FOR THE ANSWER"

echo "== 83. CONTROL: an ask to a session that never briefed does not demand one =="
# Nobody is going to answer, so requiring a listener would be theatre. The
# existing escalation path owns that case.
setup
say "done for now"
brief_now
askid deadbeef 99999999 "into the void" >/dev/null
check_quiet "an ask to an unbriefed session does not demand a waiter" "NOT LISTENING FOR THE ANSWER"

echo "== 84. CONTROL: once the peer ANSWERS, the demand lifts =="
# The obligation is to hear the reply, not to hold a process forever. This leg
# proves the check keys on OPEN requests rather than on any request having
# ever existed -- without it, a check stuck permanently on would pass case 81.
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "answer me")
as_peer cafe1234 reqcli --answer cafe1234 "$RID" "done" >/dev/null
reqcli --ack deadbeef "$RID" >/dev/null
check_quiet "an answered ask no longer demands a waiter" "NOT LISTENING FOR THE ANSWER"
