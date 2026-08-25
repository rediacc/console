#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The base battery: open items, [?] deferrals, session briefs, ## Remaining, PostCompact handback, cron shape, STATE.md size and aim.

echo "== 1. open [ ] blocks =="
setup
say "done for now"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
check "an open [ ] item blocks" block "OPEN worklist item"

echo "== 2. [?] without DEFAULT blocks =="
setup
say "here is my answer

## Remaining
nothing"
brief_now
hand_now
echo '- [?] (deadbeef) should we do X' >>"$WL"
check "a deferral with no DEFAULT: blocks" block "no DEFAULT:"

echo "== 3. [?] WITH DEFAULT passes that check =="
setup
say "answer

## Remaining
- the X decision"
brief_now
hand_now
echo '- [?] (deadbeef) should we do X DEFAULT: do X on Monday' >>"$WL"
check "a deferral WITH DEFAULT: does not block" allow "operator may answer"

echo "== 4. missing session brief blocks =="
setup
say "answer

## Remaining
- stuff"
echo '- [?] (deadbeef) q DEFAULT: d' >>"$WL"
check "a missing brief blocks" block "session brief is missing"

echo "== 5. STALE brief blocks =="
setup
say "answer

## Remaining
- stuff"
echo '- [?] (deadbeef) q DEFAULT: d' >>"$WL"
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "old" >>"${WL%.md}.sessions"
check "a stale brief blocks" block "session brief is stale"

echo "== 6. THE HEADLINE: a pending TASK with no ## Remaining blocks =="
setup
say "All done, nothing to report."
brief_now
hand_now
task 7 pending "merge the chain"
check "pending task + no ## Remaining blocks" block "no '## Remaining' section"

echo "== 7. same pending task WITH ## Remaining passes =="
setup
say "Here is the answer.

## Remaining
| #7 | merge the chain | pending, you |"
brief_now
hand_now
task 7 pending "merge the chain"
check "pending task + ## Remaining allowed (judge off)" allow ""

echo "== 8. completed tasks are not remaining work =="
setup
say "All done."
brief_now
hand_now
task 7 completed "merge the chain"
check "a completed task does not demand a Remaining section" allow ""

echo "== 9. WORKLIST_FOCUS=off: ONE block lists EVERY violation =="
# v13 made the FOCUSED single-check block the default; the dump-all contract
# survives behind WORKLIST_FOCUS=off and this case keeps that path exercised.
setup
say "nothing"
echo '- [ ] (deadbeef) open thing' >>"$WL"
echo '- [?] (deadbeef) undefaulted q' >>"$WL"
export WORKLIST_FOCUS=off
out="$(run)"
unset WORKLIST_FOCUS
n=$(grep -o "check(s) failed" <<<"$out" | wc -l)
v=$(python3 -c 'import json,sys;d=json.loads(sys.stdin.read());print(d["reason"].count("\n\n  "))' <<<"$out" 2>/dev/null)
if [[ "$n" -ge 1 && "${v:-0}" -ge 3 ]]; then
    echo "  PASS: one block carries all 3+ violations (found $v)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected >=3 violations in one block, got ${v:-0}"
    FAIL=$((FAIL + 1))
fi

# GITHUB_ACTIONS is pinned below for a reason specific to THIS case: it asserts
# EMPTY output, and the hook's CI no-op also produces empty output. Inheriting a
# true value in Actions would make this pass whether or not the recursion guard
# exists at all -- the assertion and the leak are indistinguishable. An
# empty-output test is the one shape where a silent no-op reads as success.
echo "== 10. recursion guard =="
setup
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        GITHUB_ACTIONS="${GHA:-}" STOPHOOK_CHILD=1 python3 "$HOOK" 2>&1)"
if [[ -z "$out" ]]; then
    echo "  PASS: STOPHOOK_CHILD=1 exits silently (no recursion)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: guard produced output: ${out:0:120}"
    FAIL=$((FAIL + 1))
fi

echo "== 11. judge failure FAILS CLOSED (no escape hatch) =="
setup
say "waiting on CI.

## Remaining
- #7 merge the chain (pending)"
brief_now
hand_now
task 7 pending "merge the chain"
JUDGE_MODE=on
# A live cron in the event, else the v8 idle check fires statically and the
# stop never reaches the judge path this case exists to pin.
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        PATH="$BASE/binonly" HOME="$BASE/nohome" GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>"$BASE/err.txt")"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "block" ]] && grep -qF "no-escape-hatch" <<<"$out"; then
    echo "  PASS: an unreachable judge BLOCKS rather than waving the stop through"
    PASS=$((PASS + 1))
