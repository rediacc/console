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
    # TWO live crons by default, since v9: the enforced shape is one work loop
    # plus the 5-minute inbox poll, and a session missing the poll now blocks.
    # A real looped session carries both, so that is the default to model.
    # Cases that test cron behavior (25, 26, 34, 35, 101+) or I6 pin their own.
    CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
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

shim_judge() { # shim_judge '<regression_gate JSON>' -- a canned claude that always says stop
    RG="$1" python3 -c '
import json, os, pathlib, stat, sys
rg = os.environ.get("RG", "")
out = {"is_error": False, "structured_output": {"verdict": "stop", "reason": "ok", "next_action": "none"}}
if rg:
    out["structured_output"]["regression_gate"] = json.loads(rg)
body = "#!/bin/bash\necho " + json.dumps(json.dumps(out)) + "\n"
p = pathlib.Path(sys.argv[1])
p.write_text(body)
p.chmod(p.stat().st_mode | stat.S_IEXEC)
' "$BASE/binonly/claude"
}

runj() { # like run() but with the shim claude on PATH and the judge ON
    printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":%s}' \
        "$SID" "$BASE/proj" "$BASE/t.jsonl" "${CRONS:-[]}" "${BG:-[]}" |
        PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_JUDGE=on GITHUB_ACTIONS="${GHA:-}" \
            python3 "$HOOK" 2>"$BASE/err.txt"
}

