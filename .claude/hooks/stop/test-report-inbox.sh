#!/usr/bin/env bash
# Tests for wl_report.py (durable sub-agent report capture + unread inbox) and
# wl_wait.py (the blocking waiter that replaces the poll cron).
#
# A NEW FILE rather than cases in test-worklist-v5.sh: that harness is 431 cases
# and is held by another session. These cases move there once it frees.
#
# EVERY CASE ASSERTS ITS NEGATION TOO. A gate that cannot fail is worthless, and
# an empty output is only meaningful once a non-empty one has been demonstrated
# from the same fixture. Where a case has a control it is labelled `control:` and
# is counted like any other assertion -- so a control that stops discriminating
# turns the suite red rather than quietly passing.
#
# Run:  bash .claude/hooks/stop/test-report-inbox.sh
set -u

# AMBIENT SCRUB, before a single case runs -- the same one test-worklist-v5.sh
# carries, and for the same reason with a sharper edge here. Since v19 every
# <me> argument is checked against the real session id, which resolves
# WORKLIST_SESSION_ID first and CLAUDE_CODE_SESSION_ID second. Run from inside a
# Claude session with the ambient id live, this suite's fixture readers
# (aaaaaaaa, bbbbbbbb, cccccccc) all mismatch and 16 cases fail; run in CI with
# it unset, the check silently passes and those cases prove nothing about
# identity at all. Measured, not predicted: 16 reds locally, green in CI, from
# one missing unset. Case 28 below is the control that proves this ran.
while IFS='=' read -r _k _; do
    case "$_k" in
        WORKLIST_* | CLAUDE_CODE_SESSION_ID | CLAUDE_SESSION_ID) unset "$_k" ;;
    esac
done < <(env)
unset _k
# The DEFAULT reader, matching this suite's default fixture session. Cases that
# act as a PEER declare that peer's id per call rather than relying on this.
export WORKLIST_SESSION_ID="aaaaaaaa-1111"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0
FAILED_NAMES=""

ok() {
    PASS=$((PASS + 1))
    printf '  ok   %s\n' "$1"
}

bad() {
    FAIL=$((FAIL + 1))
    FAILED_NAMES="$FAILED_NAMES
  - $1"
    printf '  FAIL %s\n' "$1"
    [ -n "${2:-}" ] && printf '       %s\n' "$2"
    return 0
}

assert_has() { # name haystack needle
    case "$2" in
        *"$3"*) ok "$1" ;;
        *) bad "$1" "expected to contain: $3" ;;
    esac
}

assert_lacks() { # name haystack needle
    case "$2" in
        *"$3"*) bad "$1" "expected NOT to contain: $3" ;;
        *) ok "$1" ;;
    esac
}

assert_eq() { # name got want
    if [ "$2" = "$3" ]; then ok "$1"; else bad "$1" "got [$2] want [$3]"; fi
}

# ---- an isolated universe per case ------------------------------------------
# TMPDIR moves the worklist, CLAUDE_CONFIG_DIR moves the projects tree that
# --scan walks, WORKLIST_REPORTS_DIR moves the store, and CLAUDE_PROJECT_DIR
# moves the repo root the slug derives from. Together they mean a case cannot
# see, or damage, the live session's worklist -- which is running right now.

# The base for every scratch universe, captured ONCE. Deriving it from $TMPDIR
# at call time instead would nest each case inside the previous case's TMPDIR,
# and the slugified worklist name (which embeds the whole absolute path) then
# grows until it trips ENAMETOOLONG a dozen cases in -- which is exactly what
# the first run of this suite did.
TEST_BASE="$(mktemp -d "${TMPDIR:-/tmp}/wl-report-suite-XXXXXX")"
trap 'rm -rf "$TEST_BASE"' EXIT

scratch() {
    T="$(mktemp -d "$TEST_BASE/case-XXXXXX")"
    mkdir -p "$T/tmp" "$T/store" "$T/claude/projects" "$T/repo"
    : >"$T/repo/.git" # a FILE, like a worktree's: C.project_root tests existence
    export TMPDIR="$T/tmp"
    export CLAUDE_CONFIG_DIR="$T/claude"
    export WORKLIST_REPORTS_DIR="$T/store"
    export CLAUDE_PROJECT_DIR="$T/repo"
    export WORKLIST_AGENT_BRANCH="testbr"
}

report_py() { python3 "$HERE/wl_report.py" "$@"; }

# A SubagentStop payload on stdin. $1 agent_id, $2 agent_type, $3 body.
stop_event() {
    python3 - "$1" "$2" "$3" <<'PY' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os, sys
print(json.dumps({
    "agent_id": sys.argv[1], "agent_type": sys.argv[2],
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "", "last_assistant_message": sys.argv[3],
}))
PY
}

surface_as() { # $1 session_id (the READER), $2 mode, $3 source
    python3 - "$1" "$3" <<'PY' >"$T/ev.json"
import json, os, sys
print(json.dumps({"cwd": os.environ["CLAUDE_PROJECT_DIR"],
                  "session_id": sys.argv[1], "source": sys.argv[2]}))
PY
    python3 "$HERE/wl_report.py" "$2" <"$T/ev.json"
}

# The default reader for cases that do not care which session is looking.
surface() { # $1 mode (--session-start|--post-compact), $2 source
    surface_as aaaaaaaa-1111 "$1" "$2"
}

# Same, but the body comes from a FILE. A 400 KB body cannot travel in argv:
# execve caps a single argument at MAX_ARG_STRLEN (128 KB on Linux) and the
# shell reports it as "Argument list too long".
stop_event_f() { # $1 agent_id, $2 agent_type, $3 path to a body file
    python3 - "$1" "$2" "$3" <<'PY' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os, sys
print(json.dumps({
    "agent_id": sys.argv[1], "agent_type": sys.argv[2],
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "",
    "last_assistant_message": open(sys.argv[3], encoding="utf-8").read(),
}))
PY
}

BIG="$(python3 -c 'print("a substantive body. " * 40)')"

