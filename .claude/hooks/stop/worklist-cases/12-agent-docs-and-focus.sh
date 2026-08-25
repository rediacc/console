#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Per-agent bootstrap and adoption, detached HEAD, trap headings, supervised leases, and the focused one-check-per-stop rotation.

echo "== 153a. T1/T2: a missing agent/<me>/ blocks with the bootstrap, ONCE as a wall =="
# Decision 5: block with the exact bootstrap commands, NEVER auto-create (the
# RULES.md copy-forward is a judgement call a hook must not make). The WALL is
# shown once per branch per session, latched on agent_boot_told; the follow-up
# is a one-liner that keeps blocking without repeating itself.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
rm -rf "$BASE/proj/agent/deadbeef"
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "mkdir -p agent/deadbeef" <<<"$OUT" &&
    grep -qF "RULES.md" <<<"$OUT"; then
    pass "T1 FIRE: a missing session dir blocks with the exact bootstrap commands"
else
    fail "T1: bootstrap wall absent or wrong: ${OUT:0:200}"
fi
if [[ -d "$BASE/proj/agent/deadbeef" ]]; then
    fail "T1: the hook AUTO-CREATED the session dir (decision 5 violated)"
else
    pass "T1: the hook did not auto-create the directory"
fi
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT2="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT2" && grep -qF "still absent" <<<"$OUT2" &&
    ! grep -qF "mkdir -p agent/deadbeef" <<<"$OUT2"; then
    pass "T2: the second stop still blocks but the wall is not repeated"
else
    fail "T2: second-stop shape wrong: ${OUT2:0:200}"
fi
# SILENT control: with the dir restored and a fresh STATE.md the wall is gone.
# The world is moved first (task 8) or the third consecutive unmoved stop
# would trip the STUCK detector and this control would test the wrong gate.
mkdir -p "$BASE/proj/agent/deadbeef"
task 8 pending "moved"
hand_now
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
check "T1 CONTROL: dir present + fresh STATE.md allows, no bootstrap text" allow ""

echo "== 153b. T7a/T7b: adopt-on-first-sight, and the adopt NEVER fires on stale =="
# A second session arriving on a branch has no recorded signature for the
# document the first session wrote; the old pure-age fallback would order an
# immediate rewrite, reproducing the churn the redesign fixes. Adoption is
# bounded (60m) and fires ONLY on an "ok" verdict: banking the signature on a
# "stale" verdict would let the next stop compare cur_sig against a signature
# recorded DURING the block and allow -- a gate that clears itself without a
# rewrite. T7b is the anti-vacuity control: it must block TWICE running.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/agent/deadbeef/STATE.md" # planted: NO signature banked
touch -d '30 minutes ago' "$BASE/proj/agent/deadbeef/STATE.md"
check "T7a: an unsigned 30-minute document is ADOPTED, not rewritten" allow ""
if python3 -c "
import json, sys
doc = json.load(open('${WL%.md}.state-deadbeef.json'))
sys.exit(0 if doc.get('state_sig') else 1)"; then
    pass "T7a: the adopt banked state_sig into the state doc (read, not inferred)"
else
    fail "T7a: no state_sig was banked on the ok verdict"
fi
# T7b: age the document past the ADOPT horizon with no signature -> stale, and
# it must STAY stale on a second stop over an unchanged world.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/agent/deadbeef/STATE.md"
touch -d '90 minutes ago' "$BASE/proj/agent/deadbeef/STATE.md"
check "T7b FIRE: an unsigned 90-minute document is past the adopt horizon" block "STATE.md is stale"
newturn
say "answer

## Remaining
- #7 thing (pending)"
check "T7b ANTI-VACUITY: it blocks AGAIN on an unchanged world (no self-clear)" block "STATE.md is stale"
if python3 -c "
import json, sys
doc = json.load(open('${WL%.md}.state-deadbeef.json'))
sys.exit(1 if doc.get('state_sig') else 0)"; then
    pass "T7b: state_sig was NOT banked during the stale blocks"
else
    fail "T7b: the stale path banked a signature (the gate would clear itself)"
