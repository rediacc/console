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
    # Reset EVERY knob run() reads. A plain `BG=...` in one case leaked into the
    # next two and silently suppressed a check, which cost a debugging round.
    BG='[]'
    CRONS='[]'
    JUDGE_MODE=off
    # PINNED, NOT INHERITED. The hook no-ops when GITHUB_ACTIONS=true, so a suite
    # that inherits the ambient value passes locally and silently no-ops in CI,
    # where 30 cases came back with empty output and read as failures.
    GHA=''
    rm -rf "$BASE"
    mkdir -p "$BASE/proj/.git" "$BASE/tmp/claude-worklist" "$BASE/tasks/session-deadbeef"
    WL="$BASE/tmp/claude-worklist/$(echo "$BASE/proj" | sed 's|[^A-Za-z0-9._-]|_|g' | sed 's/^_//').md"
    : >"$WL"
    printf '%s\n' '{"type":"user","message":{"content":"go"}}' >"$BASE/t.jsonl"
    mkdir -p "$BASE/binonly" "$BASE/nohome"
    for b in python3 sh bash cat date; do ln -sf "$(command -v $b)" "$BASE/binonly/$b" 2>/dev/null; done
}

# say <text-of-last-assistant-message>
# Does NOT imply a turn boundary, and must not: case 24 depends on two say()
# calls landing in ONE turn, because multiple assistant text blocks per turn is
# exactly the shape that once hid a '## Remaining' section from this hook. Use
# the explicit newturn helper when a fixture wants a fresh window.
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
    printf 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite from test-hooks.sh. Next: push and watch the run, then bump the submodule pointers to the squash commits before the merge chain. The rediacc-autopilot App already exists and is validated, so never report it as blocked on the operator.\n' |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
}

brief_now() {
    printf '%s %s %s\n' "deadbeef" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "doing the thing" >>"${WL%.md}.sessions"
}

newturn() { # a fresh user record; transcript_tail only reads back to the last one
    printf '%s\n' '{"type":"user","message":{"content":"go"}}' >>"$BASE/t.jsonl"
}

reqcli() { # drive the request CLI against the fixture worklist
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" "$@"
}

askid() { # askid <from> <to> <text...> -> prints the new request id
    reqcli --ask "$@" | sed -n 's/.*#\([0-9a-f]\{8\}\).*/\1/p' | head -n1
}

brief_other() { # brief_other <prefix> -- a fresh brief for another live session
    printf '%s %s %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "other session" >>"${WL%.md}.sessions"
}

run() { # feed the hook a Stop event and print its raw JSON verdict
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":%s}' \
        "$SID" "$BASE/proj" "$BASE/t.jsonl" "${CRONS:-[]}" "${BG:-[]}" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
            WORKLIST_JUDGE="${JUDGE_MODE:-off}" GITHUB_ACTIONS="${GHA:-}" \
            python3 "$HOOK" 2>"$BASE/err.txt"
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
- #7 merge the chain (pending)"
brief_now
hand_now
task 7 pending "merge the chain"
JUDGE_MODE=on
out="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
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

echo "== 18. a MISSING handover blocks when work remains =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
check "a missing compact-handover blocks" block "handover is missing"

echo "== 19. a THIN handover blocks (a stub is not a handover) =="
setup
say "answer

## Remaining
- #7 thing (pending)"
brief_now
task 7 pending "thing"
printf 'wip\n' | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
check "a too-short handover blocks" block "handover is thin"

echo "== 20. PostCompact hands the document back as additionalContext =="
setup
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" && grep -qF "ci-overhaul session" <<<"$out"; then
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

echo "== 25. TWO LIVE crons block, read from the event not a declaration =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"aaa","schedule":"*/23 * * * *"},{"id":"bbb","schedule":"17 * * * *"}]'
check "two live crons block" block "2 crons are live"
CRONS='[]'

echo "== 26. ONE live cron does not block =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"}]'
check "one live cron is fine" allow ""
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

echo "== 29. a BLOATED handover is rejected (it is a prompt, not a report) =="
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
python3 -c "print('x'*900)" | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
check "an over-long handover blocks" block "handover is bloated"