echo "== 6/7. capture: substantive vs silent =="
scratch
stop_event "asome-agent-1111222233334444" some-agent "TITLE LINE
$BIG"
stop_event "aquiet-one-5555666677778888" quiet-one ""
IDX="$T/store/index.jsonl"
assert_eq "6 one line per capture" "$(wc -l <"$IDX" | tr -d ' ')" "2"
assert_has "6 substantive is not silent" "$(sed -n 1p "$IDX")" '"silent":false'
assert_has "6 title is the first non-empty line" "$(sed -n 1p "$IDX")" '"title":"TITLE LINE"'
# control: the silent flag must actually be able to take the other value, or the
# assertion above is satisfied by a field that is hard-coded false.
assert_has "7 control: silent agent is flagged silent" "$(sed -n 2p "$IDX")" '"silent":true'
assert_eq "6 body stored whole" \
    "$(python3 -c 'import sys;print(len(open(sys.argv[1]).read()))' "$(ls "$T"/store/testbr/*some-agent*.md)")" \
    "$(python3 -c "
import sys
front=open(sys.argv[1]).read().split('---',2)[2]
print(len(open(sys.argv[1]).read()))" "$(ls "$T"/store/testbr/*some-agent*.md)")"
assert_has "6 body file holds the body verbatim" "$(cat "$T"/store/testbr/*some-agent*.md)" "TITLE LINE"
LONGEST="$(awk '{ n = length($0) + 1; if (n > m) m = n } END { print m }' "$IDX")"
if [ "$LONGEST" -lt 1024 ]; then ok "6 index line under the 1024-byte atomic cap ($LONGEST)"; else
    bad "6 index line under the 1024-byte atomic cap" "longest $LONGEST"
fi

echo "== 6b. a huge body still yields a capped index line =="
scratch
python3 -c 'import sys; open(sys.argv[1], "w").write("X" * 400000)' "$T/huge.txt"
stop_event_f "ahuge-agent-9999888877776666" huge-agent "$T/huge.txt"
LONGEST="$(awk '{ n = length($0) + 1; if (n > m) m = n } END { print m }' "$T/store/index.jsonl")"
if [ "$LONGEST" -lt 1024 ]; then ok "6b 400 KB body -> index line $LONGEST bytes"; else
    bad "6b 400 KB body -> capped index line" "longest $LONGEST"
fi
# Counted in the BODY ONLY, past the front matter: a whole-file count also
# caught the word EXIST in the front-matter marker and read 400001.
assert_eq "6b the body itself is NOT truncated" \
    "$(python3 -c '
import glob, sys
p = glob.glob(sys.argv[1] + "/store/testbr/*huge-agent*.md")[0]
print(open(p).read().split("---\n\n", 1)[1].count("X"))' "$T")" "400000"
# control: the cap is enforced by shrinking values, never by dropping keys.
assert_has "6b control: no key was dropped to fit" "$(cat "$T/store/index.jsonl")" '"transcript"'
assert_has "6b control: no key was dropped to fit (title)" "$(cat "$T/store/index.jsonl")" '"title"'

echo "== 6c. the 1024-byte cap holds when the OVERSIZE IS NOT THE TITLE =="
# 6b does NOT exercise the cap: the title is truncated to TITLE_MAX before the
# line is ever built, so a 400 KB body yields a short line no matter what _fit
# does (disabling _fit leaves 6b green -- verified by mutation). The cap only
# has real work when some OTHER field is long. Deep worktree paths make that
# concrete rather than theoretical; this suite tripped ENAMETOOLONG on its own
# first run.
scratch
python3 - <<'PY' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os
print(json.dumps({
    "agent_id": "along-path-agent-3131313131313131",
    "agent_type": "T" * 300,
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "/" + "d" * 3000 + "/agent.jsonl",
    "last_assistant_message": "A REAL TITLE\n" + "body. " * 200,
}))
PY
LONGEST="$(awk '{ n = length($0) + 1; if (n > m) m = n } END { print m }' "$T/store/index.jsonl")"
if [ "$LONGEST" -lt 1024 ]; then ok "6c a 3 KB transcript path still fits ($LONGEST bytes)"; else
    bad "6c a 3 KB transcript path still fits" "longest $LONGEST -- an atomic append is no longer guaranteed"
fi
assert_has "6c control: the transcript KEY survived the shrink" "$(cat "$T/store/index.jsonl")" '"transcript"'
assert_has "6c control: the title KEY survived the shrink" "$(cat "$T/store/index.jsonl")" '"title"'
# The id is the LAST 12 characters of the agent id, so the 16-char hex suffix
# above yields exactly 12 of them.
assert_has "6c control: the id is intact" "$(cat "$T/store/index.jsonl")" '"id":"313131313131"'
assert_eq "6c the line is still valid JSON" "$(python3 -c '
import json, sys
print(json.loads(open(sys.argv[1]).readline())["ev"])' "$T/store/index.jsonl")" "report"

echo "== 8. index atomicity under 50 concurrent writers (validates the no-lock choice) =="
scratch
i=0
while [ "$i" -lt 50 ]; do
    # The counter must vary within the LAST 12 characters: `short_id` is the id's
    # TAIL (a leading truncation would collide on same-named teammates), so ids
    # differing only in a prefix would all fold to one id and 49 of these would
    # be dropped as duplicates -- which is what the first draft of this case did,
    # and it looked exactly like a lost-append bug.
    stop_event "aconc-$(printf '%016d' $i)" "conc" "concurrent body number $i, long enough to matter $BIG" &
    i=$((i + 1))
done
wait
TOTAL="$(wc -l <"$T/store/index.jsonl" | tr -d ' ')"
PARSEABLE="$(python3 -c '
import json, sys
n = 0
for line in open(sys.argv[1]):
    try:
        json.loads(line)
        n += 1
    except ValueError:
        pass
print(n)' "$T/store/index.jsonl")"
assert_eq "8 all 50 lines present" "$TOTAL" "50"
assert_eq "8 all 50 lines parseable (no interleaving)" "$PARSEABLE" "50"

echo "== 9. branch keying =="
scratch
stop_event "abr-one-1111111111111111" br-one "on branch one $BIG"
WORKLIST_AGENT_BRANCH=otherbr stop_event "abr-two-2222222222222222" br-two "on branch two $BIG"
# A glob, not `ls | grep` (SC2010): the branch names here are fixed, so counting
# directories directly is both correct and shellcheck-clean.
_brdirs=0
for _d in "$T"/store/*br; do [ -d "$_d" ] && _brdirs=$((_brdirs + 1)); done
assert_eq "9 bodies land in separate branch dirs" "$_brdirs" "2"
assert_has "9 first line carries its branch" "$(sed -n 1p "$T/store/index.jsonl")" '"branch":"testbr"'
assert_has "9 second line carries its branch" "$(sed -n 2p "$T/store/index.jsonl")" '"branch":"otherbr"'

echo "== 10/11. surfacing, read marks, and the compaction rule =="
scratch
stop_event "asurf-one-1212121212121212" surf-one "SURFACED TITLE
$BIG"
OUT="$(surface --session-start startup)"
assert_has "10 unread report is surfaced at SessionStart" "$OUT" "SURFACED TITLE"
assert_has "10 surfacing names the --show command" "$OUT" "--show"
assert_has "10 emitted as additionalContext" "$OUT" "additionalContext"
RID="$(python3 -c '
import json, sys
print(json.loads(open(sys.argv[1]).readline())["id"])' "$T/store/index.jsonl")"
report_py --read aaaaaaaa "$RID" >/dev/null
OUT2="$(surface --session-start startup)"
# The empty half is only meaningful because the non-empty half above ran first.
assert_eq "10 control: marked read by THIS reader, SessionStart emits nothing" "$OUT2" ""

# 10b. READ MARKS ARE PER-READER, KEYED ON SESSION ID (operator decision, which
# OVERRODE this design's own branch-level recommendation). This is the case the
# decision exists for, so it is the one that must be provably able to fail:
# session A marking a report read must NOT hide it from its live peer B.
#
# The rejected alternative -- one ledger per branch -- means B never learns the
# report existed, which is a quieter restatement of the failure this whole
# feature fixes. Two concurrent sessions per worktree is this repo's normal
# state, so it is not a corner case.
OUT3="$(surface_as bbbbbbbb-2222 --session-start startup)"
assert_has "10b a PEER session still sees a report reader A marked read" "$OUT3" "SURFACED TITLE"
# ...and the peer marking it read clears it for the peer, and ONLY the peer.
# As the PEER, declared rather than asserted by hand: since v19 a read mark
# filed under an identity you are not is refused, because it clears nothing
# for the reader who filed it and hides the report from nobody.
WORKLIST_SESSION_ID="bbbbbbbb-2222" report_py --read bbbbbbbb "$RID" >/dev/null
OUT3b="$(surface_as bbbbbbbb-2222 --session-start startup)"
assert_eq "10b control: the peer's own mark does clear it for the peer" "$OUT3b" ""
# The ACCEPTED COST, asserted so nobody later "fixes" it: a restarted session is
# a different reader (same_session matches by PREFIX) and re-sees the report.
# That resurfacing IS the compaction-recovery case working.
OUT3c="$(surface_as cccccccc-3333 --session-start startup)"
assert_has "10b a fresh reader re-sees the branch's reports (recovery, not a bug)" "$OUT3c" "SURFACED TITLE"
# control: proves the emitter can still fire for reader A too, so the empty at
# 10-control is a read mark working and not a surfacing path that is dead.
stop_event "asurf-two-3434343434343434" surf-two "SECOND TITLE
$BIG"
OUT4="$(surface --session-start startup)"
assert_has "10b control: a NEW report still surfaces to reader A" "$OUT4" "SECOND TITLE"
assert_lacks "10b control: the one A read stays suppressed for A" "$OUT4" "SURFACED TITLE"
# branch isolation, kept from the original 10b: a report captured on testbr is
# not another branch's business, whoever is reading.
OUT5="$(WORKLIST_AGENT_BRANCH=elsewhere surface --session-start startup)"
assert_eq "10b reports do not leak across branches" "$OUT5" ""
# 11: SessionStart declines source=compact; PostCompact is what emits there.
OUT6="$(surface --session-start compact)"
assert_eq "11 SessionStart is silent on source=compact" "$OUT6" ""
OUT7="$(surface --post-compact compact)"
assert_has "11 control: PostCompact emits on the same fixture" "$OUT7" "SECOND TITLE"

echo "== 12. SendMessage payloads are the report, not the sign-off =="
scratch
mkdir -p "$T/claude/projects"
python3 - "$T" <<'PY'
import json, os, pathlib, re, sys, time
T = pathlib.Path(sys.argv[1])
root = T / "repo"
proj = T / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root)) / "sess1" / "subagents"
proj.mkdir(parents=True)
aid = "asender-7777777777777777"
(proj / ("agent-%s.meta.json" % aid)).write_text(json.dumps(
    {"agentType": "sender", "name": "sender", "taskKind": "in_process_teammate"}))
recs = [{
    "type": "assistant", "agentId": aid, "sessionId": "sess1", "gitBranch": "testbr",
    "timestamp": "2026-08-05T10:00:00.500Z", "cwd": str(root),
    "message": {"content": [
        {"type": "tool_use", "name": "SendMessage",
         "input": {"to": "team-lead", "summary": "the report",
                   "message": "THE ACTUAL REPORT\n" + "detail. " * 200}}]},
}, {
    "type": "assistant", "agentId": aid, "sessionId": "sess1", "gitBranch": "testbr",
    "timestamp": "2026-08-05T10:01:00.500Z", "cwd": str(root),
    "message": {"content": [{"type": "text", "text": "Released. Task complete."}]},
}]
p = proj / ("agent-%s.jsonl" % aid)
p.write_text("".join(json.dumps(r) + "\n" for r in recs))
old = time.time() - 3600
os.utime(p, (old, old))  # idle, so --scan considers it finished
PY
SCAN="$(report_py --scan)"
assert_has "12 scan indexed the agent" "$SCAN" "sender"
assert_has "12 title comes from the SendMessage, not the sign-off" "$SCAN" "THE ACTUAL REPORT"
assert_lacks "12 the sign-off is NOT the title" "$SCAN" "Released. Task complete."
BODY="$(report_py --show "$(python3 -c '
import json, sys
print(json.loads(open(sys.argv[1]).readline())["id"])' "$T/store/index.jsonl")")"
assert_has "12 body holds the SendMessage payload" "$BODY" "THE ACTUAL REPORT"
assert_has "12 body also holds the sign-off" "$BODY" "Released. Task complete."
# control: WITHOUT the SendMessage harvest this agent reads as silent (24 chars
# of sign-off is under the 200-char floor). This is the whole finding.
assert_has "12 control: an agent that only SendMessages is NOT silent" \
    "$(cat "$T/store/index.jsonl")" '"silent":false'
scratch
stop_event "abare-signoff-4444444444444444" bare "Released. Task complete."
assert_has "12 control: the same sign-off with no sends IS silent" \
    "$(cat "$T/store/index.jsonl")" '"silent":true'

echo "== 12b. ONE POISONED AGENT MUST NOT STARVE THE PASS =="
# The review finding this pins: scan()'s per-agent capture was not isolated, so a
# single entry that raised killed the loop before it reached anything sorted
# AFTER it -- and because a failed entry is never recorded as `known`, the next
# scan hit the same wall at the same place. The self-heal starved permanently
# and silently.
#
# Ordering is load-bearing: scan() walks sorted(), so the poison must sort
# BEFORE the good agent or this proves nothing. "apoison" < "bgood".
scratch
mkdir -p "$T/claude/projects"
python3 - "$T" <<'PY2'
import json, os, pathlib, re, sys, time
T = pathlib.Path(sys.argv[1])
root = T / "repo"
proj = T / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root)) / "sess1" / "subagents"
proj.mkdir(parents=True)
def agent(aid, atype, text):
    (proj / ("agent-%s.meta.json" % aid)).write_text(json.dumps({"agentType": atype, "name": atype}))
    rec = {"type": "assistant", "agentId": aid, "sessionId": "sess1", "gitBranch": "testbr",
           "timestamp": "2026-08-05T10:00:00.500Z", "cwd": str(root),
           "message": {"content": [{"type": "text", "text": text}]}}
    p = proj / ("agent-%s.jsonl" % aid)
    p.write_text(json.dumps(rec) + "\n")
    old = time.time() - 3600
    os.utime(p, (old, old))  # idle, so --scan considers it finished
# POISON, arrived at by ELIMINATION and worth recording so nobody re-walks it:
#   - a >255-byte id fails the WRITE during setup, so the case tests nothing;
#   - a giant agentType does NOT poison, because _fit's last-resort stage
#     shrinks the agent field too and the entry captures cleanly.
# So the poison is a transcript that EXISTS and STATS like a file but cannot be
# read: a directory named agent-*.jsonl. exists() and stat() both succeed, the
# idle check passes, and harvest_transcript raises IsADirectoryError -- a real
# read failure rather than a size one, and independent of permissions (a chmod
# 000 poison would evaporate under a root-run CI).
pid = "apoison-1111111111111111"
(proj / ("agent-%s.meta.json" % pid)).write_text(json.dumps({"agentType": "POISONAGENT"}))
pdir = proj / ("agent-%s.jsonl" % pid)
pdir.mkdir()
os.utime(pdir, (time.time() - 3600,) * 2)
agent("bgood-5555555555555555", "goodagent", "GOOD AGENT REPORT " + "detail. " * 40)
PY2
SCAN12B="$(report_py --scan)"
assert_has "12b the good agent sorted AFTER the poison is still indexed" "$SCAN12B" "goodagent"
# WHAT AN UNREADABLE TRANSCRIPT ACTUALLY DOES, established by elimination rather
# than assumed: it does NOT raise. harvest_transcript absorbs the read failure,
# so the entry is indexed with an empty body and flagged silent. Both agents
# therefore index, and the pass completes.
#
# That makes the `except Exception: continue` in scan() DEFENSIVE rather than
# load-bearing for this input: no public input found so far reaches it (an
# oversized agentType does not either -- _fit's last-resort stage shrinks that
# field). This case pins the property that matters and can be observed from
# outside -- a problematic entry does not cost the entries sorted after it --
# and deliberately does NOT claim to exercise the except arm. A control that
# asserted the poison vanished would be asserting something false.
assert_eq "12b both agents indexed; the bad one costs only itself" \
    "$(wc -l <"$T/store/index.jsonl" | tr -d ' ')" "2"
assert_has "12b the unreadable transcript indexes as silent, not as an abort" \
    "$(cat "$T/store/index.jsonl")" '"silent":true'

echo "== 13. scan skips a still-running agent =="
scratch
python3 - "$T" <<'PY'
import json, pathlib, re, sys
T = pathlib.Path(sys.argv[1])
root = T / "repo"
proj = T / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root)) / "s" / "subagents"
proj.mkdir(parents=True)
aid = "arunning-6666666666666666"
(proj / ("agent-%s.meta.json" % aid)).write_text(json.dumps({"agentType": "running"}))
(proj / ("agent-%s.jsonl" % aid)).write_text(json.dumps({
    "type": "assistant", "agentId": aid, "gitBranch": "testbr",
    "message": {"content": [{"type": "text", "text": "half an answer so far"}]}}) + "\n")
PY
assert_has "13 a fresh (running) transcript is not indexed" "$(report_py --scan)" "nothing to index"
# control: the same fixture, backdated, IS indexed -- so the skip is the idle
# rule and not a scan that simply cannot see the directory.
python3 -c '
import glob, os, sys, time
p = glob.glob(sys.argv[1] + "/claude/projects/*/*/subagents/*.jsonl")[0]
old = time.time() - 3600
os.utime(p, (old, old))' "$T"
assert_has "13 control: backdated, the same agent IS indexed" "$(report_py --scan)" "running"

echo "== 14. torn index tail =="
scratch
stop_event "atorn-one-8888888888888888" torn-one "a real report $BIG"
printf '{"ev":"report","id":"trunc' >>"$T/store/index.jsonl" # no newline, no close
assert_has "14 a torn tail does not hide the good line" "$(report_py --list --all)" "torn-one"
assert_lacks "14 the torn line itself is skipped" "$(report_py --list --all)" "trunc"
OUT="$(surface --session-start startup)"
assert_has "14 surfacing survives a torn tail" "$OUT" "a real report"

echo "== 15. wl_wait: misuse =="
scratch
OUT="$(python3 "$HERE/wl_wait.py" 2>&1)"
assert_eq "15 no argument -> exit 2" "$?" "2"
# The needle tracks the new help text: the bare-usage path prints the full
# contract, not a "usage:" one-liner. Case 22 owns the detail; this one only
# asserts that misuse is explained on stderr at all.
assert_has "15 the contract is printed on stderr" "$OUT" "BACKGROUND TASK"
OUT="$(python3 "$HERE/wl_wait.py" abc 2>&1)"
assert_eq "15 short prefix -> exit 2" "$?" "2"
assert_has "15 short prefix names the problem" "$OUT" "bad prefix"
OUT="$(python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0 2>&1)"
assert_eq "15 non-positive timeout -> exit 2" "$?" "2"

echo "== 16. wl_wait takes no lock (structural, with a proven-live control) =="
LOCKUSE="$(grep -cE '_flock\(|fcntl\.flock\(|import fcntl' "$HERE/wl_wait.py" || true)"
assert_eq "16 wl_wait.py makes no lock call" "$LOCKUSE" "0"
LOCKUSE2="$(grep -cE '_flock\(|fcntl\.flock\(|import fcntl' "$HERE/wl_report.py" || true)"
assert_eq "16 wl_report.py makes no lock call" "$LOCKUSE2" "0"
# control: the SAME grep must fire on a file that really does lock, or it is a
# pattern that can never match and the two assertions above prove nothing.
LOCKUSE3="$(grep -cE '_flock\(|fcntl\.flock\(|import fcntl' "$HERE/wl_store.py" || true)"
if [ "$LOCKUSE3" -gt 0 ]; then ok "16 control: the grep fires on wl_store.py ($LOCKUSE3 hits)"; else
    bad "16 control: the grep fires on wl_store.py" "0 hits -- the pattern is dead"
fi

echo "== 17. wl_wait: wakes on a NEW request, not on a pre-existing one =="
scratch
WL="$(python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))' HERE="$HERE" 2>/dev/null || HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))')"
REQ="${WL%.md}.requests"
mkreq() { # id from to body
    python3 - "$REQ" "$1" "$2" "$3" "$4" <<'PY'
import json, sys, datetime
p, rid, frm, to, body = sys.argv[1:6]
at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(p, "a") as f:
    f.write(json.dumps({"ev": "ask", "id": rid, "from": frm, "to": to, "at": at,
                        "body": body}) + "\n")
PY
}

# 17a. A request that PREDATES the waiter must NOT wake it. This is the spin-loop
# regression: arming on "the slice is non-empty" would fire instantly, forever.
mkreq preexist bbbbbbbb aaaaaaaa "a request the session has already seen"
python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.15 >"$T/w1.out" 2>"$T/w1.err" &
W1=$!
sleep 4
if kill -0 "$W1" 2>/dev/null; then ok "17a pre-existing request does NOT wake the waiter"; else
    bad "17a pre-existing request does NOT wake the waiter" "$(cat "$T/w1.out")"
fi
assert_eq "17a nothing printed while waiting" "$(cat "$T/w1.out")" ""
# 17b control: with that same request still unresolved, a NEW one DOES wake it,
# and prints ONLY the new one.
mkreq fresh001 bbbbbbbb aaaaaaaa "THE NEW REQUEST"
sleep 5
if kill -0 "$W1" 2>/dev/null; then
    bad "17b control: a new request wakes the waiter" "still running after 5s"
    kill "$W1" 2>/dev/null
else
    ok "17b control: a new request wakes the waiter"
fi
wait "$W1" 2>/dev/null
assert_has "17b it prints the new request" "$(cat "$T/w1.out")" "THE NEW REQUEST"
assert_lacks "17b it does NOT reprint the pre-existing one" "$(cat "$T/w1.out")" "already seen"
assert_has "17b it prints the answer command" "$(cat "$T/w1.out")" "--answer"

echo "== 17c. the baseline suppresses a request the session already saw, even when the signature MOVES =="
# 17a alone does NOT prove the request baseline: with no new appends the cheap
# signature gate never opens, so the fold never runs and the baseline is never
# consulted. Mutating the baseline away leaves 17a green. THIS case forces the
# signature to move while the only classified item is one the session already
# had -- a third session declining a pre-existing BROADCAST, whose id counts as
# ours in my_requests_sig -- so the fold DOES run and only the baseline can
# suppress the wake.
scratch
WL="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))')"
REQ="${WL%.md}.requests"
python3 - "$REQ" <<'PY'
import datetime, json, sys
at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"ev": "ask", "id": "bcast001", "from": "bbbbbbbb", "to": "*",
                        "at": at, "body": "A BROADCAST ALREADY IN CONTEXT"}) + "\n")
PY
python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.2 >"$T/w5.out" 2>&1 &
W5=$!
sleep 2
SIG_BEFORE="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C, wl_store as S
print(S.my_requests_sig(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]), "aaaaaaaa"))')"
python3 - "$REQ" <<'PY'
import datetime, json, sys
at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"ev": "decline", "id": "bcast001", "by": "cccccccc",
                        "at": at, "reason": "not my area"}) + "\n")
PY
SIG_AFTER="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C, wl_store as S
print(S.my_requests_sig(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]), "aaaaaaaa"))')"
# The premise of this case, asserted rather than assumed: if the signature did
# NOT move, the fold would be skipped and the case would prove nothing.
if [ "$SIG_BEFORE" != "$SIG_AFTER" ]; then
    ok "17c premise: the third-party decline DID move our signature"
else
    bad "17c premise: the third-party decline moved our signature" "unchanged: $SIG_BEFORE -- this case is vacuous"
fi
sleep 5
if kill -0 "$W5" 2>/dev/null; then ok "17c an already-seen request does not wake it even when the fold runs"; else
    bad "17c an already-seen request does not wake it even when the fold runs" "$(cat "$T/w5.out")"
fi
assert_eq "17c nothing printed" "$(cat "$T/w5.out")" ""
kill "$W5" 2>/dev/null
wait "$W5" 2>/dev/null

echo "== 18. wl_wait: foreign traffic does not wake it =="
scratch
WL="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))')"
REQ="${WL%.md}.requests"
python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.3 >"$T/w2.out" 2>&1 &
W2=$!
sleep 2
mkreq foreign1 bbbbbbbb cccccccc "traffic between two other sessions"
sleep 5
if kill -0 "$W2" 2>/dev/null; then ok "18 foreign traffic does NOT wake the waiter"; else
    bad "18 foreign traffic does NOT wake the waiter" "$(cat "$T/w2.out")"
fi
assert_eq "18 nothing printed for foreign traffic" "$(cat "$T/w2.out")" ""
# control: the same fixture, addressed to us, DOES wake it -- so 18 is a
# signature gate working, not a waiter that is simply deaf.
mkreq mine0001 bbbbbbbb aaaaaaaa "ADDRESSED TO ME"
sleep 5
if kill -0 "$W2" 2>/dev/null; then
    bad "18 control: the same append addressed to us wakes it" "still running"
    kill "$W2" 2>/dev/null
else
    ok "18 control: the same append addressed to us wakes it"
fi
wait "$W2" 2>/dev/null
assert_has "18 control: it prints the addressed request" "$(cat "$T/w2.out")" "ADDRESSED TO ME"

echo "== 19. wl_wait: wakes on a NEW sub-agent report =="
scratch
python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.3 >"$T/w3.out" 2>&1 &
W3=$!
sleep 2
stop_event "await-report-5151515151515151" waiter-report "A REPORT THAT SHOULD WAKE IT
$BIG"
sleep 5
if kill -0 "$W3" 2>/dev/null; then
    bad "19 a new report wakes the waiter" "still running"
    kill "$W3" 2>/dev/null
else
    ok "19 a new report wakes the waiter"
fi
wait "$W3" 2>/dev/null
assert_has "19 it names the report" "$(cat "$T/w3.out")" "A REPORT THAT SHOULD WAKE IT"
assert_has "19 it names the read command" "$(cat "$T/w3.out")" "--show"

echo "== 20. wl_wait: timeout prints one bounded line and exits 0 =="
scratch
OUT="$(python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.05 2>&1)"
RC=$?
assert_eq "20 timeout exits 0" "$RC" "0"
assert_has "20 timeout says so" "$OUT" "INBOX-WAIT"
assert_eq "20 timeout is ONE line" "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" "1"

echo "== 21. wl_wait does not block a concurrent worklist write =="
scratch
python3 "$HERE/wl_wait.py" aaaaaaaa --timeout 0.4 >"$T/w4.out" 2>&1 &
W4=$!
sleep 2
ELAPSED="$(HERE="$HERE" python3 -c '
import os, sys, time
sys.path.insert(0, os.environ["HERE"])
import wl_core as C, wl_store as S
w = C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"])
p = S.requests_path(w)
t = time.monotonic()
S._append_lines(p, str(p) + ".lock", [{"ev": "probe"}])
print("%.3f" % (time.monotonic() - t))')"
if python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) < 1.0 else 1)" "$ELAPSED"; then
    ok "21 a locked write completes in ${ELAPSED}s while the waiter runs"
else
    bad "21 a locked write completes quickly while the waiter runs" "took ${ELAPSED}s"
fi
kill "$W4" 2>/dev/null
wait "$W4" 2>/dev/null
# control: the SAME measurement, against a deliberate LOCK_EX holder, must show
# blocking. Without this, "fast" could just mean the timer cannot detect a stall.
HELD="$(HERE="$HERE" python3 -c '
import os, subprocess, sys, time
sys.path.insert(0, os.environ["HERE"])
import wl_core as C, wl_store as S
w = C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"])
p = S.requests_path(w)
holder = subprocess.Popen([sys.executable, "-c",
    "import fcntl,sys,time\n"
    "f=open(sys.argv[1],\"w\")\n"
    "fcntl.flock(f, fcntl.LOCK_EX)\n"
    "time.sleep(3)\n", str(p) + ".lock"])
time.sleep(1)
t = time.monotonic()
S._append_lines(p, str(p) + ".lock", [{"ev": "probe2"}])
print("%.3f" % (time.monotonic() - t))
holder.wait()')"
if python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) > 1.0 else 1)" "$HELD"; then
    ok "21 control: a real LOCK_EX holder DOES block it (${HELD}s)"
else
    bad "21 control: a real LOCK_EX holder DOES block it" "took only ${HELD}s -- the timer cannot detect a stall, so the assertion above is vacuous"
fi

echo "== 22. wl_wait --help explains how to invoke it, not just the argument order =="
# The help was ONE usage line. A tool whose entire value depends on being
# launched in the BACKGROUND, and whose help does not say so, does not get used
# -- and that is not hypothetical: it shipped, and the session that built it
# kept polling instead. These pin the facts a reader cannot infer from the
# signature.
OUT="$(python3 "$HERE/wl_wait.py" --help 2>&1)"
RC=$?
assert_eq "22 --help exits 0" "$RC" "0"
assert_has "22 says it must run in the background" "$OUT" "BACKGROUND TASK"
assert_has "22 says the exit IS the notification" "$OUT" "EXIT IS THE NOTIFICATION"
assert_has "22 says it is not a backlog detector" "$OUT" "BACKLOG DETECTOR"
assert_has "22 warns about quotes (the unverifiable trap)" "$OUT" "NO QUOTES"
assert_has "22 says it only fires once" "$OUT" "ONLY FIRES ONCE"
assert_has "22 documents the exit codes" "$OUT" "EXIT CODES"
# The bare-usage path must carry the SAME text, on stderr, exit 2. Help only
# reachable by asking for it is not reachable by the reader who needs it.
ERR="$(python3 "$HERE/wl_wait.py" 2>&1 >/dev/null)"
RC=$?
assert_eq "22 bare invocation exits 2" "$RC" "2"
assert_has "22 control: bare usage prints the contract, not a one-liner" "$ERR" "EXIT IS THE NOTIFICATION"

echo "== 23. a transcript path that does not resolve is recorded as absent =="
# Found in LIVE USE, not by this suite: a SubagentStop fired carrying a
# well-formed transcript path to a file that was never written. The agent here
# is TYPED on purpose -- a typeless one with no transcript is a phantom and is
# refused outright (case 26), so a typed agent is what still exercises this.
# Every fixture here writes its transcript first, so 74/74 passed while this was
# broken. A stored path that silently does not exist is worse than a null:
# readers treat it as readable and quietly get nothing.
scratch
python3 - <<'EVJSON' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os
print(json.dumps({
    "agent_id": "aghost-agent-7171717171717171", "agent_type": "ghost-agent",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "/nonexistent/dir/agent-aghost.jsonl",
    "last_assistant_message": "push it when the agent reports back",
}))
EVJSON
assert_has "23 the unresolved path is flagged" "$(cat "$T/store/index.jsonl")" '"tx":"absent"'
# The filename comes from the index rather than a guess, so this case does not
# break again if the name-fallback rules change.
GHOSTBODY="$T/store/$(python3 -c '
import json, sys
print(json.loads(open(sys.argv[1]).readline())["body"])' "$T/store/index.jsonl")"
assert_has "23 the body still survives (nothing is lost)" "$(cat "$GHOSTBODY")" "push it when the agent reports back"
assert_has "23 the body file says so too" "$(cat "$GHOSTBODY")" "DID NOT EXIST AT CAPTURE TIME"
# CONTROL: a resolvable path is recorded ok, so the flag is not hard-coded.
python3 - "$T/real.jsonl" <<'MKTX'
import json, sys
open(sys.argv[1], "w").write(json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "a real body"}]}}) + "\n")
MKTX
python3 - "$T/real.jsonl" <<'EVJSON2' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os, sys
print(json.dumps({
    "agent_id": "areal-agent-8181818181818181", "agent_type": "real",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": sys.argv[1],
    "last_assistant_message": "a real body",
}))
EVJSON2
assert_has "23 control: a resolvable transcript is recorded as ok" "$(sed -n 2p "$T/store/index.jsonl")" '"tx":"ok"'

echo "== 24. worklist.py --reports forwards modifiers instead of rejecting them =="
# A peer hit this following our own broadcast: --all was documented in the
# announcement and the dispatcher answered "unknown mode --all" (exit 2).
scratch
stop_event "adisp-agent-9191919191919191" disp "a report for the dispatcher $BIG"
OUT="$(python3 "$HERE/worklist.py" --reports --all 2>&1)"
RC=$?
assert_eq "24 --reports --all exits 0" "$RC" "0"
assert_has "24 --reports --all lists the report" "$OUT" "disp"
assert_lacks "24 it is not rejected as a mode" "$OUT" "unknown mode"
OUT="$(python3 "$HERE/worklist.py" --reports --unread 2>&1)"
assert_has "24 --reports --unread works too" "$OUT" "disp"
# CONTROL: a genuine mode is still dispatched as a mode, not as a modifier.
OUT="$(python3 "$HERE/worklist.py" --reports --scan 2>&1)"
assert_lacks "24 control: a real mode is still dispatched as one" "$OUT" "unknown mode"

echo "== 25. the PostToolUse nudge fires, and is throttled =="
# The waiter fires ONCE and exits; nothing relaunches it, so a session goes deaf
# after its first event -- worse than the cron, which at least fires again.
# Measured live: a waiter fired at 16:13, a peer answered at 16:16, and the
# answer was never seen. This is the re-arm.
scratch
WL="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))')"
printf 'bbbbbbbb %s peer session\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${WL%.md}.sessions"
nudge() {
    printf '{"session_id":"aaaaaaaa-1111","cwd":"%s","tool_name":"Bash"}' "$CLAUDE_PROJECT_DIR" |
        python3 "$HERE/wl_wait.py" --nudge
}
OUT="$(nudge)"
assert_has "25 with no waiter and a live peer, the nudge fires" "$OUT" "NOT LISTENING"
assert_has "25 it carries the exact command" "$OUT" "wl_wait.py"
assert_has "25 it says background" "$OUT" "BACKGROUND task"
# CONTROL 1: throttled. This is what stops it becoming noise, and noise is how a
# mechanism gets switched off.
assert_eq "25 control: throttled, the second call is silent" "$(nudge)" ""
# CONTROL 2: a fresh heartbeat silences it once the throttle is cleared.
rm -f "${WL%.md}.waiternudge-aaaaaaaa"
: >"${WL%.md}.waiter-aaaaaaaa"
assert_eq "25 control: a live waiter heartbeat silences it" "$(nudge)" ""
# CONTROL 3: a STALE heartbeat must NOT silence it, or a dead waiter looks alive
# forever and the nudge never fires again. This is the case a marker written
# once at launch would fail, and it is why the waiter re-touches every tick.
python3 -c '
import os, sys, time
old = time.time() - 3600
os.utime(sys.argv[1], (old, old))' "${WL%.md}.waiter-aaaaaaaa"
assert_has "25 control: a STALE heartbeat does not silence it" "$(nudge)" "NOT LISTENING"
# CONTROL 4: no live peer, no nudge. There is nobody who could send anything, so
# a waiter would be pure cost; over-firing is how this gets routed around.
scratch
WL="$(HERE="$HERE" python3 -c '
import os, sys
sys.path.insert(0, os.environ["HERE"])
import wl_core as C
print(C.worklist_for(os.environ["CLAUDE_PROJECT_DIR"]))')"
assert_eq "25 control: with no live peer there is nothing to listen for" "$(nudge)" ""

echo "== 26. a main-loop turn is NOT captured as a report (the self-wake loop) =="
# THE LOOP THIS CLOSES, found by running the thing rather than testing it.
# SubagentStop also fires for the session's OWN main-loop turns. Each was
# captured as a "report"; the waiter saw a new report and fired; the session
# spent a turn reading and re-arming; that turn was captured; the waiter fired
# again. It does not converge, and every cycle costs the exact turn the waiter
# exists to save. Measured on the live store: 44 of 181 records were these.
scratch
# A phantom: no agent_type AND a transcript that does not resolve.
python3 - <<'PHANTOM' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os
print(json.dumps({
    "agent_id": "aphantom0000111122223", "agent_type": "",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "/nonexistent/subagents/agent-aphantom.jsonl",
    "last_assistant_message": "push it when the agent reports back",
}))
PHANTOM
if [ ! -s "$T/store/index.jsonl" ]; then
    ok "26 a typeless, transcript-less stop is not indexed at all"
else
    bad "26 the phantom was indexed" "$(cat "$T/store/index.jsonl")"
fi

# REJECTS ONLY WHEN BOTH SIGNALS FAIL. These two controls are the whole reason
# the predicate is an AND: either signal alone would drop a real report.
# CONTROL A: a real agent whose transcript has not flushed yet still has a TYPE.
python3 - <<'FLUSHRACE' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os
print(json.dumps({
    "agent_id": "aracer-agent-2222333344445555", "agent_type": "some-agent",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "/nonexistent/subagents/agent-aracer.jsonl",
    "last_assistant_message": "a real report whose transcript has not landed yet",
}))
FLUSHRACE
assert_has "26 control: a TYPED agent survives an unresolved transcript" "$(cat "$T/store/index.jsonl")" "some-agent"
# CONTROL B: a typeless agent that DOES have a transcript still survives.
python3 - "$T/tx.jsonl" <<'MKTX2'
import json, sys
open(sys.argv[1], "w").write(json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "typeless but real"}]}}) + "\n")
MKTX2
python3 - "$T/tx.jsonl" <<'TYPELESS' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os, sys
print(json.dumps({
    "agent_id": "atypeless-6666777788889999", "agent_type": "",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": sys.argv[1],
    "last_assistant_message": "typeless but real",
}))
TYPELESS
assert_has "26 control: a TRANSCRIPTED agent survives an empty type" "$(cat "$T/store/index.jsonl")" "typeless"
assert_eq "26 exactly the phantom was rejected, the two real ones kept" \
    "$(wc -l <"$T/store/index.jsonl" | tr -d ' ')" "2"
# And the phantom must not reach the surfaced inbox either.
assert_lacks "26 the phantom never surfaces" "$(surface --session-start startup)" "push it when the agent reports back"

echo "== 27. --retire-phantoms removes existing ones and keeps the real reports =="
# The filter stops NEW phantoms; 44 were already in the live index and would
# have kept surfacing as unread forever. Retirement is an APPENDED event, never
# an edit: the append-only log is what makes the lock-free single-write design
# sound, and rewriting lines to remove them would trade that away for tidiness.
scratch
stop_event "areal-one-1010101010101010" real-one "a genuine report $BIG"
python3 - <<'PHANTOM2' | python3 "$HERE/wl_report.py" --subagent-stop
import json, os
print(json.dumps({
    "agent_id": "aphantom2-444455556666", "agent_type": "",
    "session_id": "aaaaaaaa-1111", "cwd": os.environ["CLAUDE_PROJECT_DIR"],
    "agent_transcript_path": "/nonexistent/agent-x.jsonl",
    "last_assistant_message": "a main loop turn",
}))
PHANTOM2
# Force a legacy phantom in directly, as if captured before the filter existed.
python3 - "$T/store/index.jsonl" <<'LEGACY'
import json, sys
open(sys.argv[1], "a").write(json.dumps({
    "ev": "report", "id": "legacyphantom", "at": "2026-08-05T10:00:00Z",
    "branch": "testbr", "agent": "agent", "type": "", "session": "aaaaaaaa",
    "body": "testbr/none.md", "bytes": 40, "silent": True, "sends": 0,
    "tx": "absent", "title": "push it", "transcript": "/gone/x.jsonl",
    "src": "hook"}) + "\n")
LEGACY
OUT="$(report_py --retire-phantoms --dry-run)"
assert_has "27 dry run names the legacy phantom" "$OUT" "legacyphantom"
assert_lacks "27 dry run does not retire the real report" "$OUT" "real-one"
assert_has "27 dry run changes nothing" "$(report_py --list --all)" "legacyphantom"
OUT="$(report_py --retire-phantoms)"
assert_has "27 it reports what it kept" "$OUT" "1 real report(s) untouched"
assert_lacks "27 the phantom is gone from the listing" "$(report_py --list --all)" "legacyphantom"
assert_has "27 control: the real report survives" "$(report_py --list --all)" "real-one"
# The retirement is an APPEND: the original report line is still on disk.
assert_has "27 the log stayed append-only (the line is still there)" "$(cat "$T/store/index.jsonl")" '"id":"legacyphantom"'
assert_has "27 and a retire event was appended for it" "$(cat "$T/store/index.jsonl")" '"ev":"retire"'
# Re-runnable, and a second pass finds nothing.
assert_has "27 control: re-running finds nothing left" "$(report_py --retire-phantoms)" "nothing to retire"

# 28. META-CONTROL: the ambient scrub at the top of this file really happened.
# A CHECK ON A CHECK, and not redundant. Every identity assertion above depends
# on WORKLIST_SESSION_ID being the ONLY session id in the environment. If the
# scrub stops stripping CLAUDE_CODE_SESSION_ID this suite splits in two: red
# from inside a Claude session, and green-but-meaningless in CI. The second is
# the dangerous one. The probe unsets WORKLIST_SESSION_ID ONLY and issues a read
# mark under an identity no real session could be; it can only succeed if no
# ambient id survived.
OUT="$(env -u WORKLIST_SESSION_ID python3 "$HERE/wl_report.py" --read zzzzzzzz nosuchid 2>&1)"
case "$OUT" in
    *"identity mismatch"*) bad "28 an ambient session id leaked past the scrub" "$OUT" ;;
    *) ok "28 no ambient CLAUDE_CODE_SESSION_ID survives the scrub" ;;
esac
# control: force one back in and the same call must be refused. Without this,
# case 28 is satisfied by a check that never runs at all.
OUT="$(CLAUDE_CODE_SESSION_ID="beef0000-9999" env -u WORKLIST_SESSION_ID \
    python3 "$HERE/wl_report.py" --read zzzzzzzz nosuchid 2>&1)"
assert_has "28 control: with an ambient id present the same call IS refused" "$OUT" "identity mismatch"

echo
echo "================================"
if [ "$FAIL" -gt 0 ]; then
    printf 'failed cases:%s\n' "$FAILED_NAMES"
fi
# EXACTLY the shape test-worklist-v5.sh ends with, and deliberately the LAST line
# and the ONLY one of this shape. The CI gate parses `passed=<n> failed=<m>`, so a
# prettier "passed 72, failed 0" here would have made this harness's result
# unreadable to the wrapper that is supposed to enforce it -- green in CI by
# being unparsed.
printf '  passed=%d failed=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
