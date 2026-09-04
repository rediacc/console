#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The append-only event store: migration, torn tails, write races, tick refusal, the lease ladder, OS worker verification, autonomy.

echo "== 132. THE STORE: markdown items fold into the event log (migration) =="
setup
FUT=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
cat >>"$WL" <<EOF
- [ ] (deadbeef) open thing
- [x] (deadbeef) done thing, exit 0
- [?] (deadbeef) question DEFAULT: pick A
- [>] (deadbeef) until:$FUT delegated
- [~] (deadbeef) tombstoned relic
EOF
LIST="$(reqcli --list)"
ok=1
for needle in '- [ ] (deadbeef) open thing' '- [x] (deadbeef) done thing, exit 0' \
    '- [?] (deadbeef) question DEFAULT: pick A' 'delegated'; do
    grep -qF -- "$needle" <<<"$LIST" || {
        ok=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok" == 1 ]] && ! grep -qF 'tombstoned relic' <<<"$LIST"; then
    pass "all four live states fold in; the [~] tombstone reads as deleted"
else
    fail "markdown sync lost or resurrected items: $LIST"
fi
if grep -q '"ev":"md"' <(wl_events); then
    pass "the sync left an md event in the log (the store is real, not a re-parse)"
else
    fail "no md event was appended: $(wl_events)"
fi

echo "== 133. in-place markdown edits are honoured; CLI state survives md churn =="
# The markdown is MUTATED by its writers (ticks flip the state byte in
# place), which is why the sync is a whole-file diff, not an append offset.
setup
brief_now
hand_now
say "answer

## Remaining
- the parser item"
echo '- [ ] (deadbeef) fix the parser crash, verified exit 0' >>"$WL"
check "the imported open item blocks" block "OPEN worklist item"
sed -i 's/^- \[ \] (deadbeef) fix the parser/- [x] (deadbeef) fix the parser/' "$WL"
newturn
say "done

## Remaining
nothing"
check "an in-place tick (state byte flip) clears the block" allow ""
ADDOUT="$(reqcli --add deadbeef 'wire the fixture, run pending')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
newturn
say "working

## Remaining
- the fixture item"
check "a CLI-added item blocks like any open item" block "wire the fixture"
reqcli --tick deadbeef "$AID" "suite green, exit 0" >/dev/null
echo '- [ ] (deadbeef) a fresh md item to churn the file' >>"$WL"
newturn
say "working

## Remaining
- the churn item"
out="$(run)"
if grep -qF "a fresh md item to churn" <<<"$out" && ! grep -qF "wire the fixture" <<<"$out"; then
    pass "md churn does not resurrect a CLI-ticked item (overlay outlives the sync)"
else
    fail "resurrection or lost item: ${out:0:260}"
fi

EV="${WL%.md}.events.jsonl"  # write target only; reads go through wl_events
echo "== 134. a torn event-log tail is healed, never merged into the next event =="
setup
reqcli --add deadbeef "first item" >/dev/null
printf '{"ev":"add","id":"tornado1","at":"' >>"$EV" # a crash mid-write: no newline
reqcli --add deadbeef "second item" >/dev/null
OUT=$(
    python3 - <(wl_events) <<'PYEOF'
import json, sys
adds, bad, merged = 0, 0, 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except ValueError:
        bad += 1
        if "second item" in line:
            merged += 1
        continue
    if ev.get("ev") == "add":
        adds += 1
print("adds=%d bad=%d merged=%d" % (adds, bad, merged))
PYEOF
)
if [[ "$OUT" == "adds=2 bad=1 merged=0" ]]; then
    pass "the torn fragment stays its own dead line; both real events parse"
else
    fail "torn-tail healing broke: $OUT"
fi
if reqcli --list | grep -qF "second item"; then
    pass "the fold reads through the torn line"
else
    fail "the fold lost the event after the torn line"
fi

echo "== 135. RACE: concurrent --add writers lose nothing =="
setup
for i in $(seq 1 16); do
    as_peer "sess000$i" reqcli --add "sess000$i" "concurrent item $i" >/dev/null 2>&1 &
done
wait
OUT=$(
    python3 - <(wl_events) <<'PYEOF'
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
    if ev.get("ev") == "add":
        n += 1
        ids.add(ev.get("id"))
print("adds=%d ids=%d bad=%d" % (n, len(ids), bad))
PYEOF
)
if [[ "$OUT" == "adds=16 ids=16 bad=0" ]]; then
    pass "16 concurrent adds -> 16 parseable events, 16 distinct ids"
else
    fail "concurrent adds were lost or torn: $OUT"
fi

echo "== 136. --tick REFUSES a completion without evidence =="
setup
ADDOUT="$(reqcli --add deadbeef 'prove the flag binds')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
if reqcli --tick deadbeef "$AID" "done i guess" >/dev/null 2>"$BASE/tick.err"; then
    fail "an evidence-free tick was accepted"
else
    if grep -qF "REFUSED" "$BASE/tick.err" && ! grep -q '"ev":"state"' <(wl_events); then
        pass "refused loudly (exit nonzero) and wrote nothing"
    else
        fail "refusal was silent or leaked an event: $(head -c 160 "$BASE/tick.err")"
    fi
fi
if reqcli --tick deadbeef "$AID" "suite run green, exit 0" >/dev/null 2>&1 &&
    reqcli --list | grep -qF -- '- [x]'; then
    pass "the same tick with evidence lands"
else
    fail "an evidenced tick was rejected"
fi

echo "== 137. LADDER rung 1 (45 min): a quiet lease pings, report-only =="
setup
brief_now
hand_now
OLD=$(date -u -d '-50 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa1111","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"long docs job"}\n{"ev":"lease","id":"aaaa1111","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"$EV"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the docs job rides a lease"
check "a 50-minute-quiet lease still ALLOWS the stop" allow "Liveness ping"
# CONTROL: a fresh lease draws no ping (same shape, young stamps).
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa1112","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"fresh docs job"}\n{"ev":"lease","id":"aaaa1112","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the docs job rides a lease"
out="$(run)"
if ! grep -qF "Liveness ping" <<<"$out"; then
    pass "CONTROL: a fresh lease draws no ping"
else
    fail "a fresh lease was pinged: ${out:0:200}"
fi

echo "== 138. rungs 2 and 3 block ONCE each; the DEFAULT exit always clears =="
setup
brief_now
hand_now
OLD=$(date -u -d '-100 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa2221","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"stalled docs job"}\n{"ev":"lease","id":"aaaa2221","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the stalled docs job"
check "100 quiet minutes hits the INVESTIGATE rung" block "IN-FLIGHT WORK HAS GONE QUIET"
check "the rung fires ONCE per stamp, not every stop" allow ""
setup
brief_now
hand_now
OLD=$(date -u -d '-125 minutes' +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa2222","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"two-hour stall"}\n{"ev":"lease","id":"aaaa2222","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$OLD" "$OLD" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"watch","command":"sleep 999"}]'
say "answer

## Remaining
- the two-hour stall"
check "125 quiet minutes hits the RESOLVE rung" block "QUIET FOR TWO HOURS"
reqcli --defer deadbeef aaaa2222 "keep waiting on the delegate? DEFAULT: stop it and redelegate WHY: the delegate holds state only it can flush, so killing it loses work HOW: the operator says stop, or the DEFAULT redelegates" >/dev/null
newturn
say "deferred it

## Remaining
- the stall, deferred with a default"
check "the [?]+DEFAULT exit clears the top rung (it can never trap)" allow "operator may answer"

echo "== 139. GONE fires on a vanished worker; UNVERIFIABLE never reads as dead =="
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
# worker_verified:true is the load-bearing half of this fixture. GONE means
# DROPPED: the harness could see the worker when the lease was taken and cannot
# see it now. Without that bit the case was really asserting "any id the harness
# does not list is dead", which is a different and wrong rule -- it accused an
# Agent leased by NAME, which can never appear in a background-task list, while
# that agent was actively writing files.
printf '{"ev":"add","id":"aaaa3331","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated build"}\n{"ev":"lease","id":"aaaa3331","at":"%s","by":"deadbeef","until":"%s","worker":"bogusw1","worker_verified":true}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[]'
say "answer

## Remaining
- the delegated build (ongoing on its worker)"
check "a lease whose worker the harness no longer lists blocks with the facts" block "NOT in the harness background list"

# THE OTHER HALF: a worker that was NEVER confirmable must not be called dead.
# This is the case that cost this session several round trips -- an Agent leased
# by name, absent from the background list by construction, reported as
# "finished or stopped" while its files were appearing on disk.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa3333","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated docs"}\n{"ev":"lease","id":"aaaa3333","at":"%s","by":"deadbeef","until":"%s","worker":"docdelta","worker_verified":false}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[]'
say "answer

## Remaining
- the delegated docs (ongoing on its agent)"
out="$(run)"
if grep -qF "NOT in the harness background list" <<<"$out"; then
    fail "a never-verified worker was accused of being dead: ${out:0:220}"
else
    pass "a worker that was never confirmable is not reported as dead"
fi
# THE FALSE-ACCUSATION CONTROL (the one failure mode worse than no check):
# an UNVERIFIABLE worker (teammate: no OS process exists by design) must not
# read as gone. Same fixture shape, worker present in the event.
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"aaaa3332","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"delegated design"}\n{"ev":"lease","id":"aaaa3332","at":"%s","by":"deadbeef","until":"%s","worker":"tm1"}\n' \
    "$NOW" "$NOW" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"tm1","type":"teammate","status":"running","description":"design agent"}]'
say "answer

## Remaining
- the delegated design (ongoing on its agent)"
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && ! grep -qF "NOT in the harness background list" <<<"$out"; then
    pass "an unverifiable (teammate) worker is never accused of being dead"
else
    fail "false accusation or wrong verdict (got=$got): ${out:0:260}"
fi

echo "== 140. OS verification: confirmed / suspect / unverifiable, on real processes =="
# Library-level, against the real OS: a spawned child IS found, a killed one
# is not, and a teammate task is honestly unverifiable.
OUT=$(
    cd "$BASE" && python3 - "$(dirname "$HOOK")" <<'PYEOF'
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
cmd = "sleep 987654321099"
child = subprocess.Popen(["sleep", "987654321099"])
time.sleep(0.2)
anc = {os.getpid()}
bg = [
    {"id": "sh1", "type": "shell", "status": "running", "command": cmd},
    {"id": "tm1", "type": "teammate", "status": "running", "description": "agent"},
]
v1 = L.verify_background(bg, ancestors=anc)
child.kill()
child.wait()
time.sleep(0.2)
v2 = L.verify_background(bg, ancestors=anc)
print("live=%s teammate=%s dead=%s" % (v1.get("sh1"), v1.get("tm1"), v2.get("sh1")))
PYEOF
)
if [[ "$OUT" == "live=confirmed teammate=unverifiable dead=suspect" ]]; then
    pass "a live child is confirmed, a killed one is suspect, a teammate is unverifiable"
else
    fail "verification verdicts wrong: $OUT"
fi

echo "== 141. AUTONOMY: a DEFAULT past its window is executed, not restated =="
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"bbbb1111","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"keep the flag? DEFAULT: keep it"}\n' \
    "$OLD" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "an aged deferral demands its default be executed" block "OUTLIVED their autonomy window"
reqcli --update deadbeef bbbb1111 "operator pinged; window restarted deliberately" >/dev/null
newturn
say "answer

## Remaining
- the flag decision, deferred with a default"
check "refreshing the item restarts the window (the exit is always available)" allow "operator may answer"
# CONTROL: a fresh deferral just reports (case 3 pins this too; here it is
# the explicit twin of the aged fixture above).
setup
brief_now
hand_now
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"ev":"add","id":"bbbb1112","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"keep the flag? DEFAULT: keep it"}\n' \
    "$NOW" >>"${WL%.md}.events.jsonl"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "CONTROL: a fresh deferral does not demand execution" allow "operator may answer"
# DRAIN CAP: five aged deferrals arrive three at a time, never as a wall.
setup
brief_now
hand_now
OLD=$(date -u -d '-130 minutes' +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5; do
    printf '{"ev":"add","id":"bbbb222%s","at":"%s","by":"deadbeef","s":"?","o":"deadbeef","t":"aged question %s DEFAULT: option A"}\n' \
        "$i" "$OLD" "$i" >>"${WL%.md}.events.jsonl"
done
say "answer

## Remaining
- five aged deferrals draining"
out="$(run)"
if grep -qF "OUTLIVED their autonomy window" <<<"$out" && grep -qF "and 2 more, held back" <<<"$out"; then
    pass "five expired deferrals drain 3 per stop, never as a wall"
else
    fail "drain cap wrong: ${out:0:260}"
fi

echo "== 142. the judge CACHES an identical world+message; any change re-asks =="
setup
brief_now
hand_now
task 7 pending "merge the chain"
say "answer

## Remaining
| #7 | merge the chain | pending, me |"
cat >"$BASE/binonly/claude" <<SHIM
#!/bin/bash
echo call >>"$BASE/judgecalls"
echo '{"is_error":false,"structured_output":{"verdict":"stop","reason":"legitimately parked","next_action":"none"}}'
SHIM
chmod +x "$BASE/binonly/claude"
runj >/dev/null
N1=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
out="$(runj)"
N2=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
if [[ "$N1" == "1" && "$N2" == "1" ]] && grep -qF "cached" <<<"$out"; then
    pass "an identical world and message reuses the verdict (1 paid call, not 2)"
else
    fail "cache did not hold: calls=$N1,$N2 out=${out:0:200}"
fi
task 7 in_progress "merge the chain"
newturn
say "answer

## Remaining
| #7 | merge the chain | ongoing, me |"
runj >/dev/null
N3=$(grep -c call "$BASE/judgecalls" 2>/dev/null)
if [[ "$N3" == "2" ]]; then
    pass "CONTROL: a changed world signature pays the judge again"
else
    fail "a changed world did not re-ask: calls=$N3"
fi

echo "== 143. the dead-code gate: every top-level def is referenced somewhere =="
DEADCODE_PY='
import ast, pathlib, re, sys
d = pathlib.Path(sys.argv[1])
srcs = {p.name: p.read_text() for p in sorted(d.glob("wl_*.py"))}
srcs["worklist.py"] = (d / "worklist.py").read_text()
allsrc = "\n".join(srcs.values())
orphans = []
for name, src in srcs.items():
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            refs = len(re.findall(r"\b%s\b" % re.escape(node.name), allsrc))
            if refs < 2:  # the def line itself is one
                orphans.append("%s.%s" % (name, node.name))
print("orphans=%s" % ",".join(orphans) if orphans else "orphans=none")
sys.exit(1 if orphans else 0)
'
if OUT=$(python3 -c "$DEADCODE_PY" "$(dirname "$HOOK")"); then
    pass "no unreferenced top-level function in the shipped modules ($OUT)"
else
    fail "dead code shipped: $OUT"
fi
# PROVE THE INSTRUMENT: the same gate must FIRE on a planted orphan.
mkdir -p "$BASE/deadcode"
cp "$(dirname "$HOOK")"/wl_*.py "$(dirname "$HOOK")/worklist.py" "$BASE/deadcode/"
printf '\n\ndef orphan_zombie_fn():\n    return 1\n' >>"$BASE/deadcode/wl_core.py"
if OUT=$(python3 -c "$DEADCODE_PY" "$BASE/deadcode"); then
    fail "the dead-code gate cannot fire (planted orphan passed): $OUT"
else
    if grep -qF "orphan_zombie_fn" <<<"$OUT"; then
        pass "CONTROL: the gate fires on a planted orphan def"
    else
        fail "the gate failed for the wrong reason: $OUT"
    fi
fi

echo "== 145. a TICK FLOOD is absorbed as bookkeeping, never asked about =="
# The v10 upgrade guard: tick identity hashes the RENDERED line, and the
# store rewrite can re-render history, so the first post-upgrade stop may
# see hundreds of historical [x] as "new" (791 in the live store). That is
# drift, not 791 simultaneous fixes: absorb with one note, and never route
# those lines into the I7 evidence check either.
setup
say "done for now"
brief_now
reg_repo
run >/dev/null # marker init at current HEAD with zero ticks
for i in $(seq 1 25); do
    echo "- [x] (deadbeef) historical item $i" >>"$WL"
done
out="$(run)"
got="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$out" 2>/dev/null)"
if [[ "$got" == "allow" ]] && grep -qF "absorbed as bookkeeping" <<<"$out"; then
    pass "25 suddenly-new ticks absorb silently with one note (no judge, no I7)"
else
    fail "tick flood mishandled (got=$got): ${out:0:260}"
fi
out="$(run)"
if ! grep -qF "absorbed as bookkeeping" <<<"$out"; then
    pass "the absorption is recorded; a second stop does not repeat the note"
else
    fail "flood note repeated: ${out:0:200}"
fi

echo "== 144. STATE.md staleness is WORLD-KEYED: a quiet world never stales it =="
# The v9 trap this kills: the 10-minute age limit was outpaced by the
# 5-minute poll cron, so a QUIET session went stale every other poll. Age
# alone is not staleness; the world signature must also have moved. The write
# stays INLINE rather than folded into hand_now: passing WORKLIST_TASKS_DIR
# explicitly here is the point of the case (the signature must cover the task
# dir the stop will read), and the explicitness is what documents that.
setup
brief_now
task 7 pending "thing"
say "answer

## Remaining
| #7 | thing | pending, me |"
printf 'You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite from test-hooks.sh.\n\n## Next action\n\nPush and watch the run, then bump the submodule pointers to the squash commits before the merge chain closes out.\n' |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --state deadbeef >/dev/null
check "fresh STATE.md, settled world: allowed" allow ""
age_state deadbeef 25 # the heading stamp is the age source, not the file mtime
check "an OLD STATE.md with an UNCHANGED world is NOT stale (the poll trap is dead)" allow ""
task 8 pending "the new thing"
newturn
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | the new thing | pending, me |"
check "the same old STATE.md goes stale the moment the world moves" block "STATE.md is stale"
# 1.4: the verdict must name the CAUSE. It used to print only "(N min old,
# limit M)", and a session read that as pure wall-clock and concluded the code
# disagreed with its own documentation. The age is a symptom; the signature
# moving is the trigger, and a document a week old whose world never moved is
# never stale.
OUT="$(run)"
if grep -qF "your world signature moved since it was written" <<<"$OUT"; then
    pass "212: a stale STATE.md names the signature move, not just an age"
else
    fail "212: the stale verdict does not say WHY: ${OUT:0:300}"
fi
