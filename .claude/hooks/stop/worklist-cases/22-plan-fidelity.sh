#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Plan-drift binding, unknown-plan orientation, --intent, the brief work-gate, --update carry, reggate probes, and Tier-2 plan fidelity.

echo "== 215. PLAN DRIFT: the session is bound to its own committed design record =="
# The gap the operator named: plans were surfaced at SessionStart and PostCompact
# and NOWHERE else, so a session could work all day while the committed plan
# describing that work went stale. plan_records() existed; nothing on the stop
# path called it.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/agent"
cat >"$BASE/proj/agent/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: executing
MD
# Backdate the plan, then move MY work after it. The trigger is the work, never
# the clock: a plan a week old on a branch where nothing moved is accurate.
touch -d '-2 hours' "$BASE/proj/agent/PLAN-thing.md"
# A TICKED item, deliberately. It stamps `upd` (which is what "my work moved"
# reads) without leaving anything open, so plan-drift is the ONLY rotating check
# outstanding. The focused block surfaces exactly one of those, so an open item
# here would win the rotation and this case would score whichever check happened
# to be picked -- which is how its first version passed its three controls while
# the thing they control for never fired at all.
# FOUR ticked items, not one. The check requires a THRESHOLD of moved work
# (PLAN_DRIFT_MIN_MOVES) rather than any movement at all, because a single tick
# is not a plan going stale -- and treating it as one made the check
# unsatisfiable: update the plan, tick the next item, stale again immediately.
for n in 1 2 3 4; do
    PID="$(reqcli --add deadbeef "work $n that outran the plan" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
    reqcli --tick deadbeef "$PID" "landed, suite green, exit 0" >/dev/null
done
check "215: a plan the work has moved past is flagged" block "PLAN-thing.md"

echo "== 215a. CONTROL: ONE tick is not a plan going stale =="
# The threshold is what makes the exit real. Without this control the check
# could go back to firing on any movement, which is the unsatisfiable version.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/agent"
cat >"$BASE/proj/agent/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: executing
MD
touch -d '-2 hours' "$BASE/proj/agent/PLAN-thing.md"
PID="$(reqcli --add deadbeef 'one small thing' | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$PID" "landed, exit 0" >/dev/null
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215a CONTROL: a single tick does not stale a plan"
else
    fail "215a CONTROL: one tick flagged the plan: ${OUT:0:240}"
fi

echo "== 215b. CONTROL: the same plan, touched AFTER the work, is silent =="
# Without this the check could be firing on the mere existence of a plan file,
# which would make it noise within a day.
touch "$BASE/proj/agent/PLAN-thing.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215b CONTROL: an up-to-date plan is not flagged"
else
    fail "215b CONTROL: a fresh plan was still flagged: ${OUT:0:240}"
fi

echo "== 215c. CONTROL: a DONE plan is history and is never flagged =="
# Demanding edits to history is how a check earns its way into being ignored.
cat >"$BASE/proj/agent/PLAN-thing.md" <<'MD'
# PLAN: the thing
Status: done
MD
touch -d '-2 hours' "$BASE/proj/agent/PLAN-thing.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if ! grep -qF "PLAN-thing.md" <<<"$OUT"; then
    pass "215c CONTROL: a done plan is never flagged"
else
    fail "215c CONTROL: a done plan was flagged: ${OUT:0:240}"
fi

echo "== 215d. CONTROL: a project with NO plan directory pays nothing and says nothing =="
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) work with no plan anywhere' >>"$WL"
OUT="$(run)"
if ! grep -qF "committed plan file" <<<"$OUT"; then
    pass "215d CONTROL: no plan directory means no plan-drift complaint"
else
    fail "215d CONTROL: complained about plans that do not exist: ${OUT:0:240}"
fi

echo "== 216. an UNKNOWN plan carries a DESCRIPTION and FILE POINTERS =="
# An UNKNOWN status told the one reader who has no context precisely nothing:
# "this plan cannot be parsed", full stop. It now carries the plan's title and
# the files it keeps referring to, so a new or compacted session knows what to
# open first.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
mkdir -p "$BASE/proj/agent"
cat >"$BASE/proj/agent/PLAN-mystery.md" <<'MD'
# PLAN: the mystery subject

**Status (dated parenthetical): this shape does not parse**

The work lives in pkg/chunkstore/pipeline_linux.go and pkg/chunkstore/pipeline_linux.go
again, plus cmd/renet/backup_snapshot.go. A passing mention of docs/agent-reference/ci-gates.md.
MD
touch -d '-2 hours' "$BASE/proj/agent/PLAN-mystery.md"
for n in 1 2 3 4; do
    PID="$(reqcli --add deadbeef "work $n" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
    reqcli --tick deadbeef "$PID" "landed, exit 0" >/dev/null
done
OUT="$(run)"
if grep -qF "the mystery subject" <<<"$OUT" && grep -qF "pkg/chunkstore/pipeline_linux.go" <<<"$OUT"; then
    pass "216: an UNKNOWN plan names its subject and the files to open"