fi
# Move the world (task 8) before the control stop, or the fourth consecutive
# unmoved stop trips the STUCK detector instead of testing this gate.
task 8 pending "moved"
hand_now
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
check "T7b CONTROL: a real --state rewrite clears it" allow ""

echo "== 153b2. C12: a PEER's item must not stale MY recovery document =="
# The v18 bug this pins. state_world_sig hashed EVERY item regardless of owner,
# so with ~48 agents in one worktree any peer --add/--tick moved my key. A check
# whose contract is "an unchanged world never stales it" then degenerated into
# "fires every 15 minutes" -- indistinguishable from wall-clock at the point of
# observation, which is what made the WRONG fix (raise the limit) look obvious.
# v17 had already scoped world_sig this way; state_world_sig was left behind.
setup
brief_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
printf '%s' "$STATE_BODY" >"$BASE/proj/agent/deadbeef/STATE.md"
touch -d '30 minutes ago' "$BASE/proj/agent/deadbeef/STATE.md"
check "153b2 SETUP: the document is adopted and its signature banked" allow ""
# A DIFFERENT session adds its own item. Peer bookkeeping, not my world.
reqcli --add cafe1234 "peer item nobody else owns" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
check "153b2: a peer's item does NOT stale my recovery document" allow ""

echo "== 153b3. C12 CONTROL: MY OWN item still stales it =="
# Without this the narrowing above is indistinguishable from disabling the check.
#
# The item is ADDED AND TICKED in one go, deliberately. An item merely added is
# ALSO an open-items violation, and with only one rotating check surfaced per
# stop the hook showed that one instead -- my first draft asserted on a message
# the rotation had chosen not to print. Ticking leaves exactly one rotating
# violation, so what the stop surfaces is unambiguous.
IID=$(reqcli --add deadbeef "my own item, which IS a reason to rewrite" | grep -oE '#[0-9a-f]+' | tr -d '#')
reqcli --tick deadbeef "$IID" "landed, suite green, exit 0" >/dev/null
newturn
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF "STATE.md is stale" <<<"$OUT"; then
    pass "153b3: my own item still stales it -- the ownership scope did not disable the check"
else
    fail "153b3: the ownership scope swallowed a REAL staleness: ${OUT:0:400}"
fi

echo "== 153c. T9: a detached HEAD ENFORCES now; the branch cannot change the verdict =="
# INVERTED 2026-08-18, and the inversion is the point. This case used to assert
# the opposite -- that no resolvable branch made the STATE.md check REPORT-ONLY
# (operator decision 2026-07-30) -- because the document's path needed a branch
# to resolve. HEAD detaches during every interactive rebase and this operator
# rebase-merges everything, so that exemption meant the one artifact designed to
# survive compaction went unenforced for the whole of a rebase.
#
# The path is keyed on the SESSION now, so there is nothing to be blind about.
# The document is deleted first, deliberately: asserting "it did not block" on a
# healthy tree would pass just as well on a check that had been turned off. A
# MISSING document with work outstanding must block WITHOUT a branch, and the
# control immediately below runs the identical fixture WITH one and demands the
# same verdict -- which is the actual claim, that the branch no longer matters.
setup
brief_now
hand_now
rm -f "$BASE/proj/agent/deadbeef/STATE.md"
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
WORKLIST_AGENT_BRANCH=""
OUT="$(run)"
WORKLIST_AGENT_BRANCH=agenttest
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "STATE.md is missing" <<<"$OUT" &&
    ! grep -qF "freshness check is BLIND" <<<"$OUT"; then
    pass "T9: with NO branch resolvable the STATE.md gate still fires, and names no blindness"
else
    fail "T9: the branchless stop did not enforce STATE.md: ${OUT:0:300}"
fi
say "answer

## Remaining
- #7 thing (pending)"
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "STATE.md is missing" <<<"$OUT"; then
    pass "T9 CONTROL: the same fixture WITH a branch gives the same verdict"
else
    fail "T9 CONTROL: the branch changed the verdict: ${OUT:0:300}"
fi

