#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The phantom-stop guard, unread sub-agent reports, waiter-confirmation controls, and stuck output-stream detection.

echo "== 163x. NO CLI verb may fall through to the Stop battery (the phantom stop) =="
# THE DEFECT, measured on HEAD before the fix, not theorised. A verb whose guard
# put the arity check INSIDE the condition (`len(argv) > 3 and argv[1] ==
# "--loop"`) did not fail on too few arguments -- it fell through to the hook
# path, which runs the whole battery against an EMPTY event. With stdin closed
# that returned a genuine `"decision": "block"` at EXIT 0 and wrote six
# `*-unknown` sidecars for a session id that does not exist; with stdin left open
# it hung forever in json.load(sys.stdin). Both reproduced.
#
# The fix is the CLASS, not the three verbs anyone noticed: any argv[1] with a
# leading dash that matched no verb is refused. A typo must not be able to emit a
# verdict or hang.
setup
for _bad in "--loop x" "--brief" "--tpyo" "--state"; do
    # shellcheck disable=SC2086
    OUT="$(reqcli $_bad </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "2" ]] && ! grep -qF '"decision": "block"' <<<"$OUT"; then
        pass "163x: '$_bad' is refused (exit 2) and emits NO verdict"
    else
        fail "163x: '$_bad' rc=$RC verdict=${OUT:0:120}"
    fi
done
# It must not hang either. stdin is a pipe that STAYS OPEN, and the timeout is on
# the interpreter itself -- NOT on a shell wrapping a `sleep`, which is what made
# the first measurement of this read 124 for the sleep rather than for python.
if timeout 8 env TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$HOOK" --tpyo < <(sleep 15) >/dev/null 2>&1; then
    fail "163x: an unknown verb succeeded, which it must not"
elif [[ "$?" != "124" ]]; then
    pass "163x: an unknown verb does not hang on an open stdin"
else
    fail "163x: an unknown verb still hangs reading stdin"
fi
# CONTROL 1: the legitimate forms still work, so the guards refuse arity and not
# the verb.
setup
if as_peer looppfx1 reqcli --loop looppfx1 2026-01-01T00:00:00Z 1 label </dev/null 2>&1 | grep -qF "loop declared"; then
    pass "163x CONTROL: a well-formed --loop still declares"
else
    fail "163x CONTROL: --loop broke for valid input"
fi
if as_peer briefpf1 reqcli --brief briefpf1 some text </dev/null 2>&1 | grep -qF "brief recorded"; then
    pass "163x CONTROL: a well-formed --brief still records"
else
    fail "163x CONTROL: --brief broke for valid input"
fi
# 163g: a LONE ITEM ID is a misread of the verb, not a very short brief. The word
# reads both ways (publish a brief / brief me on X) and `--brief <me> <text...>`
# is `--tick <me> <id> <evidence>` minus the evidence, so the id lands where the
# sentence goes. Paid for live: a session meaning to READ item 65ce7ca3 published
# it, and the roster then advertised "65ce7ca3" as that session's live activity to
# every later reader. Both real id widths are covered, since ids are 8 or 12 hex
# and the code must never assume one width.
#
# CAPTURE THEN MATCH, never `refusing-command | grep -q`. This suite runs under
# `set -uo pipefail` (line 5), so a pipeline carries the FIRST non-zero exit, not
# grep's. The refusal exits 2 by design, which made the pipeline false while grep
# was matching perfectly: the first version of these cases failed on a green tree
# and, worse, also failed under a mutation that disabled the guard, so its red
# proved nothing. Every other refusal case here captures first for this reason.
for _wid in 65ce7ca3 a1b2c3d4e5f6; do
    OUT="$(as_peer briefpf2 reqcli --brief briefpf2 "$_wid" </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "2" ]] && grep -qF "shape of an item id" <<<"$OUT"; then
        pass "163g a bare ${#_wid}-char id is refused as a brief"
    else
        fail "163g a bare ${#_wid}-char id: rc=$RC out=${OUT:0:90}"
    fi
done
# The controls that keep the refusal from swallowing real briefs: the discriminator
# is a LONE all-hex token of id width, so anything with a second word, any non-hex
# character, or a length outside the band must still record.
while IFS='|' read -r _why _txt; do
    # Deliberately unquoted: word-splitting is the point, since these controls
    # exist to prove a MULTI-token brief still records.
    # shellcheck disable=SC2086
    OUT="$(as_peer briefpf3 reqcli --brief briefpf3 $_txt </dev/null 2>&1)"
    RC=$?
    if [[ "$RC" == "0" ]] && grep -qF "brief recorded" <<<"$OUT"; then
        pass "163g CONTROL: $_why still records"
    else
        fail "163g CONTROL: $_why was wrongly refused (rc=$RC)"
    fi