else
    fail "216: no orientation on an UNKNOWN plan: ${OUT:0:320}"
fi

echo "== 216b. CONTROL: the most-mentioned file leads, and the plan itself is never listed =="
# A plan's own path is not a pointer to anywhere useful, and a file mentioned
# once is a passing reference rather than the subject.
if ! grep -qF "PLAN-mystery.md; opens" <<<"$OUT" && ! grep -qF "opens: docs/agent-reference/ci-gates.md" <<<"$OUT"; then
    pass "216b CONTROL: self-reference excluded and ranking puts the subject first"
else
    fail "216b CONTROL: bad pointer list: ${OUT:0:320}"
fi

echo "== 216c. CONTROL: a plan with a READABLE status gets no orientation =="
# The orientation is for UNKNOWN specifically. If it appeared on every row it
# would just be noise on plans whose state is already clear.
cat >"$BASE/proj/agent/PLAN-mystery.md" <<'MD'
# PLAN: the mystery subject
Status: executing

The work lives in pkg/chunkstore/pipeline_linux.go.
MD
touch -d '-2 hours' "$BASE/proj/agent/PLAN-mystery.md"
newturn
say "still working

## Remaining
- stuff"
OUT="$(run)"
if grep -qF "PLAN-mystery.md" <<<"$OUT" && ! grep -qF "opens:" <<<"$OUT"; then
    pass "216c CONTROL: a readable status is flagged without orientation noise"
else
    fail "216c CONTROL: ${OUT:0:320}"
fi

echo "== 217. --intent answers the two STATUS-QUESTION checks, and nothing else =="
# An intent is a statement of PLAN. Its whole legitimate power is answering the
# checks whose entire content is "what are you doing" -- brief and agent-state --
# and reordering attention. It is never evidence.
setup
say "answer

## Remaining
- stuff"
hand_now
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "old" >>"${WL%.md}.sessions"
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "217: without an intent the stale brief is one of the outstanding checks" block "OPEN worklist item"
reqcli --intent deadbeef "driving the open thing to green" --covers open-items --for 60 >/dev/null
OUT="$(run)"
if ! grep -qF "session brief is stale" <<<"$OUT"; then
    pass "217: a live intent answers the stale-brief question"
else
    fail "217: brief still fired under a live intent: ${OUT:0:260}"
fi

echo "== 217b. C8: an intent must NOT satisfy the TICK-EVIDENCE gate =="
# The plan names this as decisive. "I am working on it" is not evidence, and if
# an intent could close an item the ledger becomes a record of intentions.
IID="$(reqcli --add deadbeef 'needs real evidence' | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
OUT="$(reqcli --tick deadbeef "$IID" "I have an intent covering this" 2>&1 || true)"
if grep -qF "REFUSED" <<<"$OUT"; then
    pass "217b C8: a tick still demands real evidence with an intent live"
else
    fail "217b C8: an intent satisfied the evidence gate: ${OUT:0:240}"
fi

echo "== 217c. an intent NEVER suppresses open-items, only reorders it =="
# Covered keys sort LAST but stay in `violations`, so the header count stays
# truthful. An intent reorders attention; it does not make work disappear.
OUT="$(run)"
if grep -qE "check\(s\) outstanding" <<<"$OUT"; then
    pass "217c: covered work is still counted as outstanding, not silently dropped"
else
    fail "217c: outstanding count vanished under an intent: ${OUT:0:240}"
fi

echo "== 217d. an EXPIRED intent becomes its own violation =="
# This is what stops --intent being a mute button: going quiet has a horizon,
# and outliving it while the work is still open is itself the finding.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
# NO open item on purpose. The focused block surfaces ONE rotating check, so an
# open item here would win the rotation and this case would score whichever
# check happened to be picked rather than the expiry -- the same trap that made
# an earlier fixture pass its controls while the thing they controlled for never
# fired. An expired intent is a violation in its own right, which is precisely
# what stops --intent being a mute button.
python3 - "$WL" <<'PYEOF'
import json, sys, datetime, pathlib
p = pathlib.Path(sys.argv[1]).with_suffix(".intents")
old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
p.write_text(json.dumps({"at": old, "by": "deadbeef", "text": "said long ago", "covers": ["open-items"], "min": 30}) + "\n")
PYEOF
check "217d: an expired intent blocks in its own right" block "stated intent has EXPIRED"

echo "== 217e. CONTROL: an expired intent covering only CLOSED work stays quiet =="
# V_INTENT_EXPIRED tells the reader "what it covered is still outstanding", and
# until v18 the check never verified that. It fired live on an intent whose one
# covered item had been ticked WITH EVIDENCE, so the message asserted something
# demonstrably false. This is 217d's control: same expired intent, same
# horizon, the ONLY difference is that the covered item is closed.
#
# 217d keeps firing because its `covers` names "open-items", which resolves to
# no record -- unresolvable is deliberately NOT treated as done.
setup
say "answer