checkj() { # check <label> <expect-decision> <must-contain>, through runj
    local label="$1" want="$2" needle="$3" out
    out="$(runj)"
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

reg_repo() { # a git repo with one base commit; the marker will init at this HEAD
    (
        cd "$BASE/proj" || exit
        git init -q 2>/dev/null
        git config user.email t@t
        git config user.name t
        echo base >base.txt
        git add -A
        git commit -qm "chore: base"
    ) >/dev/null 2>&1
    MARKER="${WL%.md}.reggate-deadbeef"
}

fixcommit() { # fixcommit <file> <subject>
    (
        cd "$BASE/proj" || exit
        mkdir -p "$(dirname "$1")"
        echo x >>"$1"
        git add -A
        git commit -qm "$2"
    ) >/dev/null 2>&1
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
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
run >/dev/null
CRONS='[]'
check "losing the last cron blocks" block "WORK LOOP DIED"

echo "== 35. a session that NEVER had a cron is not nagged =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
# No cron ever, but a running background agent, so the v8 idle check stays
# quiet and this case keeps pinning ONLY the loop-died non-fire.
CRONS='[]'
BG='[{"status":"running","description":"agent"}]'
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

echo "== 81. v7: marker init asks nothing; a DOC-ONLY fix never asks =="
setup
say "done for now"
brief_now
reg_repo
check "the first stop initialises the reggate marker silently" allow ""
if [[ -f "$MARKER" ]] && grep -q '"head": "' "$MARKER"; then
    echo "  PASS: the marker exists with a recorded HEAD"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no marker was written: $(ls "${WL%.md}".* 2>/dev/null)"
    FAIL=$((FAIL + 1))
fi
fixcommit docs/note.md "fix: typo in the docs"
check "THE NAG CONTROL: a doc-only fix commit never asks" allow ""
if [[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["head"])' "$MARKER")" == "$(git -C "$BASE/proj" rev-parse HEAD)" ]]; then
    echo "  PASS: the marker advanced past the doc-only fix (it will never ask)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the marker did not advance past a skipped fix"
    FAIL=$((FAIL + 1))
fi

echo "== 82. a fix COVERED by a real existing gate settles, once =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null # marker init
fixcommit src.ts "fix(cli): guard the empty ref"
shim_judge '{"applicable":true,"blind_spot":"no check compared refs","existing_gate":"check:ci-real","recurring":true,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "a REAL existing gate settles the fix-set as covered" allow "settled as covered"
if grep -q '"verdict": "covered"' "$MARKER"; then
    echo "  PASS: the verdict is recorded in the marker"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no covered verdict in the marker: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi
checkj "a settled fix-set is NEVER re-asked" allow ""

echo "== 83. HALLUCINATED coverage cannot settle: block with three exits =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: a real defect"
shim_judge '{"applicable":true,"blind_spot":"uncovered path","existing_gate":"check:ci-i-dreamed-this","recurring":true,"gate_needed":false,"gate_proven":false,"instruction":"write a gate"}'
OUT="$(runj)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "HALLUCINATED" <<<"$OUT" &&
    grep -qF "WRITE THE GATE control-first" <<<"$OUT" && grep -qF "REBUT" <<<"$OUT"; then
    echo "  PASS: a nonexistent gate name is called hallucinated and the block names the exits"
    PASS=$((PASS + 1))
else
    echo "  FAIL: hallucinated coverage was not caught: ${OUT:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 84. the DEFERRAL exit settles it as an operator decision =="
TOK="$(grep -o 'reggate:[0-9a-f]\{8\}' <<<"$OUT" | head -n1)"
if [[ -n "$TOK" ]]; then
    echo "  PASS: the block hands the session its exact deferral token ($TOK)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no reggate token in the block"
    FAIL=$((FAIL + 1))
fi
printf -- '- [?] (deadbeef) %s should this be gated? DEFAULT: no gate, operator decides\n' "$TOK" >>"$WL"
# The [?] is now OUR deferred item, so the something-remains machinery
# (handover + ## Remaining) applies to this stop -- intended, as in case 74.
hand_now
say "deferred the gate question to the operator

## Remaining
- the reggate deferral, waiting on the operator"
checkj "the [?] deferral settles the fix-set" allow "settled as deferred"

echo "== 85. recurring=false settles as one-off =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: pasted one wrong constant"
shim_judge '{"applicable":true,"blind_spot":"typo with no invariant behind it","existing_gate":"","recurring":false,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "a one-off mistake warrants no gate and settles" allow "settled as one-off"

echo "== 86. PROOF: a new gate, wired TRANSITIVELY and green, settles as proven =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"npm run check:ci-batch","check:ci-batch":"npm run check:ci-newgate","check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n' >"$BASE/proj/package.json"
run >/dev/null # init seeds gate hashes (no scripts yet)
fixcommit src.ts "fix: the recurring defect"
mkdir -p "$BASE/proj/.ci/scripts/quality"
printf '#!/bin/bash\nexit 0\n' >"$BASE/proj/.ci/scripts/quality/check-newgate.sh"
shim_judge '{"applicable":true,"blind_spot":"nothing asserted the invariant","existing_gate":"","recurring":true,"gate_needed":true,"gate_proven":true,"instruction":"gate written"}'
checkj "a wired (ci -> batch -> gate), green gate is the proof" allow "settled as proven"
if grep -q '"exit": 0' "$MARKER" && grep -q 'check-newgate.sh' "$MARKER"; then
    echo "  PASS: the bounded run is cached in the marker by content hash"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no cached gate run in the marker: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi

echo "== 87. CONTROL: a gate DEFINED but not reachable from ci does not prove =="
# Also the anti-substring control: ci MENTIONS the key inside an echo, so a
# substring reachability test would wrongly pass this. Only `npm run` edges count.
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"echo check:ci-newgate","check:ci-newgate":"bash .ci/scripts/quality/check-newgate.sh"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: the recurring defect"
mkdir -p "$BASE/proj/.ci/scripts/quality"
printf '#!/bin/bash\nexit 0\n' >"$BASE/proj/.ci/scripts/quality/check-newgate.sh"
shim_judge '{"applicable":true,"blind_spot":"nothing asserted the invariant","existing_gate":"","recurring":true,"gate_needed":true,"gate_proven":true,"instruction":"gate written"}'
checkj "defined-but-never-run does not count as proof" block "NOT reachable"

echo "== 88. a CORRUPT marker is forgotten loudly, never a block =="
setup
say "done for now"
brief_now
reg_repo
run >/dev/null
echo 'not json {{{' >"$MARKER"
check "corruption re-initialises and reports, allowing the stop" allow "forgotten"
if python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$MARKER" 2>/dev/null; then
    echo "  PASS: the marker is valid JSON again after the reset"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the marker was left corrupt"
    FAIL=$((FAIL + 1))
fi

echo "== 89. a judge that OMITS regression_gate on a fix stop fails closed =="
setup
say "done for now"
brief_now
reg_repo
printf '{"name":"p","version":"0.0.0","scripts":{"ci":"true"}}\n' >"$BASE/proj/package.json"
run >/dev/null
fixcommit src.ts "fix: something real"
shim_judge ''
checkj "a missing regression_gate on a fix-signal stop blocks" block "no usable regression_gate"

echo "== 90. TICKS are the uncommitted-tree signal; pre-existing ones are not =="
setup
say "done for now"
brief_now
reg_repo
echo '- [x] (deadbeef) an old already-done item' >>"$WL"
shim_judge '{"applicable":true,"blind_spot":"x","existing_gate":"","recurring":false,"gate_needed":false,"gate_proven":false,"instruction":"none"}'
checkj "init with a pre-existing tick asks nothing" allow ""
if grep -q '"fixsets": {}' "$MARKER"; then
    echo "  PASS: the pre-existing tick was seeded, not asked about"
    PASS=$((PASS + 1))
else
    echo "  FAIL: init asked about an old tick: $(cat "$MARKER")"
    FAIL=$((FAIL + 1))
fi
# Evidence in the line (a real sha), else I7 blocks before the reggate settle.
echo "- [x] (deadbeef) fixed the parser crash on empty input, $(git -C "$BASE/proj" rev-parse --short HEAD)" >>"$WL"
checkj "a NEWLY ticked [x] is a fix signal even with no commit" allow "settled as one-off"

echo "== 91. I6: a stop with NOTHING inbound blocks on the first stop =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
CRONS='[]'
check "pending task + no cron + no bg + no lease blocks immediately" block "NOTHING WILL WAKE THIS SESSION"

echo "== 92. I6 CONTROLS: each wake-up source suppresses it =="
# Fresh fixture per control: chaining them on one fixture walks the stuck
# counter to its threshold and a later control fails for the wrong reason.
i6_fixture() {
    setup
    brief_now
    hand_now
    say "answer

## Remaining
| #7 | thing | pending, me |"
    task 7 pending "thing"
    CRONS='[]'
}
i6_fixture
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "a live work cron is a wake-up" allow ""
i6_fixture
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "v9: a poll cron ALONE is not a wake-up (it only reacts to others)" block "NOTHING WILL WAKE THIS SESSION"
i6_fixture
BG='[{"status":"running","description":"agent"}]'
check "a running background task is a wake-up" allow ""
i6_fixture
echo "- [>] (deadbeef) until:$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ) delegated to agent" >>"$WL"
check "a fresh [>] lease is a wake-up" allow ""

echo "== 93. I6: a CONFIRMED operator-blocked task is a legitimate idle =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, You (User Thinks So) |"
task 7 pending "thing"
CRONS='[]'
check "confirmed 'You (User Thinks So)' waits without a wake-up" allow ""

echo "== 94. I7: a tick without evidence blocks; a REAL pointer clears it =="
setup
say "done for now"
brief_now
reg_repo
run >/dev/null # marker init
echo '- [x] (deadbeef) fixed the flaky teardown' >>"$WL"
check "an evidence-free tick blocks" block "COMPLETION WITHOUT EVIDENCE"
# A fabricated hex pointer must NOT count: it names no real object.
python3 - "$WL" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read().replace(
    "fixed the flaky teardown",
    "fixed the flaky teardown, see 0123abc4567",
)
open(p, "w").write(s)
PYEOF
check "a fabricated sha is not evidence" block "COMPLETION WITHOUT EVIDENCE"
python3 - "$WL" "$(git -C "$BASE/proj" rev-parse --short HEAD)" <<'PYEOF'
import sys
p, sha = sys.argv[1], sys.argv[2]
s = open(p).read().replace("see 0123abc4567", "proof " + sha)
open(p, "w").write(s)
PYEOF
check "a REAL git object in the line is evidence" allow ""

echo "== 95. I7: a task flipping to completed needs evidence near its #id =="
setup
brief_now
hand_now
reg_repo
task 7 pending "prove the budget flag binds"
say "working on it

## Remaining
| #7 | prove the budget flag binds | pending, me |"
run >/dev/null # marker init snapshots task 7 as pending
task 7 completed "prove the budget flag binds"
newturn
say "All done."
check "S-2 REPLAY: completed with no evidence anywhere blocks" block "COMPLETION WITHOUT EVIDENCE"
newturn
say "Done: #7 verified, exit 0 from the budget run."
check "evidence on the #id line clears it" allow ""

echo "== 96. I7 CONTROL: completions that predate the marker never nag =="
setup
brief_now
reg_repo
task 9 completed "long-finished thing"
say "nothing new"
check "an init-stop snapshot asks nothing about old completions" allow ""
check "and the next stop sees no transition" allow ""

echo "== 97. a DOT-LEADING path is a valid citation (.ci, .github, .claude) =="
# `\b[\w]` cannot start on a dot, so `.ci/x.sh:9` matched but CAPTURED `ci/x.sh`,
# which resolves to nothing. That made most of this repo uncitable while the
# check looked strict. Caught by I7 firing on a real tick of mine.
setup
brief_now
hand_now
mkdir -p "$BASE/proj/.ci/scripts"
printf 'a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n' >"$BASE/proj/.ci/scripts/thing.sh"
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/thing.sh:3 |"
task 7 pending "thing"
check "a .ci path resolves as a citation" allow ""

echo "== 98. CONTROL: a dot-leading path that does NOT exist is still rejected =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/nope.sh:3 |"
task 7 pending "thing"
check "an invented .ci path is caught" block "which does not exist"

echo "== 99. A CRASHING HOOK BLOCKS, it does not wave the stop through =="
# The hook's global escape hatch, and nobody put it there on purpose: an
# unhandled exception writes a traceback to stderr and NOTHING to stdout, the
# harness sees no decision, and the stop is ALLOWED. One bug anywhere silently
# disabled every check. A v8 cut really did crash on a tuple unpack and sail
# through; only a needle assertion caught it.
setup
CRASHED="$BASE/crashy.py"
sed "s/^def main():/def main():\n    raise RuntimeError('planted crash')/" "$HOOK" >"$CRASHED"
OUT=$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        GITHUB_ACTIONS="" python3 "$CRASHED" 2>/dev/null)
GOT=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$GOT" == "block" ]] && grep -qF 'planted crash' <<<"$OUT"; then
    echo "  PASS: a crash blocks and carries its traceback"
    PASS=$((PASS + 1))
else
    echo "  FAIL: a crash produced decision=$GOT (a crash must never allow)"
    echo "        out: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 100. CONTROL: the UNMODIFIED hook still allows a clean stop =="
# Without this, case 99 would pass on a hook that blocks unconditionally.
setup
brief_now
hand_now
say "all done"
CRONS='[{"id":"c","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]' check "a clean stop is still allowed" allow ""

echo "== 101. v9: a loop with NO 5-minute poll blocks (the enforced shape) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"}]'
check "a work cron without the poll cron blocks" block "5-MINUTE INBOX POLL"

