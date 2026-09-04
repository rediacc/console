#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner.
#
# The tracked store and /migrate. Every case here names the defect it would
# catch, because the expensive direction of this feature is silent: a store
# that reads one file and misses the rest, or a migration that moves work out
# from under a session that is still doing it, both look like success.

# A peer with remaining work, aged so no artifact says it is live.
# WHY `aged` AND NOT just "no artifacts": the phantom check owns the
# never-stopped case and answers it with --reassign. /migrate is for a session
# that DID stop. Writing a .lastevent and backdating it is what tells the two
# apart, and getting this wrong makes every case below test the wrong feature.
# EVERY CLI CALL GOES THROUGH THIS. The harness only passes TMPDIR and
# CLAUDE_PROJECT_DIR per invocation (see reqcli); a bare `python3 "$HOOK" ...`
# resolves the REAL repo worklist instead of the fixture, so the verb read its
# items from the fixture store (WORKLIST_STORE_DIR is exported) while looking
# for `.lastevent-*` beside the operator's real one -- found none, called a
# live session idle, and migrated it. Every case below depends on this.
wlcli() { TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" "$@"; }

mig_peer() { # mig_peer <prefix> <text> [minutes-old]
    local pfx="$1" text="$2" mins="${3:-180}"
    WORKLIST_SESSION_ID="$pfx" wlcli --add "$pfx" "$text" >/dev/null 2>&1
    python3 - "$WORKLIST_STORE_DIR" "$mins" <<'PYEOF'
import datetime, json, pathlib, sys
d = pathlib.Path(sys.argv[1])
old = (datetime.datetime.now(datetime.timezone.utc)
       - datetime.timedelta(minutes=int(sys.argv[2]))).strftime("%Y-%m-%dT%H:%M:%SZ")
for f in d.glob("*.jsonl"):
    lines = [json.dumps({**json.loads(l), "at": old}, separators=(",", ":"))
             for l in f.read_text().splitlines() if l.strip()]
    f.write_text("\n".join(lines) + "\n")
PYEOF
    : >"${WL%.md}.lastevent-${pfx:0:8}.json"
    python3 - "${WL%.md}.lastevent-${pfx:0:8}.json" "$mins" <<'PYEOF'
import os, sys, time
os.utime(sys.argv[1], (time.time() - int(sys.argv[2]) * 60,) * 2)
PYEOF
}

mig() { WORKLIST_SESSION_ID=deadbeef wlcli --migrate deadbeef "$@" 2>&1; }

echo "== 190. the store is a DIRECTORY of per-writer files, not one file =="
setup
say "done for now"
brief_now
wlcli --add deadbeef "an item of my own" >/dev/null 2>&1
if [[ -s "$WORKLIST_STORE_DIR/deadbeef.jsonl" ]] && [[ ! -s "${WL%.md}.events.jsonl" ]]; then
    echo "  PASS: the add landed in the tracked per-writer file, not the legacy log"
    PASS=$((PASS + 1))
else
    echo "  FAIL: wrong append target (store=$(ls "$WORKLIST_STORE_DIR" 2>/dev/null), legacy=$(wc -c <"${WL%.md}.events.jsonl" 2>/dev/null))"
    FAIL=$((FAIL + 1))
fi
# PLANT: a second writer must not touch the first's file. Two appenders on one
# path is exactly the merge conflict the layout exists to avoid.
before="$(cat "$WORKLIST_STORE_DIR/deadbeef.jsonl")"
WORKLIST_SESSION_ID=cafe1234 wlcli --add cafe1234 "a peer item" >/dev/null 2>&1
if [[ -s "$WORKLIST_STORE_DIR/cafe1234.jsonl" ]] && [[ "$before" == "$(cat "$WORKLIST_STORE_DIR/deadbeef.jsonl")" ]]; then
    echo "  PASS: a second writer gets its OWN file and leaves the first byte-identical"
    PASS=$((PASS + 1))
else
    echo "  FAIL: writers are sharing a file"
    FAIL=$((FAIL + 1))
fi

echo "== 191. the reader unions every file and SORTS -- name order is not time order =="
setup
say "done for now"
brief_now
# zz holds the older add, aa the newer tick. Concatenating in name order would
# fold the tick before the item exists and report the item as still open.
python3 - "$WORKLIST_STORE_DIR" <<'PYEOF'
import datetime, json, pathlib, sys
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.timezone.utc)
t1 = (now - datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
t2 = (now - datetime.timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
(d / "zz.jsonl").write_text(json.dumps(
    {"ev": "add", "id": "sortcase01", "at": t1, "by": "deadbeef", "s": " ",
     "o": "deadbeef", "t": "(deadbeef) ordered by time, not by filename"}) + "\n")
(d / "aa.jsonl").write_text(json.dumps(
    {"ev": "state", "id": "sortcase01", "at": t2, "by": "deadbeef", "s": "x",
     "note": "done, proven by run 123"}) + "\n")
PYEOF
if wlcli --list 2>/dev/null | grep -q '\[x\].*ordered by time'; then
    echo "  PASS: the union folds in timestamp order across files"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the tick in the name-later file was folded before its add"
    FAIL=$((FAIL + 1))
fi

echo "== 192. the LEGACY tmpdir log is still read, so nothing stopped blocking =="
setup
say "done for now"
brief_now
# PLANT: an open item that exists ONLY in the pre-move location. A reader that
# looked at the tracked store alone would let this session stop.
python3 - "${WL%.md}.events.jsonl" <<'PYEOF'
import datetime, json, sys
at = (datetime.datetime.now(datetime.timezone.utc)
      - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
open(sys.argv[1], "a").write(json.dumps(
    {"ev": "add", "id": "legacyopen1", "at": at, "by": "deadbeef", "s": " ",
     "o": "deadbeef", "t": "(deadbeef) only in the legacy log"}) + "\n")
PYEOF
check "an open item living only in the legacy log still blocks" block "only in the legacy log"

echo "== 193. --migrate REFUSES a session that is live here =="
setup
say "done for now"
brief_now
mig_peer livepeer1 "(livepeer1) work of a running session" 180
: >"${WL%.md}.lastevent-livepeer.json" # fresh: written this second
OUT="$(mig livepeer1)"
if [[ "$OUT" == *"REFUSED"* ]] && [[ "$OUT" == *"lastevent"* ]]; then
    echo "  PASS: a live session is refused, and the refusal names the artifact"
    PASS=$((PASS + 1))
else
    echo "  FAIL: migrated (or refused without evidence) a LIVE session: $OUT"
    FAIL=$((FAIL + 1))
fi
# CONTROL ON THE CONTROL: the same peer, artifact backdated, must migrate.
# Without this the case above would also pass if the verb refused everything.
python3 - "${WL%.md}.lastevent-livepeer.json" <<'PYEOF'
import os, sys, time
os.utime(sys.argv[1], (time.time() - 7200,) * 2)
PYEOF
OUT="$(mig livepeer1)"
if [[ "$OUT" == *"migrated 1 item"* ]]; then
    echo "  PASS: CONTROL: the SAME peer migrates once its artifact is stale"
    PASS=$((PASS + 1))
else
    echo "  FAIL: CONTROL: refusal is unconditional, so case 193 proves nothing: $OUT"
    FAIL=$((FAIL + 1))
fi

echo "== 194. a migrated item is MINE, and the original is closed =="
setup
say "done for now"
brief_now
mig_peer oldsess1 "(oldsess1) the stranded work"
mig oldsess1 >/dev/null
if wlcli --list --open deadbeef 2>/dev/null | grep -q 'the stranded work'; then
    echo "  PASS: the item is now in MY open slice, so the Stop hook blocks on it"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the migrated item is not owned by me"
    FAIL=$((FAIL + 1))
fi
if wlcli --list 2>/dev/null | grep -q 'migrated to #'; then
    echo "  PASS: the original is ticked with a note naming the new id"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the original was not closed, so the work is now double-counted"
    FAIL=$((FAIL + 1))
fi

echo "== 195. idempotent: a second run moves nothing =="
OUT="$(mig oldsess1)"
if [[ "$OUT" == *"nothing left to migrate"* ]]; then
    echo "  PASS: a second migration is a no-op that says so"
    PASS=$((PASS + 1))
else
    echo "  FAIL: re-migrating duplicated the work: $OUT"
    FAIL=$((FAIL + 1))
fi

echo "== 196. an in-flight item arrives OPEN, with its dead lease reset =="
setup
say "done for now"
brief_now
mig_peer leasesess "(leasesess) leased to a worker that died with its session"
ITEM="$(wlcli --list 2>/dev/null | grep -o '#[0-9a-f]\{8,\}' | head -1 | tr -d '#')"
WORKLIST_SESSION_ID=leasesess wlcli --lease leasesess "$ITEM" +60 worker:ghost1 "held" >/dev/null 2>&1
mig leasesess >/dev/null
if wlcli --list --open deadbeef 2>/dev/null | grep -q '\[ \].*leased to a worker'; then
    echo "  PASS: the lease is reset, so the liveness ladder can ask about it again"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the item arrived still leased to a worker on the other machine"
    FAIL=$((FAIL + 1))
fi

echo "== 197. a deferral keeps its DEFAULT window rather than restarting it =="
setup
say "done for now"
brief_now
mig_peer defersess "(defersess) a question for the operator"
ITEM="$(wlcli --list 2>/dev/null | grep -o '#[0-9a-f]\{8,\}' | head -1 | tr -d '#')"
WORKLIST_SESSION_ID=defersess wlcli --defer defersess "$ITEM" \
    "which branch? DEFAULT: use main WHY: it is the base HOW: rerun the gate" >/dev/null 2>&1
mig defersess >/dev/null
# The window is measured from `upd`. Carried, the item is already ~180 min old
# (mig_peer aged it) and its default is due; restarted, it would read as fresh.
if wlcli --list --open deadbeef 2>/dev/null | grep -q '\[?\]'; then
    echo "  PASS: the deferral arrives as a deferral, not as a plain open item"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the [?] state was lost in the move"
    FAIL=$((FAIL + 1))
fi

echo "== 198. --migrate refuses ME, and refuses a prefix with no events =="
setup
say "done for now"
brief_now
OUT="$(mig deadbeef)"
[[ "$OUT" == *"already yours"* ]] &&
    {
        echo "  PASS: migrating from myself is refused"
        PASS=$((PASS + 1))
    } ||
    {
        echo "  FAIL: self-migration was allowed: $OUT"
        FAIL=$((FAIL + 1))
    }
OUT="$(mig nosuchse)"
[[ "$OUT" == *"REFUSED"* ]] &&
    {
        echo "  PASS: a prefix with no events is refused"
        PASS=$((PASS + 1))
    } ||
    {
        echo "  FAIL: migrated from a session that never existed: $OUT"
        FAIL=$((FAIL + 1))
    }

echo "== 199. the Stop hook names a stopped session's work, and never blocks on it =="
setup
say "done for now"
brief_now
mig_peer handoff1 "(handoff1) work its session left behind"
export WORKLIST_REPORT_PER_STOP=6
check "a stopped peer's work is REPORTED, never blocked on" allow "HANDOFF CANDIDATES"
unset WORKLIST_REPORT_PER_STOP
# CONTROL: a LIVE peer is not a handoff candidate -- its work is not yours.
setup
say "done for now"
brief_now
mig_peer handoff2 "(handoff2) work of a running session"
: >"${WL%.md}.lastevent-handoff2.json"
export WORKLIST_REPORT_PER_STOP=6
OUT="$(run 2>&1)"
if [[ "$OUT" != *"HANDOFF CANDIDATES"* ]]; then
    echo "  PASS: CONTROL: a LIVE peer is never offered for handoff"
    PASS=$((PASS + 1))
else
    echo "  FAIL: CONTROL: offered a live session's work for adoption"
    FAIL=$((FAIL + 1))
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 200. --doctor catches what a TRACKED file makes possible =="
setup
say "done for now"
brief_now
# Every plant is a shape that is SILENT by default: the reader skips
# unparseable lines by contract, so a conflict marker costs events and says
# nothing, and a secret in TMPDIR was private while a secret here is pushed.
printf '<<<<<<< HEAD\n{"ev":"add","id":"docok1","at":"2026-09-04T00:00:00Z","by":"deadbeef","s":" ","o":"deadbeef","t":"fine"}\nnot json at all\n{"ev":"add","id":"docok2","at":"2026-09-04T00:00:01Z","by":"deadbeef","s":" ","o":"deadbeef","t":"tok ghp_abcdefghijklmnopqrstuvwxyz0123456789"}\n' >"$WORKLIST_STORE_DIR/planted.jsonl"
OUT="$(wlcli --doctor 2>&1)"
RC=$?
if [[ "$RC" -ne 0 ]] && [[ "$OUT" == *"merge conflict marker"* ]] &&
    [[ "$OUT" == *"unparseable"* ]] && [[ "$OUT" == *"secret-shaped"* ]]; then
    echo "  PASS: conflict markers, torn lines and a secret shape are all named"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --doctor missed a planted defect (rc=$RC): ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi
# The secret SHAPE is named and the value is not echoed back: printing it would
# be the leak this check exists to prevent.
if [[ "$OUT" != *"ghp_abcdefghijklmnopqrstuvwxyz0123456789"* ]]; then
    echo "  PASS: the finding names the shape, never the value"
    PASS=$((PASS + 1))
else
    echo "  FAIL: --doctor echoed the secret it was reporting"
    FAIL=$((FAIL + 1))
fi
# CONTROL: without the plants it must pass, or case 200 proves only that
# --doctor always fails.
rm -f "$WORKLIST_STORE_DIR/planted.jsonl"
OUT="$(wlcli --doctor 2>&1)"
if [[ $? -eq 0 ]] && [[ "$OUT" == *"store OK"* ]]; then
    echo "  PASS: CONTROL: a clean store passes"
    PASS=$((PASS + 1))
else
    echo "  FAIL: CONTROL: --doctor fails even on a clean store: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 201. compaction NEVER rewrites a file a live peer is appending to =="
setup
say "done for now"
brief_now
wlcli --add deadbeef "my own item" >/dev/null 2>&1
WORKLIST_SESSION_ID=deadpeer wlcli --add deadpeer "a dead peer item" >/dev/null 2>&1
WORKLIST_SESSION_ID=livepeer wlcli --add livepeer "a LIVE peer item" >/dev/null 2>&1
# deadpeer's events aged past WORKLIST_DEAD_HOURS; livepeer left fresh.
python3 - "$WORKLIST_STORE_DIR" <<'PYEOF'
import datetime, json, pathlib, sys
f = pathlib.Path(sys.argv[1]) / "deadpeer.jsonl"
old = (datetime.datetime.now(datetime.timezone.utc)
       - datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
f.write_text("\n".join(json.dumps({**json.loads(l), "at": old}, separators=(",", ":"))
                       for l in f.read_text().splitlines() if l.strip()) + "\n")
PYEOF
: >"${WL%.md}.lastevent-livepeer.json"
OUT="$(wlcli --compact 2>&1)"
if [[ -f "$WORKLIST_STORE_DIR/livepeer.jsonl" ]] && [[ "$OUT" == *"kept livepeer.jsonl"* ]]; then
    echo "  PASS: the live peer's file is untouched, and the reason is printed"
    PASS=$((PASS + 1))
else
    echo "  FAIL: compaction rewrote a file a live session is still appending to"
    FAIL=$((FAIL + 1))
fi
if [[ ! -f "$WORKLIST_STORE_DIR/deadpeer.jsonl" ]]; then
    echo "  PASS: the dead writer's file is absorbed"
    PASS=$((PASS + 1))
else
    echo "  FAIL: nothing was compacted, so this case proves nothing"
    FAIL=$((FAIL + 1))
fi
# THE PROPERTY THAT MATTERS: no item may be lost, whichever files moved.
N="$(wlcli --list 2>/dev/null | grep -c 'own item\|dead peer item\|LIVE peer item')"
if [[ "$N" -eq 3 ]]; then
    echo "  PASS: all three items survive the compaction"
    PASS=$((PASS + 1))
else
    echo "  FAIL: compaction lost items (found $N of 3)"
    FAIL=$((FAIL + 1))
fi
