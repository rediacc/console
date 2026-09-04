#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The store-derived guide on every stop, --defer justification, aged [?] demands, and the sitting-on-a-watch backlog forcing.

echo "== 146. v11: the store-derived GUIDE rides every full stop, bounded =="
# The operator's ask: "--list should be used always on stop hook to output
# enforced guided instructions". The defect it fixes: v10 stamped every item
# and the hand-authored Remaining prose never read the store.

# (a) ALLOW stop: guide present, with the state-correct verbs.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"cccc1111","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated build"}\n{"ev":"lease","id":"cccc1111","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n{"ev":"add","id":"cccc1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"ship the flag? DEFAULT: ship it"}\n' \
    "$NOW" "$NOW" "$UNTIL" "$NOW" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the delegated build and the flag question"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF -- "--update deadbeef cccc1111" <<<"$out" &&
    grep -qF "DEFAULT executes in" <<<"$out"; then
    pass "an ALLOW stop carries the guide: [>] gets --update, fresh [?] gets its window"
else
    fail "guide missing or wrong verbs on allow (got=$got): ${out:0:300}"
fi

# (b) BLOCK stop under WORKLIST_FOCUS=off: the guide rides the dump-all block
# reason, [ ] gets --tick. v13's FOCUSED block deliberately drops the guide
# (operator, 2026-07-31, superseding the v11 every-full-stop mandate), so the
# focused variant is asserted guide-FREE in (b2) below.
setup
brief_now
hand_now
echo '- [ ] (deadbeef) wire the perf fixture' >>"$WL"
say "answer

## Remaining
- the perf fixture"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF -- "--tick deadbeef" <<<"$out" && grep -qF "do it, then" <<<"$out"; then
    pass "a FOCUS=off block carries the guide, and an open item gets --tick"
else
    fail "guide missing from the FOCUS=off block path: ${out:0:300}"
fi

# (b2) the v13 FOCUSED block is guide-free: the noise reduction IS the
# feature, and the one check that needs store data carries its own slice.
out="$(run)"
if grep -qF '"decision": "block"' <<<"$out" && ! grep -qF "WORKLIST GUIDE" <<<"$out" &&
    grep -qF "OPEN worklist item" <<<"$out"; then
    pass "the focused block drops the guide and still names the open item"
else
    fail "focused block carried the guide or lost the item: ${out:0:300}"
fi

# (c) ZERO actionable: SILENT since v18. This case used to assert the
# opposite -- "a short honest line, never ambiguous silence" -- and the
# operator overruled it (2026-08-04, quoting a stop whose whole output was
# that line plus the wakeup times): "silent when there is nothing to act on...
# let's go for efficient ai context usage". The ambiguity the old line guarded
# against is also gone, because the poll fast path already exits silently many
# times an hour, so zero bytes is the session's familiar "nothing to do".
setup
brief_now
hand_now
say "all done"
out="$(run)"
if ! grep -qF "no actionable items in the store" <<<"$out"; then
    pass "an empty store no longer announces its own emptiness"
else
    fail "the empty-guide line survived: ${out:0:260}"
fi
# This fixture is NOT silent, and it should not be: a repo with no request
# traffic at all trips the poll-backoff advisory, which is a real thing to act
# on. Pinning that here keeps the zero-byte case below honest -- it proves the
# silence there comes from having nothing to say, not from a muted report.
if grep -qF "INBOX HAS BEEN QUIET" <<<"$out"; then
    pass "and the one section that DID have something to say still speaks"
else
    fail "the backoff advisory was swallowed with the guide: ${out:0:260}"
fi
# NOW the zero-byte case: one fresh request in the log (between two OTHER
# sessions, so it never reaches this inbox) resets the quiet clock and silences
# the backoff advisory, leaving a stop with genuinely nothing to report.
askid_as cafe1234 beefcafe "a question between two other sessions" >/dev/null
newturn
say "all done"
out="$(run)"
rc=$?
if [[ "$rc" -eq 0 && -z "$out" ]]; then
    pass "a clean stop with nothing to act on emits ZERO bytes"
else
    fail "the nothing-to-report stop was not silent (rc=$rc): ${out:0:260}"
fi
# CONTROL, so the silence above is the guide standing down and not the battery
# being skipped: the SAME fixture plus one real item speaks up immediately.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
newturn
say "all done

## Remaining
- the flag decision, deferred with a default"
out="$(run)"
if grep -qF "WORKLIST GUIDE" <<<"$out" && grep -qF "keep the flag?" <<<"$out"; then
    pass "CONTROL: one actionable item brings the guide straight back"
else
    fail "CONTROL: the guide stayed silent with a real item: ${out:0:260}"