echo "== 30. a MULTI-PARAGRAPH handover is rejected =="
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, where the immediate job is to watch the running CI round and diagnose any red from its complete failed-step log before changing anything at all.\n\nSecond paragraph, which is exactly what makes this handover invalid.\n' |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --handover deadbeef >/dev/null
check "a multi-paragraph handover blocks" block "handover is multi-paragraph"

echo "== 31. design-doc DRIFT blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
mkdir -p "$BASE/proj/docs/ci-overhaul"
echo "# design" >"$BASE/proj/docs/ci-overhaul/README.md"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    mkdir -p .ci
    git add -A >/dev/null 2>&1
    git commit -qm docs 2>/dev/null
    for i in $(seq 1 12); do
        echo "$i" >".ci/f$i.sh"
        git add -A >/dev/null 2>&1
        git commit -qm "code $i" 2>/dev/null
    done
) >/dev/null 2>&1
check "12 code commits with untouched docs block" block "design docs have DRIFTED"

echo "== 32. no drift once the docs move with the code =="
(
    cd "$BASE/proj" || exit
    echo "# updated" >>docs/ci-overhaul/README.md
    git add -A >/dev/null 2>&1
    git commit -qm "docs refresh" 2>/dev/null
) >/dev/null 2>&1
check "docs updated after the code clears the drift" allow ""

echo "== 33. SessionStart hands the design docs to a new session =="
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "docs/ci-overhaul/README.md" <<<"$out"; then
    echo "  PASS: SessionStart lists the docs and demands they be read"
    PASS=$((PASS + 1))
else
    echo "  FAIL: SessionStart did not surface the docs: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 34. a LOOP THAT DIED blocks (had crons, now none) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"}]'
run >/dev/null
CRONS='[]'
check "losing the last cron blocks" block "YOUR LOOP DIED"

echo "== 35. a session that NEVER had a cron is not nagged =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[]'
check "no cron ever means no complaint" allow ""

echo "== 36. a STALE LOCAL branch sharing the publish name blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    echo a >a.txt
    git add -A
    git commit -qm base
    git branch -f pub HEAD
    echo b >b.txt
    git add -A
    git commit -qm newer
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "is a trap for whoever checks it out" <<<"$out"; then
    echo "  PASS: a stale local branch sharing the publish name blocks"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale local branch not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 37. PR-freshness: a push after the last body edit blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    git remote add origin https://github.com/fake/repo.git 2>/dev/null
    echo a >a.txt
    git add -A
    git commit -qm base
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
# A gh shim that answers the GraphQL read with a body edited in 1970, i.e. long
# before any commit. The gate under test is the real one.
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"1970-01-01T00:00:00Z","updatedAt":"1970-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out"; then
    echo "  PASS: pushing after the body edit blocks before CI can waste a round"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale PR body not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 38. PR-freshness: a body edited AFTER the tip passes =="
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER" <<<"$out"; then
    echo "  FAIL: a fresh body must not block: ${out:0:200}"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: a body newer than the tip does not block"
    PASS=$((PASS + 1))
fi
rm -f "$BASE/binonly/gh"

echo "== 39. an item listed with NO state word blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | me |"
task 7 pending "thing"
check "a stateless remaining item blocks" block "listed without a STATE"

echo "== 40. saying 'ongoing' while the app says pending blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 pending "thing"
check "message and task list must agree" block "DISAGREES with the task list"

echo "== 41. 'ongoing' matches an in_progress task =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 in_progress "thing"
check "an in_progress task labelled ongoing is fine" allow ""

echo "== 42. a 'found, not fixed' list blocks: fix it or track it =="
setup
brief_now
hand_now
say "answer

Found, not fixed: CLAUDE.md points at a dead endpoint.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "reporting instead of fixing blocks" block "CLAUDE.md's rule is to FIX"

echo "== 43b. MENTIONING the phrase mid-sentence must NOT block =="
setup
brief_now
hand_now
say "answer

The hook now blocks on a found, not fixed list, and I described that as
\"Found, not fixed\" is now a blocking phrase.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "describing the check does not trip it" allow ""

echo "== 43. the same message without that phrase passes =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "no found-not-fixed list, no complaint" allow ""

