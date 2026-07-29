#!/bin/bash
# Controls for worklist.py v5. Every check must FIRE on a planted defect and
# stay silent when clean. Nothing here touches the live worklist: TMPDIR,
# WORKLIST_TASKS_DIR and the project root are all isolated fixtures.
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worklist.py"
BASE="$(mktemp -d)/hookfix"
trap 'rm -rf "$(dirname "$BASE")"' EXIT
SID="deadbeef-1111-2222-3333-444444444444"
PASS=0
FAIL=0

setup() {
    rm -rf "$BASE"
    mkdir -p "$BASE/proj/.git" "$BASE/tmp/claude-worklist" "$BASE/tasks/session-deadbeef"
    WL="$BASE/tmp/claude-worklist/$(echo "$BASE/proj" | sed 's|[^A-Za-z0-9._-]|_|g' | sed 's/^_//').md"
    : >"$WL"
    printf '%s\n' '{"type":"user","message":{"content":"go"}}' >"$BASE/t.jsonl"
    mkdir -p "$BASE/binonly" "$BASE/nohome"
    for b in python3 sh bash cat date; do ln -sf "$(command -v $b)" "$BASE/binonly/$b" 2>/dev/null; done
}

# say <text-of-last-assistant-message>
say() {
    python3 -c '
import json,sys
rec={"type":"assistant","message":{"content":[{"type":"text","text":sys.argv[1]}]}}
open(sys.argv[2],"a").write(json.dumps(rec)+"\n")
' "$1" "$BASE/t.jsonl"
}

task() { # task <id> <status> <subject>
    printf '{"id":"%s","status":"%s","subject":"%s"}\n' "$1" "$2" "$3" >"$BASE/tasks/session-deadbeef/$1.json"
}

hand_now() { # a handover fresh enough and long enough to satisfy the gate
    printf 'Resume point: round 23 diagnosis.\nStatus: two Quality jobs red on a dead-shell finding, fixed by wiring the stop suite into test-hooks.sh.\nNext: push and watch. Do not report the autopilot App as blocked, it exists.\n' |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
}

brief_now() {
    printf '%s %s %s\n' "deadbeef" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "doing the thing" >>"${WL%.md}.sessions"
}

run() { # feed the hook a Stop event and print its raw JSON verdict
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_JUDGE="${JUDGE_MODE:-off}" python3 "$HOOK" 2>"$BASE/err.txt"
}

check() { # check <label> <expect-decision> <must-contain>
    local label="$1" want="$2" needle="$3" out
    out="$(run)"
    local got
    got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
    if [[ "$got" == "$want" ]] && grep -qF "$needle" <<<"$out"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (want=$want got=$got, needle '$needle' $(grep -qF "$needle" <<<"$out" && echo present || echo MISSING))"
        echo "        out: ${out:0:220}"
        [[ -s "$BASE/err.txt" ]] && echo "        err: $(head -c 200 "$BASE/err.txt")"
        FAIL=$((FAIL + 1))
    fi
}

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
check "a deferral WITH DEFAULT: does not block" allow "deferred rather than done"

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
| #7 | merge the chain | you |"
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

echo "== 9. ONE block lists EVERY violation =="
setup
say "nothing"
echo '- [ ] (deadbeef) open thing' >>"$WL"
echo '- [?] (deadbeef) undefaulted q' >>"$WL"
out="$(run)"
n=$(grep -o "check(s) failed" <<<"$out" | wc -l)
v=$(python3 -c 'import json,sys;d=json.loads(sys.stdin.read());print(d["reason"].count("\n\n  "))' <<<"$out" 2>/dev/null)
if [[ "$n" -ge 1 && "${v:-0}" -ge 3 ]]; then
    echo "  PASS: one block carries all 3+ violations (found $v)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected >=3 violations in one block, got ${v:-0}"
    FAIL=$((FAIL + 1))
fi

echo "== 10. recursion guard =="
setup
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        STOPHOOK_CHILD=1 python3 "$HOOK" 2>&1)"
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
- #7 merge the chain"
brief_now
hand_now
task 7 pending "merge the chain"
JUDGE_MODE=on
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        PATH="$BASE/binonly" HOME="$BASE/nohome" python3 "$HOOK" 2>"$BASE/err.txt")"
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

loop_at() { # loop_at <offset-minutes> <cron-count>
    printf '%s %s %s %s\n' deadbeef "$(date -u -d "$1 minutes" +%Y-%m-%dT%H:%M:%SZ)" "$2" "hourly loop" \
        >>"${WL%.md}.loop"
}

echo "== 13. an OVERDUE declared loop blocks (the loop died and nobody restarted it) =="
setup
say "answer

## Remaining
- #7 thing"
brief_now
hand_now
task 7 pending "thing"
loop_at -30 1
check "an overdue loop declaration blocks" block "loop is OVERDUE"

echo "== 14. a FUTURE loop declaration does not block =="
setup
say "answer

## Remaining
- #7 thing"
brief_now
hand_now
task 7 pending "thing"
loop_at +30 1
check "a future loop declaration is fine" allow ""

echo "== 15. MORE THAN ONE cron blocks (one is almost always enough) =="
setup
say "answer

## Remaining
- #7 thing"
brief_now
hand_now
task 7 pending "thing"
loop_at +30 2
check "two declared crons block" block "declared 2 crons"

echo "== 16. a Remaining section that OMITS an open task blocks =="
setup
say "answer

## Remaining
| #7 | thing | me |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "an omitted task id blocks" block "OUT OF SYNC"

echo "== 17. naming every open task passes =="
setup
say "answer

## Remaining
| #7 | thing | me |
| #8 | the forgotten one | you |"
brief_now
hand_now
task 7 pending "thing"
task 8 pending "the forgotten one"
check "all task ids named is fine" allow ""

echo "== 18. a MISSING handover blocks when work remains =="
setup
say "answer

## Remaining
- #7 thing"
brief_now
task 7 pending "thing"
check "a missing compact-handover blocks" block "handover is missing"

echo "== 19. a THIN handover blocks (a stub is not a handover) =="
setup
say "answer

## Remaining
- #7 thing"
brief_now
task 7 pending "thing"
printf 'wip\n' | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
check "a too-short handover blocks" block "handover is thin"

echo "== 20. PostCompact hands the document back as additionalContext =="
setup
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "CONTEXT WAS JUST COMPACTED" <<<"$out" && grep -qF "Resume point" <<<"$out"; then
    echo "  PASS: PostCompact returns the handover body as additionalContext"
    PASS=$((PASS + 1))
else
    echo "  FAIL: PostCompact did not return the handover: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 21. PostCompact with NO handover still tells the session what to do =="
setup
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "NO handover document" <<<"$out"; then
    echo "  PASS: a missing handover after compaction is reported, not silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: missing-handover PostCompact was silent: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 22. an UNREADABLE transcript blames the HOOK, not the session =="
setup
brief_now
hand_now
task 7 pending "thing"
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/does-not-exist.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_JUDGE=off python3 "$HOOK" 2>/dev/null)"
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
- #7 thing"
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
| #7 | thing | me |"
say "Checking one more thing."
say "And another."
check "a Remaining section survives later narration blocks" allow ""

echo
echo "  passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]