done <<'BRIEFOK'
an id followed by real words|65ce7ca3 is what I am reading
a short non-hex word|triage
a hex string past the id width|abcdefabcdefabcde
a hex string under the id width|abcde
BRIEFOK
# CONTROL 2, THE LOAD-BEARING ONE: the real Stop hook takes NO arguments, so the
# leading-dash catch-all must not be able to swallow it. If this regressed, every
# stop in the repo would exit 2 instead of running any check at all.
setup
brief_now
hand_now
say "answer"
task 7 pending "something"
OUT="$(run)"
if grep -qF '"decision"' <<<"$OUT" || [[ -n "$OUT" ]]; then
    pass "163x CONTROL: a bare (no-argv) invocation still runs the battery"
else
    fail "163x CONTROL: the catch-all swallowed the real hook: '${OUT:0:200}'"
fi

echo "== 163y. v18: unread sub-agent reports are surfaced on an ORDINARY stop =="
# SessionStart and PostCompact are covered by wl_report's own hooks. This is the
# commoner case they miss: a long-running session whose teammate finished twenty
# minutes ago and whose SendMessage has scrolled out of reach. Report-only: an
# unread report is information, not an obligation, and there is no honest
# evidence a stop could demand for "I read it".
setup
brief_now
hand_now
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "agenttest").mkdir(parents=True, exist_ok=True)
(store / "agenttest" / "r.md").write_text("SUBSTANTIVE FINDING FROM A TEAMMATE\nbody")
(store / "index.jsonl").write_text(json.dumps({
    "ev": "report", "id": "abcdef123456", "at": "2026-08-05T10:00:00Z",
    "branch": "agenttest", "agent": "some-teammate", "type": "some-teammate",
    "session": "deadbeef", "body": "agenttest/r.md", "bytes": 900,
    "silent": False, "sends": 1, "title": "SUBSTANTIVE FINDING FROM A TEAMMATE",
    "transcript": "", "src": "hook"}) + "\n")
PYEOF
say "all done, nothing outstanding"
OUT="$(run)"
if grep -qF "UNREAD SUB-AGENT REPORTS" <<<"$OUT" && grep -qF "SUBSTANTIVE FINDING FROM A TEAMMATE" <<<"$OUT"; then
    pass "163y: an unread report is surfaced on an ordinary stop, with its title"
else
    fail "163y: no unread-report section: ${OUT:0:300}"
fi
if ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "163y: it is REPORT-ONLY and does not block the stop"
else
    fail "163y: an unread report blocked the stop: ${OUT:0:300}"
