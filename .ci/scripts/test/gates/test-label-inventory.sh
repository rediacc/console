#!/bin/bash
# Behavioural test for .ci/scripts/quality/check-label-inventory.sh.
#
# WHAT IT GUARDS. The gate reconciles .github/labels.yml against the labels that
# actually exist on the repo, in BOTH directions, and the direction that bit was
# declared-but-absent: `rollback` was declared and referenced and did not exist,
# and promote-stable.yml searches `label:rollback`. A GitHub search for a
# nonexistent label returns zero PRs rather than an error, so the promotion
# block never fired. Nothing said so. That is the class this gate catches.
#
# Every case here carries its control: a firing direction is only meaningful
# next to the matching clean case, and a refusal is only meaningful next to a
# read that succeeds.
#
# NO NETWORK. The live list is injected through LABEL_INVENTORY_LIVE_FILE, which
# is also how the real-tree case below drives the REAL gate over the REAL
# .github/labels.yml inside run-all.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-label-inventory.sh"
REAL_LABELS="$REPO_ROOT/.github/labels.yml"
LAST_OUT=""

# run_gate <labels-file> <live-file>: returns the gate's exit code, output in
# LAST_OUT. Env is scoped to the call so cases cannot leak into each other.
run_gate() {
    local rc=0
    LAST_OUT="$(LABEL_INVENTORY_LABELS_FILE="$1" LABEL_INVENTORY_LIVE_FILE="$2" bash "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

# A declaration set big enough to clear the gate's own floor (5).
write_labels() {
    local out="$1"
    shift
    : >"$out"
    for name in "$@"; do
        printf -- '- name: %s\n  color: "FFFFFF"\n  description: "%s does a thing"\n\n' "$name" "$name" >>"$out"
    done
}

# ---------------------------------------------------------------------------

test_matching_sets_are_clean() {
    # The control for everything below. Without it, a gate that failed on
    # ANYTHING would pass all four firing cases.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five six
    printf 'one\ntwo\nthree\nfour\nfive\nsix\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 0 "$rc" "matching declaration and live sets must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "reconciled" "and say so"
    log_pass "matching sets reconcile cleanly"
}

test_declared_but_absent_fires() {
    # THE ROLLBACK CASE. A declared label that does not exist makes every search
    # and filter on it fail open, silently.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five ghost-label
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "a declared-but-absent label must fail the gate"
    assert_contains "$LAST_OUT" "ghost-label" "the offender is named"
    assert_contains "$LAST_OUT" "FAILS OPEN" "and the fail-open consequence is stated"
    assert_contains "$LAST_OUT" "gh label create" "with the exact fix"
    log_pass "a declared-but-absent label fires, naming the fail-open risk"
}

test_live_but_undeclared_fires() {
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five
    printf 'one\ntwo\nthree\nfour\nfive\nstowaway\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "a live-but-undeclared label must fail the gate"
    assert_contains "$LAST_OUT" "stowaway" "the offender is named"
    assert_contains "$LAST_OUT" "label guide" "and the consequence (invisible to the PR guide) is stated"
    log_pass "a live-but-undeclared label fires"
}

test_both_directions_report_together() {
    # A gate that exits on the first problem makes fixing an N-label drift an
    # N-round job.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five ghost-label
    printf 'one\ntwo\nthree\nfour\nfive\nstowaway\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "both-direction drift fails"
    assert_contains "$LAST_OUT" "ghost-label" "the absent one is reported"
    assert_contains "$LAST_OUT" "stowaway" "and the undeclared one, in the same run"
    assert_contains "$LAST_OUT" "2 label inventory mismatch" "the count is exact"
    log_pass "both directions are reported in one run"
}

test_create_on_demand_label_is_forgiven_when_absent() {
    # nightly-red does not exist until the first red night, because
    # report-nightly-status.cjs creates it right before opening the rolling
    # issue. Declared-and-absent is its NORMAL state.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five nightly-red
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 0 "$rc" "an absent create-on-demand label must NOT fail (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "created on demand" "and the exemption is stated out loud, not applied silently"
    log_pass "the create-on-demand label is forgiven while absent"
}

test_create_on_demand_label_is_still_fine_when_present() {
    # The exemption forgives ABSENCE only; once the label exists it must not
    # start failing the other direction.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five nightly-red
    printf 'one\ntwo\nthree\nfour\nfive\nnightly-red\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 0 "$rc" "a present create-on-demand label is ordinary (output: $LAST_OUT)"
    log_pass "the create-on-demand label passes once it exists"
}

test_a_stale_allowlist_entry_is_refused() {
    # The exemption must self-expire. If nightly-red stops being declared, the
    # allowlist entry is a permanent hole pointing at nothing.
    #
    # The verification is scoped to the real declaration file (a fixture tree
    # legitimately has no nightly-red), so the flag is driven on explicitly here
    # rather than left to the scoping heuristic.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    LAST_OUT="$(LABEL_INVENTORY_VERIFY_ALLOWLIST=true LABEL_INVENTORY_LABELS_FILE="$d/labels.yml" \
        LABEL_INVENTORY_LIVE_FILE="$d/live.txt" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "an allowlist entry naming an undeclared label must fail"
    assert_contains "$LAST_OUT" "not declared" "and say the exemption is stale"
    log_pass "a stale create-on-demand entry is refused, so the exemption cannot rot"
}

test_empty_live_list_is_a_refusal_not_a_clean_tree() {
    # An empty list would make direction (b) vacuously green. This repo cannot
    # have zero labels, so empty means the read failed.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five
    : >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "an empty live list must be refused"
    assert_contains "$LAST_OUT" "EMPTY" "and named as a failed read"
    assert_contains "$LAST_OUT" "failed read" "explicitly, not as a tree state"
    log_pass "an empty live list is a refusal, not a clean tree"
}

test_unreadable_live_source_is_a_refusal() {
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five
    run_gate "$d/labels.yml" "$d/does-not-exist.txt" || rc=$?
    assert_exit_code 1 "$rc" "an unreadable live source must be refused"
    assert_contains "$LAST_OUT" "refuses to pass blind" "and say it is blind"
    log_pass "an unreadable live source refuses rather than passing blind"
}

test_a_broken_declaration_read_trips_the_floor() {
    # A parse yielding almost nothing is a broken parse, and treating it as a
    # small declaration set would make direction (b) scream about every live
    # label while direction (a) stayed silent.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two
    printf 'one\ntwo\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "a two-label declaration file must trip the floor"
    assert_contains "$LAST_OUT" "floor" "and say the reader is broken, not the file"
    log_pass "the declaration floor refuses a broken read"
}

test_a_stale_list_read_is_re_verified_before_accusing() {
    # THE FALSE POSITIVE THIS EXISTS TO STOP. Observed on a real full run: the
    # gate accused `no-auto-retry` of not existing while it existed and
    # watchdog-monitor.cjs was reading it. Someone was mid-way through
    # delete-and-recreate on it, and the paginated list came back one short.
    # Wrong-by-one clears the empty-list guard and then fires this gate's
    # loudest message, the one about rollback and silent fail-open -- and a gate
    # that cries wolf that hard on a race gets ignored.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five racy
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    # The single-label re-read disagrees with the list: `racy` does exist.
    printf 'one\ntwo\nthree\nfour\nfive\nracy\n' >"$d/probe.txt"
    LAST_OUT="$(LABEL_INVENTORY_PROBE_FILE="$d/probe.txt" LABEL_INVENTORY_LABELS_FILE="$d/labels.yml" \
        LABEL_INVENTORY_LIVE_FILE="$d/live.txt" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "a label the re-read finds must NOT be reported (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "re-read found it" "the re-verification is stated, not silent"
    assert_not_contains "$LAST_OUT" "FAILS OPEN" "and the alarming accusation is never printed"
    log_pass "a stale list read is re-verified, and the false positive is dropped"
}

test_a_genuinely_absent_label_still_fires_after_re_verification() {
    # THE CONTROL, and the one that matters most: re-verification must not
    # become a blanket excuse. When both reads agree the label is gone, the
    # finding stands with its full message.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five ghost-label
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    # The re-read agrees: ghost-label is absent from the probe set too.
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/probe.txt"
    LAST_OUT="$(LABEL_INVENTORY_PROBE_FILE="$d/probe.txt" LABEL_INVENTORY_LABELS_FILE="$d/labels.yml" \
        LABEL_INVENTORY_LIVE_FILE="$d/live.txt" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a label both reads agree is absent must still fail"
    assert_contains "$LAST_OUT" "ghost-label" "the offender is still named"
    assert_contains "$LAST_OUT" "FAILS OPEN" "with the full fail-open explanation"
    assert_not_contains "$LAST_OUT" "re-read found it" "and no false re-verification note"
    log_pass "re-verification is not a blanket excuse: a real absence still fires"
}

test_re_verification_does_not_touch_the_undeclared_direction() {
    # An EXTRA name cannot be a partial-read artifact -- a stale read loses
    # entries, it does not invent them -- so direction (b) must fire whatever
    # the probe says. A probe set that "confirms" the stowaway must not silence
    # it, which is the mistake a symmetric implementation would make.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five
    printf 'one\ntwo\nthree\nfour\nfive\nstowaway\n' >"$d/live.txt"
    printf 'one\ntwo\nthree\nfour\nfive\nstowaway\n' >"$d/probe.txt"
    LAST_OUT="$(LABEL_INVENTORY_PROBE_FILE="$d/probe.txt" LABEL_INVENTORY_LABELS_FILE="$d/labels.yml" \
        LABEL_INVENTORY_LIVE_FILE="$d/live.txt" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "the undeclared direction is unaffected by re-verification"
    assert_contains "$LAST_OUT" "stowaway" "and still names the offender"
    log_pass "re-verification applies to the absent direction only"
}

test_injected_mode_without_a_probe_seam_still_reports() {
    # The offline seam must keep working. With no probe file and no API to
    # re-read, the injected list stands as its own authority: the probe reports
    # "could not", and the finding is REPORTED rather than dropped. Failing the
    # other way would make every offline run of this gate vacuously green.
    local d="$1" rc=0
    write_labels "$d/labels.yml" one two three four five ghost-label
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 1 "$rc" "an unprobeable absence is reported, not forgiven"
    assert_contains "$LAST_OUT" "ghost-label" "naming it"
    log_pass "with no probe available the finding stands (offline seam unchanged)"
}

test_indented_fields_are_never_mistaken_for_names() {
    # .github/labels.yml carries `color:`, `description:` and `guide:` under
    # each entry. The name extraction anchors on `^- name:`, so an indented
    # field cannot be picked up -- but "it currently passes" is not the same as
    # "it cannot". If a field value ever leaked in, the gate would report a
    # phantom label (`false`, a hex colour) as declared-but-absent, and the fix
    # would be hunting a label that was never a label.
    local d="$1" rc=0
    cat >"$d/labels.yml" <<'EOF'
- name: one
  color: "FFFFFF"
  description: "first"
- name: two
  color: "000000"
  description: "second"
  guide: false
- name: three
  color: "AAAAAA"
  description: "third"
  guide: true
- name: four
  color: "BBBBBB"
  description: "fourth"
- name: five
  color: "CCCCCC"
  description: "fifth"
EOF
    printf 'one\ntwo\nthree\nfour\nfive\n' >"$d/live.txt"
    run_gate "$d/labels.yml" "$d/live.txt" || rc=$?
    assert_exit_code 0 "$rc" "indented fields must not be read as label names (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "5 declared" "exactly the five names, not their field values"
    assert_not_contains "$LAST_OUT" "'false'" "no phantom label from a guide value"
    assert_not_contains "$LAST_OUT" "FFFFFF" "no phantom label from a colour value"
    log_pass "color/description/guide lines are never mistaken for label names"
}

test_real_tree_reconciles_against_an_injected_live_list() {
    # THE REAL-TREE CASE, and the one the manifest BLOCKER points at. The gate
    # runs seam-free over the REAL .github/labels.yml -- real parse, real floor,
    # real allowlist verification against the real report-nightly-status.cjs --
    # with the live list injected so no network is touched. The live GitHub read
    # itself cannot run in the quality lane (no label-read token there); it runs
    # on `npm run check:ci-label-inventory`.
    #
    # The injected list is DERIVED from the real declaration file rather than
    # hand-copied: a hardcoded twelve names here would be a second source of
    # truth that rots the next time a label is added.
    local d="$1" rc=0
    grep -E '^- name:' "$REAL_LABELS" | sed -E 's/^- name:[[:space:]]*//' >"$d/live.txt"
    LAST_OUT="$(LABEL_INVENTORY_LIVE_FILE="$d/live.txt" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real labels file must reconcile against itself (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "reconciled" "the real run reports a reconciliation"

    # Control on the real tree: drop one real label from the live list and the
    # real gate must fire. Without this, the case above would also pass if the
    # gate had quietly become a no-op on the real file.
    local dropped rc2=0
    dropped="$(head -1 "$d/live.txt")"
    grep -vx "$dropped" "$d/live.txt" >"$d/live-short.txt"
    LAST_OUT="$(LABEL_INVENTORY_LIVE_FILE="$d/live-short.txt" bash "$GATE" 2>&1)" || rc2=$?
    assert_exit_code 1 "$rc2" "removing a real label from the live list must fire the real gate"
    assert_contains "$LAST_OUT" "$dropped" "naming the real label that went missing"

    # And the other direction, on the real tree.
    local rc3=0
    cat "$d/live.txt" >"$d/live-extra.txt"
    echo "an-undeclared-live-label" >>"$d/live-extra.txt"
    LAST_OUT="$(LABEL_INVENTORY_LIVE_FILE="$d/live-extra.txt" bash "$GATE" 2>&1)" || rc3=$?
    assert_exit_code 1 "$rc3" "an extra live label must fire the real gate too"
    assert_contains "$LAST_OUT" "an-undeclared-live-label" "naming it"

    log_pass "the real gate runs over the real labels file and fires in both directions"
}

test_malformed_live_json_fails_closed() {
    # Found by the automated review of 01e7111c, and confirmed real: LIVE_JSON
    # feeds a python heredoc that used to swallow a JSON decode failure with a
    # bare `sys.exit(0)`. The outer bash captures that exit code as `drift_rc`,
    # so a truncated/malformed API response (a real risk: `gh api ... --paginate
    # || echo ""` can leave partial stdout on a mid-stream failure) read as "the
    # comparison ran and found nothing" -- the exact swallowed-failure class
    # 1eac336b already fixed once at the shell `|| true` level, one layer down.
    local d="$1" rc=0
    grep -E '^- name:' "$REAL_LABELS" | sed -E 's/^- name:[[:space:]]*//' >"$d/live.txt"
    printf 'not valid json{{{' >"$d/live.json"
    LAST_OUT="$(LABEL_INVENTORY_LIVE_FILE="$d/live.txt" LABEL_INVENTORY_LIVE_JSON_FILE="$d/live.json" bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "malformed LIVE_JSON must fail closed, not report a clean tree (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "FAILED to run" "the failure names itself as an unreadable comparison, not a clean reconciliation"
    if grep -qi "all agree" <<<"$LAST_OUT"; then
        log_fail "malformed LIVE_JSON was reported as a reconciled, agreeing tree"
    fi

    # CONTROL, built by construction: restore the exact bug this test exists
    # for (a literal string replace of the CURRENT fixed line, not a pattern
    # over unrelated text) and require the same input to flip to a false-clean
    # exit 0. If it does not flip, this test is not measuring anything.
    #
    # The mutant is a plain copy elsewhere, so two more lines that assume the
    # gate's OWN directory location also need patching, or it fails on those
    # for a DIFFERENT reason (source-not-found, or "labels file not found"
    # from get_repo_root()'s 3-levels-up walk landing nowhere) -- either of
    # which looks identical to "control did not fire" without proving
    # anything. Pinning both to the real, already-known $REPO_ROOT sidesteps
    # that path math entirely.
    local mutant="$d/mutant-gate.sh"
    cp "$GATE" "$mutant"
    python3 - "$mutant" "$REPO_ROOT" <<'PY'
import sys
path, repo_root = sys.argv[1], sys.argv[2]
src = open(path, encoding="utf-8").read()
needle = 'except Exception as e:'
assert src.count(needle) == 1, "mutation anchor missing or ambiguous"
start = src.index(needle)
end = src.index("sys.exit(1)", start) + len("sys.exit(1)")
src = src[:start] + "except Exception:\n    sys.exit(0)" + src[end:]
source_needle = 'source "$SCRIPT_DIR/../lib/common.sh"'
assert src.count(source_needle) == 1, "source anchor missing or ambiguous"
src = src.replace(source_needle, 'source %r' % (repo_root + "/.ci/scripts/lib/common.sh"), 1)
root_needle = 'REPO_ROOT="$(get_repo_root)"'
assert src.count(root_needle) == 1, "REPO_ROOT anchor missing or ambiguous"
src = src.replace(root_needle, 'REPO_ROOT=%r' % repo_root, 1)
open(path, "w", encoding="utf-8").write(src)
PY
    local rc2=0
    LAST_OUT="$(LABEL_INVENTORY_LIVE_FILE="$d/live.txt" LABEL_INVENTORY_LIVE_JSON_FILE="$d/live.json" bash "$mutant" 2>&1)" || rc2=$?
    if [ "$rc2" -eq 1 ]; then
        log_fail "CONTROL DID NOT FIRE: the mutant with the old sys.exit(0) still failed closed"
    fi
    assert_exit_code 0 "$rc2" "control: the pre-fix behavior swallows malformed JSON as a clean tree"
    log_pass "malformed LIVE_JSON fails closed; control proves the old code did not"
}

log_test "test-label-inventory"
with_temp_dir test_matching_sets_are_clean
with_temp_dir test_declared_but_absent_fires
with_temp_dir test_live_but_undeclared_fires
with_temp_dir test_both_directions_report_together
with_temp_dir test_create_on_demand_label_is_forgiven_when_absent
with_temp_dir test_create_on_demand_label_is_still_fine_when_present
with_temp_dir test_a_stale_allowlist_entry_is_refused
with_temp_dir test_empty_live_list_is_a_refusal_not_a_clean_tree
with_temp_dir test_unreadable_live_source_is_a_refusal
with_temp_dir test_a_broken_declaration_read_trips_the_floor
with_temp_dir test_a_stale_list_read_is_re_verified_before_accusing
with_temp_dir test_a_genuinely_absent_label_still_fires_after_re_verification
with_temp_dir test_re_verification_does_not_touch_the_undeclared_direction
with_temp_dir test_injected_mode_without_a_probe_seam_still_reports
with_temp_dir test_indented_fields_are_never_mistaken_for_names
with_temp_dir test_real_tree_reconciles_against_an_injected_live_list
with_temp_dir test_malformed_live_json_fails_closed
echo ""
log_pass "all tests passed"