echo "== 102. two poll crons block (one is the shape) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p1","schedule":"*/5 * * * *"},{"id":"p2","schedule":"*/5 * * * *"}]'
check "a redundant poll cron blocks" block "poll crons"

echo "== 103. the work loop dying BEHIND a surviving poll still fires =="
# The reason cron_memory is work-scoped in v9: a total-count high-water mark
# reads "1 cron live" and misses that the one driving work is gone.
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
run >/dev/null
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "work loop gone, poll surviving, still fires" block "WORK LOOP DIED"

echo "== 104. CONTROL: poll-only from the START never trips loop-death =="
setup
brief_now
say "all done"
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "a session that never had a work cron is not nagged" allow ""

echo "== 105. v9: waiting-cross-session with a VERIFIED open ask passes =="
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "who owns caption regen? DEFAULT: I take it")
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session #$XRID |"
check "a verified open request IS the citation" allow "still OPEN"

echo "== 106. and it exempts the task from I6 under a poll-only cron =="
# The pair for case 92's poll-only block: same crons, but the wait is real
# and verified, and the poll is exactly what delivers the answer. Fresh
# fixture, so cron_memory never saw a work cron here.
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "who owns caption regen? DEFAULT: I take it")
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session #$XRID |"
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "verified waiting-cross-session + poll cron is a legitimate idle" allow ""