fi

# (d) TRUNCATION is loud: 15 open items show 12 and SAY 3 were held back.
setup
brief_now
hand_now
for i in $(seq 1 15); do
    echo "- [ ] (deadbeef) backlog item number $i" >>"$WL"
done
say "answer

## Remaining
- fifteen backlog items"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
# -o, not -c: the hook's output is ONE JSON line, so a line count reads 1.
NSHOWN=$(grep -oF "do it, then --tick" <<<"$out" | wc -l)
if [[ "$NSHOWN" == "12" ]] && grep -qF "+3 more actionable" <<<"$out" &&
    grep -qF "HELD BACK by the 12-line cap" <<<"$out"; then
    pass "the cap emits 12 of 15 and names the 3 it dropped"
else
    fail "silent or wrong truncation: shown=$NSHOWN out=${out:0:300}"
fi

# (e) VERB-STATE MATCH for the remaining shapes: undefaulted [?], expired
# window, dead lease, each with its own exit spelled out.
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
PAST=$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"cccc2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged choice DEFAULT: option A"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
echo '- [?] (deadbeef) an undefaulted question' >>"$WL"
echo "- [>] (deadbeef) until:$PAST stale delegation" >>"$WL"
say "answer

## Remaining
- three differently broken items"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
ok=1
for needle in "execute its DEFAULT now" "--defer deadbeef" "LEASE DEAD" "re-lease: --lease deadbeef"; do
    grep -qF -- "$needle" <<<"$out" || {
        ok=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok" == 1 ]]; then
    pass "expired [?], undefaulted [?] and a dead lease each carry their own exit"
else
    fail "verb-state mismatch: ${out:0:400}"
fi

# (f) --list --open is the SAME slice from the CLI, and the full dump keeps
# the [x] history the slice excludes.
setup
echo '- [ ] (deadbeef) open thing' >>"$WL"
echo '- [x] (deadbeef) finished thing, exit 0' >>"$WL"
OPEN="$(reqcli --list --open deadbeef)"
FULL="$(reqcli --list)"
if grep -qF -- "--tick deadbeef" <<<"$OPEN" && grep -qF "open thing" <<<"$OPEN" &&
    ! grep -qF "finished thing" <<<"$OPEN" && grep -qF "finished thing" <<<"$FULL"; then
    pass "--list --open shows the hook's slice; plain --list keeps the history"
else
    fail "CLI slice mismatch: OPEN=${OPEN:0:200} FULL=${FULL:0:120}"
fi

# (f2) the CLI slice is UNCAPPED. GUIDE_TRUNCATED (case (d)) tells the reader
# to run this exact command "for the full slice", and until the full= flag the
# command re-rendered the same 12 rows -- advice that looped back onto itself.
# 15 open items must all appear here, with NO truncation footer. The 12-line
# cap stays on the Stop path, which case (d) pins; this case and that one are
# each other's control, so a regression that lifts the cap everywhere (or
# restores it here) fails one of the two.
setup
for i in $(seq 1 15); do
    echo "- [ ] (deadbeef) uncapped backlog item number $i" >>"$WL"
done
OPEN="$(reqcli --list --open deadbeef)"
NSHOWN=$(grep -cF "do it, then --tick" <<<"$OPEN")
MISS=""
for i in $(seq 1 15); do
    grep -qF "uncapped backlog item number $i" <<<"$OPEN" || MISS="$MISS $i"
done
if [[ "$NSHOWN" == "15" && -z "$MISS" ]] && ! grep -qF "HELD BACK" <<<"$OPEN"; then
    pass "--list --open lifts the 12-line cap: all 15 items, no truncation footer"
else
    fail "CLI slice still capped (shown=$NSHOWN missing=[$MISS]): ${OPEN:0:300}"
fi

# ---------------------------------------------------------------------------
# v12 (cases 147+): deferral justification (WHY/HOW as real store fields),
# the harsh judge audit over sitting [?] items, and the CI-waiting force.
# The operator's evidence: 30+ deferrals sat 117 minutes while the session
# stopped three times with "the run is healthy"; one deferral requested a
# feature that had ALREADY been built. Every FIRE case is paired with a
# SILENT control differing by one planted fact, and every demand's solo exit
# is proven to reach an allowed stop (the anti-deadlock property).
# ---------------------------------------------------------------------------

shim_judge_out() { # shim_judge_out '<structured_output JSON>' -- canned claude + call counter
    SO="$1" CALLS="$BASE/judgecalls" SHIM="$BASE/binonly/claude" python3 -c '
import json, os, pathlib, stat
out = {"is_error": False, "structured_output": json.loads(os.environ["SO"])}
body = ("#!/bin/bash\necho x >> " + json.dumps(os.environ["CALLS"]) + "\n"
        "echo " + json.dumps(json.dumps(out)) + "\n")
p = pathlib.Path(os.environ["SHIM"])
p.write_text(body)
p.chmod(p.stat().st_mode | stat.S_IEXEC)
'
}

echo "== 147. --defer refuses a deferral that cannot justify its seat =="
setup
NID=$(reqcli --add deadbeef "choose the flag default" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "WHY:" <<<"$OUT" && grep -qF "HOW:" <<<"$OUT"; then
    pass "a deferral with no WHY/HOW is refused, naming both fields"
else
    fail "unjustified --defer was accepted (rc=$RC): ${OUT:0:200}"
fi
if ! grep -q '"ev":"state"' <(wl_events); then
    pass "the refused defer wrote NO state event (a rejected write is not a delivered one)"
else
    fail "a refused defer still wrote an event: $(grep '"ev":"state"' <(wl_events))"
fi
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it WHY: did not get to it yet HOW: revisit next week" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "avoidance" <<<"$OUT"; then
    pass "a vacuous WHY ('did not get to it') is refused as avoidance"
else
    fail "the vague-why gate did not fire (rc=$RC): ${OUT:0:200}"
fi
OUT=$(reqcli --defer deadbeef "$NID" "keep the flag? DEFAULT: keep it WHY: flipping it changes billing for live users, an operator-only call HOW: operator confirms, or the DEFAULT keeps it TRIED: read the pricing doc BLOCKED_ON: operator" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -q '"j":{' <(wl_events) &&
    grep -qF '"why":"flipping it changes billing' <(wl_events) &&
    grep -qF '"blocked_on":"operator"' <(wl_events); then
    pass "a justified defer lands with WHY/HOW/TRIED/BLOCKED_ON as real JSON fields"
else
    fail "justified defer rc=$RC or fields missing: $(wl_events | tail -c 300)"
fi

echo "== 148. an AGED [?] with no justification is demanded, bounded =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"dddd1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"quarantine the leg? DEFAULT: quarantine it"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the quarantine decision, deferred"
check "a 60-minute [?] with no WHY/HOW blocks for its justification" block "NO justification on record"
# THE HONEST-ANSWER EXIT (anti-deadlock): re-deferring with a WHY/HOW is
# completable alone in one turn, and it reaches an allowed stop.
reqcli --defer deadbeef dddd1111 "quarantine the leg? DEFAULT: quarantine it WHY: only the operator can accept the coverage loss it causes HOW: operator approves, or the DEFAULT quarantines it" >/dev/null
newturn
say "justified the deferral

## Remaining
- the quarantine decision, deferred with its justification"
check "answering the WHY/HOW honestly reaches an allowed stop" allow "operator may answer"
# CONTROL: the same age WITH a justification never fires (one planted fact).
setup
brief_now
hand_now
printf '{"ev":"add","id":"dddd1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"price the tier? DEFAULT: keep the price WHY: pricing is an operator-only call with revenue stakes HOW: operator picks a number"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the pricing decision, deferred with its justification"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && ! grep -qF "NO justification on record" <<<"$out"; then
    pass "CONTROL: the same aged [?] WITH a WHY/HOW does not fire"
else
    fail "justified deferral was nagged (got=$got): ${out:0:260}"
fi
# DRAIN CAP: five aged unjustified arrive three at a time, never as a wall.
setup
brief_now
hand_now
for i in 1 2 3 4 5; do
    printf '{"ev":"add","id":"dddd222%s","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged bare question %s DEFAULT: option A"}\n' \
        "$i" "$OLD" "$i" >>"${WL%.md}.events.jsonl"
done
say "answer

## Remaining
- five bare deferrals"
out="$(run)"
if grep -qF "5 deferred item(s) have sat" <<<"$out" && grep -qF "and 2 more, held back" <<<"$out"; then
    pass "five unjustified deferrals drain 3 per stop, never as a wall"
else
    fail "justification drain cap wrong: ${out:0:300}"
fi

echo "== 149. THE CENTREPIECE: sitting on a CI watch forces the backlog =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"eeee1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":".ci/scripts/ci/ci-trace.py --wait","description":"watch CI run"}]'
say "the run is healthy, nothing to do

## Remaining
- the backfill decision, deferred"
check "a CI watch as the ONLY in-flight work demands the aged backlog by id" block "YOU ARE SITTING ON CI"
out="$(run)"
if grep -qF "#eeee1111" <<<"$out" && grep -qF "NEXT:" <<<"$out"; then
    pass "the force names the item id and its next verb"
else
    fail "no id or verb in the CI-waiting block: ${out:0:300}"
fi
# ANTI-DEADLOCK: doing the demanded work reaches an allowed stop, with the
# same watch still running.
reqcli --tick deadbeef eeee1111 "backfilled, exit 0" >/dev/null
newturn
say "executed the backfill default while the run finished

## Remaining
nothing open; the CI watch is still running"
check "doing the demanded work reaches an allowed stop under the same watch" allow ""
# CONTROL 1 (one planted fact: a real worker beside the watch): not sitting.
setup
brief_now
hand_now
printf '{"ev":"add","id":"eeee2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":".ci/scripts/ci/ci-trace.py --wait","description":"watch CI run"},{"id":"bw2","type":"shell","status":"running","command":"bash scripts/build-embed.sh","description":"rebuild embed assets"}]'
say "watching the run while the embed rebuild runs

## Remaining
- the backfill decision, deferred"
out="$(run)"
if ! grep -qF "SITTING ON CI" <<<"$out"; then
    pass "CONTROL: a non-watch worker beside the watch means not sitting"
else
    fail "the force fired despite real delegated work: ${out:0:260}"
fi
# CONTROL 2 (one planted fact: the backlog is fresh): nothing to force.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"eeee3331","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator can accept the storage cost HOW: operator confirms the budget"}\n' \
    "$NOW" >>"${WL%.md}.events.jsonl"
BG='[{"id":"cw1","type":"shell","status":"running","command":".ci/scripts/ci/ci-trace.py --wait","description":"watch CI run"}]'
say "watching the run

## Remaining
- the backfill decision, freshly deferred"
out="$(run)"
if ! grep -qF "SITTING ON CI" <<<"$out"; then
    pass "CONTROL: a FRESH deferral is not demanded (re-justifying is a real exit)"
else
    fail "the force fired on a fresh backlog: ${out:0:260}"
fi

echo "== 150. the judge AUDITS sitting justifications; do_now REOPENS the item =="
setup
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"ffff1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"quarantine the flaky leg? DEFAULT: quarantine it WHY: only the operator can accept the coverage loss HOW: operator approves the quarantine"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the quarantine decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"ok","next_action":"none","defer_audit":[{"id":"ffff1111","verdict":"do_now","reason":"the flake stats are in the tree","order":"read the flake stats and quarantine it yourself"}]}'
checkj "a do_now audit verdict blocks with the judge's order" block "DEFERRAL AUDIT REJECTED"
LIST="$(reqcli --list)"
if grep -qF -- "- [ ]" <<<"$LIST" && grep -qF "REOPENED by the stop-gate judge" <<<"$LIST"; then
    pass "the rejected deferral is REOPENED as ordinary open work"
else
    fail "no reopened item in the store: ${LIST:0:260}"
fi
# ANTI-DEADLOCK: doing the reopened work reaches an allowed stop.
reqcli --tick deadbeef ffff1111 "quarantined, exit 0" >/dev/null
newturn
say "quarantined the leg as ordered

## Remaining
nothing"
checkj "ticking the reopened item with evidence reaches an allowed stop" allow ""

echo "== 151. a VALID audit verdict is banked; an untouched item is asked once =="
setup
# The [?] item is also an operator-only mail candidate, so the unconfigured
# email channel queues a class-1 note ahead of the audit note. Both are
# one-shots and neither is lost; this case asserts the audit note is produced,
# so it drains wide rather than waiting a stop for its turn.
export WORKLIST_REPORT_PER_STOP=9
brief_now
hand_now
OLD=$(date -u -d '-60 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"ffff2221","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every teammate out for an hour, an operator-only call HOW: operator names the window"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the rotation decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"genuinely operator-only","next_action":"none","defer_audit":[{"id":"ffff2221","verdict":"valid","reason":"locking teammates out is a real operator-only stake","order":""}]}'
checkj "a valid verdict allows and reports the banked reason" allow "survived interrogation"
N1=$(wc -l <"$BASE/judgecalls" 2>/dev/null || echo 0)
checkj "the untouched item is not re-audited (banked per stamp)" allow ""
N2=$(wc -l <"$BASE/judgecalls" 2>/dev/null || echo 0)
if [[ "$N1" -eq 1 && "$N2" -eq 1 ]]; then
    pass "one judge call total: the bank and the verdict cache both held ($N1,$N2)"
else
    fail "judge was re-paid for an untouched item: calls=$N1 then $N2"
fi
# FAIL CLOSED: an audit that was requested and not answered is a judge error.
setup
brief_now
hand_now
printf '{"ev":"add","id":"ffff3331","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every teammate out for an hour, an operator-only call HOW: operator names the window"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the rotation decision, deferred with its justification"
shim_judge_out '{"verdict":"stop","reason":"ok","next_action":"none"}'
checkj "a requested audit with no defer_audit answer FAILS CLOSED" block "no usable defer_audit"

echo "== 152. the silent poll forfeits to the justification demand =="
setup
brief_now
hand_now
OLD=$(date -u -d '-40 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"dddd7771","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"bare aged question DEFAULT: option A"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the bare deferral"
check "the full stop demands the justification (and banks the poll baseline)" block "NO justification on record"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "NO justification on record" <<<"$OUT"; then
    pass "a poll stop cannot slip past an unjustified aged [?]"
else
    fail "the poll fast path swallowed the justification demand: '${OUT:0:200}'"
fi
# CONTROL (one planted fact: the same item, justified): the poll is silent.
setup
brief_now
hand_now
printf '{"ev":"add","id":"dddd7772","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged question DEFAULT: option A WHY: only the operator can weigh the trade HOW: operator answers"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the justified deferral"
check "baseline stop allows" allow ""
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "CONTROL: the same age WITH a justification keeps the silent poll"
else
    fail "a justified deferral forfeited the fast path: rc=$RC '${OUT:0:160}'"
fi

echo "== 153. a LATCHED ladder rung must not forfeit the silent poll forever =="
# WHAT BROKE. The ladder is latched (fire_once records each rung against the
# subject's stamp), but poll_fast_path forfeited on RAW AGE and never consulted
# that latch. So the two disagreed: the report went silent after firing once
# while the forfeit kept firing on every poll.
#
# Measured 2026-07-30: task #20 sat in_progress for 298 minutes, legitimately,
# waiting on an operator decision and a running agent. Its rung had long since
# fired, yet every five-minute inbox poll paid the full battery and demanded a
# full report, with no way to discharge it short of finishing or abandoning a
# task that was not this session's to finish. That is the "a gate that cannot be
# satisfied deadlocks the session" trap the v10 brief warned about, reintroduced
# by a threshold comparison that looked harmless.
#
# Both directions are asserted, because the cure must not silence a rung that
# has NOT yet been reported.
setup
brief_now
hand_now
# The task must exist BEFORE the baseline stop banks the poll baseline: task
# statuses are part of the world signature, so creating it afterwards moves the
# signature and a DIFFERENT check fires. That fixture bug cost a round here, and
# it is worth stating because it makes a real fix look broken.
task 20 in_progress "wave B acceptance, blocked on the operator"
say "answer

## Remaining
| #20 | wave B acceptance | ongoing, the operator |"
check "baseline stop allows" allow ""
# Its rung ALREADY fired against this exact stamp. Written straight into the
# state doc (which is NOT part of the world signature, so this is safe after the
# baseline) because the point is the latch, not how it got set.
python3 - "$WL" <<'PY'
import json, pathlib, sys
wl = pathlib.Path(sys.argv[1])
p = wl.with_suffix(".state-deadbeef.json")
doc = json.loads(p.read_text()) if p.exists() else {}
stamp = "2026-07-30T06:29:37Z"
doc.setdefault("tasks_seen", {})["20"] = {"status": "in_progress", "since": stamp}
doc.setdefault("ladder", {})["task:20"] = {"investigate": stamp, "resolve": stamp}
p.write_text(json.dumps(doc))
PY
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "a latched rung on a 298m task keeps the silent poll"
else
    fail "a latched rung still forfeited the fast path: rc=$RC '${OUT:0:200}'"
fi

# CONTROL, and it is the one that matters: the SAME task at the SAME age with
# the rung NOT yet fired must still forfeit. Without this the fix could be a
# blanket "never forfeit on tasks" and the suite would not notice.
setup
brief_now
hand_now
task 20 in_progress "wave B acceptance, blocked on the operator"
say "answer

## Remaining
| #20 | wave B acceptance | ongoing, the operator |"
check "baseline stop allows" allow ""
python3 - "$WL" <<'PY'
import json, pathlib, sys
wl = pathlib.Path(sys.argv[1])
p = wl.with_suffix(".state-deadbeef.json")
doc = json.loads(p.read_text()) if p.exists() else {}
doc.setdefault("tasks_seen", {})["20"] = {"status": "in_progress", "since": "2026-07-30T06:29:37Z"}
doc["ladder"] = {}  # never fired
p.write_text(json.dumps(doc))
PY
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "CONTROL: an UNFIRED rung at the same age still forfeits the silent poll"
else
    fail "an unfired blocking rung was swallowed by the fast path"
fi