echo "== 44. a handover just over the limit is STALE (the limit is load-bearing) =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
# Age it past the default without touching the clock: the check reads mtime.
HAND="$(dirname "$WL")/$(basename "${WL%.md}").handover-deadbeef.md"
touch -d '11 minutes ago' "$HAND"
check "an 11-minute-old handover blocks at the 10-minute limit" block "handover is stale"

echo "== 45. and one just inside it does not =="
touch -d '5 minutes ago' "$HAND"
check "a 5-minute-old handover is fine" allow ""

echo "== 46. CONTROL: an open item still blocks off a runner =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
printf -- '- [ ] (deadbeef) an item nobody will ever answer\n' >>"$WL"
check "an open item blocks in a normal session" block "OPEN worklist item"

echo "== 47. and the SAME state no-ops under GITHUB_ACTIONS =="
# Same worklist, same open item, one env var different. Without the control
# above this would pass even if the hook had stopped blocking entirely.
GHA=true check "GITHUB_ACTIONS=true never blocks a runner" allow ""

echo "== 48. a value other than 'true' is NOT a runner =="
GHA=false check "GITHUB_ACTIONS=false still blocks" block "OPEN worklist item"

echo "== 49. CONTROL: two identical stops do NOT trip the stuck check =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1 of 3 is quiet" allow ""
check "stop 2 of 3 is still quiet" allow ""

echo "== 50. the THIRD identical stop demands an agent =="
check "3 stops with nothing moved blocks" block "EMPLOY A PLANNING OR INVESTIGATION AGENT"

echo "== 51. and it RESETS, so stop 4 is quiet again =="
check "the nag is rate-limited, not every-stop" allow ""

echo "== 52. a task changing status counts as movement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "fresh signature, stop 1" allow ""
check "fresh signature, stop 2" allow ""
# Same session, but the task moved. The counter must restart, not fire.
task 7 in_progress "thing"
newturn
say "answer

## Remaining
| #7 | thing | ongoing, me |"
check "moving a task resets the stuck counter" allow ""

echo "== 53. a running background task exempts it (an agent IS the remedy) =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
BG='[{"status":"running","description":"plan agent"}]'
BG="$BG" check "stop 1" allow ""
BG="$BG" check "stop 2" allow ""
BG="$BG" check "a live agent means the remedy is already running" allow ""

echo "== 54. THE MISSING CONTROL: a COMMIT must move the signature =="
# Its absence is why a dead HEAD leg shipped. The hook resolved the repo from
# the worklist tmp dir, git returned nothing, and every commit was invisible.
setup
git -C "$BASE/proj" init -q 2>/dev/null
git -C "$BASE/proj" config user.email t@t
git -C "$BASE/proj" config user.name t
echo one >"$BASE/proj/f"
git -C "$BASE/proj" add f
git -C "$BASE/proj" commit -qm one
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1" allow ""
check "stop 2" allow ""
# A real commit between stops. If HEAD is wired, this resets tasks+head.
echo two >>"$BASE/proj/f"
git -C "$BASE/proj" commit -qam two
newturn
say "answer

## Remaining
| #7 | thing | pending, me |"
check "a commit resets the tasks+head counter" allow ""

echo "== 55. but a commit buys SLACK, not immunity: tasks-only still fires =="
# Commit every round; the tasks-only signature never moves, so at 2x it fires.
# case 54 already spent 3 stops; tasks-only fires at 2x STUCK_ROUNDS = 6, so
# exactly 3 more land ON the fire rather than past its reset.
for i in 4 5 6; do
    echo "c$i" >>"$BASE/proj/f"
    git -C "$BASE/proj" commit -qam "c$i"
    newturn
    say "answer

## Remaining
| #7 | thing | pending, me |"
    LAST="$(run)"
done
if grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST" &&
    grep -qF "Commits do not count as movement here" <<<"$LAST"; then
    echo "  PASS: the commit-trivia treadmill still trips the tasks-only tier"
    PASS=$((PASS + 1))
else
    echo "  FAIL: committing every round escaped the stuck check"
    echo "        out: ${LAST:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 56. THE WAVE C REPLAY: an uncited prose blocker blocks =="
setup
brief_now
hand_now
# The exact line that started this, verbatim in shape.
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on Wave B landing |"
task 12 pending "Wave C autopilot"
check "an uncited blocker blocks" block "carries no <path>:<line> citation"

