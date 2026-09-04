#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Fixture isolation, judge-child diagnostics, and the v19 identity ladder: verb refusal, phantom sessions, --reassign, root resolution.

echo "== 181. ISOLATION: the suite can never reach the live worklist =="
# Raised by the team lead after a run of this suite came back with failures a
# clean tree could not reproduce, on the hypothesis that fixture state and live
# session state were mixing. They were not mixing on DISK -- every invocation
# passes TMPDIR -- but the check belongs here rather than in anyone's memory,
# because the cost of being wrong is a suite that tests the operator's real
# store. Two halves: the store path resolves inside the fixture, and the
# ENVIRONMENT the hook reads carries no ambient knob.
setup
RESOLVED="$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
if [[ "$RESOLVED" == "$BASE/tmp/"* ]]; then
    pass "181: the fixture store resolves inside the fixture, not beside the live one"
else
    fail "181: fixture store escaped to '$RESOLVED'"
fi
# CONTROL: without the fixture TMPDIR the SAME command resolves somewhere else
# entirely, so the assertion above is about TMPDIR doing the work and not about
# the path being unconditionally fixture-shaped.
ELSEWHERE="$(TMPDIR=/var/tmp CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --path)"
if [[ "$ELSEWHERE" != "$RESOLVED" && "$ELSEWHERE" == /var/tmp/* ]]; then
    pass "181 CONTROL: TMPDIR is what pins it; a different one moves the store"
else
    fail "181 CONTROL: TMPDIR did not move the store ('$ELSEWHERE')"
fi
# The env half. Every WORKLIST_* knob the operator's shell might carry is
# scrubbed at suite start, and setup() re-scrubs the ones cases set, so a stop
# here runs on the suite's own configuration whatever the launching shell had.
LEAKED=""
for _v in WORKLIST_QUIET_WAKES WORKLIST_BG_OUTPUT_DIR WORKLIST_HARNESS_PID \
    WORKLIST_BG_REPORT_MIN WORKLIST_REPORT_PER_STOP WORKLIST_FOCUS \
    WORKLIST_STUCK_ROUNDS WORKLIST_JUDGE_CACHE_MIN; do
    [[ -n "${!_v:-}" ]] && LEAKED="$LEAKED $_v=${!_v}"
done
if [[ -z "$LEAKED" ]]; then
    pass "181: no ambient WORKLIST_* knob survives into a case"
else
    fail "181: ambient knobs leaked into the suite:$LEAKED"
fi
# The report store is pinned rather than scrubbed: an UNSET WORKLIST_REPORTS_DIR
# is not neutral, it points wl_report at the operator's real store under $HOME.
if [[ "${WORKLIST_REPORTS_DIR:-}" == "$BASE/reports" ]]; then
    pass "181: the report store is pinned inside the fixture"
else
    fail "181: report store is '${WORKLIST_REPORTS_DIR:-<unset -- reads the REAL store>}'"
fi

echo "== 182. SessionStart source=compact does NOT re-inject the docs blurb =="
# THE BUG (operator, 2026-08-04): a long-running licensing session compacted,
# Claude Code fired SessionStart with source=compact, and the session was handed
# "N design doc(s) in docs/ci-overhaul" plus an order to read all of them --
# material belonging to an unrelated program, injected mid-task. Compaction is
# handle_post_compact's job (cases 20, 21, 171): it already re-points at the
# design docs AND hands back the branch's plans, so SessionStart must stay quiet.
setup
mkdir -p "$BASE/proj/docs/ci-overhaul" "$BASE/proj/agent"
printf '# doc\nbody\n' >"$BASE/proj/docs/ci-overhaul/01-design.md"
printf '# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-08-04\n\nbody\n' \
    >"$BASE/proj/agent/PLAN-a.md"
ss_out() { # ss_out <source-json-fragment>
    printf '{"session_id":"%s","cwd":"%s","hook_event_name":"SessionStart"%s}' \
        "$SID" "$BASE/proj" "$1" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
            python3 "$HOOK" --session-start 2>/dev/null
}
out="$(ss_out ',"source":"compact"')"
if [[ -z "$out" ]]; then
    pass "a compact-sourced SessionStart says nothing at all"
else
    fail "compact still injects context: ${out:0:300}"
fi
# THE CONTROL, because a check that can only pass is not a check: the very same
# fixture must still speak on a genuinely new session, and on an event with no
# source field at all (the shape every older case in this suite feeds).
out="$(ss_out ',"source":"startup"')"
if grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "READ EVERY NON-DONE PLAN" <<<"$out"; then
    pass "182 CONTROL: source=startup still gets the docs AND the plans"
else
    fail "182 CONTROL: startup lost its context: ${out:0:300}"
fi
out="$(ss_out '')"
if grep -qF "READ ALL OF THEM" <<<"$out"; then
    pass "182 CONTROL: an event with no source field is not treated as compact"
else
    fail "182 CONTROL: a missing source silenced the hook: ${out:0:300}"
fi
# The marker the judge stamp rides on is set BEFORE the compact return, so a
# compacted session still gets the full approval reason on its next judged stop.
rm -f "$BASE"/tmp/claude-worklist/*.state-*.json
ss_out ',"source":"compact"' >/dev/null
if python3 - "$BASE" <<'PY'; then
import glob, json, sys
docs = [json.load(open(p)) for p in glob.glob(sys.argv[1] + "/tmp/claude-worklist/*.state-*.json")]
sys.exit(0 if any(d.get("ctx_fresh", {}).get("why", "").startswith("session-start") for d in docs) else 1)
PY
    pass "182: compact still marks the context fresh for the judge stamp"
else
    fail "182: the compact path stopped marking ctx_fresh"
fi

echo "== 183. a failed judge child explains ITSELF, not an empty stderr =="
# THE BUG (2026-08-05): the Stop gate blocked with "judge exited 1: " and nothing
# after the colon, which is unactionable. wl_judge reported proc.stderr on a
# non-zero exit, but the claude CLI writes its error ENVELOPE TO STDOUT -- stderr
# is empty -- and the is_error branch that would have explained it sits behind
# returncode == 0, so it was unreachable exactly when needed. The real cause was
# error_max_budget_usd at $0.1025 against a $0.10 cap. A gate that cannot say why
# it failed is an escape hatch wearing a gate's clothes: the same swallowed-
# failure class this repo scans for, inside the thing that audits it.
if python3 - "$(dirname "$HOOK")" <<'JUDGEDIAG'; then
import sys, json
sys.path.insert(0, sys.argv[1])
import wl_judge

class P:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err

# Derive the over-budget cost from the CURRENT constant rather than hardcoding
# the 0.1025 that was measured against a $0.10 default. The first draft of this
# case pinned the literal and went red the moment the default was raised to
# $0.25 -- a test coupled to a constant it does not own, caught by running it.
budget = float(wl_judge.JUDGE_BUDGET_USD)
envelope = json.dumps({
    "is_error": True, "subtype": "error_max_budget_usd",
    "stop_reason": "tool_use", "total_cost_usd": budget + 0.01,
})
msg = wl_judge._explain_failed_exit("judge", P(1, envelope, ""))
# The cause must be NAMED. Asserting merely "non-empty" would have passed on the
# original defect too, whose message was also non-empty.
assert "error_max_budget_usd" in msg, msg
assert "cost=" in msg, msg
assert "BUDGET EXHAUSTED" in msg, msg

# CONTROL 0: a failure UNDER budget must NOT cry budget. Without this, a message
# that always shouted BUDGET EXHAUSTED would satisfy the assertion above.
under = json.dumps({"is_error": True, "subtype": "error_during_execution",
                    "total_cost_usd": budget / 2})
m0 = wl_judge._explain_failed_exit("judge", P(1, under, ""))
assert "BUDGET EXHAUSTED" not in m0, m0
assert "error_during_execution" in m0, m0

# CONTROL 1: unparseable stdout must still say something concrete rather than
# falling back to the empty stderr that started all this.
m2 = wl_judge._explain_failed_exit("judge", P(1, "segfault", ""))
assert "segfault" in m2, m2

# CONTROL 2: a populated stderr must still be surfaced, so the fix did not trade
# one blind spot for another.
m3 = wl_judge._explain_failed_exit("triage", P(2, "", "boom: no such model"))
assert "no such model" in m3, m3

# CONTROL 3: the label distinguishes the two call sites, which is how an operator
# knows whether triage or the judge died.
assert m3.startswith("triage exited 2"), m3

# CONTROL 4 -- THE ONE THAT MATTERS, and it was missing from the first draft.
# Everything above exercises the HELPER. The defect lived in the CALL SITES, which
# formatted their own message from an empty stderr. Reverting a call site leaves
# the helper perfect and the bug fully restored, and the planted-defect proof
# showed exactly that: the case passed with the original defect back in place.
# A test that cannot see the regression it was written for is the ninth instance
# of the probe-tests-the-wrong-thing class in this campaign. So assert the wiring,
# not just the function.
import pathlib
src = pathlib.Path(sys.argv[1], "wl_judge.py").read_text(encoding="utf-8")
code = "\n".join(
    ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
)
assert code.count("_explain_failed_exit(") >= 3, (
    "both non-zero-exit call sites must route through the helper "
    "(definition + 2 uses); found %d" % code.count("_explain_failed_exit(")
)
assert "exited %d: %s" not in code, (
    "a call site is formatting its own exit message again -- that is the "
    "2026-08-05 defect, which reports an EMPTY stderr because the CLI writes "
    "its error envelope to stdout"
)

# THE EXIT-ZERO TWIN, 2026-08-26. Everything above is the non-zero path. The
# failure that actually stopped a session exits ZERO: transport fine, is_error
# false, structured_output null. The gate said "produced no usable
# structured_output: None" and nothing else, while the same envelope held the
# cost and the turn count -- and the very next sentence of that block offers to
# DISABLE the gate, so the unhelpful line is the worst place to be uninformative.
spent = json.dumps({"subtype": "success", "is_error": False,
                    "stop_reason": "tool_use", "num_turns": 29,
                    "total_cost_usd": budget})
e_spent = wl_judge._explain_no_output("judge", json.loads(spent), None)
assert "BUDGET EXHAUSTED" in e_spent, e_spent
assert "turns=29" in e_spent, e_spent
assert "cost=" in e_spent, e_spent

# CONTROL 5: a CHEAP exit-zero failure must not cry budget either. This is the
# same control as CONTROL 0, on the twin path, and it is what makes the
# assertion above evidence rather than a slogan.
cheap = {"subtype": "success", "is_error": False, "stop_reason": "end_turn",
         "num_turns": 2, "total_cost_usd": budget / 10}
e_cheap = wl_judge._explain_no_output("judge", cheap, None)
assert "BUDGET EXHAUSTED" not in e_cheap, e_cheap
assert "turns=2" in e_cheap, e_cheap

# CONTROL 6: no envelope at all must still name the label and the payload
# rather than raising, because an unparseable stdout reaches here too.
e_none = wl_judge._explain_no_output("triage", None, None)
assert e_none.startswith("triage produced no usable"), e_none

# CONTROL 7 -- THE WIRING, for the same reason CONTROL 4 exists. The helper can
# be perfect while a call site still formats its own bare message, which is
# precisely how the exit-zero path stayed uninformative while the exit-non-zero
# path was fixed. All FOUR unusable-output sites must route through it.
assert code.count("_explain_no_output(") >= 5, (
    "every unusable-output call site must route through the helper "
    "(definition + 4 uses); found %d" % code.count("_explain_no_output(")
)
assert "produced no usable structured_output: %s" not in code.replace(
    'bits = ["%s produced no usable structured_output: %s"', ""
), "a call site is formatting its own no-output message again"
JUDGEDIAG
    pass "183: a failed judge child names its own cause (budget, stdout, stderr, label)"
else
    fail "183: wl_judge._explain_failed_exit no longer explains a failed child"
fi

# ---------------------------------------------------------------------------
# v19: RUNTIME CALLER IDENTITY. Every <me> argument used to be accepted on SHAPE
# alone (PREFIX_RE), and nothing had ever compared one to reality.
# ---------------------------------------------------------------------------

echo "== 184. v19 L1: every verb taking a <me> refuses an identity this session is not =="
# THE DEFECT, replayed verbatim. A session copied a SUB-AGENT's namespace token
# out of a Task-spawn tool result (`agent_id: search-renet2@session-4c3e095a`)
# and passed it as its own <me> for 26 hours: 219 calls under 4c3e095a and 20
# under its real id, from ONE process. Every call SUCCEEDED, because writes and
# reads key off the same unvalidated string -- so one typo splits a session into
# two internally-consistent halves, and a peer's message waited 34 hours in the
# half nobody was reading.
#
# THREE CONTROLS PER VERB, each differing from FIRE in ONE planted fact:
#   A  the prefix is this session's        -> accepted, and the effect HAPPENS
#   B  the environment cannot say who I am -> accepted (the deliberate silent
#      pass), which also proves FIRE was caused by the CHECK and not by an
#      unrelated failure in the same command
#   C  the prefix is too short             -> refused by the length floor
setup
brief_now
brief_other cafe1234
mkdir -p "$BASE/reports/agenttest"
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "agenttest").mkdir(parents=True, exist_ok=True)
(store / "agenttest" / "l1.md").write_text("L1 FIXTURE REPORT\nbody")
(store / "index.jsonl").write_text(json.dumps({
    "ev": "report", "id": "l1report0001", "at": "2026-08-05T10:00:00Z",
    "branch": "agenttest", "agent": "l1-teammate", "type": "l1-teammate",
    "session": "deadbeef", "body": "agenttest/l1.md", "bytes": 900,
    "silent": False, "sends": 1, "title": "L1 FIXTURE REPORT",
    "transcript": "", "src": "hook"}) + "\n")
PYEOF

l1run() { # the CLI under the fixture; STATE body on stdin so --state is drivable
    printf '%s' "$STATE_BODY" |
        TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_JUDGE=off \
            WORKLIST_PUBLISH_ROOT="$BASE" WORKLIST_PROJECTS_DIR="$BASE/l1projects" \
            python3 "$HOOK" "$@" 2>&1
}

# Fixtures the write verbs need. Built as deadbeef, which is this suite's own
# identity, so building them exercises CONTROL A's path before the table runs.
mkitem() { l1run --add deadbeef "$1" | sed -n 's/^added #\([0-9a-f]*\).*/\1/p'; }
I_TICK=$(mkitem l1-tick-item)
I_DEFER=$(mkitem l1-defer-item)
I_UPDATE=$(mkitem l1-update-item)
I_LEASE=$(mkitem l1-lease-item)
mkitem l1-list-item >/dev/null # the --list row asserts on the TEXT, not the id
R_ANSWER=$(askid_as cafe1234 deadbeef l1-answer-me)
R_DECLINE=$(askid_as cafe1234 deadbeef l1-decline-me)
R_ACK=$(l1run --ask deadbeef cafe1234 l1-ack-me | sed -n 's/.*#\([0-9a-f]\{8\}\).*/\1/p' | head -n1)
as_peer cafe1234 l1run --answer cafe1234 "$R_ACK" l1-their-answer >/dev/null
# A phantom for the --reassign row: three aged events under an identity that has
# never stopped, owning open items. Case 184 runs no Stop hook, so no
# .lastevent- file exists for anybody here, which is exactly the phantom shape.
phantom_store phantom1 90

# A CHAIN for the --adopt row. Same reasoning as the phantom above: --adopt is a
# me-taking verb so L1_TABLE must drive it, and CONTROL A demands rc=0 -- which
# for an EVIDENCE-GATED verb means planting the evidence. The predecessor's
# transcript needs the continued-in line, the boundary pair, AND a record this
# suite's own transcript also carries; without all three the verb refuses, which
# is the whole point of it.
L1_PROJ="$BASE/l1projects"
mkdir -p "$L1_PROJ"
python3 - "$L1_PROJ" "$SID" adopt111 <<'PYEOF'
import json, pathlib, sys
d, sid, prev = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
prev_sid = "%s-9999-8888-7777-666666666666" % prev
bu, lu = "ad0b7ed0-0000-0000-0000-000000000001", "ad0b7ed0-0000-0000-0000-000000000002"
shared = "ad0b7ed0-1111-2222-3333-444444444444"
(d / ("%s.jsonl" % sid)).write_text("".join(json.dumps(r) + "\n" for r in [
    {"type": "mode", "mode": "default"},
    {"type": "system", "subtype": "compact_boundary", "parentUuid": None,
     "uuid": bu, "logicalParentUuid": lu},
    {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried"}},
]), encoding="utf-8")
(d / ("%s.jsonl" % prev_sid)).write_text("".join(json.dumps(r) + "\n" for r in [
    {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried"}},
    {"type": "system", "subtype": "compact_boundary", "uuid": bu, "logicalParentUuid": lu},
    {"type": "continued-in", "continuedInSessionId": sid},
]), encoding="utf-8")
PYEOF

# label | args (@ME@ is substituted) | needle proving the effect happened
L1_TABLE=(
    "--add|--add @ME@ l1-table-add|added #"
    "--triage|--triage @ME@ l1-table-finding|triaging #"
    "--tick|--tick @ME@ $I_TICK https://ci.invalid/run/1|ticked #"
    "--defer|--defer @ME@ $I_DEFER q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers|deferred #"
    "--update|--update @ME@ $I_UPDATE moved-a-bit|updated #"
    "--lease|--lease @ME@ $I_LEASE +30 worker:l1bg|leased #"
    "--list|--list --open @ME@|l1-list-item"
    "--state|--state @ME@|STATE.md section written"
    "--loop|--loop @ME@ 2099-01-01T00:00:00Z 1 l1-label|loop declared"
    "--brief|--brief @ME@ l1-brief-text|brief recorded"
    "--intent|--intent @ME@ l1-intent-text --for 30|intent recorded"
    "--reap|--reap @ME@ l1task9|reaped 1 task"
    "--migrate|--migrate @ME@ --candidates|"
    "--ask|--ask @ME@ cafe1234 l1-table-ask|request #"
    "--answer|--answer @ME@ $R_ANSWER l1-my-answer|answered #"
    "--decline|--decline @ME@ $R_DECLINE l1-my-decline|declined #"
    "--ack|--ack @ME@ $R_ACK|acked #"
    "--poll|--poll @ME@|"
    "--reports|--reports --read @ME@ l1report0001|marked 1 report"
    "--reports|--reports --list --as @ME@|L1 FIXTURE REPORT"
    # Both take a <me> and both must prove their effect, not merely exit 0.
    "--epic|--epic @ME@ new L1 probe epic|epic #"
    "--publish|--publish @ME@ l1probe|wrote agent/pr/"
    "--reassign|--reassign @ME@ phantom1|reassigned phantom1 -> deadbeef"
    # Evidence-gated, so CONTROL A only passes against the chain planted above.
    "--adopt|--adopt @ME@ adopt111|adopted"
)
COVERED="$BASE/l1covered"
: >"$COVERED"
L1_FAIL=0
for row in "${L1_TABLE[@]}"; do
    IFS='|' read -r verb tmpl needle <<<"$row"
    echo "$verb" >>"$COVERED"
    read -ra FIREARGS <<<"${tmpl//@ME@/4c3e095a}"
    read -ra GOODARGS <<<"${tmpl//@ME@/deadbeef}"
    read -ra SHORTARGS <<<"${tmpl//@ME@/dead}"

    # FIRE: the exact literal from the incident, against this suite's own id.
    OUT=$(l1run "${FIREARGS[@]}")
    RC=$?
    if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT" &&
        grep -qF "deadbeef" <<<"$OUT"; then
        pass "184 FIRE $verb: a foreign <me> is refused, naming the real session"
    else
        fail "184 FIRE $verb: accepted a foreign <me> (rc=$RC): ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL A: one planted fact changed -- the prefix -- and the effect lands.
    OUT=$(l1run "${GOODARGS[@]}")
    RC=$?
    if [[ "$RC" -eq 0 ]] && { [[ -z "$needle" ]] || grep -qF "$needle" <<<"$OUT"; }; then
        pass "184 CONTROL A $verb: this session's own prefix works, effect included"
    else
        fail "184 CONTROL A $verb: the check broke the verb (rc=$RC, needle '$needle'): ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL B: the instrument BLIND. No id anywhere, so the check cannot know
    # and must say nothing -- and the FIRE command then succeeds, which is what
    # proves FIRE was the check firing rather than the command failing anyway.
    OUT=$(env -u CLAUDE_CODE_SESSION_ID -u WORKLIST_SESSION_ID bash -c '
        printf "%s" "$1"; shift
        TMPDIR="$2/tmp" CLAUDE_PROJECT_DIR="$2/proj" WORKLIST_JUDGE=off \
            WORKLIST_PUBLISH_ROOT="$2" \
            python3 "$3" "${@:4}" 2>&1' _ "" "$STATE_BODY" "$BASE" "$HOOK" "${FIREARGS[@]}" </dev/null)
    if ! grep -qF "identity mismatch" <<<"$OUT"; then
        pass "184 CONTROL B $verb: an unresolvable environment accuses nobody"
    else
        fail "184 CONTROL B $verb: accused a caller it could not verify: ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi

    # CONTROL C: the length floor, generalised from --poll's. `dead` IS a prefix
    # of this session's id, so only the floor can refuse it -- which is the
    # whole point: same_session's symmetry would have accepted `--add d`.
    OUT=$(l1run "${SHORTARGS[@]}")
    RC=$?
    if [[ "$RC" -ne 0 ]]; then
        pass "184 CONTROL C $verb: a promiscuously short prefix is refused"
    else
        fail "184 CONTROL C $verb: accepted a 4-char <me>: ${OUT:0:200}"
        L1_FAIL=$((L1_FAIL + 1))
    fi
done
# --poll's effect is a FILE, not a line: an empty inbox prints nothing by
# contract, so CONTROL A above can only check the exit code for it.
if [[ -f "${WL%.md}.pollmark-deadbeef" ]]; then
    pass "184 CONTROL A --poll: the marker was actually written"
else
    fail "184 CONTROL A --poll: exit 0 but no marker; the verb did nothing"
fi

echo "== 184w. --wait is on the same rule, and it is the one that BLOCKS on the answer =="
# Separate because it is a different entry point (wl_wait.py, not worklist.py)
# and because getting it wrong is expensive in a way the others are not: a
# waiter armed against the wrong slice blocks for MINUTES on an inbox that is
# not its own, then reports nothing new.
WAITBIN="$(dirname "$HOOK")/wl_wait.py"
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$WAITBIN" 4c3e095a --timeout 0.02 2>&1)
RC=$?
echo "--wait" >>"$COVERED"
if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "184w FIRE: the waiter refuses to listen as another session"
else
    fail "184w FIRE: the waiter armed against a foreign identity (rc=$RC): ${OUT:0:200}"
fi
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    python3 "$WAITBIN" deadbeef --timeout 0.02 2>&1)
RC=$?
# The heartbeat is UNLINKED on a clean timeout exit (wl_wait.py:202), so the
# effect to assert is the report line naming the session it actually listened
# for -- a waiter armed against the wrong slice would name that one.
if [[ "$RC" -eq 0 ]] && grep -qF "nothing new for deadbeef" <<<"$OUT"; then
    pass "184w CONTROL A: its own prefix waits, and listens on its OWN inbox"
else
    fail "184w CONTROL A: the check broke the waiter (rc=$RC): ${OUT:0:200}"
fi

echo "== 185. ANTI-VACUITY: the verb list is DERIVED from the source, not typed here =="
# THE MOST IMPORTANT CASE IN THIS CHANGE. The defect's shape is "a rule applied
# to some call sites and not others", so a hand-written table is the same bug
# one layer up: add verb 14 next month, forget the table, and the suite stays
# green over a reopened hole. So the verb list comes from worklist.py's OWN
# dispatch, and every me-taking verb must have been DRIVEN above -- proven by
# the coverage file the loop wrote at runtime, not by grepping this file, which
# would pass on a case that never ran.
OUT=$(
    python3 - "$(dirname "$HOOK")" "$COVERED" <<'PYEOF'
import pathlib, re, sys
d = pathlib.Path(sys.argv[1])
src = (d / "worklist.py").read_text(encoding="utf-8")
verbs = set()
verbs.update(re.findall(r'sys\.argv\[1:2\] == \["(--[a-z-]+)"\]', src))
verbs.update(re.findall(r'sys\.argv\[1\] == "(--[a-z-]+)"', src))
for tup in re.findall(r'sys\.argv\[1\] in \(([^)]*)\)', src):
    verbs.update(re.findall(r'"(--?[a-z-]+)"', tup))
# Verbs that take NO <me>, each for a stated reason. Adding to this list is a
# deliberate act; forgetting to add a NEW me-taking verb is not, which is the
# asymmetry that makes this check work.
NO_ME = {
    "--git",                  # the mediated git capability. Its argv is
                              # <subcommand> [args] [--execute], never a <me>:
                              # it does not read, write or tick a worklist item,
                              # so there is no identity for an L1_TABLE row to
                              # substitute @ME@ into. Its risk is git writes, not
                              # identity handling, and that is covered where the
                              # risk lives: wl_git.py --selftest, which
                              # test-hooks.sh now RUNS (it did not when this
                              # exemption was written, so the citation was
                              # coverage claimed from a suite nothing executed).
                              # IF IT EVER TAKES A <me>, delete this line.
    "--store",                # prints the tracked store's directory. Reads no
                              # item and writes none, exactly like --path: there
                              # is no identity for an L1_TABLE row to substitute.
    "--doctor",               # parses the store files and reports conflict
                              # markers, torn lines and secret shapes. It never
                              # writes, and its subject is the FILES rather than
                              # any session's items.
    "--import-tmp",           # relocates bytes this machine already had, from
                              # the legacy TMPDIR log into the tracked store. It
                              # claims no ownership: every item keeps the owner
                              # it already carried, which is why it takes no <me>.
    "--help", "-h", "help",   # prints the catalogue
    "--path", "--compact",    # store-level queries, no identity
    "--requests",             # unfiltered listing of everybody's requests
    "--session-start", "--post-compact",  # harness hooks; identity is in the event
    "--teammate-idle",        # the same shape: a harness hook (TeammateIdle) whose
                              # whole input is the event on stdin, carrying
                              # session_id and agent_id. It takes no argv at all,
                              # so an L1_TABLE row would substitute @ME@ into a
                              # slot that does not exist and assert nothing. Its
                              # risk is not identity handling -- it writes a
                              # per-worker telemetry sidecar, never an item -- and
                              # it is covered where that risk lives: the
                              # never-block/always-exit-0 contract, and the
                              # 17 controls in test-teammate-idle.py.
                              # IF IT EVER TAKES A <me>, delete this line.
    "--reports",              # a CONTAINER: its me-taking sub-modes are driven
                              # explicitly as `--reports --read` and
                              # `--reports --list --as`, and it is recorded
                              # covered by both.
    "--roundlog",             # takes a BRANCH, not an identity: it splices the
                              # STATUS block of reports/pr-babysit-<branch>.md,
                              # a single-owner document with no per-session
                              # sections to protect. An L1_TABLE row would
                              # substitute @ME@ into the branch slot and assert
                              # nothing real. It is covered where its risk actually
                              # lives instead: 19 splice controls in
                              # `wl_roundlog.py --selftest` (including one that
                              # asserts the naive splice still destroys the
                              # appendix) and 11 guard cases in test-hooks.sh.
                              # IF IT EVER TAKES A <me>, delete this line: the
                              # exemption would then be hiding real identity
                              # handling, which is the hole this check exists
                              # to keep shut.
}
covered = {ln.strip() for ln in pathlib.Path(sys.argv[2]).read_text().splitlines() if ln.strip()}
# The derivation's own control. An empty or broken regex would produce an empty
# `verbs` and this whole case would pass by finding nothing to check -- exactly
# the can't-fail shape it exists to prevent.
if not {"--add", "--tick", "--ask", "--poll", "--state", "--brief"} <= verbs:
    print("DERIVATION BROKEN: the dispatch scan found %s" % sorted(verbs))
    sys.exit(1)
gap = sorted((verbs - NO_ME) - covered)
if gap:
    print("UNCOVERED me-taking verb(s), add a row to L1_TABLE: %s" % gap)
    sys.exit(1)
print("derived=%d covered=%d" % (len(verbs - NO_ME), len(covered)))
PYEOF
)
if [[ $? -eq 0 ]]; then
    pass "185: every verb the dispatch offers with a <me> was actually driven ($OUT)"
else
    fail "185: $OUT"
fi

echo "== 186. META-CONTROL: the ambient scrub at the top of the runner really happened =="
# A CHECK ON A CHECK, and it is not redundant. Everything above depends on
# WORKLIST_SESSION_ID being the ONLY identity in the environment. If the scrub
# at line 16 ever stops stripping CLAUDE_CODE_SESSION_ID, this suite splits in
# two: run from inside a Claude session every fixture prefix mismatches and ~110
# sites refuse, and run in CI the variable is unset, check_me silently passes,
# and every identity case above passes VACUOUSLY. The second is the dangerous
# one, because it is green.
#
# The probe: unset WORKLIST_SESSION_ID ONLY, then issue a command that would
# FIRE against any real session id, and require it to PASS. It can only pass if
# there is no ambient id left to compare against.
OUT=$(env -u WORKLIST_SESSION_ID bash -c '
    TMPDIR="$1/tmp" CLAUDE_PROJECT_DIR="$1/proj" \
        python3 "$2" --add 4c3e095a scrub-probe 2>&1' _ "$BASE" "$HOOK" </dev/null)
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "identity mismatch" <<<"$OUT"; then
    pass "186: no ambient CLAUDE_CODE_SESSION_ID survives the scrub"
else
    fail "186: an ambient session id leaked past the scrub, so case 184 is measuring the SHELL, not the check: ${OUT:0:200}"
fi
# CONTROL: force one back in and the same command must FIRE. Without this,
# case 186 is satisfied by a check that never runs at all.
OUT=$(CLAUDE_CODE_SESSION_ID="beef0000-9999-8888-7777-666666666666" \
    env -u WORKLIST_SESSION_ID bash -c '
    TMPDIR="$1/tmp" CLAUDE_PROJECT_DIR="$1/proj" \
        python3 "$2" --add 4c3e095a scrub-probe 2>&1' _ "$BASE" "$HOOK" </dev/null)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "beef0000" <<<"$OUT"; then
    pass "186 CONTROL: with an ambient id present the same command FIRES, so 186 measures something"
else
    fail "186 CONTROL: CLAUDE_CODE_SESSION_ID is not read at all (rc=$RC): ${OUT:0:200}"
fi

echo "== 184x. a SHORT <me> that exactly matches an explicit declaration is honoured =="
# REGRESSION, from a defect the floor itself caused (26d7814c5). Legacy
# sub-agents tagged items with their NAME rather than a session prefix, and
# `w2s-en` is 6 characters. The floor refused it even WITH the override
# declared, and the refusal then advised "rerun with <me>=w2s-en" -- the exact
# value it had just rejected. An instruction to retry the thing it refused
# leaves no next move: the listing path was closed, so the only way to see
# those items was to reassign them BLIND, which is the opposite of
# inspect-then-decide. A capability reachable only by acting blind is not
# reachable.
#
# The floor guards against an UNDER-SPECIFIED GUESS about self. An exact match
# to an explicit declaration is not a guess, so it is honoured -- and the three
# controls below are what keep that from being a loophole.
#
# PLACED HERE, not beside case 184, deliberately: setup() does `rm -rf $BASE`,
# which would wipe the coverage file case 185 reads. Do not move it up.
setup
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --add w2s-en "a legacy agent-named item" 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "added #" <<<"$OUT"; then
    pass "184x FIRE: a 6-char <me> matching its declaration exactly is accepted"
else
    fail "184x FIRE: the floor still refuses a declared short identity (rc=$RC): ${OUT:0:200}"
fi
# ...and the path that was actually closed: READING before deciding ownership.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --list --open w2s-en 2>&1)
if [[ $? -eq 0 ]] && grep -qF "a legacy agent-named item" <<<"$OUT"; then
    pass "184x FIRE: its items can be INSPECTED, so ownership is a decision and not a gamble"
else
    fail "184x FIRE: the listing path is still closed: ${OUT:0:200}"
fi
# CONTROL A: one planted fact -- no declaration at all. This is the case the
# floor was built for, and it must still refuse.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    CLAUDE_CODE_SESSION_ID=w2s-en-1111-2222 python3 "$HOOK" --add w2s-en "x" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "shorter than 8 characters" <<<"$OUT"; then
    pass "184x CONTROL A: a bare short <me> with no declaration is still refused"
else
    fail "184x CONTROL A: the escape swallowed the whole floor (rc=$RC): ${OUT:0:200}"
fi
# CONTROL B: a declaration that does not EXACTLY match. A prefix relationship is
# not enough -- that is what makes this an exact-match rule rather than a second
# way to express the guess the floor exists to refuse.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_SESSION_ID=w2s-en-1111-2222 python3 "$HOOK" --add w2s-en "x" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "shorter than 8 characters" <<<"$OUT"; then
    pass "184x CONTROL B: a declaration the value merely prefixes is not an exact match"
else
    fail "184x CONTROL B: near-enough counted as exact (rc=$RC): ${OUT:0:200}"
fi
# CONTROL C: THE PROPERTY THAT MAKES THE ESCAPE SAFE, and nothing else asserts
# it. --poll and --wait key SIDECAR FILENAMES off <me>[:8], so a short prefix
# there names a different marker than the Stop hook derives from the full
# session id and silently disables the fast path. Those two carry their own
# floor, ahead of check_me, and the escape must not reach them.
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$HOOK" --poll w2s-en 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "8-char" <<<"$OUT"; then
    pass "184x CONTROL C: --poll keeps its own floor; the escape does not reach the sidecar verbs"
else
    fail "184x CONTROL C: a declared short prefix reached the poll marker (rc=$RC): ${OUT:0:200}"
fi
OUT=$(TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_SESSION_ID=w2s-en \
    python3 "$(dirname "$HOOK")/wl_wait.py" w2s-en --timeout 0.01 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "8-char" <<<"$OUT"; then
    pass "184x CONTROL C: --wait keeps its own floor too"
else
    fail "184x CONTROL C: a declared short prefix armed the waiter (rc=$RC): ${OUT:0:200}"
fi

echo "== 187. --ask refuses a recipient that has never briefed here =="
# The same defect from the SENDER'S side, and it cost the same incident 34
# hours: peers addressed `4c3e095a`, an identity that never existed, and the
# request sat until it auto-escalated with "recipient silent for 2062min".
setup
brief_now
brief_other cafe1234
OUT=$(reqcli --ask deadbeef 4c3e095a "into the void" 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "has never briefed" <<<"$OUT" && grep -qF "cafe1234" <<<"$OUT"; then
    pass "187 FIRE: an ask to a never-briefed prefix is refused, listing who is real"
else
    fail "187 FIRE: posted into an inbox nobody reads (rc=$RC): ${OUT:0:200}"
fi
# CONTROL A: one planted fact -- the recipient HAS briefed.
OUT=$(reqcli --ask deadbeef cafe1234 "a real recipient" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "request #" <<<"$OUT"; then
    pass "187 CONTROL A: a briefed recipient is accepted"
else
    fail "187 CONTROL A: the check refused a real session: ${OUT:0:200}"
fi
# CONTROL B: '*' and 'operator' are not roster entries and never will be.
if reqcli --ask deadbeef '*' "broadcast" >/dev/null 2>&1 &&
    reqcli --ask deadbeef operator "a question DEFAULT: proceed as planned" >/dev/null 2>&1; then
    pass "187 CONTROL B: '*' and 'operator' bypass the roster check"
else
    fail "187 CONTROL B: the roster check swallowed a broadcast or an operator ask"
fi
# CONTROL C: the INSTRUMENT BLIND. An empty roster means the check has no data
# -- a fresh worktree, a wiped TMPDIR -- and refusing every ask there would
# break the mechanism exactly where nothing is wrong.
setup
OUT=$(reqcli --ask deadbeef nobody99 "no roster at all" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "request #" <<<"$OUT"; then
    pass "187 CONTROL C: with an EMPTY roster the check abstains instead of refusing everything"
else
    fail "187 CONTROL C: an empty roster refused every ask: ${OUT:0:200}"
fi

echo "== 188. 'operator' is exempt, and the exemption is narrow =="
# The stop report prints `worklist.py --answer operator <id> '<words>'` for the
# HUMAN. They
# run it in whatever shell is open, and if that is a Claude session's Bash the
# identity check would refuse the one command the mail exists to get run.
# "operator" is a name, not a session prefix, and was never verifiable.
setup
brief_now
brief_other cafe1234
RID=$(askid_as cafe1234 deadbeef "for the operator to answer")
OUT=$(reqcli --answer operator "$RID" "the human's answer" 2>&1)
if [[ $? -eq 0 ]] && grep -qF "answered #" <<<"$OUT"; then
    pass "188: the operator's mailed reply command still works inside a session"
else
    fail "188: the identity check broke the operator's reply path: ${OUT:0:200}"
fi
# CONTROL: the exemption is ONE literal, not "any non-session word".
OUT=$(reqcli --answer operator2 "$RID" "an impostor" 2>&1)
if [[ $? -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "188 CONTROL: a lookalike is not exempt"
else
    fail "188 CONTROL: the exemption is wider than one literal: ${OUT:0:200}"
fi

echo "== 189. v19 L2: an identity that WRITES here and has never stopped is reported =="
# The backstop for what L1 cannot reach: history already written, and the
# deliberate silent-pass where the environment cannot name the caller. The
# signature is exact and binary -- `.lastevent-<prefix>.json` is written at
# exactly ONE place (run_stop), so no file means no Stop hook has ever run under
# that identity, and a real session always stops.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null # one real stop, so a .lastevent-deadbeef.json exists
phantom_store phantom1 90
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if grep -qF "PHANTOM IDENTITY IN THE STORE" <<<"$OUT" && grep -qF "phantom1" <<<"$OUT" &&
    grep -qF -- "--reassign deadbeef" <<<"$OUT"; then
    pass "189 FIRE: the phantom is named, with the exact repair verb"
else
    fail "189 FIRE: no phantom section: ${OUT:0:400}"
fi
if ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "189: it is REPORT-ONLY and never blocks"
else
    fail "189: the phantom report blocked a stop it is not this session's job to fix"
fi

echo "== 189a. CONTROL: a .lastevent- file means it DID stop, so it is a real session =="
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
printf '{"session_id":"phantom1-x"}' >"${WL%.md}.lastevent-phantom1.json"
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189a CONTROL: one planted fact -- the .lastevent- file -- and it goes silent"
else
    fail "189a CONTROL: flagged an identity that has stopped: ${OUT:0:300}"
fi

echo "== 189b. CONTROL: a brand-new session writes before its first stop =="
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 2 # younger than WORKLIST_PHANTOM_MIN (30)
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189b CONTROL: a 2-minute-old writer is not yet a phantom"
else
    fail "189b CONTROL: accused a session that has not had time to stop: ${OUT:0:300}"
fi

echo "== 189c. CONTROL: a phantom that owns NOTHING is not worth a word =="
# This is the gate that keeps `state-spotchk1`/`state-spotchk2` -- real test
# residue in the operator's live store -- silent.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
# tick every phantom-owned item: it still WROTE the events, it just owns nothing open
# READS the whole store, WRITES to the legacy log (still unioned by the reader).
# Those must be two different paths: a process substitution is a read-only pipe,
# so appending to <(wl_events) writes into a pipe nobody reads and the ticks
# silently do not happen -- which made this control accuse a phantom that had in
# fact been closed.
python3 - <(wl_events) "${WL%.md}.events.jsonl" <<'PYEOF'
import json, sys
ids = [json.loads(l)["id"] for l in open(sys.argv[1]) if l.strip()
       and json.loads(l).get("by") == "phantom1"]
with open(sys.argv[2], "a", encoding="utf-8") as fh:
    for i in ids:
        fh.write(json.dumps({"ev": "state", "id": i, "at": "2026-08-05T00:00:00Z",
                             "by": "phantom1", "s": "x", "note": "done"}) + "\n")
PYEOF
newturn
say "all done, nothing outstanding"
OUT="$(run)"
if ! grep -qF "PHANTOM IDENTITY" <<<"$OUT"; then
    pass "189c CONTROL: a phantom owning no open work stays silent"
else
    fail "189c CONTROL: flagged an identity with nothing outstanding: ${OUT:0:300}"
fi

echo "== 189d. CONTROL: with ZERO .lastevent- files the check says it is BLIND =="
# Asserting silence here would be indistinguishable from the check not running.
# With no .lastevent-* anywhere the signature cannot discriminate -- it
# recognises a phantom by the ABSENCE of one -- and it would indict every
# identity at once, so it must report the blindness in words and flag nobody.
#
# DRIVEN AS A LIBRARY CALL, not through a Stop event, and that is a real fact
# about the code rather than test convenience: run_stop writes its OWN
# .lastevent-<me8>.json before this check runs, so on the Stop path the set is
# never empty. The branch guards a store where that write FAILED (an unwritable
# TMPDIR) and any future caller that has not just written one. 189e is its
# control: same call, one file present, and the phantom is named.
setup
brief_now
hand_now
phantom_store phantom1 90
rm -f "${WL%.md}".lastevent-*.json
probe_phantom() { # probe_phantom -> "BLIND: <reason>" or "FLAGGED: <prefixes>"
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 - "$(dirname "$HOOK")" "$WL" <<'PYEOF'
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import wl_checks as CK, wl_store as S, wl_requests as R
wl = pathlib.Path(sys.argv[2])
found, blind = CK.phantom_identities(wl, "deadbeef-1111-2222-3333-444444444444",
                                     S.load(wl, sync=False), R.read_requests(wl))
print("BLIND: %s" % blind if blind else "FLAGGED: %s" % ",".join(f[0] for f in found))
PYEOF
}
OUT=$(probe_phantom)
if [[ "$OUT" == BLIND:* ]] && grep -qF "is BLIND this stop" <<<"$OUT"; then
    pass "189d CONTROL: blindness is stated out loud, and nobody is accused"
else
    fail "189d CONTROL: a blind check answered anyway: ${OUT:0:300}"
fi

echo "== 189e. CONTROL for 189d: one .lastevent- file and the same call FLAGS =="
# Without this, 189d is satisfied by a function that never looks at anything.
printf '{"session_id":"deadbeef-x"}' >"${WL%.md}.lastevent-deadbeef.json"
OUT=$(probe_phantom)
if [[ "$OUT" == "FLAGGED: phantom1" ]]; then
    pass "189e CONTROL: one planted file, and the blindness turns into a verdict"
else
    fail "189e CONTROL: the probe cannot flag at all, so 189d proves nothing: ${OUT:0:300}"
fi

echo "== 190. v19 L3: --reassign moves the OPEN work and leaves the history alone =="
# BEFORE AND AFTER in one run. The before-assert is the control: without it the
# test passes on a store that already contained the item and the request.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store phantom1 90
# a request the phantom sent, and one sent TO it -- the incident's real damage
# was in .requests, so a repair that leaves those unreachable fixes the symptom
# nobody complained about and skips the one they did
brief_other phantom1
askid_as phantom1 deadbeef "the message that was lost" >/dev/null
brief_other cafe1234
PRID_TO=$(askid_as cafe1234 phantom1 "a question nobody read")
BEFORE_LIST=$(reqcli --list --open deadbeef 2>&1)
BEFORE_POLL=$(reqcli --poll deadbeef 2>&1)
if ! grep -qF "phantom-owned item" <<<"$BEFORE_LIST" && ! grep -qF "$PRID_TO" <<<"$BEFORE_POLL"; then
    pass "190 BEFORE: neither the items nor the unread request are visible to deadbeef"
else
    fail "190 BEFORE: the fixture already showed them, so the after-assert proves nothing"
fi
OUT=$(reqcli --reassign deadbeef phantom1 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "reassigned phantom1 -> deadbeef" <<<"$OUT"; then
    pass "190: --reassign reports what it moved"
else
    fail "190: --reassign failed (rc=$RC): ${OUT:0:300}"
fi
AFTER_LIST=$(reqcli --list --open deadbeef 2>&1)
AFTER_POLL=$(reqcli --poll deadbeef 2>&1)
if grep -qF "phantom-owned item" <<<"$AFTER_LIST"; then
    pass "190 AFTER: the phantom's open items are now in this session's slice"
else
    fail "190 AFTER: the items did not move: ${AFTER_LIST:0:300}"
fi
if grep -qF "$PRID_TO" <<<"$AFTER_POLL"; then
    pass "190 AFTER: the request nobody was reading is now in this session's inbox"
else
    fail "190 AFTER: the lost request is still unreachable: ${AFTER_POLL:0:300}"
fi
# The history must still say the phantom wrote them. A tidy log that lies about
# who did what is worse than an untidy one.
if grep -q '"by": *"phantom1"' <(wl_events) ||
    grep -q '"by":"phantom1"' <(wl_events); then
    pass "190: the event log still records phantom1 as the writer"
else
    fail "190: --reassign rewrote history instead of appending to it"
fi

echo "== 190b. CONTROL: --reassign refuses a peer that is FRESH but has never stopped =="
# THE REVIEW FINDING THIS PINS (medium, PR #551). The `.lastevent-` guard alone
# does not deliver the guarantee the docstring claims. That file is written at a
# session's FIRST STOP, so a peer that has added items and not yet stopped has
# no file either and is indistinguishable from a genuine phantom. Any session can
# read a peer's prefix out of `--list --open`, and concurrent sessions in one
# tree are routine here, so without an age gate a peer's OPEN items and request
# routing could be moved onto the caller WHILE that peer was working on them.
#
# Case 190 (the FIRE) ages its target 90 minutes and 190a's target has already
# stopped; NEITHER covers a merely-fresh, still-working target, so the untested
# path was the vulnerable one.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
# 2 minutes old and NO .lastevent- file: exactly the mid-first-turn peer.
phantom_store fresh999 2
OUT=$(reqcli --reassign deadbeef fresh999 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "mid-turn" <<<"$OUT"; then
    pass "190b CONTROL: a fresh peer that never stopped cannot be harvested"
else
    fail "190b CONTROL: took over a live peer's work (rc=$RC): ${OUT:0:300}"
fi
# CONTROL ON THE CONTROL: the SAME prefix, aged past the floor, still moves --
# so 190b proves an age gate and not a blanket refusal.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store fresh999 90
OUT=$(reqcli --reassign deadbeef fresh999 2>&1)
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "reassigned fresh999" <<<"$OUT"; then
    pass "190b CONTROL: the same prefix aged past the floor still reassigns"
else
    fail "190b CONTROL: the age gate refuses even a real phantom (rc=$RC): ${OUT:0:300}"
fi

echo "== 190c. --lease <id> release accepts the # this tool's own output prints =="
# REVIEW FINDING, PR #551: the release branch read argv[2] raw while every other
# verb goes through the .lstrip("#") at the top of _item_cli. So an id copied
# straight from this tool's OWN output -- it prints ids as `#abc123` -- appended
# an unlease event matching nothing, printed "released ##abc123", and left the
# item [>]. A verb that reports success while changing nothing is precisely what
# this suite exists to catch, and it shipped inside the fix for a different
# silent no-op.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
RID=$(reqcli --add deadbeef "item for the hash-prefix release case" | grep -oE "#[0-9a-f]+" | head -1 | tr -d '#')
reqcli --lease deadbeef "$RID" +30 worker:probe-worker "riding a probe" >/dev/null 2>&1
OUT=$(reqcli --lease deadbeef "#$RID" release "released with the hash form" 2>&1)
if grep -qF "released #$RID" <<<"$OUT" && ! grep -qF "##$RID" <<<"$OUT"; then
    pass "190c FIRE: the # form is accepted and echoed back singly"
else
    fail "190c FIRE: the # form was mangled: ${OUT:0:200}"
fi
STATE=$(reqcli --list --open deadbeef 2>&1 | grep -oE "\- \[.\] #$RID" | head -1)
if [[ "$STATE" == "- [ ] #$RID" ]]; then
    pass "190c FIRE: the item actually returned to open, not just a success message"
else
    fail "190c FIRE: reported success but the state is '$STATE'"
fi
# CONTROL: the bare form must keep working, so the fix is a widening and not a swap.
reqcli --lease deadbeef "$RID" +30 worker:probe-worker "riding again" >/dev/null 2>&1
reqcli --lease deadbeef "$RID" release "released with the bare form" >/dev/null 2>&1
STATE=$(reqcli --list --open deadbeef 2>&1 | grep -oE "\- \[.\] #$RID" | head -1)
if [[ "$STATE" == "- [ ] #$RID" ]]; then
    pass "190c CONTROL: the bare id form still releases"
else
    fail "190c CONTROL: the bare form broke: '$STATE'"
fi

echo "== 190a. CONTROL: --reassign refuses a session that HAS stopped =="
# The rule that stops this verb becoming a way to steal a live peer's items.
setup
brief_now
hand_now
say "all done, nothing outstanding"
run >/dev/null
phantom_store cafe1234 90
printf '{"session_id":"cafe1234-x"}' >"${WL%.md}.lastevent-cafe1234.json"
OUT=$(reqcli --reassign deadbeef cafe1234 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "it is a real session" <<<"$OUT"; then
    pass "190a CONTROL: a peer that has stopped cannot be harvested"
else
    fail "190a CONTROL: took over a live session's work (rc=$RC): ${OUT:0:300}"
fi
# And <me> itself faces the same identity check, so you cannot reassign TO a
# fiction and make the problem worse.
OUT=$(reqcli --reassign 4c3e095a phantom1 2>&1)
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "identity mismatch" <<<"$OUT"; then
    pass "190a CONTROL: you cannot reassign work TO an identity you are not"
else
    fail "190a CONTROL: --reassign accepted a foreign <me> (rc=$RC): ${OUT:0:200}"
fi