fi
# CONTROL: marked read, the section is gone. Without this the assertion above is
# satisfied by any section that is simply always emitted.
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "read.jsonl").write_text(json.dumps({
    "ev": "read", "id": "abcdef123456", "by": "deadbeef",
    "at": "2026-08-05T10:05:00Z", "branch": "agenttest"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "UNREAD SUB-AGENT REPORTS" <<<"$OUT"; then
    pass "163y CONTROL: once marked read, the section is gone"
else
    fail "163y CONTROL: a read report is still surfaced: ${OUT:0:300}"
fi
# CONTROL: a report on ANOTHER branch is not this branch's business.
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
with (store / "index.jsonl").open("a") as f:
    f.write(json.dumps({
        "ev": "report", "id": "999999999999", "at": "2026-08-05T10:00:00Z",
        "branch": "some-other-branch", "agent": "elsewhere", "type": "elsewhere",
        "session": "deadbeef", "body": "x/y.md", "bytes": 900, "silent": False,
        "sends": 1, "title": "FROM ANOTHER BRANCH", "transcript": "",
        "src": "hook"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "FROM ANOTHER BRANCH" <<<"$OUT"; then
    pass "163y CONTROL: another branch's report is not surfaced here"
else
    fail "163y CONTROL: a foreign branch's report leaked in: ${OUT:0:300}"
fi

echo "== 163z-c1. CONTROL: a waiter that is NOT confirmed buys nothing =="
# Same fixture, same command string, but the process is DEAD -- so the verdict is
# `suspect`. Without this control, 163z would equally pass if the code had simply
# stopped running either check at all.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
export WORKLIST_HARNESS_PID=$$
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([{"id": "wt1", "type": "shell", "status": "running",
                   "command": sys.argv[1], "description": "inbox waiter (dead)"}]))
PYEOF
)"
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
task 7 in_progress "waiting on the inbox"
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on the inbox (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z-c1 CONTROL: an unconfirmed waiter still owes the check-in"
else
    fail "163z-c1 CONTROL: the check-in was skipped for a DEAD waiter: ${OUT:0:250}"
fi

echo "== 163z-c2. CONTROL: a waiter does not silence a REAL job running beside it =="
# Relaxing on "any waiter present" would let one waiter suppress supervision of
# everything else. The suppression requires EVERY live task to be a confirmed
# waiter, and this is the case that pins that word.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'worker stream content\n' >"$BASE/bgout/bw1.output"
TMPDIR="$BASE/waittmp2" CLAUDE_PROJECT_DIR="$BASE" $WAITER_CMD >/dev/null 2>&1 &
WAITER_PID=$!
export WORKLIST_HARNESS_PID=$$
sleep 1
BG="$(
    python3 - "$WAITER_CMD" <<'PYEOF'
import json, sys
print(json.dumps([
    {"id": "wt1", "type": "shell", "status": "running", "command": sys.argv[1],
     "description": "inbox waiter"},
    {"id": "bw1", "type": "shell", "status": "running", "command": "sleep 999",
     "description": "long CI watch"},
]))
PYEOF
)"
task 7 in_progress "waiting on both"
say "answer

## Remaining
- #7 waiting on both (in_progress)"
run >/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 waiting on both (in_progress)"
OUT="$(run)"
if grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163z-c2 CONTROL: a real job beside the waiter still gets its check-in"
else
    fail "163z-c2 CONTROL: one waiter silenced supervision of a real job: ${OUT:0:250}"
fi
kill "$WAITER_PID" 2>/dev/null
wait "$WAITER_PID" 2>/dev/null
unset WORKLIST_HARNESS_PID

echo "== 163b. a stale output stream is flagged POSSIBLY STUCK =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bw2.output"
touch -d '25 minutes ago' "$BASE/bgout/bw2.output"
BG='[{"id":"bw2","type":"shell","status":"running","description":"quiet worker"}]'
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "POSSIBLY STUCK" <<<"$OUT"; then
    pass "163b: a 25-minute-silent stream is called out"
else
    fail "163b: stale stream not flagged: ${OUT:0:300}"
fi

echo "== 163c. CONTROL: an open item means normal battery, no wait check-in =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
BG='[{"id":"bw3","type":"shell","status":"running","description":"worker"}]'
echo '- [ ] (deadbeef) real open work' >>"$WL"
say "answer

## Remaining
- the open work"
OUT="$(run)"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR
if ! grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163c CONTROL: open work suppresses the wait check-in"
else
    fail "163c: check-in fired despite open work: ${OUT:0:250}"
fi

echo "== 163d. a due check-in forfeits the silent poll; a fresh one does not =="
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'stream\n' >"$BASE/bgout/bw4.output"
BG='[{"id":"bw4","type":"shell","status":"running","description":"watch"}]'
task 6 in_progress "the live prerequisite"
task 7 pending "thing" 6 # v19: blocked scenery so the pure-wait premise holds
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # establishes the bgwait mark via the first check-in
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -z "$OUT" ]]; then
    pass "163d: a fresh check-in mark keeps the silent poll"
else
    fail "163d: poll paid the battery inside the window: ${OUT:0:200}"
fi
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
BG='[]'
unset WORKLIST_BG_OUTPUT_DIR
if [[ -n "$OUT" ]] && grep -qF "PURE BACKGROUND WAIT" <<<"$OUT"; then
    pass "163d CONTROL: a due check-in forfeits the silent poll and delivers the facts"
else
    fail "163d CONTROL: due check-in stayed silent: ${OUT:0:200}"
fi

echo "== 163e. the output-stream path DERIVATION finds the claude-<uid> layout =="
# Regression gate for 9b557ab0e: every other 163 case overrides the base via
# WORKLIST_BG_OUTPUT_DIR, so the derivation itself was untested and its first
# live firing missed the claude-<uid> segment. This case exercises the real
# derivation end to end: no override, TMPDIR pointed at a fixture root, the
# stream living exactly where the harness writes it.
setup
FAKETMP="$BASE/faketmp"
SID_FULL="b9491d9c-full-session-id-fixture"
MUNGED="-x-y" # re.sub non-alnum -> '-' of cwd "/x/y"
mkdir -p "$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks"
printf 'stream\n' >"$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks/bw5.output"
FOUND=$(
    TMPDIR="$FAKETMP" python3 - "$SID_FULL" "$HOOK" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(sys.argv[2]))
import tempfile
tempfile.tempdir = None  # re-read TMPDIR
import wl_liveness
rows = wl_liveness.bg_output_facts("/x/y", sys.argv[1],
    [{"id": "bw5", "status": "running", "description": "d"}])
print("found" if rows and rows[0][2] is not None else "missing")
PYEOF
)
if [[ "$FOUND" == "found" ]]; then
    pass "163e: the real derivation locates the claude-<uid> stream layout"
else
    fail "163e: derivation missed the claude-<uid> layout (got: $FOUND)"
fi
# CONTROL: with the stream ABSENT the same call reports missing, so the case
# cannot pass vacuously on a derivation that never stats anything.
rm -f "$FAKETMP/claude-$(id -u)/$MUNGED/$SID_FULL/tasks/bw5.output"
FOUND=$(
    TMPDIR="$FAKETMP" python3 - "$SID_FULL" "$HOOK" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(sys.argv[2]))
import tempfile
tempfile.tempdir = None
import wl_liveness
rows = wl_liveness.bg_output_facts("/x/y", sys.argv[1],
    [{"id": "bw5", "status": "running", "description": "d"}])
print("found" if rows and rows[0][2] is not None else "missing")
PYEOF
)
if [[ "$FOUND" == "missing" ]]; then
    pass "163e CONTROL: an absent stream reads as missing, the probe is real"