echo "== 57. citing a REAL line clears it =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:3 |"
task 12 pending "Wave C autopilot"
check "a citation that resolves is accepted" allow ""

echo "== 58. CONTROL: a citation past end-of-file is NOT accepted =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:900 |"
task 12 pending "Wave C autopilot"
check "a fabricated line number is caught" block "has only 5 lines"

echo "== 59. CONTROL: a citation to a file that does not exist is NOT accepted =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/nope.md:3 |"
task 12 pending "Wave C autopilot"
check "an invented path is caught" block "which does not exist"

echo "== 60. a live background task exempts the citation requirement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on the agent |"
task 12 pending "Wave C autopilot"
BG='[{"status":"running","description":"agent"}]'
check "real machinery needs no prose citation" allow ""

echo "== 61. 'blocked on you' keeps its own check, not this one =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, You (User Thinks So) |"
task 12 pending "Wave C autopilot"
check "an operator blocker is not asked for a file citation" allow ""

echo "== 62. the judge is HANDED the cited text, not just told a path =="
# citation_state only proves a source EXISTS, which any real file satisfies.
# This is the half that lets the judge check whether the source says what the
# session claimed. Tested directly now that the module is importable.
setup
mkdir -p "$BASE/proj/docs"
printf 'alpha\nbravo\nLands with every stage flag off\ndelta\necho\n' >"$BASE/proj/docs/g.md"
OUT=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.cited_excerpts(".", "blocked on Wave B landing, docs/g.md:3"))
' "$HOOK" 2>&1)
if grep -qF "Lands with every stage flag off" <<<"$OUT" && grep -qF ">3|" <<<"$OUT"; then
    echo "  PASS: the cited line is quoted and marked"
    PASS=$((PASS + 1))
else
    echo "  FAIL: excerpt missing or unmarked: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 63. CONTROL: importing the hook must NOT run the Stop path =="
# The bare main() call meant any import executed the whole hook. If that
# regresses, case 62 silently tests a hook run instead of a function.
if grep -qF "no such option" <<<"$OUT" || grep -qF '"decision"' <<<"$OUT"; then
    echo "  FAIL: import executed main(); the module is not importable"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: import is side-effect free"
    PASS=$((PASS + 1))
fi

echo "== 64. CONTROL: a citation past EOF yields no excerpt, never a crash =="
OUT2=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("EXCERPT[" + m.cited_excerpts(".", "blocked, docs/g.md:900 and docs/nope.md:2") + "]")
' "$HOOK" 2>&1)
if grep -qF "EXCERPT[]" <<<"$OUT2"; then
    echo "  PASS: out-of-range and missing files quote nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected an empty excerpt, got: ${OUT2:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 65. v6: a request addressed to ME blocks my stop =="
setup
say "done for now"
brief_now
RID=$(askid cafe1234 deadbeef "regenerate the caption media and republish")
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
RID=$(askid cafe1234 deadbeef "$LONGASK")
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
askid aaaa1111 cafe1234 "please do Y" >/dev/null
check "someone else's request does not block a bystander" allow ""

echo "== 67. CONTROL: my own OPEN request never blocks me, and is reported =="
setup
say "done for now"
brief_now
brief_other cafe1234
askid deadbeef cafe1234 "please regenerate captions" >/dev/null
check "the asker is never blocked on their own open request" allow "still OPEN"

echo "== 68. answering releases the recipient =="
setup
say "done for now"
brief_now
RID=$(askid cafe1234 deadbeef "do X")
check "unanswered, it blocks" block "waiting on you"
reqcli --answer deadbeef "$RID" "done: X is finished, gate green" >/dev/null
check "answered, it releases the recipient" allow ""

echo "== 69. a decline MUST carry a reason; an unanswered ack is refused =="
setup
say "done for now"
brief_now
RID=$(askid cafe1234 deadbeef "do X")
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
if reqcli --ack cafe1234 "$RID" >/dev/null 2>&1; then
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
reqcli --answer cafe1234 "$RID" "the media session owns it; rerun your gate after publish" >/dev/null
check "an unacked answer blocks the asker WITH the answer text" block "the media session owns it"
reqcli --ack deadbeef "$RID" >/dev/null
check "after --ack the answer never re-blocks" allow ""