echo "== 153d. T10/T11: trap TITLES feed the judge; bodies and ### never do =="
setup
mkdir -p "$BASE/proj/docs/agent-reference"
printf '# Traps\n\n## Real trap title one\n\nsecret body line\n\n### a sub-heading\n\n## Second title\n' >"$BASE/proj/docs/agent-reference/TRAPS.md"
OUT=$(
    python3 - "$(dirname "$HOOK")" "$BASE/proj" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import wl_store as S
import worklist_messages as M
heads = S.trap_headings(sys.argv[2])
prompt = M.JUDGE_PROMPT % {
    "streak": 1, "remaining": "r", "leases": 0, "loop": "l",
    "citations": "c", "message": "m",
    "traps": "\n".join("  - " + h for h in heads) or "  (none recorded)",
}
checks = [
    ("titles-only", heads == ["Real trap title one", "Second title"]),
    ("prompt-has-title", "Real trap title one" in prompt),
    ("prompt-no-body", "secret body line" not in prompt),
    ("prompt-no-subheading", "a sub-heading" not in prompt),
]
import pathlib
empty = S.trap_headings(sys.argv[2] + "/nonexistent")
checks.append(("absent-file-empty-list", empty == []))
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
PYEOF
)
if grep -qF "FAIL" <<<"$OUT"; then
    fail "T10/T11: $OUT"
else
    pass "T10/T11: judge sees ## titles only; bodies, ###, and absent files are safe"
fi

echo "== 153f. TRAP_HEADING_CAP: the live file is not silently truncated =="
# WHY A LIVE-FILE CASE AND NOT ONLY FIXTURES. The old cap was the literal 40 and
# TRAPS.md reached exactly 40 on 2026-08-23, one entry from invisibility, with
# no warning anywhere -- the list simply ended and the judge saw a corpus that
# looked complete. A fixture case cannot notice that, because a fixture never
# grows. This one compares the parser against the REAL file and reds the day the
# corpus outgrows the cap.
REPO_ROOT="$(cd "$(dirname "$HOOK")/../../.." && pwd)"
OUT=$(
    python3 - "$(dirname "$HOOK")" "$REPO_ROOT" "$BASE" <<'PYEOF'
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
import wl_store as S  # noqa: E402

repo, base = sys.argv[2], sys.argv[3]
cap = S.TRAP_HEADING_CAP
live = S.trap_headings(repo)
on_disk = sum(
    1
    for ln in (pathlib.Path(repo) / "docs/agent-reference/TRAPS.md")
    .read_text(encoding="utf-8", errors="replace")
    .splitlines()
    if ln.startswith("## ") and not ln.startswith("### ")
)

checks = [
    # THE ALARM. Equality alone would pass VACUOUSLY on a moved or renamed
    # TRAPS.md (0 == 0), so the floor is asserted separately.
    (
        "live-parses-every-heading (%d parsed vs %d on disk)" % (len(live), on_disk),
        len(live) == on_disk,
    ),
    ("live-file-is-not-empty (%d >= 42)" % on_disk, on_disk >= 42),
    ("live-file-under-cap (%d <= %d)" % (on_disk, cap), on_disk <= cap),
    ("live-has-no-sentinel", not any("further entries" in h for h in live)),
]

# ABOVE the cap: exactly one synthetic element, naming the count dropped.
over = pathlib.Path(base) / "capfix-over" / "docs" / "agent-reference"
over.mkdir(parents=True, exist_ok=True)
(over / "TRAPS.md").write_text(
    "".join("## heading %d\n\nbody\n\n" % i for i in range(cap + 5)), encoding="utf-8"
)
got_over = S.trap_headings(str(over.parents[1]))
checks += [
    ("over-cap-length-is-cap-plus-one (%d)" % len(got_over), len(got_over) == cap + 1),
    ("over-cap-sentinel-names-5", bool(got_over) and "+5 further entries" in got_over[-1]),
]

# THE CONTROL. Exactly AT the cap must be indistinguishable from under it: no
# sentinel, no truncation, nothing appended. Without this the sentinel arm
# passes just as happily with an off-by-one that tags every list ever built.
at = pathlib.Path(base) / "capfix-at" / "docs" / "agent-reference"
at.mkdir(parents=True, exist_ok=True)
(at / "TRAPS.md").write_text(
    "".join("## heading %d\n\nbody\n\n" % i for i in range(cap)), encoding="utf-8"
)
got_at = S.trap_headings(str(at.parents[1]))
checks += [
    ("CONTROL-at-cap-length-is-cap (%d)" % len(got_at), len(got_at) == cap),
    ("CONTROL-at-cap-has-no-sentinel", not any("further entries" in h for h in got_at)),
]

for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
PYEOF
)
if grep -qF "FAIL" <<<"$OUT"; then
    fail "153f: $OUT"