else
    fail "163e CONTROL: vacuous probe (got: $FOUND)"
fi

echo "== 163f. a stale stream with a VERIFIED-ALIVE OS process is not called stuck =="
# Fired live 2026-07-31: a healthy `until ... completed` CI poll loop, silent
# by design for 29 minutes, was accused POSSIBLY STUCK. Two fixes pinned here
# at once: _needle must extract a quote-free SEGMENT (the poll-loop command
# has a quoted middle, so the old whole-line rule made it unverifiable), and
# the check-in must consult verify_background before accusing.
setup
brief_now
hand_now
mkdir -p "$BASE/bgout"
export WORKLIST_BG_OUTPUT_DIR="$BASE/bgout"
printf 'old content\n' >"$BASE/bgout/bw6.output"
touch -d '25 minutes ago' "$BASE/bgout/bw6.output"
sleep 3717171717 &
PROBE163F=$!
export WORKLIST_HARNESS_PID=$$
# The quoted tail is load-bearing: the OLD _needle refused any line carrying
# a quote, which is exactly how the live worker became unverifiable.
BG='[{"id":"bw6","type":"shell","status":"running","description":"silent poll loop","command":"sleep 3717171717 \"# ci watch tail\""}]'
task 7 pending "thing"
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null # seed the wait clock
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "VERIFIED ALIVE" <<<"$OUT" && ! grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT"; then
    # NOT a plain "POSSIBLY STUCK" grep: V_BG_REPORT's fixed instruction text
    # says "restart or replace anything marked POSSIBLY STUCK" on every
    # check-in, so only the per-row "<- POSSIBLY STUCK" marker is the accusation.
    pass "163f: a stale stream backed by a live OS process is reported alive, not stuck"
else
    fail "163f: alive worker still accused, or not reported: ${OUT:0:300}"
fi
# CONTROL: kill the process and the SAME setup goes back to POSSIBLY STUCK,
# so the rescue is the verification, not an unconditional soft-pedal.
kill "$PROBE163F" 2>/dev/null
wait "$PROBE163F" 2>/dev/null
python3 - "$WL" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1].replace(".md", ".state-deadbeef.json"))
doc = json.loads(p.read_text())
doc["bgwait"] = {"at": "2026-01-01T00:00:00Z"}
p.write_text(json.dumps(doc))
PYEOF
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF -- "<- POSSIBLY STUCK" <<<"$OUT" && ! grep -qF "VERIFIED ALIVE" <<<"$OUT"; then
    pass "163f CONTROL: with the process dead the same worker is called out as stuck"
else
    fail "163f CONTROL: dead worker not flagged: ${OUT:0:300}"
fi
unset WORKLIST_HARNESS_PID
unset WORKLIST_BG_OUTPUT_DIR
BG='[]'

# ---------------------------------------------------------------------------
# v16 (cases 164+): the fix-in-session rule. A finding is fixed by the session
# that finds it, so --triage answers the size question and hands back the exact
# next command, --tick refuses a completion whose only evidence is an issue
# reference, and agent/PLAN-*.md becomes a durable design record
# the SessionStart and PostCompact hooks hand back. Every FIRE case is paired
# with a SILENT control differing by one planted fact.
# ---------------------------------------------------------------------------

EVENTS="${WL%.md}.events.jsonl"

triage() { # triage <judge-mode> <args...> -- the --triage verb, judge pinned
    local mode="$1"
    shift
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_AGENT_BRANCH=agenttest WORKLIST_JUDGE="$mode" \
        python3 "$HOOK" --triage "$@"
}