## Remaining
- stuff"
brief_now
hand_now
ADDOUT="$(reqcli --add deadbeef 'the work the intent covered')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
reqcli --tick deadbeef "$AID" "suite run green, exit 0" >/dev/null 2>&1
python3 - "$WL" "$AID" <<'PYEOF'
import json, sys, datetime, pathlib
p = pathlib.Path(sys.argv[1]).with_suffix(".intents")
old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
p.write_text(json.dumps({"at": old, "by": "deadbeef", "text": "said long ago",
                         "covers": [sys.argv[2]], "min": 30}) + "\n")
PYEOF
check_absent "217e: an expired intent whose covered work is DONE stays quiet" allow "stated intent has EXPIRED"

echo "== 210. the brief work-gate: an old brief on an UNCHANGED world =="
# A brief goes stale when the WORLD moves, not when the clock does. A sentence
# that still describes what this session is doing is still true at 200 minutes,
# and nagging for a rewrite of an accurate sentence trains the reader to dismiss
# the check.
#
# Uses the REAL --brief CLI, because only that path stamps the world signature
# the gate compares. The direct .sessions writes elsewhere in this suite
# deliberately carry no signature and must keep falling back to wall-clock --
# case 5 above is that fallback, and it still blocks.
#
# hand_now() is required, not decoration: the hook surfaces ONE outstanding
# check, so without a STATE.md this case would pass or fail on whichever
# complaint happened to win the rotation rather than on the brief.
setup
say "answer

## Remaining
- nothing open"
hand_now
TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
    WORKLIST_AGENT_BRANCH=agenttest python3 "$HOOK" --brief deadbeef "doing the thing" >/dev/null 2>&1
# Backdate it. Last line for a prefix wins, so this is an append like any other.
printf '%s %s %s\n' deadbeef "$(date -u -d '-200 minutes' +%Y-%m-%dT%H:%M:%SZ)" "doing the thing" >>"${WL%.md}.sessions"
check_absent "an old brief on an unchanged world does NOT nag" allow "session brief is stale"

echo "== 210b. CONTROL: the same old brief once the world MOVES =="
# Without this the gate above could be a check that can never fire. Same fixture
# and the same 200-minute-old brief; the only difference is that the world moved,
# which is exactly when peers can no longer see what this session is doing.
#
# A DONE item, deliberately: it moves the item structure the signature covers
# without leaving anything open, so the brief stays the only thing left to
# complain about and the rotation cannot surface something else instead.
echo '- [x] (deadbeef) a finished piece of work' >>"$WL"
check "an old brief blocks once the world has moved" block "session brief is stale"

echo "== 218. --update on a [?] CARRIES its DEFAULT forward instead of dropping it =="
# The trap this pins: the rendered line carries only the MOST RECENT update, so
# an --update that omitted DEFAULT: made the deferral's default INVISIBLE, and
# the next stop blocked on a [?] that provably had one when it was written.
# Found live, by the session that wrote this.
#
# Refusing the update was the first fix and case 141 killed it: a refresh is
# "the exit is always available", and the aged-deferral rung tells a session to
# refresh. So the default is carried forward and the carry is ANNOUNCED. The
# defect was silence, not the exit.
setup
ADDOUT="$(reqcli --add deadbeef 'a thing needing an operator ruling')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
reqcli --defer deadbeef "$AID" \
    'which way? DEFAULT: take the left fork WHY: only the operator picks HOW: they answer' \
    >/dev/null 2>&1
if reqcli --update deadbeef "$AID" "made progress" >/dev/null 2>"$BASE/upd.err"; then
    if grep -qF "carried forward verbatim" "$BASE/upd.err" &&
        reqcli --list | grep -qF "DEFAULT: take the left fork"; then
        pass "the default survived the update, and the carry was announced"
    else
        fail "218: default lost or carry silent: $(head -c 200 "$BASE/upd.err")"
    fi
else
    fail "218: the refresh exit was removed (case 141 pins that it must stay)"
fi

echo "== 218b. CONTROL: an OPEN item is untouched, and no carry is announced =="
# Without this, 218 could pass because --update announces a carry for
# EVERYTHING. The only difference here is the item's state.
setup
ADDOUT="$(reqcli --add deadbeef 'ordinary open work')"
AID="$(sed -n 's/^added #\([0-9a-f]\{8\}\).*/\1/p' <<<"$ADDOUT")"
if reqcli --update deadbeef "$AID" "made progress" >/dev/null 2>"$BASE/upd2.err"; then
    if grep -qF "carried forward verbatim" "$BASE/upd2.err"; then
        fail "218b: the [?] carry rule leaked onto an open item"
    else
        pass "an open item is untouched by the [?] default rule"
    fi
else
    fail "218b: an ordinary update on an open item was rejected"
fi

