#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The regression-gate marker: what asks, what settles, hallucinated coverage, transitive gate proof, tick signals.

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