else
    pass "153f: the live TRAPS.md is fully parsed; the cap sentinel fires above it and stays off at it"
fi

echo "== 153e. T12: the silent poll survives an old STATE.md on a quiet world =="
# The poll fast path needs NO new forfeit: STATE.md staleness is world-keyed,
# so an unchanged world cannot stale it, and a moved world already forfeits
# the fast path at the world_sig comparison. Adding a forfeit would
# reintroduce the 5-minute-poll trap the world-keying exists to kill.
setup
brief_now
hand_now
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it WHY: operator trade HOW: operator answers' >>"$WL"
say "answer

## Remaining
- the flag decision, deferred with a default"
check "T12 baseline stop allows" allow ""
age_state deadbeef 25
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 && -z "$OUT" ]]; then
    pass "T12: a 25-minute STATE.md on an unchanged world keeps the silent poll"
else
    fail "T12: the old STATE.md forfeited the fast path: rc=$RC '${OUT:0:160}'"
fi
task 9 pending "world moved"
reqcli --poll deadbeef >/dev/null
OUT="$(run)"
if [[ -n "$OUT" ]]; then
    pass "T12 CONTROL: a moved world pays the full battery"
else
    fail "T12 CONTROL: the moved world stayed silent"
fi

echo "== 154. v18: NEXT WAKEUPS is GONE, and a broken schedule still warns =="
# Operator, 2026-08-04: "we don't need to print next wakeup times. We should
# just track the hook moments and notify/warn when needed. let's go for
# efficient ai context usage." The section printed every task's next firing on
# every full stop. This case is what remains of the old case 154: the display
# must be absent on BOTH emit paths, and the one actionable row it used to
# carry -- a schedule the hook cannot parse -- must still fire on its own.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"17 * * * *","prompt":"HOURLY LOOP fixture: advance the campaign."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
# A real item, so this stop has a guide to print: without one the whole report
# would be silent (v18) and the absence assertion below would pass vacuously.
echo '- [?] (deadbeef) keep the flag? DEFAULT: keep it' >>"$WL"
say "answer

## Remaining
- #7 thing (pending)
- the flag decision, deferred with a default"
task 7 pending "thing"
OUT="$(run)"
if ! grep -qF "NEXT WAKEUPS" <<<"$OUT" && ! grep -qF "HOURLY LOOP fixture" <<<"$OUT" &&
    ! grep -qF "INBOX POLL fixture" <<<"$OUT"; then
    pass "154a: the allow stop prints no wakeup times and no cron prompt labels"
else
    fail "154a: the wakeup display survived on allow: ${OUT:0:260}"
fi
# CONTROL that 154a is not vacuous: the stop DID produce its normal report, so
# the absence above is the section being gone rather than the hook being mute.
if grep -qF "WORKLIST GUIDE" <<<"$OUT" && grep -qF "keep the flag?" <<<"$OUT"; then
    pass "154a CONTROL: the stop still emitted its guide, so the absence is real"
else
    fail "154a CONTROL: the stop emitted nothing at all: ${OUT:0:260}"
fi
# The FOCUS=off dump-all block carried the section too; it must not any more.
age_state deadbeef 20
task 8 pending "moved"
newturn
say "answer