echo "== 219. the reggate probe SEES package-local gates =="
# Nine real gates live under packages/*/scripts (check:ci-tutorial-parity,
# check:ci-locale-tutorial-assets, check:ci-solution-videos, ...), because a
# gate about www content belongs beside www. The probe's globs once covered
# only scripts/check-*.ts, so it answered "no new or changed check script
# found; a claimed gate must leave one" at a session that had just written
# packages/www/scripts/check-tutorial-card-fonts.ts, wired its check:ci-* key
# and proven it with a planted defect. The only way to satisfy it was to move
# a www gate to the repo root, letting the probe dictate layout.
if python3 -c "
import sys
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
assert 'packages/*/scripts/check-*.ts' in R.CHECK_SCRIPT_GLOBS, R.CHECK_SCRIPT_GLOBS
" 2>"$BASE/reggate-glob.err"; then
    pass "219: the probe globs cover package-local check scripts"
else
    fail "219: the probe is blind to packages/*/scripts gates ($(cat "$BASE/reggate-glob.err"))"
fi

echo "== 219b. CONTROL: widening the globs must not stampede every gate =="
# 219 alone would pass on a probe that runs all 224 visible scripts at up to
# REGGATE_TIMEOUT_S each, i.e. a stop hook measured in tens of minutes. The
# probe only exercises gates the working tree TOUCHED; everything else is
# seeded. This control pins that discrimination, and errs toward running.
if python3 -c "
import sys, subprocess
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
root = subprocess.run(['git','rev-parse','--show-toplevel'], capture_output=True,
                      text=True, check=True).stdout.strip()
clean = subprocess.run(['git','ls-files','--','packages/www/scripts/check-tutorial-parity.ts'],
                       cwd=root, capture_output=True, text=True, check=True).stdout.strip()
assert clean, 'fixture missing: check-tutorial-parity.ts is not tracked'
dirty = subprocess.run(['git','status','--porcelain','--',clean], cwd=root,
                       capture_output=True, text=True, check=True).stdout.strip()
assert not dirty, 'fixture moved: check-tutorial-parity.ts is modified in this tree'
assert R._is_dirty(clean, root) is False, 'an untouched gate was reported dirty'
# And it must err toward RUNNING: a path git cannot report on is treated as touched.
assert R._is_dirty(clean, '/nonexistent-repo-root') is True, 'a git failure must not skip a gate'
" 2>"$BASE/reggate-dirty.err"; then
    pass "219b CONTROL: an untouched gate is seeded, not re-run"
else
    fail "219b: dirty-detection does not discriminate ($(cat "$BASE/reggate-dirty.err"))"
fi

echo "== 219c. the reggate accepts a case on a surface that is NOT a check script =="
# ci.yml has six regression surfaces; the globs above see one. A fix whose home
# is an E2E case, an ops step, an install script or a unit test had NO
# acceptable answer -- the only provable artifact was a static gate, which for a
# behavioural defect asserts that the source still looks right. The judge now
# names the surface and the path, and the probe checks THAT path, so a surface
# this machinery has never heard of still has a checkable answer.
if python3 -c "
import sys, subprocess
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
root = subprocess.run(['git','rev-parse','--show-toplevel'], capture_output=True,
                      text=True, check=True).stdout.strip()
# A tracked, UNTOUCHED file proves nothing: the case has to have been written.
clean = 'packages/www/scripts/check-tutorial-parity.ts'
ok, note = R.prove_named_artifact(root, clean)
assert ok is False, 'an untouched artifact was accepted as proof: %r' % (note,)
assert 'did not touch' in note, note
# A path that does not exist proves nothing either.
ok, note = R.prove_named_artifact(root, 'packages/e2e-tests/tests/99-no-such.test.ts')
assert ok is False and 'does not exist' in note, note
# CONTROL: the escape hatches must not be reachable.
for bad in ('', '   ', '../etc/passwd', '/etc/passwd'):
    ok, note = R.prove_named_artifact(root, bad)
    assert ok is False, 'traversal or empty path accepted: %r' % (bad,)
# A DOTFILE PATH must resolve. The first spelling used lstrip('./'), which takes
# a character SET, so '.claude/hooks/...' arrived as 'claude/hooks/...' and every
# hook-surface artifact was reported as nonexistent. This control is why that was
# caught before it shipped.
# ASSERT RESOLUTION, NOT DIRTINESS. The first spelling of this control required
# the file to be dirty, which was true while it was being written and false the
# moment it was committed: a fixture that depends on the working tree passes
# today and fails tomorrow. What the lstrip bug produced was 'does not exist';
# that is the thing to pin.
for spelling in ('.claude/hooks/stop/wl_reggate.py', './.claude/hooks/stop/wl_reggate.py'):
    ok, note = R.prove_named_artifact(root, spelling)
    assert 'does not exist' not in note, 'a dotfile path did not resolve: %r' % (note,)
" 2>"$BASE/reggate-artifact.err"; then
    pass "219c: the named-artifact probe rejects untouched, absent and traversal paths"