else
    echo "  FAIL: judge failure did not block (got=$got): ${out:0:200}"
    FAIL=$((FAIL + 1))
fi
JUDGE_MODE=off

echo "== 12. nothing tracked anywhere = clean stop, no judge, no block =="
setup
say "All finished."
brief_now
hand_now
check "an empty world allows the stop" allow ""

echo "== 16. a Remaining section that OMITS an open task blocks =="
setup
say "answer

## Remaining
| #7 | thing | pending, me |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "an omitted task id blocks" block "OUT OF SYNC"

echo "== 17. naming every open task passes =="
setup
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | the forgotten one | pending, you |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "all task ids named is fine" allow ""

echo "== 18. a MISSING STATE.md blocks when work remains =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
check "a missing STATE.md blocks" block "STATE.md is missing"

echo "== 19. a THIN STATE.md blocks (a stub is not a recovery document) =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
plant_state 'wip'
check "a too-short STATE.md blocks" block "STATE.md is thin"
# 1.4 CONTROL: a SHAPE verdict must carry no age at all. `thin` is about the
# body, and printing a staleness limit beside it suggests that waiting or
# re-stamping would help. Without this control the change above could have
# simply appended a phrase everywhere and still read as wall-clock.
OUT="$(run)"
if ! grep -qE "min old" <<<"$OUT"; then
    pass "212b CONTROL: a thin STATE.md carries no age, because age is irrelevant to shape"
else
    fail "212b CONTROL: a shape verdict printed an age: ${OUT:0:300}"
fi

echo "== 20. PostCompact hands back STATE.md, RULES.md AND the trap titles =="
setup
hand_now
printf 'settled fact: the reconciler exists, never rebuild it\n' >"$BASE/proj/agent/deadbeef/RULES.md"
mkdir -p "$BASE/proj/docs/agent-reference"
printf '# Traps\n\n## The review tooling comes from main\n\nbody detail here\n' >"$BASE/proj/docs/agent-reference/TRAPS.md"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" && grep -qF "ci-overhaul session" <<<"$out" &&
    grep -qF "settled fact: the reconciler exists" <<<"$out" &&
    grep -qF "The review tooling comes from main" <<<"$out" &&
    ! grep -qF "body detail here" <<<"$out"; then
    echo "  PASS: PostCompact returns STATE + RULES + trap TITLES (never trap bodies)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: PostCompact briefing incomplete or carries trap bodies: ${out:0:300}"
    FAIL=$((FAIL + 1))
fi

echo "== 21. PostCompact with NO STATE.md still tells the session what to do =="
setup
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "NO STATE.md" <<<"$out"; then
    echo "  PASS: a missing STATE.md after compaction is reported, not silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: missing-STATE.md PostCompact was silent: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 21b. PostCompact puts MY section first and LABELS the peer's =="
# A compacted session reads top-down, and the block it must act on is its own.
# The peer's section rides along because this checkout runs several sessions at
# once and a peer's section is the only place the reader learns which
# uncommitted files are not theirs to sweep -- but it must be unmistakably
# marked as not theirs to rewrite, or the briefing itself becomes the next
# clobber's instruction.
setup
hand_now
PEER_BODY='Session cafe1234 owns packages/cli/src/services/licensing and the two drill scripts under scripts/dev, all of them uncommitted. A git add -A from any other session in this checkout would sweep them into somebody else s commit, which is the cross-session fact that has no home in a per-session file.

## Next action
Finish the renewal drill and report the soft-claim slot count.'
state_as cafe1234 "$PEER_BODY"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
OWN_AT="$(python3 -c "import sys; print(sys.stdin.read().find('ci-overhaul session'))" <<<"$out")"
PEER_AT="$(python3 -c "import sys; print(sys.stdin.read().find('SESSION cafe1234'))" <<<"$out")"
if [[ "$OWN_AT" -ge 0 && "$PEER_AT" -gt "$OWN_AT" ]] &&
    grep -qF "NOT YOURS" <<<"$out" && grep -qF "owns packages/cli" <<<"$out"; then
    pass "21b: own section first, peer's after it and labelled NOT YOURS"
else
    fail "21b: ordering/labelling wrong (own@$OWN_AT peer@$PEER_AT): ${out:0:300}"
fi
# CONTROL: with no peer section there is no peers block at all, so the label is
# information about the file rather than boilerplate on every briefing.
setup
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "ci-overhaul session" <<<"$out" && ! grep -qF "OTHER SESSIONS'" <<<"$out"; then
    pass "21b CONTROL: a solo document produces no peers block"