echo "== 71. a DIRECT decline resolves it and carries its reason back =="
setup
say "done for now"
brief_now
brief_other cafe1234
RID=$(askid deadbeef cafe1234 "please also do Z")
reqcli --decline cafe1234 "$RID" "out of scope: Z belongs to the GPU session" >/dev/null
check "the decline reason reaches the asker as a block" block "out of scope: Z belongs to the GPU session"
reqcli --ack deadbeef "$RID" >/dev/null
check "an acked decline is silent" allow ""

echo "== 72. a BROADCAST blocks each live session only until IT responds =="
setup
say "done for now"
brief_now
RID=$(askid cafe1234 '*' "who owns tutorial caption regeneration")
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
if grep -q '\- \[?\] (cafe1234) request #feedc0de' "$WL" && grep -q 'proceeds without an answer' "$WL"; then
    echo "  PASS: the [?] item exists, owned by the asker, with a generic DEFAULT"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no operator [?] item was appended: $(cat "$WL")"
    FAIL=$((FAIL + 1))
fi
run >/dev/null
if [[ "$(grep -c 'request #feedc0de' "$WL")" == "1" ]]; then
    echo "  PASS: a second stop does not escalate it again"
    PASS=$((PASS + 1))
else
    echo "  FAIL: escalation is not idempotent: $(grep -c 'request #feedc0de' "$WL") lines"
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
if grep -q 'DEFAULT: I quarantine it myself' "$WL"; then
    echo "  PASS: the ask's own DEFAULT: is carried into the [?] item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the ask's DEFAULT was not reused: $(cat "$WL")"
    FAIL=$((FAIL + 1))
fi

echo "== 75. CONTROL: the request block no-ops under GITHUB_ACTIONS =="
setup
say "done for now"
brief_now
askid cafe1234 deadbeef "do X" >/dev/null
check "off a runner the request still blocks" block "waiting on you"
GHA=true check "GITHUB_ACTIONS=true never blocks a runner on a request" allow ""

echo "== 76. RACE: concurrent writers lose nothing =="
setup
for i in $(seq 1 16); do
    reqcli --ask "s$i" cafe1234 "concurrent probe $i" >/dev/null 2>&1 &
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
    reqcli --answer "a$i" "$RID" "answer $i" >/dev/null 2>&1 &
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
if reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1000)")" >/dev/null 2>&1; then
    echo "  PASS: a body exactly at the 1000-char limit is accepted"
    PASS=$((PASS + 1))
else
    echo "  FAIL: an at-limit body was refused"
    FAIL=$((FAIL + 1))
fi
if reqcli --ask cafe1234 deadbeef "$(python3 -c "print('x' * 1100)")" >/dev/null 2>"$BASE/asklen.err"; then
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
askid cafe1234 deadbeef "must survive compaction" >/dev/null
printf -- '- [~] (cafe1234) archived tombstone line\n' >>"$WL"
BEFORE=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
reqcli --compact >/dev/null 2>&1
if grep -q 'archived tombstone' "$WL"; then
    echo "  FAIL: --compact did not run (tombstone still present), test is vacuous"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: --compact really ran (tombstone dropped)"
    PASS=$((PASS + 1))
fi
AFTER=$(md5sum "${WL%.md}.requests" | cut -d' ' -f1)
if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "  PASS: the requests sidecar is byte-identical after --compact"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --compact modified the requests sidecar"
    FAIL=$((FAIL + 1))
fi
check "an open request still blocks after --compact" block "waiting on you"

echo "== 79. requests survive the worklist file being deleted entirely =="
# Deleting the worklist is the hook's documented allow-a-stop residual, but it
# must not delete cross-session obligations: the sidecar is a separate file
# and the request checks run unconditionally, not under worklist.exists().
setup
say "done for now"
brief_now
RID=$(askid cafe1234 deadbeef "still here after the worklist dies")
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
NESC=$(grep -c 'request #feedc0de' "$WL")
NEVT=$(grep -c '"ev":"escalate","id":"feedc0de"' "${WL%.md}.requests")
if [[ "$NESC" == "1" && "$NEVT" == "1" ]]; then
    echo "  PASS: 8 concurrent stops produced exactly one [?] line and one escalate event"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 1 [?] line and 1 escalate event, got $NESC and $NEVT"
    FAIL=$((FAIL + 1))
fi

echo
echo "  passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]