else
    fail "219c: named-artifact proof is not discriminating ($(cat "$BASE/reggate-artifact.err"))"
fi

echo "== 219g. a docs-only tick is BANKED, not re-discovered every stop =="
# Real bug, found in review, not by a control. `tick_touches_code` correctly kept a
# docs-only tick out of `ids`/`ticks` (so it is never asked about), but the id was then
# dropped ENTIRELY -- never returned at all -- so the caller's only bank site
# (`reg_new_ticks`) never saw it. A stop with only a docs-only tick and no new commit hit
# neither of the caller's two save branches, so nothing was written to disk, and the same
# tick was rediscovered and re-filtered on every future stop, forever.
if python3 -c "
import sys, subprocess
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
root = subprocess.run(['git','rev-parse','--show-toplevel'], capture_output=True,
                      text=True, check=True).stdout.strip()
head = subprocess.run(['git','rev-parse','HEAD'], cwd=root, capture_output=True,
                      text=True, check=True).stdout.strip()
line = '- [x] fixed a typo in docs/agent-reference/TRAPS.md'
lines = [line]
state = {'head': head, 'seen_ticks': [], 'fixsets': {}, 'gate_runs': {}}
descriptions, ids, ticks, new_head, banked = R.fix_signals(root, lines, 'sess', state)
assert ids == [] and ticks == [], 'a docs-only tick was asked about: %r %r' % (ids, ticks)
tid = R._tick_id(line)
assert banked == [tid], 'the docs-only tick id was not banked: got %r, want [%r]' % (banked, tid)
# CONVERGENCE: once banked, the SAME tick must not reappear as new_ticks on the next pass.
state['seen_ticks'] = banked
descriptions2, ids2, ticks2, _, banked2 = R.fix_signals(root, lines, 'sess', state)
assert banked2 == [], 'a banked docs-only tick was rediscovered: %r' % (banked2,)
" 2>"$BASE/reggate-bank.err"; then
    pass "219g: a docs-only tick is banked once and never rediscovered"
else
    fail "219g: docs-only ticks are not converging ($(cat "$BASE/reggate-bank.err"))"
fi

echo "== 219f. a settled fixset RECORDS the surface it was routed to =="
# Found by dogfooding, not review: sixteen settled fixsets carried no surface at all,
# because the judge produced one, the router used it, and the settle path dropped it. The
# only question worth asking of the routing -- is it any good? -- was unanswerable from
# the record, and it had already misrouted a www DOM change to packages/e2e-tests.
if grep -q '"surface": str(rg.get("surface", ""))' "$(dirname "$HOOK")/wl_checks.py" &&
    grep -q '"artifact": str(rg.get("artifact", ""))' "$(dirname "$HOOK")/wl_checks.py"; then
    pass "219f: the settle path persists surface and artifact"
else
    fail "219f: a settled fixset drops the routing, so the record cannot be audited"
fi

echo "== 219e. ONE fix asked per stop, and only code-touching ticks =="
# Every commit and every new tick of a stop used to be hashed into ONE fix-set,
# so a single verdict had to cover unrelated fixes. Asking per item is the
# operator's rule; asking about all of them at once would wall a busy stop in
# behind eight simultaneous demands, so the rest stay unbanked for later stops.
if python3 -c "
import sys
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
# The docs-only filter mirrors the one commits already face, and it FAILS TOWARD
# ASKING: no path is not evidence that nothing shipped.
assert R.tick_touches_code('- [x] #a (me) packages/cli/src/foo.ts:12 exit 0') is True
assert R.tick_touches_code('- [x] #a (me) docs/agent-reference/TRAPS.md and README.md') is False
assert R.tick_touches_code('- [x] #a (me) no paths at all, exit 0') is True, \
    'a tick with no path was silently dropped'
assert R.tick_touches_code('- [x] #a (me) docs/x.md plus packages/www/src/a.css') is True, \
    'a mixed tick was treated as docs-only'
" 2>"$BASE/reggate-onetick.err"; then
    pass "219e: code-touching filter fails toward asking"
else
    fail "219e: the per-tick filter is wrong ($(cat "$BASE/reggate-onetick.err"))"
fi

echo "== 219d. CONTROL: a static gate still faces the STRICTER probe =="
# 219c alone would pass on a machinery that let ANY touched file settle a
# finding, which would gut the wired-and-green requirement for check:ci-* keys.
# The named-artifact path is consulted only when the judge routed AWAY from
# `gates`; `gates` and `none` must still go through prove_new_gate.
if python3 -c "
import sys, subprocess
sys.path.insert(0, '$(dirname "$HOOK")')
import wl_reggate as R
src = open(R.__file__, encoding='utf-8').read()
assert 'surface not in (' in src and 'gates' in src and 'none' in src, 'fence gone'
# The fence as ruff formats it, double quotes and all.
assert 'if surface and surface not in (' in src, \
    'the named-artifact shortcut is no longer fenced away from static gates'
