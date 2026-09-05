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

# Age EVERY event in the store, and the peer's .lastevent with it. A case that
# leases or defers as the peer writes a FRESH event, which makes liveness say
# "wrote to the store 0 min ago" -- correctly, that is a session still acting --
# and the migration is then refused. Re-age after such a write to model a peer
# that has since stopped.
age_store() { # age_store <prefix> [minutes-old]
    local pfx="$1" mins="${2:-180}"
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
# BY THE ITEM'S OWN TEXT, not `head -1` over the whole listing: that took the
# first id that happened to sort first, which is another session's item as often
# as the peer's, so the lease landed on the wrong thing and the migration then
# had nothing leased to carry.
ITEM="$(wlcli --list 2>/dev/null | grep 'leased to a worker' | grep -o '#[0-9a-f]\{8,\}' | head -1 | tr -d '#')"
[[ -n "$ITEM" ]] || echo "  FAIL: could not find the peer's item to lease"
WORKLIST_SESSION_ID=leasesess wlcli --lease leasesess "$ITEM" +60 worker:ghost1 "held" >/dev/null 2>&1
age_store leasesess # the lease above was a FRESH write; the peer must read as stopped
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
ITEM="$(wlcli --list 2>/dev/null | grep 'a question for the operator' | grep -o '#[0-9a-f]\{8,\}' | head -1 | tr -d '#')"
[[ -n "$ITEM" ]] || echo "  FAIL: could not find the peer's item to defer"
WORKLIST_SESSION_ID=defersess wlcli --defer defersess "$ITEM" \
    "which branch? DEFAULT: use main WHY: it is the base HOW: rerun the gate" >/dev/null 2>&1
age_store defersess # same reason as the lease case above
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
NOW_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '<<<<<<< HEAD\n{"ev":"add","id":"docok1","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"fine"}\nnot json at all\n{"ev":"add","id":"docok2","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"tok ghp_abcdefghijklmnopqrstuvwxyz0123456789"}\n' "$NOW_TS" "$NOW_TS" >"$WORKLIST_STORE_DIR/planted.jsonl"
ls -la "$WORKLIST_STORE_DIR" >/dev/null
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
# CONTROL: without the PLANTS it must pass, or case 200 proves only that
# --doctor always fails. The store must still hold a VALID file: --doctor
# refuses an empty store outright (a check that scanned nothing is not a pass),
# so deleting the plant and leaving the directory bare would test that refusal
# instead of the clean-store path.
rm -f "$WORKLIST_STORE_DIR/planted.jsonl"
printf '{"ev":"add","id":"docclean1","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"a clean event"}\n' \
    "$NOW_TS" >"$WORKLIST_STORE_DIR/clean.jsonl"
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

echo "== 202. THE TIED CASE: same second, and file order contradicts write order =="
setup
say "done for now"
brief_now
# `at` has SECOND resolution, so a judge reopen and a session tick inside one
# second TIE. Sorting on `at` alone left the tie to file-glob order, and a
# ticked item came back OPEN (case 150 caught it live). The nanosecond sequence
# is what restores real write order -- and the file names below deliberately
# contradict it, so a sort that ignored `ns` would get this backwards.
python3 - "$WORKLIST_STORE_DIR" <<'PYEOF'
import datetime, json, pathlib, sys, time
d = pathlib.Path(sys.argv[1])
# ONE second for both events, on purpose -- but DERIVED, not a literal. What the
# case needs is that the two stamps are equal, not that they name a fixed day,
# and a literal here would age exactly as the two fixtures did earlier in this
# wave (a retention window, then a fold order).
at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
later = time.time_ns()
(d / "zzz.jsonl").write_text(
    json.dumps({"ev": "add", "id": "tiecase001", "at": at, "ns": later - 1000,
                "by": "deadbeef", "s": " ", "o": "deadbeef",
                "t": "(deadbeef) written first, in the name-LATER file"}) + "\n")
(d / "aaa.jsonl").write_text(
    json.dumps({"ev": "state", "id": "tiecase001", "at": at, "ns": later,
                "by": "judge", "s": "x", "note": "closed later in the same second"}) + "\n")
PYEOF
if wlcli --list 2>/dev/null | grep -q '\[x\].*written first'; then
    echo "  PASS: within one second the LATER write wins, whatever the filename"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the tie was broken by filename, not by write order"
    FAIL=$((FAIL + 1))
fi
# CONTROL ON THE CONTROL: strip `ns` and the same two events must fold the OTHER
# way. Without this the case would pass just as well if `ns` did nothing.
python3 - "$WORKLIST_STORE_DIR" <<'PYEOF'
import json, pathlib, sys
for name in ("aaa.jsonl", "zzz.jsonl"):
    p = pathlib.Path(sys.argv[1]) / name
    e = json.loads(p.read_text())
    e.pop("ns", None)
    p.write_text(json.dumps(e) + "\n")
PYEOF
if wlcli --list 2>/dev/null | grep -q '\[ \].*written first'; then
    echo "  PASS: CONTROL: without ns the tie really does fall back to file order"
    PASS=$((PASS + 1))
else
    echo "  FAIL: CONTROL: ns is not the deciding field, so this case proves nothing"
    FAIL=$((FAIL + 1))
fi

echo "== 203. the fixture owns BOTH halves of the store, so no call can straddle them =="
# WHAT THIS CATCHES, and it is not hypothetical -- it happened to the operator's
# own worklist on 2026-09-04. The store has two halves that resolve from
# DIFFERENT places: the tracked writer files come from WORKLIST_STORE_DIR, while
# the legacy event log, the markdown mirror and the `.lastevent-*` liveness
# artifacts all resolve from the worklist path under TMPDIR. setup() exported
# only the first and left TMPDIR to a per-invocation prefix at seven call sites.
# One call without that prefix therefore read items from the FIXTURE store and
# resolved the legacy half against the REAL /tmp/claude-worklist -- and since
# compact() folds both halves and rewrites the legacy file from the union, three
# fixture items from this file's own neighbourhood ("my own item", "a dead peer
# item", "a LIVE peer item", added at the lines above) were written into the
# operator's real worklist, where the Stop hook reported them as open work every
# round. Worse, they arrived owned by prefixes that never wrote under their own
# name, which put them beyond every sanctioned verb at once: --tick refuses
# another session's item, and --reassign refused the same item as having
# "written no events at all".
#
# THE ASSERTION IS ON `--path`, DELIBERATELY. The first version of this case
# asserted that a bare `--compact` wrote the fixture's legacy event log, and it
# FAILED for a reason that had nothing to do with the straddle: compact()
# returns early when that file does not exist yet, so the case tested an
# artifact the fix never produces, and its inverted control "passed" for the
# same empty reason. `--path` prints the resolved worklist, which is the one
# thing the straddle actually gets wrong, and it is the shortest statement of
# what must be true.
#
# It is also deliberately about a BARE invocation. Fixing the seven call sites
# would leave the eighth free to reintroduce this; exporting both halves
# together is what makes the straddle unrepresentable, and this case fails if
# anyone unpairs them again.
setup
OUT="$(CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path 2>/dev/null)"
if [[ "$OUT" == "$BASE"/* ]]; then
    echo "  PASS: a bare invocation resolved the worklist inside the fixture"
    PASS=$((PASS + 1))
else
    echo "  FAIL: a bare invocation resolved the worklist to $OUT, outside \$BASE -- it straddled"
    FAIL=$((FAIL + 1))
fi
# CONTROL ON THE CONTROL: the assertion above must actually be sensitive to
# TMPDIR, or it would pass just as well if TMPDIR did nothing here -- which is
# precisely the false comfort that let the original leak through. Point one
# invocation at a THIRD directory and the resolved path must follow it.
mkdir -p "$BASE/other"
OUT="$(TMPDIR="$BASE/other" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path 2>/dev/null)"
if [[ "$OUT" == "$BASE/other"/* ]]; then
    echo "  PASS: CONTROL: TMPDIR really is what steers the worklist half"
    PASS=$((PASS + 1))
else
    echo "  FAIL: CONTROL: TMPDIR does not steer the worklist ($OUT), so 203 proves nothing"
    FAIL=$((FAIL + 1))
fi

echo "== 204. compaction is LOSSLESS: the fold before equals the fold after =="
# WHY THIS EXISTS, and why it is a property and not another example. Compaction
# rewrites the whole log as a fresh snapshot, so every field the fold reads has
# to survive a round trip through snapshot_events. The suite tested compaction
# by its OUTPUTS -- items consolidated, a live peer's file untouched, three
# items still present -- and an output test only ever checks the fields the
# author happened to name. The field that went missing was the one nobody
# asserted: `by` is rewritten to "compact", which is deliberate, and `o` is the
# only thing left naming whose work an item is. Two readers scanned `by` and
# went blind on every compacted store (case 190b), and the cost was an item that
# --tick refused as another session's while --reassign refused it as having
# written no events at all.
#
# So this case asserts the INVARIANT rather than a field: fold(store) must equal
# fold(compact(store)), across every key a record carries -- basetext, first,
# id, lastnote, line, origin, owner, state, text, upd -- for an item in every
# state the store can hold. A field added to the fold later is covered the day
# it is added, with no edit here, which is the property an example-based case
# cannot have.
setup
IID_OPEN=$(wlcli --add deadbeef "an open item" 2>/dev/null | grep -oE '#[0-9a-f]+' | tr -d '#')
IID_DONE=$(wlcli --add deadbeef "a done item" 2>/dev/null | grep -oE '#[0-9a-f]+' | tr -d '#')
IID_DEFER=$(wlcli --add deadbeef "a deferred item" 2>/dev/null | grep -oE '#[0-9a-f]+' | tr -d '#')
IID_LEASE=$(wlcli --add deadbeef "a leased item" 2>/dev/null | grep -oE '#[0-9a-f]+' | tr -d '#')
wlcli --tick deadbeef "$IID_DONE" 'closed at abc1234 with exit 0' >/dev/null 2>&1
wlcli --defer deadbeef "$IID_DEFER" 'which way DEFAULT: do-it WHY: operator-call HOW: they-answer' >/dev/null 2>&1
wlcli --lease deadbeef "$IID_LEASE" +60 worker:bg1 note >/dev/null 2>&1

# EVERY KEY OF EVERY RECORD, sorted, so the comparison cannot silently narrow to
# the fields this case's author thought of.
fold_dump() {
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 - "$HOOK" <<'PYEOF'
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent))
import wl_core as C
import wl_store as S

fold = S.load(C.worklist_for(C.project_start()), sync=False)
for rec in sorted(fold.items, key=lambda r: r["id"]):
    print(json.dumps({k: rec[k] for k in sorted(rec)}, sort_keys=True))
PYEOF
}

fold_dump >"$BASE/fold-before.txt" 2>/dev/null
BEFORE_N=$(grep -c . "$BASE/fold-before.txt" 2>/dev/null || echo 0)
# ANTI-VACUITY: two empty dumps compare equal, and that is the shape this whole
# file exists to distrust. Four items were planted; fewer means the fixture, not
# the invariant, is what is being measured.
if [[ "$BEFORE_N" -eq 4 ]]; then
    echo "  PASS: the fixture really holds 4 items across open/done/deferred/leased"
    PASS=$((PASS + 1))
else
    echo "  FAIL: the fixture holds $BEFORE_N item(s), not 4 -- the comparison below would be vacuous"
    FAIL=$((FAIL + 1))
fi
wlcli --compact >/dev/null 2>&1
fold_dump >"$BASE/fold-after.txt" 2>/dev/null
if diff -q "$BASE/fold-before.txt" "$BASE/fold-after.txt" >/dev/null 2>&1; then
    echo "  PASS: every field of every item survives a compaction unchanged"
    PASS=$((PASS + 1))
else
    echo "  FAIL: compaction changed the fold: $(diff "$BASE/fold-before.txt" "$BASE/fold-after.txt" | head -4 | tr '\n' ' ')"
    FAIL=$((FAIL + 1))
fi
# CONTROL ON THE CONTROL: a passing diff proves nothing unless a real loss makes
# it fail. Strip `o` from the compacted add events -- the exact field whose
# absence caused the incident -- and the same comparison must fire. Without this
# the case would pass just as well if fold_dump silently printed nothing, which
# is how a green assertion ends up guarding an empty set.
python3 - "$WORKLIST_STORE_DIR" <<'PYEOF'
import json, pathlib, sys
for f in pathlib.Path(sys.argv[1]).glob("*.jsonl"):
    out = []
    for line in f.read_text().splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("ev") == "add":
            ev.pop("o", None)
        out.append(json.dumps(ev, separators=(",", ":")))
    f.write_text("\n".join(out) + "\n")
PYEOF
fold_dump >"$BASE/fold-lossy.txt" 2>/dev/null
if diff -q "$BASE/fold-before.txt" "$BASE/fold-lossy.txt" >/dev/null 2>&1; then
    echo "  FAIL: CONTROL: dropping the owner changed nothing, so 204 proves nothing"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: CONTROL: a genuinely dropped owner DOES fail the same comparison"
    PASS=$((PASS + 1))
fi