else
    fail "21b CONTROL: a peers block appeared with no peers: ${out:0:300}"
fi

echo "== 20b. PostCompact with NO section of MY OWN still hands back the peer's =="
# Before sections, this path returned NO state content whatsoever: a compacted
# session on a branch where only a peer had written was told to reconstruct
# from what survived, while the peer's section sat unread in the file in front
# of it. The instruction to write one must survive too, or this becomes a way
# to inherit a peer's document as your own.
setup
state_as cafe1234 "$PEER_BODY"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "NO STATE.md" <<<"$out" && grep -qF "owns packages/cli" <<<"$out" &&
    grep -qF "NOT YOURS" <<<"$out"; then
    pass "20b: the own-missing instruction AND the peer's body are both returned"
else
    fail "20b: the missing branch dropped the peer's section: ${out:0:300}"
fi

echo "== 22. an UNREADABLE transcript blames the HOOK, not the session =="
setup
brief_now
hand_now
task 7 pending "thing"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/does-not-exist.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "THIS IS A HOOK BUG" <<<"$out" && grep -qF '"decision": "block"' <<<"$out"; then
    echo "  PASS: a blind read blocks AND says it is the hook's fault"
    PASS=$((PASS + 1))
else
    echo "  FAIL: blind read not distinguished: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 23. a heading that lands LATE is still honoured (flush race) =="
setup
brief_now
hand_now
task 7 pending "thing"
say "answer with no section yet"
(
    sleep 0.6
    say "answer

## Remaining
- #7 thing (pending)"
) &
check "a heading written mid-check is picked up by the retry" allow ""
wait

echo "== 24. THE REGRESSION: narration blocks after the answer must not hide it =="
# Every narration line before a tool call is its own assistant text block, so
# reading only the LAST block sees a one-liner and calls the section missing.
# This fired on a real message that did carry its heading.
setup
brief_now
hand_now
task 7 pending "thing"
say "Here is the answer.

## Remaining
| #7 | thing | pending, me |"
say "Checking one more thing."
say "And another."
check "a Remaining section survives later narration blocks" allow ""

echo "== 25. TWO LIVE work crons block, read from the event not a declaration =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"aaa","schedule":"*/23 * * * *"},{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "two live work crons block" block "2 work crons are live"
CRONS='[]'

echo "== 26. the canonical shape (one work cron + the poll) does not block =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "work cron + poll cron is fine" allow ""
CRONS='[]'

echo "== 27. 'blocked on You' WITHOUT confirmation blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, You |"
task 7 pending "thing"
check "an unconfirmed operator-block is rejected" block "WITHOUT their confirmation"

echo "== 28. the confirmed form passes =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, You (User Thinks So) |"
task 7 pending "thing"
check "the confirmed operator-block is accepted" allow ""

echo "== 29. a BLOATED STATE.md is rejected (it is a prompt, not a report) =="
# agent-notes split: the cap moved 1500 -> 4000. Rules and traps left the budget,
# so STATE.md needs room for state alone; 4000 still refuses a pasted
# transcript. The boundary pair pins the new edge, and both bodies carry the
# '## Next action' section so length is the ONLY variable under test.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
plant_state "$(python3 -c "print('## Next action\\ngo\\n' + 'x'*4100)")"
check "an over-long STATE.md blocks" block "STATE.md is bloated"
plant_state "$(python3 -c "print('## Next action\\ngo\\n' + 'x'*3900)")"
check "3900-odd chars sits inside the new 4000 budget" allow ""

echo "== 30. AIMLESS: a STATE.md without a Next action section blocks =="
# The paragraph guard is DELETED: it was an explicit proxy for the old
# 600-char cap and split("\n\n") counted every markdown heading as a
# paragraph, which is why the old message had to forbid headings outright.
# `aimless` is the strictly better gate: presence of a next action IS the
# value, and padding cannot satisfy it. Three probes: FIRE without the
# section, SILENT with it, SILENT with unusual case (the regex is
# case-insensitive on purpose; a shouted heading is still a next action).
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
plant_state 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, where the immediate job is to watch the running CI round and diagnose any red from its complete failed-step log before changing anything at all. Padding padding padding padding to comfortably clear the thin floor of the shape gate.'
check "a STATE.md with no Next action section is aimless and blocks" block "STATE.md is aimless"
plant_state 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, where the immediate job is to watch the running CI round and diagnose any red from its complete failed-step log before changing anything at all.

## Next action