" 2>"$BASE/reggate-fence.err"; then
    pass "219d CONTROL: the shortcut is fenced away from static gates"
else
    fail "219d: a static gate could be settled by touching any file ($(cat "$BASE/reggate-fence.err"))"
fi

# ============================================================================
# 220. PLAN FIDELITY (stop/wl_planfid.py, wired in wl_checks.planfid_check).
#
# The 2026-08-19 incident, driven end to end through the real hook: an operator
# approved a plan with several discrete tasks and the session tracked it as two
# umbrella items ('www round 4 Wave A', 'www round 4 Waves B-D'), which leaves
# the open-item gate unable to tell one task from twenty.
#
# Every case here carries its own control, and 220c is the one that matters
# most: the shim still says 'unfaithful' and the check must stay SILENT because
# no plan was ever approved. Without it, a passing 220 would only prove that a
# canned answer can be printed.
# ============================================================================

shim_planfid() { # shim_planfid '<plan_fidelity JSON>' -- a canned claude
    # Answers the PLAN-FIDELITY call and gives every other call the ordinary
    # 'stop' verdict, because a case that turns the judge on must not make the
    # main judge fail closed on an answer meant for someone else. Every
    # invocation is COUNTED, which is what lets a case assert that the
    # PREFILTER, and not the model, was the thing that stayed quiet.
    cat >"$BASE/binonly/claude" <<SHIMEOF
#!/usr/bin/env python3
import json, sys
prompt = " ".join(sys.argv[1:])
if "DECOMPOSITION" in prompt:
    open("$BASE/planfid-calls", "a").write("call\n")
    out = {"is_error": False,
           "structured_output": {"plan_fidelity": json.loads('''$1''')}}
else:
    out = {"is_error": False,
           "structured_output": {"verdict": "stop", "reason": "ok", "next_action": "none"}}
print(json.dumps(out))
SHIMEOF
    chmod +x "$BASE/binonly/claude"
    : >"$BASE/planfid-calls"
}

planfid_calls() { # how many times the plan-fidelity call was actually made
    if [[ -f "$BASE/planfid-calls" ]]; then wc -l <"$BASE/planfid-calls"; else echo 0; fi
}

plant_plan() { # plant_plan -- write the fixture plan and record its APPROVAL
    cat >"$BASE/plan.md" <<'PLANEOF'
# round 4: the page frame, the voice, and a docs surface

## Context

Round 3 shipped and is on the open PR. This round is the operator's next pass,
and the decisions below are locked by them.

## Waves

### Wave A: the page frame

- The nav container gains a 1280px max-width and 80px gutters.
- The footer background goes black, full bleed, matching the header container.
- Both menus are rebuilt on the native popover API, deleting the hover timers.
- One backdrop rule dims the page behind the popup and both menus.

### Wave B: the solution-page bottom

- Move the two download sections adjacent and pair them in one two-column row.
- The row must degrade to one column when the gated button is absent.
- New sources component: a native details element rendering the reference items.
- Callouts lose only their source line.

### Wave C: the voice

1. Rewrite English second person to imperative across the solution pages.
2. Regenerate the translation hashes and re-naturalize only the changed delta.
PLANEOF
    python3 -c '
import json, sys
rec = {"type": "attachment", "isSidechain": False,
       "attachment": {"type": "plan_mode_exit", "planFilePath": sys.argv[1],
                      "planExists": True}}
open(sys.argv[2], "a").write(json.dumps(rec) + "\n")
' "$BASE/plan.md" "$BASE/t.jsonl"
}