## Remaining
- #7 thing (pending)
- #8 moved (pending)"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF '"decision": "block"' <<<"$OUT" && ! grep -qF "NEXT WAKEUPS" <<<"$OUT"; then
    pass "154b: the FOCUS=off block carries no wakeup section either"
else
    fail "154b: the wakeup section survived on the dump-all block: ${OUT:0:220}"
fi
# THE SURVIVING WARNING. An unparseable schedule is invisible to every other
# cron check, so deleting the display must not delete this.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"not a cron","prompt":"BROKEN fixture."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
if grep -qF "CANNOT PARSE" <<<"$OUT" && grep -qF "BROKEN fixture." <<<"$OUT"; then
    pass "154c: an unparseable schedule is still named, on its own warning"
else
    fail "154c: a broken schedule went silent with the section: ${OUT:0:260}"
fi
# CONTROL: with every schedule valid the warning is silent, so it reports a
# real defect rather than firing on any cron list at all.
setup
brief_now
hand_now
CRONS='[{"id":"w","schedule":"17 * * * *","prompt":"HOURLY LOOP fixture."},{"id":"p","schedule":"*/5 * * * *","prompt":"INBOX POLL fixture."}]'
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
OUT="$(run)"
if ! grep -qF "CANNOT PARSE" <<<"$OUT"; then
    pass "154c CONTROL: valid schedules raise no warning"
else
    fail "154c CONTROL: the warning fired on a healthy cron list: ${OUT:0:260}"
fi

echo "== 155. supervised MUST correlate to the live worker, not just be fresh =="
# Real review finding (PR #546, comment 3686791985): the freshest [>] item
# across ALL in-flight records was taken as proof of supervision, with no
# check that it names the SAME worker as the one in live_bg. Two leases: one
# tracking bw1 (the actual watched job) gone STALE past the threshold, one
# tracking an UNRELATED worker zz9 kept FRESH. The unrelated fresh one must
# NOT excuse the stale one -- that is exactly the forgotten-watch case this
# exemption exists to exclude.
export WORKLIST_STUCK_ROUNDS=1
setup
brief_now
hand_now
STALE=$(date -u -d '-100 minutes' +%Y-%m-%dT%H:%M:%SZ)
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"bbbb0001","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"watching the real job"}\n{"ev":"lease","id":"bbbb0001","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$STALE" "$STALE" "$UNTIL" >>"${WL%.md}.events.jsonl"
printf '{"ev":"add","id":"bbbb0002","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"unrelated, still being renewed"}\n{"ev":"lease","id":"bbbb0002","at":"%s","by":"deadbeef","until":"%s","worker":"zz9"}\n' \
    "$FRESH" "$FRESH" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the actual watched job"}]'
task 9 pending "thing"
say "answer

## Remaining
- #9 thing (pending), watched via bw1 and zz9"
for i in 1 2 3; do LAST="$(run)"; done
if grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST"; then
    pass "155: an uncorrelated fresh lease does NOT excuse a stale supervising one"
else
    fail "155: the unrelated fresh lease wrongly silenced the exempt-overrun: ${LAST:0:220}"
fi

echo "== 155b. CONTROL: the CORRELATED lease being fresh DOES supervise =="
setup
brief_now
hand_now
FRESH=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UNTIL=$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ)
printf '{"ev":"add","id":"bbbb0003","at":"%s","by":"deadbeef","s":" ","o":"deadbeef","t":"watching the real job"}\n{"ev":"lease","id":"bbbb0003","at":"%s","by":"deadbeef","until":"%s","worker":"bw1"}\n' \
    "$FRESH" "$FRESH" "$UNTIL" >>"${WL%.md}.events.jsonl"
BG='[{"id":"bw1","type":"shell","status":"running","description":"the actual watched job"}]'
task 9 pending "thing"
say "answer

## Remaining
- #9 thing (pending), watched via bw1"
for i in 1 2 3; do LAST="$(run)"; done
if ! grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST"; then
    pass "155b CONTROL: a fresh lease correlated to the live worker DOES supervise"
else
    fail "155b: a genuinely fresh, correlated lease still fired: ${LAST:0:220}"