echo "== 107. FIRE: waiting-cross-session with NO request id blocks =="
setup
brief_now
hand_now
task 7 pending "caption regen"
say "answer

## Remaining
| #7 | caption regen | waiting-cross-session on the media session |"
check "the state without a request id is a synonym for blocked" block "names no request id"

echo "== 108. FIRE: someone ELSE'S request does not make it your wait =="
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid cafe1234 beef9999 "between two other sessions")
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | waiting-cross-session #$XRID |"
check "citing a request you did not ask blocks" block "not by you"

echo "== 109. FIRE: an ANSWERED request is a stale wait =="
setup
brief_now
hand_now
brief_other cafe1234
XRID=$(askid deadbeef cafe1234 "please confirm the regen path")
reqcli --answer cafe1234 "$XRID" "confirmed: regen goes via the media session" >/dev/null
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | waiting-cross-session #$XRID |"
check "an answered id means the wait is over" block "already ANSWERED"

echo "== 110. FIRE: an ESCALATED request is the operator's now =="
setup
brief_now
hand_now
printf '{"ev":"ask","id":"feedc0de","from":"deadbeef","to":"beef9999","at":"%s","body":"republish the caption media"}\n' \
    "$(date -u -d '-120 minutes' +%Y-%m-%dT%H:%M:%SZ)" >>"${WL%.md}.requests"