echo "== 220. an approved plan tracked as two umbrella items BLOCKS =="
setup
say "seeded the round"
brief_now
plant_plan
A_ID=$(reqcli --add deadbeef 'www round 4 Wave A' | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
B_ID=$(reqcli --add deadbeef 'www round 4 Waves B-D' | sed -n 's/^added #\([0-9a-f]*\).*/\1/p')
# Both umbrella ids named, and ONE plan task quoted verbatim. Both kinds of
# evidence are verified against the artifacts before they can block; 220e is
# the case that proves the verification is load-bearing.
shim_planfid "{\"faithful\":false,\"umbrella_ids\":[\"$A_ID\",\"$B_ID\"],\"missing\":[\"Callouts lose only their source line.\"],\"instruction\":\"split these into one item per plan task\"}"
OUT="$(runj)"
if grep -qF '"decision": "block"' <<<"$OUT" &&
    grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT" &&
    grep -qF "DECOMPOSE" <<<"$OUT" && grep -qF "REBUT" <<<"$OUT" && grep -qF "DEFER" <<<"$OUT"; then
    pass "220 FIRE: two umbrella items for an approved plan block, naming three exits"
else
    fail "220 FIRE: no plan-fidelity block: ${OUT:0:300}"
fi
if grep -qF "$A_ID" <<<"$OUT" && grep -qF "Callouts lose only their source line" <<<"$OUT"; then
    pass "220 the block names the real umbrella item and quotes the untracked task"
else
    fail "220 the block carries no verified evidence: ${OUT:0:300}"
fi
PFTOK="$(grep -o 'planfid:[0-9a-f]\{8\}' <<<"$OUT" | head -n1)"
if [[ -n "$PFTOK" ]]; then
    pass "220 the block hands the session its exact deferral token ($PFTOK)"
else
    fail "220 no planfid deferral token in the block"
fi

echo "== 220a. the DEFERRAL exit settles it =="
printf -- '- [?] (deadbeef) %s is this plan superseded? DEFAULT: decompose it WHY: the scope may have moved HOW: the operator answers\n' "$PFTOK" >>"$WL"
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT"; then
    pass "220a CONTROL: a deferred item carrying the token settles the question"
else
    fail "220a: the deferral exit did not settle it: ${OUT:0:300}"
fi

echo "== 220b. faithful=true settles, and is never asked again =="
setup
say "seeded the round"
brief_now
plant_plan
reqcli --add deadbeef 'www round 4 Wave A' >/dev/null
reqcli --add deadbeef 'www round 4 Waves B-D' >/dev/null
shim_planfid '{"faithful":true,"umbrella_ids":[],"missing":[],"instruction":"nothing to do"}'
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT"; then
    pass "220b CONTROL A: a faithful verdict does not block"
else
    fail "220b: a faithful verdict still blocked: ${OUT:0:300}"
fi
N1=$(planfid_calls)
OUT="$(runj)"
N2=$(planfid_calls)
if [[ "$N1" -ge 1 ]] && [[ "$N2" == "$N1" ]]; then
    pass "220b CONTROL B: a settled plan is never re-asked (calls stayed at $N1)"
else
    fail "220b: the settled plan was re-judged ($N1 -> $N2)"
fi
if grep -q '"verdict": "faithful"' "$WL.planfid-deadbeef.json" 2>/dev/null; then
    pass "220b the verdict is recorded in the planfid marker"
else
    fail "220b no faithful verdict in the marker"
fi

echo "== 220c. THE INSTRUMENT BLIND: no approved plan, same accusing shim =="
setup
say "seeded the round"
brief_now
# Deliberately NO plant_plan. Same umbrella items, same shim that would accuse.
reqcli --add deadbeef 'www round 4 Wave A' >/dev/null
reqcli --add deadbeef 'www round 4 Waves B-D' >/dev/null
shim_planfid '{"faithful":false,"umbrella_ids":["aaaa1111"],"missing":["Callouts lose only their source line."],"instruction":"split them"}'
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT" && [[ "$(planfid_calls)" == "0" ]]; then
    pass "220c CONTROL: with no approved plan the check says nothing and spends no call"
else
    fail "220c: fired without a plan (calls=$(planfid_calls)): ${OUT:0:300}"
fi

echo "== 220d. a DECOMPOSED worklist never reaches the model at all =="
setup
say "seeded the round"
brief_now
plant_plan
for t in \
    'r4-A1 nav container 1280px max-width and 80px gutters' \
    'r4-A2 footer background black, full bleed, matching container' \
    'r4-A3 rebuild both menus on the native popover API' \
    'r4-A4 one backdrop rule dims the page behind popup and menus' \
    'r4-B1 move the two download sections adjacent to each other' \
    'r4-B2 the row degrades to one column when the gated button is absent' \
    'r4-B3 new sources component using a native details element' \
    'r4-B4 callouts lose only their source line' \
    'r4-C1 rewrite English second person to imperative on solution pages' \
    'r4-C2 regenerate hashes and re-naturalize only the changed delta'; do
    reqcli --add deadbeef "$t" >/dev/null
done
shim_planfid '{"faithful":false,"umbrella_ids":["aaaa1111"],"missing":["Callouts lose only their source line."],"instruction":"split them"}'
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT" && [[ "$(planfid_calls)" == "0" ]]; then
    pass "220d CONTROL: a faithful decomposition is filtered out before any model call"
else
    fail "220d: false positive on a decomposed worklist (calls=$(planfid_calls)): ${OUT:0:300}"
fi

echo "== 220e. an INVENTED item id cannot manufacture a block =="
setup
say "seeded the round"
brief_now
plant_plan
reqcli --add deadbeef 'www round 4 Wave A' >/dev/null
reqcli --add deadbeef 'www round 4 Waves B-D' >/dev/null
# Both axes hallucinated at once: an id no item carries, and a 'plan task' that
# appears nowhere in the plan. Neither survives verification, so no evidence is
# left and the check must not block on the model's word alone.
shim_planfid '{"faithful":false,"umbrella_ids":["9999zzzz"],"missing":["rewrite the kernel scheduler in rust"],"instruction":"do it"}'
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT" && [[ "$(planfid_calls)" -ge 1 ]]; then
    pass "220e CONTROL: the model was asked, and its unevidenced verdict was refused"
else
    fail "220e: an unevidenced verdict blocked (calls=$(planfid_calls)): ${OUT:0:300}"
fi

echo "== 220f. a broken judge DEGRADES, it does not wall the session in =="
setup
say "seeded the round"
brief_now
plant_plan
reqcli --add deadbeef 'www round 4 Wave A' >/dev/null
reqcli --add deadbeef 'www round 4 Waves B-D' >/dev/null
# A claude that exits non-zero. wl_judge fails CLOSED on the stop verdict, and
# this check deliberately does not: a heuristic trigger must not become a wall
# when the model is unreachable. It must also not go quiet about it.
printf '#!/bin/bash\nexit 3\n' >"$BASE/binonly/claude"
chmod +x "$BASE/binonly/claude"
OUT="$(runj)"
if ! grep -qF "AN APPROVED PLAN IS NOT DECOMPOSED" <<<"$OUT"; then
    pass "220f CONTROL: an unreachable judge does not block on plan fidelity"
else
    fail "220f: a broken judge produced a plan-fidelity block: ${OUT:0:300}"
fi
if grep -qF "plan-fidelity check could not run" "${WL%.md}.state-deadbeef.json" 2>/dev/null; then
    pass "220f the failure is queued for the session, not swallowed"
else
    fail "220f: a failed plan-fidelity run left no trace at all"
fi

# ---- 220h. the Tier-2 verdict log ------------------------------------------
# The wl_checks call sites are INVISIBLE to wl_planfid's own --selftest, so this
# is their only coverage: delete either one and the module controls stay green.
# The error branch specifically, because a judge that could not be reached is
# exactly the outcome nobody currently counts.
echo "== 220h. a failed Tier-2 call is RECORDED, not just reported =="
setup
say "seeded the round"
brief_now
plant_plan
reqcli --add deadbeef 'www round 4 Wave A' >/dev/null
reqcli --add deadbeef 'www round 4 Waves B-D' >/dev/null
printf '#!/bin/bash\nexit 3\n' >"$BASE/binonly/claude"
chmod +x "$BASE/binonly/claude"
runj >/dev/null
VLOG="$WL.planfid-verdicts-deadbeef.jsonl"
if [[ -f "$VLOG" ]] && grep -q '"branch": "error"' "$VLOG"; then
    pass "220h an unreachable judge leaves an error row in the verdict log"
else
    fail "220h no error row: $(head -c 200 "$VLOG" 2>&1)"
fi

echo "== 221. docs drift counts an UNCOMMITTED doc edit =="
# WHY: docs_drift measured the last COMMIT touching the design docs, and this
# repo's standing rule is that work stays uncommitted until the operator asks.
# So a session that DID update the docs was told they had drifted at every
# stop, and the only way to satisfy the check was to commit -- the one action
# that rule forbids doing unilaterally. The middle assertion below is the guard
# rail: a genuinely un-updated docs tree must STILL report drifted, or this fix
# has merely disarmed the check.
OUT=$(
    cd "$(dirname "$HOOK")" && python3 - <<'PYEOF'
import pathlib, subprocess, sys, tempfile
sys.path.insert(0, ".")
import wl_checks as W


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def build(dirty_docs, extra_commits):
    d = tempfile.mkdtemp()
    sh(d, "git", "init", "-q")
    sh(d, "git", "config", "user.email", "p@x")
    sh(d, "git", "config", "user.name", "p")
    docs = pathlib.Path(d, "docs/ci-overhaul")
    docs.mkdir(parents=True)
    (docs / "06-progress.md").write_text("start\n")
    pathlib.Path(d, ".ci").mkdir()
    pathlib.Path(d, ".ci/a.sh").write_text("x\n")
    sh(d, "git", "add", "-A")
    sh(d, "git", "commit", "-qm", "base")
    for i in range(extra_commits):
        pathlib.Path(d, ".ci/a.sh").write_text("x%d\n" % i)
        sh(d, "git", "add", "-A")
        sh(d, "git", "commit", "-qm", "c%d" % i)
    if dirty_docs:
        (docs / "06-progress.md").write_text("start\nuncommitted update\n")
    return d


over = W.DOCS_DRIFT_MAX + 2
checks = {
    "quiet-when-aligned": W.docs_drift(build(False, 0))[0] == "ok",
    "still-fires-when-ignored": W.docs_drift(build(False, over))[0] == "drifted",
    "uncommitted-edit-counts": W.docs_drift(build(True, over))[0] == "pending",
}
bad = [k for k, v in checks.items() if not v]
print("DRIFT", "OK" if not bad else "BAD:" + ",".join(bad))
PYEOF
)
if grep -q "^DRIFT OK$" <<<"$OUT"; then
    pass "221: uncommitted doc edits satisfy the drift check, and an ignored docs tree still fires"
else
    fail "221: docs_drift states wrong: $(grep '^DRIFT' <<<"$OUT")"
fi