fi
unset WORKLIST_STUCK_ROUNDS

echo "== 156. v13 FOCUS: one rotating check per stop, LRU rotation =="
# Two rotating checks outstanding (an open item and a stale brief). Stop 1
# surfaces exactly one; stop 2 surfaces the OTHER; stop 3 cycles back. The
# header counts what is held back, so nothing is silently forgotten.
setup
hand_now
export WORKLIST_STUCK_ROUNDS=99
echo '- [ ] (deadbeef) open thing' >>"$WL"
# no brief_now: the session-brief check is the second rotating violation.
# The message carries a '## Remaining' section so exactly TWO rotating
# checks are outstanding and the cycle length is 2, not 3.
say "answer

## Remaining
- the open thing (pending, mine)"
OUT1="$(run)"
newturn
say "answer

## Remaining
- the open thing (pending, mine)"
OUT2="$(run)"
newturn
say "answer

## Remaining
- the open thing (pending, mine)"
OUT3="$(run)"
unset WORKLIST_STUCK_ROUNDS
has() { grep -qF "$2" <<<"$1"; }
o1_open=$(has "$OUT1" "OPEN worklist item" && echo y || echo n)
o1_brief=$(has "$OUT1" "session brief" && echo y || echo n)
o2_open=$(has "$OUT2" "OPEN worklist item" && echo y || echo n)
o2_brief=$(has "$OUT2" "session brief" && echo y || echo n)
if [[ "$o1_open$o1_brief" == "yn" || "$o1_open$o1_brief" == "ny" ]] &&
    [[ "$o2_open$o2_brief" == "yn" || "$o2_open$o2_brief" == "ny" ]] &&
    [[ "$o1_open" != "$o2_open" ]] &&
    grep -qF "check(s) outstanding, surfacing" <<<"$OUT1" &&
    grep -qF "more check(s) outstanding" <<<"$OUT1"; then
    pass "156: each stop surfaces exactly one rotating check, and they alternate"
else
    fail "156: rotation wrong (stop1 open=$o1_open brief=$o1_brief, stop2 open=$o2_open brief=$o2_brief)"
fi
o3_open=$(has "$OUT3" "OPEN worklist item" && echo y || echo n)
if [[ "$o3_open" == "$o1_open" ]]; then
    pass "156b: stop 3 cycles back to stop 1's check (LRU, nothing starves)"
else
    fail "156b: rotation did not cycle (stop1 open=$o1_open, stop3 open=$o3_open)"
fi
unset -f has

echo "== 156c. CONTROL: WORKLIST_FOCUS=off restores the dump-all block =="
# The revert control for the whole feature: the same two-check fixture shows
# BOTH bodies in one block when focus is off.
setup
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
say "answer"
export WORKLIST_FOCUS=off
OUT="$(run)"
unset WORKLIST_FOCUS
if grep -qF "OPEN worklist item" <<<"$OUT" && grep -qF "session brief" <<<"$OUT" &&
    grep -qF "check(s) failed" <<<"$OUT"; then
    pass "156c CONTROL: FOCUS=off carries every violation in one block"
else
    fail "156c: FOCUS=off lost a violation: ${OUT:0:300}"
fi

echo "== 156d. ALWAYS tier rides every focused block beside the rotation =="
# CI-red is latched (its block budget is spent at compute time), so hiding it
# behind rotation would swallow it forever. It must appear IN ADDITION to the
# one rotating check.
ci_setup
ci_rollup FAILURE "[$(ci_job "Quality / Static" FAILURE)]"
echo '- [ ] (deadbeef) open thing' >>"$WL"
out="$(ci_run)"
if grep -qF '"decision": "block"' <<<"$out" && grep -qF "CI IS RED ON PR" <<<"$out" &&
    grep -qF "OPEN worklist item" <<<"$out"; then
    pass "156d: the latched CI-red text and one rotating check ride the same focused block"
else
    fail "156d: ALWAYS tier missing from the focused block: ${out:0:400}"
fi

echo "== 157. CI-queue backpressure: a saturated queue says DO NOT PUSH =="