say "answer

## Remaining
- the republish ask, escalated to the operator as a [?]"
run >/dev/null # this stop escalates feedc0de into an operator [?]
task 7 pending "thing"
newturn
say "answer

## Remaining
| #7 | thing | waiting-cross-session #feedc0de |"
check "an escalated id can no longer justify waiting" block "already ESCALATED"

echo "== 111. THE HEADLINE: a no-op poll stop is SILENT (zero output, exit 0) =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "the full stop allows and reports (writes the poll baseline)" allow "deferred rather than done"
if [[ -f "${WL%.md}.pollbase-deadbeef" ]]; then
    echo "  PASS: the allowed full stop wrote the poll baseline"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no pollbase file after an allowed stop"
    FAIL=$((FAIL + 1))
fi
POLLOUT="$(reqcli --poll deadbeef 2>"$BASE/poll.err")"
RC=$?
if [[ "$RC" -eq 0 && -z "$POLLOUT" && ! -s "$BASE/poll.err" ]]; then
    echo "  PASS: --poll on an empty inbox prints NOTHING and exits 0"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --poll rc=$RC out='${POLLOUT:0:120}' err='$(head -c 120 "$BASE/poll.err")'"
    FAIL=$((FAIL + 1))
fi
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    echo "  PASS: the poll stop is SILENT: exit 0, zero bytes of output"
    PASS=$((PASS + 1))
else
    echo "  FAIL: poll stop rc=$RC out='${OUT:0:160}'"
    FAIL=$((FAIL + 1))
fi
if [[ ! -f "${WL%.md}.pollmark-deadbeef" ]]; then
    echo "  PASS: the marker was CONSUMED (one poll vouches for one stop)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the poll marker survived the stop"
    FAIL=$((FAIL + 1))
fi
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "deferred rather than done" <<<"$OUT"; then
    echo "  PASS: CONTROL: without a fresh marker the same world is NOT silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: an ordinary stop went silent without a poll marker: '${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi

echo "== 112. the poll DELIVERS: a waiting request forfeits the silence =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
XRID=$(askid cafe1234 deadbeef "please rebuild the docs index")
POLLOUT="$(reqcli --poll deadbeef)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "INBOX #$XRID" <<<"$POLLOUT" &&
    grep -qF "please rebuild the docs index" <<<"$POLLOUT"; then
    echo "  PASS: --poll prints the full pending payload"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --poll rc=$RC out='${POLLOUT:0:160}'"
    FAIL=$((FAIL + 1))
fi
check "and the stop after it blocks with the delivery, never silently" block "waiting on you"

