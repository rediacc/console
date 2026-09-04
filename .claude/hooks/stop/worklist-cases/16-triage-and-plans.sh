#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The --triage verb (refusals, degradation, judge path), the plan-file demand, plan listing, and the allow-report diet.

echo "== 164. --triage refuses an empty finding and appends NO event =="
setup
OUT=$(triage off deadbeef 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "usage:" <<<"$OUT"; then
    pass "--triage with no finding at all exits non-zero with the usage"
else
    fail "empty --triage was accepted (rc=$RC): ${OUT:0:200}"
fi
OUT=$(triage off deadbeef "   " 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "empty finding triages nothing" <<<"$OUT"; then
    pass "--triage with blank finding text is refused, naming why"
else
    fail "blank-text --triage was accepted (rc=$RC): ${OUT:0:200}"
fi
if [[ -z "$(wl_events)" ]]; then
    pass "both refusals appended NO event (a rejected write is not a delivered one)"
else
    fail "a refused triage still wrote an event: $(wl_events | head -c 200)"
fi
# CONTROL: the same verb WITH a finding does append, so the assertion above
# could have failed. Without this the no-event check passes on a dead verb.
triage off deadbeef "the retry loop swallows the exit code" >/dev/null 2>&1
if [[ -n "$(wl_events)" ]] && grep -q '"ev":"add"' <(wl_events); then
    pass "164 CONTROL: a real finding DOES append an add event"
else
    fail "164 CONTROL: the verb appends nothing at all: $(wl_events | head -c 200)"
fi

echo "== 165. --triage degrades to a self-assessment and claims NO verdict =="
setup
OUT=$(triage off deadbeef "the fork path copies .env into the child repo" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "INLINE" <<<"$OUT" && grep -qF "PLAN+SUBAGENT" <<<"$OUT" &&
    grep -qF "OPERATOR-ONLY" <<<"$OUT" && grep -qF "agent/PLAN-<slug>.md" <<<"$OUT"; then
    pass "a judge-off triage hands back all three recipes and exits 0"
else
    fail "degraded triage wrong (rc=$RC): ${OUT:0:300}"
fi
if grep -q '"ev":"add"' <(wl_events); then
    pass "the finding is TRACKED even when no verdict could be produced"
else
    fail "the degraded triage tracked nothing: $(wl_events | head -c 200)"
fi
if ! grep -q '"ev":"triage"' <(wl_events); then
    pass "165 CONTROL: degraded mode records NO triage event, so the machinery never claims a verdict it did not produce"
else
    fail "degraded mode recorded a verdict: $(grep '"ev":"triage"' <(wl_events))"
fi

echo "== 166. --triage --id refuses another session's item =="
setup
NID=$(as_peer other123 reqcli --add other123 "their finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(triage off deadbeef --id "$NID" "my take on their finding" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "is owned by other123" <<<"$OUT"; then
    pass "triaging another session's item is refused by owner"
else
    fail "cross-session triage was accepted (rc=$RC): ${OUT:0:200}"
fi
if ! grep -q '"ev":"triage"' <(wl_events); then
    pass "166 CONTROL: the refused triage recorded nothing"
else
    fail "a refused triage still recorded a verdict: $(grep '"ev":"triage"' <(wl_events))"
fi
# The same item, triaged by its OWNER, reaches the degraded printout: the
# refusal is about ownership and not about --id being broken.
OUT=$(as_peer other123 triage off other123 --id "$NID" "their own finding" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "TRIAGE, SELF-ASSESSED (#$NID)" <<<"$OUT"; then
    pass "166 CONTROL: the OWNER triages the same item fine"
else
    fail "166 CONTROL: --id is broken for the owner too: ${OUT:0:200}"
fi

echo "== 167. --triage judge path: verdict, recipe, recorded event, ONE call =="
setup
: >"$BASE/judgecalls"
shim_judge_out '{"verdict":"plan-subagent","reason":"multi-file","plan_slug":"fix-x"}'
OUT=$(triage on deadbeef "renet forks inherit the parent buildkit session" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "PLAN+SUBAGENT" <<<"$OUT" &&
    grep -qF "agent/PLAN-fix-x.md" <<<"$OUT"; then
    pass "a plan-subagent verdict prints the prefilled plan path and the recipe"
else
    fail "plan-subagent recipe wrong (rc=$RC): ${OUT:0:300}"
fi
if grep -q '"ev":"triage"' <(wl_events) && grep -qF '"v":"plan-subagent"' <(wl_events) &&
    grep -qF '"plan":"agent/PLAN-fix-x.md"' <(wl_events); then
    pass "the verdict is RECORDED with its plan path"
else
    fail "triage event missing or wrong: $(wl_events | tail -c 300)"
fi
if [[ "$(wc -l <"$BASE/judgecalls")" -eq 1 ]]; then
    pass "the judge was called exactly once (no retry loop, no double spend)"
else
    fail "judge called $(wc -l <"$BASE/judgecalls") times"
fi
# CONTROL: one different verdict from the same shim takes the other branch.
setup
: >"$BASE/judgecalls"
shim_judge_out '{"verdict":"inline","reason":"one line and one check","plan_slug":""}'
OUT=$(triage on deadbeef "the error message names the wrong flag" 2>&1)
TID=$(sed -n 's/^triaging #\([0-9a-f]*\).*/\1/p' <<<"$OUT")
if grep -qF "TRIAGE VERDICT: INLINE" <<<"$OUT" && grep -qF -- "--tick deadbeef $TID" <<<"$OUT" &&
    grep -qF '"v":"inline"' <(wl_events) && ! grep -qF '"plan":' <(wl_events); then
    pass "167 CONTROL: an inline verdict orders the fix now and records no plan"
else
    fail "167 CONTROL: inline branch wrong: ${OUT:0:300}"
fi

EVENTS="${WL%.md}.events.jsonl"  # write target only; reads go through wl_events
echo "== 168. a TRIAGED BIG item with no plan file on disk is demanded =="
setup
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"deadbee1","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"forks leak the parent secrets"}\n' \
    "$NOW" >>"$EVENTS"
printf '{"ev":"triage","id":"deadbee1","at":"%s","by":"deadbeef","v":"plan-subagent","reason":"multi-file","plan":"agent/PLAN-big.md"}\n' \
    "$NOW" >>"$EVENTS"
OUT=$(reqcli --list --open deadbeef 2>&1)
if grep -qF "TRIAGED BIG, plan file missing: agent/PLAN-big.md" <<<"$OUT" &&
    grep -qF -- "--triage deadbeef --id deadbee1" <<<"$OUT"; then
    pass "a big finding whose design was never written is demanded, with both exits"
else
    fail "the plan follow-through never fired: ${OUT:0:300}"
fi
mkdir -p "$BASE/proj/agent"
printf '# PLAN: big\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n' \
    >"$BASE/proj/agent/PLAN-big.md"
OUT=$(reqcli --list --open deadbeef 2>&1)
if ! grep -qF "TRIAGED BIG" <<<"$OUT" &&
    grep -qF "plan: agent/PLAN-big.md" <<<"$OUT"; then
    pass "168 CONTROL: writing the plan silences the demand and advertises the path"
else
    fail "168 CONTROL: the probe does not read the disk: ${OUT:0:300}"
fi

echo "== 169. --tick refuses evidence that is ONLY an issue reference =="
setup
reg_repo
SHA=$(cd "$BASE/proj" && git rev-parse HEAD)
NID=$(reqcli --add deadbeef "the retry loop swallows the exit code" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --tick deadbeef "$NID" "filed as https://github.com/x/y/issues/560" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "door:operator-only" <<<"$OUT" &&
    grep -qF "door:operator-deferred" <<<"$OUT" && grep -qF "door:no-write-access" <<<"$OUT"; then
    pass "a bare issue URL cannot close a finding, and the refusal names all three doors"
else
    fail "the bare-issue tick was accepted (rc=$RC): ${OUT:0:300}"
fi
if ! grep -q '"ev":"state"' <(wl_events); then
    pass "the refused tick wrote NO state event"
else
    fail "a refused tick still closed the item: $(grep '"ev":"state"' <(wl_events))"
fi
OUT=$(reqcli --tick deadbeef "$NID" "filed as https://github.com/x/y/issues/560 door:no-write-access, that repo is not writable here" 2>&1)
if [[ $? -eq 0 ]] && grep -q '"ev":"state"' <(wl_events); then
    pass "the SAME evidence naming its door is accepted (the door is the exit)"
else
    fail "a door-carrying tick was refused: ${OUT:0:300}"
fi
# REGRESSION CONTROLS: the gate is narrow. Ordinary evidence still ticks, and
# a URL that is not an issue reference must keep working, because the gate
# rides on the URL shape completion_evidence already accepts.
N2=$(reqcli --add deadbeef "second finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT=$(reqcli --tick deadbeef "$N2" "ran the suite, exit 0" 2>&1)
RC=$?
N3=$(reqcli --add deadbeef "third finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT2=$(reqcli --tick deadbeef "$N3" "green on https://github.com/rediacc/console/actions/runs/123456789" 2>&1)
RC2=$?
N4=$(reqcli --add deadbeef "fourth finding" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
OUT3=$(reqcli --tick deadbeef "$N4" "fixed in $SHA" 2>&1)
RC3=$?
if [[ "$RC" -eq 0 && "$RC2" -eq 0 && "$RC3" -eq 0 ]]; then
    pass "169 CONTROLS: exit-code, run-URL and verified-sha ticks all still pass"
else
    fail "169 CONTROLS: the door gate is too wide (rc=$RC/$RC2/$RC3): ${OUT:0:100} | ${OUT2:0:100} | ${OUT3:0:100}"
fi

echo "== 170. SessionStart lists non-done plans, with NO design-docs dir =="
setup
mkdir -p "$BASE/proj/agent"
printf '# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/agent/PLAN-a.md"
printf '# PLAN: b\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/agent/PLAN-b.md"
printf '# PLAN: c\nOwner: t\nUpdated: 2026-07-31\n\nbody\n' \
    >"$BASE/proj/agent/PLAN-c.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "agent/PLAN-a.md [draft]" <<<"$out" &&
    ! grep -qF "PLAN-b.md" <<<"$out" && grep -qF "1 done or superseded plan(s)" <<<"$out"; then
    pass "draft plans are listed, executed ones collapse to a count"
else
    fail "the plans listing is wrong: ${out:0:400}"
fi
if grep -qF "agent/PLAN-c.md [UNKNOWN]" <<<"$out"; then
    pass "a plan with no readable Status line surfaces LOUDLY as [UNKNOWN]"
else
    fail "an unparseable Status was hidden: ${out:0:400}"
fi
# THE CONTROL ON THE RESTRUCTURE: docs/ci-overhaul does not exist in this
# fixture, and the old code RETURNED EARLY on that, which would have eaten
# the plans block entirely. The design-docs prose must be absent and the
# plans block present in the SAME output.
if ! grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "READ EVERY NON-DONE PLAN" <<<"$out"; then
    pass "170 CONTROL: a missing design-docs dir no longer eats the plans block"
else
    fail "170 CONTROL: the two blocks are still coupled: ${out:0:400}"
fi
# And the reverse: with NEITHER, SessionStart stays silent as it always did.
# The plans left docs/ when the tree moved, so removing docs/ alone no longer
# removes them -- and this control would then fail for the right reason.
rm -rf "$BASE/proj/docs"
rm -f "$BASE/proj/agent"/PLAN-*.md
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --session-start 2>/dev/null)"
if [[ -z "$out" ]]; then
    pass "170 CONTROL: no docs and no plans stays silent, as before"
else
    fail "170 CONTROL: SessionStart now talks about nothing: ${out:0:200}"
fi

echo "== 171. PostCompact hands back the executing plan's ## Status cursor =="
setup
hand_now
mkdir -p "$BASE/proj/agent"
printf '# PLAN: exec\nStatus: executing\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\nMARKER_EXEC_CURSOR wave two landed, wave three is next.\n\n## Detail\n\nnot the cursor\n' \
    >"$BASE/proj/agent/PLAN-exec.md"
printf '# PLAN: old\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\nMARKER_DONE_PLAN must never be handed back.\n' \
    >"$BASE/proj/agent/PLAN-old.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "MARKER_EXEC_CURSOR" <<<"$out" && grep -qF "PLAN-exec.md [executing]" <<<"$out" &&
    grep -qF "picking up an in-progress session" <<<"$out"; then
    pass "the compacted session gets the plan listing AND the executing plan's cursor"
else
    fail "PostCompact plan excerpt missing: ${out:0:400}"
fi
if ! grep -qF "MARKER_DONE_PLAN" <<<"$out" && ! grep -qF "not the cursor" <<<"$out"; then
    pass "171 CONTROL: a done plan is not handed back, and only the Status section is"
else
    fail "171 CONTROL: the excerpt is unbounded: ${out:0:400}"
fi

echo "== 172. allow-report diet: guide is the single source, advisories latch =="
# Operator, 2026-07-31: "Why I see such a big output? We already had round
# robin." The allow report's in-flight section duplicated the guide's own
# [>] rows, and week-stable advisories (other sessions' briefs) repeated on
# every full stop. Now the guide says it once, and slow-moving sections
# re-show only on content change or after the refresh window.
setup
# The default two-cron shape also produces a poll-backoff tip, which is
# another class-2 section and would take the single per-stop slot. The latch
# is what this case is about, so it drains wide and cases 173 to 177 own the
# per-stop rationing.
export WORKLIST_REPORT_PER_STOP=9
brief_now
hand_now
IID=$(reqcli --add deadbeef "carry the CI watch to green" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --lease deadbeef "$IID" +60 worker:bw7 "watching the run" >/dev/null
BG='[{"id":"bw7","type":"shell","status":"running","description":"the watch"}]'
printf '%s %s %s\n' "cafebabe" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "building the fixture" >>"${WL%.md}.sessions"
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if grep -qF -- "- [>] #$IID" <<<"$OUT" && ! grep -qF "in flight on background work" <<<"$OUT"; then
    pass "172: the guide carries the lease once; the duplicate section is gone"
else
    fail "172: duplication or missing guide row: ${OUT:0:400}"
fi
if grep -qF "Other sessions in this worktree" <<<"$OUT"; then
    pass "172: a fresh other-session brief appears on first sight"
else
    fail "172: first sight of the other session was hidden: ${OUT:0:400}"
fi
newturn
reqcli --update deadbeef "$IID" "still watching, run pending" >/dev/null
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if ! grep -qF "Other sessions in this worktree" <<<"$OUT"; then
    pass "172: an unchanged advisory stays quiet on the next stop"
else
    fail "172: the advisory repeated with unchanged content: ${OUT:0:400}"
fi
# CONTROL: changed content re-shows immediately, so the latch is a dedupe,
# not a mute.
printf '%s %s %s\n' "cafebabe" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "pivoted to the deploy fix" >>"${WL%.md}.sessions"
newturn
reqcli --update deadbeef "$IID" "watch still healthy" >/dev/null
say "watching.

## Remaining
- #$IID carry the CI watch to green (in flight)"
OUT="$(run)"
if grep -qF "Other sessions in this worktree" <<<"$OUT" && grep -qF "pivoted to the deploy fix" <<<"$OUT"; then
    pass "172 CONTROL: changed advisory content re-shows immediately"
else
    fail "172 CONTROL: the latch muted a real change: ${OUT:0:400}"
fi
BG='[]'
unset WORKLIST_REPORT_PER_STOP

echo "== 173. one report section per stop; the rest queue and SAY SO =="
