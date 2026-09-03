# 24-lineage.sh -- a compaction must not cost a session its own items.
#
# THE INCIDENT. A compaction can hand one continuous conversation a NEW session
# id. The ownership rule then refuses to let it resolve items its earlier self
# opened -- correct by the letter of the rule, and catastrophic in effect: on
# 2026-09-02 four settled decisions sat open all night, reported to the operator
# every stop as a peer's, while the session reasoned about a peer that did not
# exist. The operator had to say "I've never switched to another window."
#
# WHAT IS TESTED is that the fix is an EVIDENCE GATE and not a new way to take
# someone else's work. `plant_chain` writes the records a real compaction leaves
# behind; `plant_concurrent` writes two sessions alike in every way a heuristic
# would check -- same cwd, same branch, overlapping times -- sharing no
# conversational record. The second is the one that matters: measured on this
# machine, four live sessions all carried cwd=/home/developer/console and
# gitBranch=main with overlapping times, so "same cwd + time-adjacent" is the
# WRONG discriminator on exactly the population it would judge.

echo "== 24. lineage: adopting a pre-compaction self, and refusing everyone else =="

LIN="$BASE/lineage"
mkdir -p "$LIN/projects"

plant_chain() { # <next-sid> <prev-sid> <shared-uuid>
    python3 - "$LIN/projects" "$1" "$2" "$3" <<'PYEOF'
import json, pathlib, sys
d, nxt, prev, shared = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
bu, lu = "bde8bb05-0000-0000-0000-000000000001", "bde8bb05-0000-0000-0000-000000000002"
# The successor: gate-1 requires the head record to be a compact_boundary with
# parentUuid None, so this shape is what makes a session eligible to adopt at all.
(d / ("%s.jsonl" % nxt)).write_text("".join(json.dumps(r) + "\n" for r in [
    {"type": "mode", "mode": "default"},
    {"type": "system", "subtype": "compact_boundary", "parentUuid": None,
     "uuid": bu, "logicalParentUuid": lu},
    {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried over"}},
]), encoding="utf-8")
# The predecessor: the same shared record (E3), the boundary pair (E2), and the
# continued-in tail the harness writes when it finally closes the file (E1).
(d / ("%s.jsonl" % prev)).write_text("".join(json.dumps(r) + "\n" for r in [
    {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried over"}},
    {"type": "system", "subtype": "compact_boundary", "uuid": bu, "logicalParentUuid": lu},
    {"type": "continued-in", "continuedInSessionId": nxt},
]), encoding="utf-8")
PYEOF
}

plant_concurrent() { # <a-sid> <b-sid> -- real peers: everything alike, uuids disjoint
    python3 - "$LIN/projects" "$1" "$2" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
for sid, u in ((sys.argv[2], "aaaa1111-0000-0000-0000-00000000000a"),
               (sys.argv[3], "bbbb2222-0000-0000-0000-00000000000b")):
    (d / ("%s.jsonl" % sid)).write_text(json.dumps(
        {"type": "user", "uuid": u, "cwd": "/home/developer/console",
         "gitBranch": "main", "timestamp": "2026-09-03T04:00:00Z",
         "message": {"role": "user", "content": "hello"}}) + "\n", encoding="utf-8")
PYEOF
}

linrun() { # <session-id> <argv...>
    local sid="$1"
    shift
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_JUDGE=off \
        WORKLIST_PUBLISH_ROOT="$BASE" WORKLIST_PROJECTS_DIR="$LIN/projects" \
        CLAUDE_CODE_SESSION_ID="$sid" WORKLIST_SESSION_ID="$sid" \
        python3 "$HOOK" "$@" </dev/null 2>&1
}
# </dev/null is not decoration. test-hooks.sh:2328 runs this suite as
# `out="$(bash "$STOP_SUITE" 2>&1)"` with NO stdin redirect, so the suite
# inherits the harness's stdin -- which, under a backgrounded run, is a pipe
# nobody ever closes. A verb that reads stdin then blocks forever, and the
# symptom is indistinguishable from a slow suite: the process sits in
# anon_pipe_read with 5 seconds of CPU after 7 minutes, no children, and no
# output. Every case helper must close its own stdin rather than trust the
# caller's.

NEXT="cafe9911-1111-2222-3333-444444444444"
PREV="beef7722-5555-6666-7777-888888888888"
plant_chain "$NEXT" "$PREV" "11111111-2222-3333-4444-555555555555"
for n in lin-a lin-b lin-c; do linrun "$PREV" --add beef7722 "$n" >/dev/null; done
TICKME=$(linrun "$PREV" --list --open beef7722 |
    sed -n 's/.*#\([0-9a-f]\{8\}\).*lin-a.*/\1/p' | head -n1)

# ---- BEFORE, and without it every case below passes on an empty store -------
OUT=$(linrun "$NEXT" --list --open cafe9911)
if grep -qF "lin-a" <<<"$OUT"; then
    fail "24 BEFORE: the ancestor's items were visible with no edge; the case proves nothing"
else
    pass "24 BEFORE: without an edge the successor cannot see its ancestor's items"
fi
OUT=$(linrun "$NEXT" --tick cafe9911 "$TICKME" "https://ci.invalid/x")
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "owned by" <<<"$OUT"; then
    pass "24 BEFORE: without an edge the successor is refused the tick"
else
    fail "24 BEFORE: ticked an ancestor's item with no edge (rc=$RC): ${OUT:0:200}"
fi

# ---- FIRE ------------------------------------------------------------------
OUT=$(linrun "$NEXT" --adopt cafe9911 beef7722)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "adopted" <<<"$OUT"; then
    pass "24 FIRE: a proven chain is adopted"
else
    fail "24 FIRE: refused a genuine compaction chain (rc=$RC): ${OUT:0:200}"
fi
OUT=$(linrun "$NEXT" --list --open cafe9911)
if grep -qF "lin-a" <<<"$OUT"; then
    pass "24 FIRE: the ancestor's items are now in the successor's open slice"
else
    fail "24 FIRE: adopted, but the items are still invisible: ${OUT:0:200}"
fi
OUT=$(linrun "$NEXT" --tick cafe9911 "$TICKME" "https://ci.invalid/run/24")
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "ticked" <<<"$OUT"; then
    pass "24 FIRE: the successor can now resolve its own pre-compaction work"
else
    fail "24 FIRE: still refused after adoption (rc=$RC): ${OUT:0:200}"
fi

# ---- THE REFUSAL, and this is the one that matters -------------------------
CA="dddd3311-1111-1111-1111-111111111111"
CB="eeee4422-2222-2222-2222-222222222222"
plant_concurrent "$CA" "$CB"
OUT=$(linrun "$CA" --adopt dddd3311 eeee4422)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qiE "cannot prove|REFUSED" <<<"$OUT"; then
    pass "24 REFUSE: two concurrent sessions are NOT adoptable, however alike"
else
    fail "24 REFUSE: adopted a peer on same-cwd/same-branch resemblance (rc=$RC): ${OUT:0:200}"
fi
# A control on the control: the SAME pair, once real evidence exists.
plant_chain "$CA" "$CB" "99999999-8888-7777-6666-555555555555"
OUT=$(linrun "$CA" --adopt dddd3311 eeee4422)
RC=$?
if [[ "$RC" -eq 0 ]]; then
    pass "24 REFUSE CONTROL: the same pair IS adopted once the evidence exists"
else
    fail "24 REFUSE CONTROL: refused even with a planted chain, so the gate is a blanket no: ${OUT:0:200}"
fi

# ---- E3 alone cannot be defeated -------------------------------------------
FN="ffff5533-1111-1111-1111-111111111111"
FP="ffff6644-2222-2222-2222-222222222222"
plant_chain "$FN" "$FP" "77777777-6666-5555-4444-333333333333"
python3 - "$LIN/projects/$FP.jsonl" "$FN" <<'PYEOF'
import json, pathlib, sys
# KEEP continued-in (E1, the easiest line to forge); STRIP every shared record
# and the boundary. If this adopts, one hand-written line takes another's work.
pathlib.Path(sys.argv[1]).write_text(
    json.dumps({"type": "continued-in", "continuedInSessionId": sys.argv[2]}) + "\n",
    encoding="utf-8")
PYEOF
OUT=$(linrun "$FN" --adopt ffff5533 ffff6644)
RC=$?
if [[ "$RC" -ne 0 ]]; then
    pass "24 E3: a continued-in line with no shared record is refused"
else
    fail "24 E3: one forged line was enough to adopt: ${OUT:0:200}"
fi

# ---- Store compaction must not eat the edge --------------------------------
linrun "$NEXT" --compact >/dev/null 2>&1
OUT=$(linrun "$NEXT" --list --open cafe9911)
if grep -qF "lin-b" <<<"$OUT"; then
    pass "24 COMPACT: the lineage edge survives a store compaction"
else
    fail "24 COMPACT: --compact ate the edge; adoptions revert to a peer's: ${OUT:0:200}"
fi

# ---- Additive: no edge anywhere, nothing changes ---------------------------
NOEDGE="0a0a0a0a-1111-1111-1111-111111111111"
python3 - "$LIN/projects/$NOEDGE.jsonl" <<'PYEOF'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text(json.dumps(
    {"type": "user", "uuid": "0a0a0a0a-0000-0000-0000-000000000001",
     "message": {"role": "user", "content": "solo"}}) + "\n", encoding="utf-8")
PYEOF
OUT=$(linrun "$NOEDGE" --add 0a0a0a0a lin-solo)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "added #" <<<"$OUT"; then
    pass "24 ADDITIVE: a session with no lineage behaves exactly as before"
else
    fail "24 ADDITIVE: lineage broke the no-edge path (rc=$RC): ${OUT:0:200}"
fi