echo "== 113. ABUSE CONTROL: tracked work forfeits the fast path =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
task 9 pending "the new thing I quietly started"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "OUT OF SYNC" <<<"$OUT"; then
    echo "  PASS: a changed world signature pays the full battery despite the poll"
    PASS=$((PASS + 1))
else
    echo "  FAIL: work slipped through the poll fast path: '${OUT:0:160}'"
    FAIL=$((FAIL + 1))
fi

echo "== 114. the fast path EXPIRES: an old baseline pays the battery again =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
touch -d '80 minutes ago' "${WL%.md}.pollbase-deadbeef"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]] && grep -qF "deferred rather than done" <<<"$OUT"; then
    echo "  PASS: past the horizon a poll stop runs the full battery (and re-arms)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the horizon did not expire the fast path: '${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    echo "  PASS: the full stop re-armed the baseline, so the next poll is silent"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the baseline did not re-arm: rc=$RC out='${OUT:0:120}'"
    FAIL=$((FAIL + 1))
fi

echo "== 115. an EXPIRING lease forfeits the silence (the poll notices in 5min) =="
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "baseline stop" allow ""
echo "- [>] (deadbeef) until:$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%MZ) delegated thing" >>"$WL"
reqcli --poll deadbeef >/dev/null
check "an expired lease is a wake-up the poll stop must not sleep through" block "lease expired"

echo "== 116. --poll misuse is refused loudly (a short prefix half-works) =="
setup
if reqcli --poll dead >/dev/null 2>"$BASE/pollmis.err"; then
    echo "  FAIL: a 4-char prefix was accepted (its marker would never match)"
    FAIL=$((FAIL + 1))
elif grep -qF "8-char" "$BASE/pollmis.err"; then
    echo "  PASS: a short prefix is refused with the reason (exit nonzero)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: refusal was silent: $(head -c 120 "$BASE/pollmis.err")"
    FAIL=$((FAIL + 1))
fi

echo "== 117. the message catalogue renders at every call-site arity =="
# Seven catalogue strings have no needle in this suite (V_DIVERGED,
# V_PR_UNREADABLE, V_EVENT_UNPARSEABLE, R_JUDGE_CONTINUE, CLI_REQUEST_USAGE,
# CTX_SESSION_START_STALE, the exempt-overrun stuck detail). This case is
# their shape protection: every constant must exist and render with the
# EXACT argument arity its call site in worklist.py uses, so a placeholder
# added or dropped in the catalogue cannot lurk in a branch no test drives.
OUT=$(
    python3 - "$(dirname "$HOOK")/worklist_messages.py" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wm", sys.argv[1])
wm = importlib.util.module_from_spec(spec); spec.loader.exec_module(wm)
ARITY = {
    "V_STUCK": ("H", 3, "D"), "V_EVENT_UNPARSEABLE": ("f",),
    "V_OPEN_ITEMS": (1, "x"), "V_UNDEFAULTED": (1, "x"),
    "V_REQUESTS_WAITING": (1, "r", "m", "m"), "V_ANSWERS_UNACKED": ("r", "m"),
    "V_COMPLETION_EVIDENCE": ("a", "b"), "V_COMPLETION_TICKS": ("x",),
    "V_COMPLETION_TASKS": ("x",), "V_IDLE": ("#1",),
    "V_XSESSION_BAD": ("r", "m"), "V_BRIEF": ("s", "", "m"),
    "V_STALE_LOCAL": ("r", 2), "V_DIVERGED": ("r", 2, "r"),
    "V_PR_STALE": ("d",), "V_PR_UNREADABLE": ("d",), "V_LOOP_DIED": (1,),
    "V_NO_POLL_CRON": ("m",), "V_MANY_WORK_CRONS": (2, "l"),
    "V_MANY_POLL_CRONS": (2,), "V_HANDOVER": ("s", "", 250, 600, "m"),
    "V_DOCS_DRIFT": (3, "s", "d"), "V_UNCONFIRMED": ("#1",),
    "V_UNCITED": ("x",), "V_FOUND_NOT_FIXED": None, "V_UNSTATED": ("#1",),
    "V_MISLABELLED": ("x",), "V_OUT_OF_SYNC": (1, "#1"),
    "V_HOOK_BLIND": ("p", "e", "f"), "V_NO_REMAINING": ("x",),
    "R_BLOCK": (1, "v", "f"), "R_JUDGE_UNAVAILABLE": ("e", "f", "m"),
    "R_REGGATE_MALFORMED": ("p", "f"), "R_JUDGE_CONTINUE": ("r", "n", "t"),
    "R_REGGATE_BLOCK": ("b", "i", "", "", "m", "t"),
    "R_REGGATE_HALLUCINATED": ("g",), "CLI_REQUEST_USAGE": None,
    "CLI_BODY_REFUSED": ("b", 1200, 1000), "CTX_SESSION_START": ("d", "l", ""),
    "CTX_SESSION_START_STALE": (3, "s"), "CTX_POSTCOMPACT_MISSING": ("p", "m"),
    "CTX_POSTCOMPACT_BRIEFING": ("d", "t"),
    "JUDGE_PROMPT": {"streak": 1, "remaining": "r", "leases": 0, "loop": "l",
                     "citations": "c", "message": "m"},
    "REGGATE_PROMPT": {"fixset": "f", "keys": "k"},
}
fail = 0
for name, args in ARITY.items():
    val = getattr(wm, name, None)
    if val is None:
        print("MISSING %s" % name); fail += 1; continue
    if args is None:
        continue
    try:
        _ = val % args
    except Exception as exc:
        print("ARITY %s: %s" % (name, exc)); fail += 1
strs = {k for k, v in vars(wm).items()
        if not k.startswith("_") and isinstance(v, str)}
gap = strs - set(ARITY)
if gap:
    print("UNMAPPED new constant(s), add arity here: %s" % sorted(gap)); fail += 1
print("catalogue-arity failures=%d" % fail)
sys.exit(1 if fail else 0)
PYEOF
)
RC=$?
if [[ "$RC" -eq 0 ]]; then
    echo "  PASS: every catalogue constant renders at its call-site arity"
    PASS=$((PASS + 1))