Diagnose the red from its complete failed-step log, then fix the gate it names.'
# The lead used to be "Watch the run and diagnose from the job logs API", which the
# v21 waitled rule now refuses. Reworded rather than exempted, and worth noting: this
# fixture predates the rule by months, so the wait-led habit it encodes was in the
# repo's own suite before any one session picked it up. The case still tests what it
# always tested, that a document WITH a Next action section is not aimless.
check "the same document WITH a Next action section is fine" allow ""
# Case-insensitivity probed as a UNIT assertion rather than a third stop:
# three consecutive stops on an unmoved world trip the stuck detector, which
# would make this case test the wrong gate.
if python3 -c "
import sys; sys.path.insert(0, '$(dirname "$HOOK")')
import wl_store as S
v, _ = S.agent_state_shape('x'*260 + chr(10) + '## NEXT ACTION' + chr(10) + 'go')
sys.exit(0 if v == 'ok' else 1)"; then
    pass "the Next action heading is matched case-insensitively"
else
    fail "a shouted '## NEXT ACTION' heading was not recognised"
fi

# ---- v21 WAITLED: '## Next action' may not LEAD with a wait -----------------
# The root cause of a wave spent watching CI while dozens of open items sat
# untouched. Every instrument was correctly silent: the no-op wake ladder needs
# a wake where NOTHING moved, and the session moved something every time. What
# carried the inversion across compaction was STATE.md itself, whose next action
# opened with "1. Watch <worker>", so the recovered session did CI first and
# then wrote the same instruction again.
# Both directions, because a rule that only ever fires is as useless as one that
# never does: the wait must be refused in the LEAD and allowed further down.
_shape() { python3 -c "
import sys; sys.path.insert(0, '$(dirname "$HOOK")')
import wl_store as S
print(S.agent_state_shape('x'*300 + chr(10)*2 + '## Next action' + chr(10)*2 + sys.argv[1])[0])" "$1"; }

for lead in \
    "1. Watch \`byvmf1xid\`; re-check with gh api." \
    "Wait for the run to finish, then review." \
    "- Watch CI run 32259770610" \
    "1) Monitor the watch, 2) resume" \
    "Keep watching the run." \
    "1. Re-arm the watch on the run." \
    "1. Await green, then review."; do
    if [ "$(_shape "$lead")" = "waitled" ]; then
        pass "waitled: refused a next action leading with '${lead:0:28}...'"
    else
        fail "waitled: a wait-led next action was ACCEPTED: $lead"
    fi
done

# CONTROLS. Each is a document that must still pass, so the rule cannot be
# satisfied by rejecting everything. The last two matter most: a substring match
# would reject both, and rejecting a correct document is how a check gets routed
# around rather than obeyed.
for ok_lead in \
    "1. Wire A4 into Navigation.tsx.\n2. Watch CI 322; on green, review." \
    "1. Finish #c84a8a4b, CI is watched by bg byvmf1xid." \
    "1. Read the watchdog classifier verdict and fix the gate." \
    "1. Document the wait semantics in RULES.md."; do
    if [ "$(_shape "$(printf '%b' "$ok_lead")")" = "ok" ]; then
        pass "waitled CONTROL: work-led next action still passes"
    else
        fail "waitled CONTROL: a legitimate next action was refused: $ok_lead"
    fi
done

# ---- v22 SOLO GRIND: a long queue worked alone gets asked ONCE --------------
# Advisory, never blocking. The controls that matter are the SILENT ones: it must
# not fire twice in an episode, must not fire while a teammate is live, and must
# re-arm only after the queue actually drains. A nag would be routed around.
if python3 -c "
import sys; sys.path.insert(0, '$(dirname "$HOOK")')
import wl_checks as C
d = {}
ok = C.solo_grind_due(39, 0, d) is True            # fires: long queue, working alone
ok = ok and C.solo_grind_due(39, 0, d) is False    # once per episode, not per stop
ok = ok and C.solo_grind_due(39, 2, d) is False    # silent once a teammate is live
ok = ok and C.solo_grind_due(3, 0, d) is False     # queue drained: episode ends
ok = ok and C.solo_grind_due(20, 0, d) is True     # and it re-arms when it climbs back
ok = ok and C.solo_grind_due(11, 0, {}) is False   # below the floor it never speaks
ok = ok and C.solo_grind_due(39, None, {}) is True  # a fact-gatherer that returns None
ok = ok and C.solo_grind_due(None, 0, {}) is False  # crashed the whole hook once
sys.exit(0 if ok else 1)"; then
    pass "solo-grind fires once per episode, stays silent with a teammate live"
else
    fail "solo-grind advisory logic is wrong"
fi
