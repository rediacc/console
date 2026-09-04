#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# CI-queue backpressure and its cache, operator email (ask, cooldown, answer loop, digest, transport failure), and the v14 gap set.

# The operator's live incident (2026-07-31): pushes queued runs behind each
# other and a run sat pending 25+ minutes. The hook must see the jam and tell
# the session to work locally instead of pushing more.
ci_queue_fixture() { # ci_queue_fixture <runs-json>
    echo "$1" >"$BASE/ci-runs.json"
    rm -f "${WL%.md}.ciqueue-deadbeef"
    cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) cat "$BASE/ci-runs.json"; exit 0 ;;
    *actions/jobs/*) cat "$BASE/ci-job.json"; exit 0 ;;
esac
echo '{}'
SHIM
    chmod +x "$BASE/binonly/gh"
}
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
QOLD=$(date -u -d '-30 minutes' +%Y-%m-%dT%H:%M:%SZ)
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"},{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if grep -qF "CI QUEUE IS SATURATED" <<<"$out" && grep -qF "DO NOT PUSH" <<<"$out"; then
    pass "157: a 30-minute-queued newest run raises the saturation note"
else
    fail "157: saturation note missing: ${out:0:300}"
fi

echo "== 157b. CONTROL: an in-progress run with an empty queue is clear =="
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"in_progress\",\"created_at\":\"$QOLD\"},{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if ! grep -qF "CI QUEUE IS SATURATED" <<<"$out"; then
    pass "157b CONTROL: a running (not queued) newest run stays quiet"
else
    fail "157b: clear queue raised the note: ${out:0:300}"
fi

echo "== 157c. depth trigger: two queued runs saturate even when fresh =="
QNEW=$(date -u -d '-1 minute' +%Y-%m-%dT%H:%M:%SZ)
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QNEW\"},{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
out="$(ci_run)"
if grep -qF "CI QUEUE IS SATURATED" <<<"$out" && grep -qF "2 queued run(s)" <<<"$out"; then
    pass "157c: queue depth >= 2 saturates regardless of the newest run's age"
else
    fail "157c: depth trigger missing: ${out:0:300}"
fi

echo "== 157d. FAILURE MODE: a broken gh grants NO slack (fails toward pressure) =="
rm -f "${WL%.md}.ciqueue-deadbeef"
cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) echo "boom" >&2; exit 1 ;;
esac
echo '{}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(ci_run)"
if ! grep -qF "CI QUEUE IS SATURATED" <<<"$out"; then
    pass "157d: gh failure reads as unknown, note absent, no relaxation granted"
else
    fail "157d: a blind queue check granted slack: ${out:0:300}"
fi

echo "== 157e. SUPPRESSION PAIR: pr-stale folds into the note only while saturated =="
# Stale body: last push AFTER the PR-body edit (edit stamped in 2000).
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"lastEditedAt":"2000-01-01T00:00:00Z","updatedAt":"2000-01-01T00:00:00Z"}]}}}}' >"$BASE/ci-fresh.json"
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
CIMSG="answer with work remaining"
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(ci_run)"
if ! grep -qF "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out" &&
    grep -qF "the PR body is stale; fold the refresh into that next push" <<<"$out"; then
    pass "157e: under saturation the stale-body nag folds into the queue note"
else
    fail "157e: fold wrong: ${out:0:400}"
fi
# The pair's control: same stale body, queue now clear -> the check fires.
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"completed\",\"created_at\":\"$QOLD\"}]}"
export WORKLIST_FOCUS=off
out="$(ci_run)"
unset WORKLIST_FOCUS
unset CIMSG
if grep -qF "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out"; then
    pass "157e CONTROL: with the queue clear the stale-body check fires again"
else
    fail "157e CONTROL: pr-stale did not fire on a clear queue: ${out:0:300}"
fi

echo "== 157f. the queue read is cached: two stops inside the TTL, one gh hit =="
ci_setup
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
ci_queue_fixture "{\"workflow_runs\":[{\"status\":\"queued\",\"created_at\":\"$QOLD\"}]}"
cat >"$BASE/binonly/gh" <<SHIM
#!/bin/bash
for a in "\$@"; do
    case "\$a" in
        *lastEditedAt*) cat "$BASE/ci-fresh.json"; exit 0 ;;
        query=*) cat "$BASE/ci-rollup.json"; exit 0 ;;
    esac
done
case "\$*" in
    *actions/runs*) echo hit >>"$BASE/runs-hits.txt"; cat "$BASE/ci-runs.json"; exit 0 ;;
esac
echo '{}'
SHIM
chmod +x "$BASE/binonly/gh"
rm -f "$BASE/runs-hits.txt" "${WL%.md}.ciqueue-deadbeef"
ci_run >/dev/null
ci_run >/dev/null
HITS=$(wc -l <"$BASE/runs-hits.txt" 2>/dev/null || echo 0)
if [[ "$HITS" == "1" ]]; then
    pass "157f: the second stop served the queue state from the cache"
else
    fail "157f: expected exactly 1 runs-endpoint hit, got $HITS"
fi

echo "== 159. operator requests: asked once, relayed by the stop report =="
# The operator EMAIL channel that used to carry these was removed: it was
# dormant rather than disabled (WORKLIST_EMAIL defaulted to "on", and only a
# failed-send backoff was silencing it, so a credential rotation would have
# re-armed it without anyone asking). The REQUEST layer it fed is not
# email-specific and is what actually holds these questions, so everything it
# proved that was not about SES is still proved here.
setup
brief_now
hand_now
RID=$(askid deadbeef operator 'which tier map? DEFAULT: ship the draft map')
say "answer

## Remaining
- the tier map question, now with the operator"
out="$(run)"
if grep -qF "which tier map?" <<<"$out" && grep -qF "$RID" <<<"$out" &&
    grep -qF -- "--answer operator <id>" <<<"$out"; then
    pass "159: the stop report carries the question, its id, and the relay command"
else
    fail "159: report=${out:0:400}"
fi
# CONTROL: the relay line is for the OPERATOR, not decoration on every request.
RIDS=$(askid deadbeef cafe1234 'restart the ceph leg? DEFAULT: restart it')
newturn
say "answer

## Remaining
- the tier map question and a session request"
out="$(run)"
if grep -qF "$RIDS" <<<"$out"; then
    pass "159 CONTROL: an ordinary session request is still reported"
else
    fail "159 CONTROL: the session request vanished: ${out:0:400}"
fi
RID2=$(askid deadbeef operator 'ship the ceph leg? DEFAULT: hold it for the next wave')
newturn
say "answer

## Remaining
- two operator questions outstanding"
run >/dev/null

echo "== 159c. ANSWER LOOP: --answer operator reaches the asker, --ack clears it =="
reqcli --answer operator "$RID" 'use tier map B, the draft undercounts seats' >/dev/null
newturn
say "answer

## Remaining
- act on the operator's tier map answer"
export WORKLIST_FOCUS=off
check "the operator's answer blocks its asker with the text in the reason" block \
    "use tier map B, the draft undercounts seats"
reqcli --ack deadbeef "$RID" >/dev/null
newturn
say "acted on it

## Remaining
- one operator question still open"
out="$(run)"
unset WORKLIST_FOCUS
if ! grep -qF "use tier map B" <<<"$out"; then
    pass "159c: --ack ends the delivery permanently"
else
    fail "159c: the acked answer still blocked: ${out:0:300}"
fi
# CONTROL: the self-answer guard is untouched by the operator recipient.
reqcli --answer deadbeef "$RID2" 'answering myself' >"$BASE/self.out" 2>&1
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "your own request" "$BASE/self.out"; then
    pass "159c CONTROL: answering your own request is still refused"
else
    fail "159c CONTROL: self-answer rc=$RC out=$(head -c 200 "$BASE/self.out")"
fi

echo "== 159d. an operator request does NOT escalate into a duplicate [?] =="
# Without the exemption every operator question would ALSO clone itself into a
# deferral carrying the same text and its own DEFAULT window.
setup
brief_now
hand_now
OLDREQ=$(date -u -d '-300 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"ask","id":"aaaa1111","from":"deadbeef","to":"operator","at":"%s","body":"which tier map? DEFAULT: ship the draft"}\n' \
    "$OLDREQ" >>"${WL%.md}.requests"
say "answer

## Remaining
- the operator question"
run >/dev/null
if ! grep -q '"ev":"escalate"' "${WL%.md}.requests" &&
    ! grep -q 'aaaa1111' <(wl_events) 2>/dev/null; then
    pass "159d: a 300-minute-old operator request is not cloned into a [?]"
else
    fail "159d: the operator request escalated: $(grep escalate "${WL%.md}.requests" | head -c 200)"
fi
# CONTROL: the dead-recipient rule itself still works for an ordinary session.
printf '{"ev":"ask","id":"bbbb2222","from":"deadbeef","to":"zzzzzzzz","at":"%s","body":"restart the leg? DEFAULT: restart it"}\n' \
    "$OLDREQ" >>"${WL%.md}.requests"
newturn
say "answer

## Remaining
- the operator question and the dead-recipient one"
run >/dev/null
if grep -q '"ev":"escalate"' "${WL%.md}.requests" && grep -q 'bbbb2222' <(wl_events); then
    pass "159d CONTROL: an ordinary request to a silent session still escalates"
else
    fail "159d CONTROL: dead-recipient escalation stopped working"
fi

echo "== 159g. --ask operator needs a DEFAULT: =="
setup
brief_now
hand_now
reqcli --ask deadbeef operator 'just tell me what you think' >"$BASE/ask.out" 2>&1
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "must carry a DEFAULT:" "$BASE/ask.out"; then
    pass "159g: an operator request with no DEFAULT: is refused at the door"
else
    fail "159g: DEFAULT-less operator ask rc=$RC out=$(head -c 200 "$BASE/ask.out")"
fi

echo "== 160. v14 gap 1: displays show basetext + LATEST note, never the whole history =="
# One live item reached ~20 concatenated notes and every block printed them
# all. brief_line/brief_text keep the full accumulation in the store (--list)
# and render base + newest only.
setup
brief_now
hand_now
GID=$(reqcli --add deadbeef "campaign base text for the brief test" | grep -oE '#[0-9a-f]+' | tr -d '#')
JW="WHY: only the operator can pick between the two tier maps because both are defensible and the code decides nothing HOW: the operator answers on their next pass"
reqcli --defer deadbeef "$GID" "first old note DEFAULT: alpha $JW" >/dev/null
reqcli --defer deadbeef "$GID" "second old note DEFAULT: beta $JW" >/dev/null
reqcli --defer deadbeef "$GID" "newest note wins DEFAULT: gamma $JW" >/dev/null
say "answer

## Remaining
- the deferred campaign item"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
if grep -qF "campaign base text for the brief test" <<<"$out" &&
    grep -qF "newest note wins" <<<"$out" &&
    ! grep -qF "first old note" <<<"$out" &&
    ! grep -qF "second old note" <<<"$out"; then
    pass "160: the stop shows base + LATEST and drops the middle history"
else
    fail "160: brief rendering wrong: ${out:0:400}"
fi
FULL="$(reqcli --list)"
if grep -qF "first old note" <<<"$FULL" && grep -qF "second old note" <<<"$FULL"; then
    pass "160 CONTROL: --list still carries the full accumulated history"
else
    fail "160 CONTROL: the store lost history: ${FULL:0:300}"
fi

echo "== 160b. v14 gap 2: own worklist activity resets the stuck counter =="
# A session ticking/leasing/updating items hourly is MOVING even when its
# long-horizon harness tasks never flip; only a session doing neither counts.
# STUCK_ROUNDS=2 so tasks+head fires at 2 unchanged stops (1 would fire on
# every stop by construction: a fresh signature starts its count at 1).
setup
brief_now
hand_now
export WORKLIST_STUCK_ROUNDS=2
task 7 pending "long-horizon watch"
FIRED=0
for i in 1 2 3 4; do
    newturn
    say "answer

## Remaining
- #7 long-horizon watch (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
    AID=$(reqcli --add deadbeef "movement item $i" | grep -oE '#[0-9a-f]+' | tr -d '#')
    reqcli --tick deadbeef "$AID" "done, exit 0" >/dev/null
done
if [[ "$FIRED" == 0 ]]; then
    pass "160b: worklist activity between stops keeps the stuck detector quiet"
else
    fail "160b: an active session still read as stuck: ${OUT:0:250}"
fi
# CONTROL: the identical shape WITHOUT worklist activity fires.
setup
brief_now
hand_now
task 7 pending "long-horizon watch"
FIRED=0
for i in 1 2 3 4; do
    newturn
    say "answer

## Remaining
- #7 long-horizon watch (pending)"
    OUT="$(run)"
    grep -qF "CONSECUTIVE STOPS" <<<"$OUT" && FIRED=1
done
unset WORKLIST_STUCK_ROUNDS
if [[ "$FIRED" == 1 ]]; then
    pass "160b CONTROL: with no activity the detector still fires"
else
    fail "160b CONTROL: the stuck detector never fired: ${OUT:0:250}"
fi

echo "== 160c. v14 gap 3: --lease warns when the worker id is not a running task =="
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "leased thing" | grep -oE '#[0-9a-f]+' | tr -d '#')
printf '{"background_tasks":[{"id":"bw1","type":"shell","status":"running","description":"real watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
OUT="$(reqcli --lease deadbeef "$CID" +30 worker:my-agent-name "watching" 2>&1)"
if grep -qF "WARNING: worker:my-agent-name is not among" <<<"$OUT" && grep -qF "bw1" <<<"$OUT"; then
    pass "160c: a name-not-id lease is warned about, naming the real ids"
else
    fail "160c: no warning for an unverifiable worker: ${OUT:0:250}"
fi
OUT="$(reqcli --lease deadbeef "$CID" +30 worker:bw1 "watching" 2>&1)"
if grep -qF "worker verified against the harness" <<<"$OUT" && ! grep -qF "WARNING" <<<"$OUT"; then
    pass "160c CONTROL: a real task id is verified, no warning"
else
    fail "160c CONTROL: verification suffix missing: ${OUT:0:250}"
fi

echo "== 160d. v14 gap 4: an expired lease with an OS-verified-alive worker stays in-flight =="
setup
brief_now
hand_now
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PAST=$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"dddd0001","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"long CI watch"}\n{"ev":"lease","id":"dddd0001","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$FRESH" "$FRESH" "$PAST" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the long CI watch"}]'
say "answer

## Remaining
- the long CI watch, in flight on bw1"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if ! grep -qF "lease expired; finish it" <<<"$OUT" && ! grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "160d: the verified-alive worker keeps the expired lease in flight"
else
    fail "160d: a supervised long job still failed closed: ${OUT:0:300}"
fi
# CONTROL: the same expired lease with the worker GONE fails closed as before.
BG='[]'
newturn
say "answer

## Remaining
- the long CI watch, in flight on bw1"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
BG=''
if grep -qF "lease expired; finish it" <<<"$OUT"; then
    pass "160d CONTROL: a gone worker still fails the expired lease closed"
else
    fail "160d CONTROL: the expired lease was tolerated without a live worker: ${OUT:0:300}"
fi

echo "== 160e. v14 gap 5: own bookkeeping does not stale STATE.md; structure does =="
setup
brief_now
# The lease vehicle exists and is ALREADY [>] before the document is written,
# so the later renewal changes no structure (state stays '>', only until/upd
# move), which is exactly the bookkeeping-only shape this gap is about.
FID=$(reqcli --add deadbeef "lease vehicle" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$FID" +60 worker:bw9 "watching the long job" >/dev/null
BG='[{"id":"bw9","type":"shell","status":"running","description":"the long job"}]'
hand_now
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
age_state deadbeef 20
reqcli --lease deadbeef "$FID" +90 worker:bw9 "renewing the watch lease" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if ! grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "160e: an aged STATE.md survives a same-session lease renewal"
else
    fail "160e: own bookkeeping staled the document: ${OUT:0:300}"
fi
# CONTROL: a STRUCTURAL move (new open item) stales the aged document.
reqcli --add deadbeef "genuinely new work" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "160e CONTROL: a structural move stales the aged document"
else
    fail "160e CONTROL: structure moved and staleness never fired: ${OUT:0:300}"
fi

echo "== 160f. v14 gap 6: an unchanged world accepts the banked Remaining report =="
setup
brief_now
hand_now
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
newturn
say "bookkeeping-only turn, nothing moved since the last report"
OUT="$(run)"
if ! grep -qF "no '## Remaining' section" <<<"$OUT"; then
    pass "160f: the banked report stands on an unchanged world"
else
    fail "160f: an unchanged world still demanded a restatement: ${OUT:0:300}"
fi
# CONTROL: the world moves (new open item) and the demand returns.
reqcli --add deadbeef "new work invalidates the bank" >/dev/null
newturn
say "another turn without a remaining section"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "no '## Remaining' section" <<<"$OUT"; then
    pass "160f CONTROL: a moved world demands a fresh report"
else
    fail "160f CONTROL: the bank outlived the world it described: ${OUT:0:300}"
fi