else
    echo "  FAIL: $OUT"
    FAIL=$((FAIL + 1))
fi

echo "== 118. a MISSING catalogue fails CLOSED and spares the query modes =="
# The import is guarded so a broken worklist_messages.py cannot become the
# old crash-reads-as-ALLOW hole: message USE raises into the crash handler
# (block, naming the catalogue), while --path, which uses no messages,
# keeps working for the scripts that call it.
mkdir -p "$BASE/nocat/proj/.git" "$BASE/nocat/tmp"
cp "$HOOK" "$BASE/nocat/worklist.py"
OUT=$(TMPDIR="$BASE/nocat/tmp" CLAUDE_PROJECT_DIR="$BASE/nocat/proj" python3 "$BASE/nocat/worklist.py" --path 2>&1)
RC=$?
if [[ "$RC" -eq 0 && "$OUT" == *"claude-worklist"* ]]; then
    echo "  PASS: --path works without the catalogue"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --path broke without the catalogue: rc=$RC ${OUT:0:120}"
    FAIL=$((FAIL + 1))
fi
NWL="$BASE/nocat/tmp/claude-worklist/$(echo "$BASE/nocat/proj" | sed 's|[^A-Za-z0-9._-]|_|g' | sed 's/^_//').md"
echo '- [ ] (deadbeef) open thing' >>"$NWL"
OUT=$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"/none","last_assistant_message":"done"}' "$SID" "$BASE/nocat/proj" |
    TMPDIR="$BASE/nocat/tmp" CLAUDE_PROJECT_DIR="$BASE/nocat/proj" WORKLIST_TASKS_DIR="$BASE/nocat/tasks" \
        GITHUB_ACTIONS="" python3 "$BASE/nocat/worklist.py" 2>/dev/null)
GOT=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$GOT" == "block" ]] && grep -qF "worklist_messages" <<<"$OUT"; then
    echo "  PASS: a blocking stop without the catalogue BLOCKS naming it"
    PASS=$((PASS + 1))
else
    echo "  FAIL: missing catalogue produced decision=$GOT: ${OUT:0:160}"
    FAIL=$((FAIL + 1))
fi

echo
echo "  passed=$PASS failed=$FAIL"
[[ "$FAIL" -eq 0 ]]
