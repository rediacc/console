#!/bin/bash
# Tests for the phase-0 scaffolding the media gate tests are built on:
# with_fake_bin / fake_bin_record in .ci/scripts/test/lib/test-helpers.sh, and the
# .ci/media scan root added to .ci/scripts/quality/check-dead-case-arms.sh.
#
# WHY THIS FILE EXISTS AT ALL. Six other gate tests claim to prove things about code
# that drives a GPU, a libvirt cluster and an R2 bucket, and every one of those claims
# rests on with_fake_bin actually emptying PATH. A helper that quietly left PATH intact
# would make all six pass against the host's real binaries while reporting hermetic
# isolation -- the exact shape of a green that means nothing. So the helper is tested
# first, and the assertion that carries the most weight is the negative one: the
# binaries nobody named are GONE.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$ROOT/.ci/scripts/quality/check-dead-case-arms.sh"

# ---------------------------------------------------------------------------
# with_fake_bin
# ---------------------------------------------------------------------------

_probe_path_is_only_fakes() {
    assert_eq "$PATH" "$FAKE_BIN_DIR" "PATH must be the fake dir and nothing else"
}

test_path_is_replaced_not_prefixed() {
    with_fake_bin "docker" _probe_path_is_only_fakes
    log_pass "PATH is REPLACED by the fake dir, not prefixed onto the real one"
}

_probe_unnamed_binaries_are_absent() {
    local absent=(docker node npm npx nvcc aws ssh rsync curl wget git python3 ffmpeg)
    local b present=()
    for b in "${absent[@]}"; do
        command -v "$b" >/dev/null 2>&1 && present+=("$b")
    done
    assert_eq "${present[*]:-}" "" "these should not be reachable inside with_fake_bin"
}

test_everything_unnamed_is_absent() {
    # THE LOAD-BEARING ASSERTION. Every other media gate test's hermeticity claim is
    # this one assertion wearing a different hat.
    with_fake_bin "true" _probe_unnamed_binaries_are_absent
    log_pass "docker, node, npm, npx, nvcc, aws, ssh, rsync, curl, wget, git, python3 and ffmpeg are all absent"
}

_probe_fake_records_argv() {
    docker run --rm alpine echo hi
    nvcc --version
    assert_eq "$(fake_bin_record docker)" "run --rm alpine echo hi" "docker's argv is recorded verbatim"
    assert_eq "$(fake_bin_record nvcc)" "--version" "nvcc's argv is recorded verbatim"
}

test_a_named_fake_records_its_arguments() {
    with_fake_bin "docker nvcc" _probe_fake_records_argv
    log_pass "a named fake is on PATH and records the argv it was called with"
}

_probe_never_called_records_nothing() {
    assert_eq "$(fake_bin_record aws)" "" "a fake that was never invoked records nothing"
}

test_a_never_called_fake_records_nothing() {
    # "nvcc was never invoked" is an assertion the CUDA module's test makes, so the
    # empty-record case has to be distinguishable from a broken recorder.
    with_fake_bin "aws" _probe_never_called_records_nothing
    log_pass "a fake that was never called reports no invocations"
}

_probe_exit_code_is_honoured() {
    local rc=0
    flaky || rc=$?
    assert_exit_code 7 "$rc" "name!7 must exit 7"
}

test_exit_code_suffix_is_honoured() {
    with_fake_bin "flaky!7" _probe_exit_code_is_honoured
    log_pass "the name!<n> form controls the fake's exit code"
}

_probe_passthrough_is_the_real_binary() {
    # `cut`, deliberately: it is not a bash builtin, so this can only succeed if the
    # symlink to the real binary is what answered. An earlier draft asserted on `printf`
    # and proved nothing, because bash's builtin would have satisfied it with PATH empty.
    assert_eq "$(echo 'a:b' | cut -d: -f2)" "b" "+cut must be the real cut"
    assert_eq "$(fake_bin_record cut)" "" "a passthrough is not a recorder, so it records nothing"
}

test_passthrough_admits_the_real_binary() {
    with_fake_bin "+cut" _probe_passthrough_is_the_real_binary
    log_pass "the +name form admits the real binary by name"
}

test_the_callers_path_is_never_touched() {
    # The restriction lives in a subshell, so the calling test's PATH is not restored
    # afterwards -- it was never changed. That distinction is what keeps a failing
    # assertion from being followed by "rm: command not found" as the EXIT traps unwind.
    local before="$PATH"
    with_fake_bin "docker" _probe_path_is_only_fakes
    assert_eq "$PATH" "$before" "the caller's PATH must be unchanged by with_fake_bin"
    log_pass "the caller's PATH is untouched: the restriction is scoped to a subshell"
}

# ---------------------------------------------------------------------------
# The .ci/media scan root in check-dead-case-arms.sh
# ---------------------------------------------------------------------------

LAST=""
run_gate_media() {
    local rc=0
    LAST="$(DEAD_CASE_MEDIA_DIRS="$1" bash "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

test_media_root_is_wired_into_the_real_scan() {
    # The failure this catches is not "the scanner is broken" -- the gate's own control
    # covers that -- but "the new variable was declared and never passed to scan". Only
    # driving the REAL gate with the root overridden can tell those apart.
    local d="$1"
    mkdir -p "$d/media"
    printf 'case "$1" in\n    *"zzznosuchmediafield=1"*) exit 1 ;;\nesac\n' >"$d/media/mod.sh"
    local rc=0
    run_gate_media "$d/media" || rc=$?
    assert_exit_code 1 "$rc" "a dead arm in the media root must fail the gate"
    assert_contains "$LAST" "zzznosuchmediafield" "names the dead field it found in the media root"
    log_pass "MEDIA_DIRS reaches the real scan: a dead arm planted there reds the gate"
}

test_the_real_media_folder_is_clean_and_counted() {
    local rc=0
    LAST="$(bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must have no dead case arms (output: $LAST)"
    assert_contains "$LAST" ".ci/media" "the verdict must name the media root it scanned"
    assert_not_contains "$LAST" "(0 media shell file(s)" "a zero-file media root is vacuous, not clean"
    log_pass "the real .ci/media folder is scanned, counted and clean"
}

test_an_empty_media_root_is_vacuous_not_clean() {
    # Anti-vacuity for the new root, driven through the real gate: a root that has
    # stopped matching files must be a failure, because otherwise it is indistinguishable
    # from a clean one.
    local d="$1"
    mkdir -p "$d/nothing"
    local rc=0
    run_gate_media "$d/nothing" || rc=$?
    assert_exit_code 1 "$rc" "an empty media root must fail rather than report clean"
    assert_contains "$LAST" "VACUOUS" "says the scan root proves nothing"
    log_pass "an empty media root is refused as vacuous"
}

log_test "test-media-helpers"
test_path_is_replaced_not_prefixed
test_everything_unnamed_is_absent
test_a_named_fake_records_its_arguments
test_a_never_called_fake_records_nothing
test_exit_code_suffix_is_honoured
test_passthrough_admits_the_real_binary
test_the_callers_path_is_never_touched
with_temp_dir test_media_root_is_wired_into_the_real_scan
test_the_real_media_folder_is_clean_and_counted
with_temp_dir test_an_empty_media_root_is_vacuous_not_clean
echo ""
log_pass "all tests passed"
