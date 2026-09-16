#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: none
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# Tests for .ci/media/cuda.sh -- the flash-attn accelerator probe.
#
# This is the one function in the media pipeline whose behaviour depends on hardware,
# and it is therefore the one most likely to be edited on a machine that HAS a GPU and
# never exercised on one that does not. All four of its exits are driven here with no
# GPU, no CUDA toolkit, no torch and no PyPI: a scripted `python` fake answers the two
# questions the function asks it, `nvcc` is present or absent by name, and `pip` records
# what it was asked to install without installing anything.
#
# The ownership assertion below is the other half. It used to be byte-identity against
# run.sh's copy; run.sh has no copy any more, so what it asserts now is that this module
# is the ONLY definition of the function, that run.sh and media.sh no longer carry one,
# and that sourcing media-entry.sh resolves the name to this file's body. There is no
# verb that reaches this function -- it is called from venv.sh, three levels below
# `www tutorials generate` -- so the chain probe other media tests use does not apply
# here, and the mutation control instead re-runs a real behaviour case against a
# deliberately altered copy of this module.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/cuda.sh"

# script_python <flash-attn-imports> <torch-cuda-answer>
#
# Replaces the recording `python` fake with one that answers the function's two probes
# independently, which a uniform fake cannot do: `import flash_attn` and the
# torch.cuda.is_available() query are both `python -c`, and the four exits differ only
# in how those two answer.
script_python() {
    cat >"$FAKE_BIN_DIR/python" <<PY
#!/bin/bash
case "\$*" in
    *flash_attn*) exit $([ "$1" = yes ] && echo 0 || echo 1) ;;
    *torch.cuda*) echo "$2"; exit 0 ;;
esac
exit 0
PY
    chmod +x "$FAKE_BIN_DIR/python"
}

run_cuda() {
    media_run_module "$1" "cuda.sh" "$2"
}

test_this_module_solely_owns_the_moved_function() {
    media_assert_module_owns cuda.sh install_flash_attn_if_supported
}

test_the_ownership_assertion_can_fail() {
    # CONTROL, in every way this assertion could go quiet: a second definition put back
    # into an origin (which is what a badly resolved merge against the pre-cutover file
    # would produce), a name nothing defines anywhere (the vacuity the old byte-identity
    # helper was built around), and an origin file that is not there to be read.
    media_assert_ownership_control "$1" cuda.sh install_flash_attn_if_supported
}

_case_a_mutated_module_changes_what_the_behaviour_cases_see() {
    # CONTROL FOR EVERY BEHAVIOUR CASE BELOW, and the reason MEDIA_MODULE_DIR exists.
    # The four exits are asserted by their messages; this re-runs the no-CUDA exit against
    # a copy of cuda.sh whose message has been changed, and requires the change to show up.
    # If it did not, those four assertions would be reading something other than the module
    # under test, and their green would mean nothing.
    local d="$1"
    local MEDIA_MODULE_DIR="$d/mutant"
    script_python no false
    local rc=0
    run_cuda "$d" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "the mutated copy still runs; only its wording changed"
    media_assert_mutation_swapped "$LAST_OUT" "CUDA not available in torch" "CUDA MUTATED" "message"
}

test_a_planted_mutation_is_visible_to_the_behaviour_cases() {
    local d="$1"
    mkdir -p "$d/mutant"
    sed 's/CUDA not available in torch/CUDA MUTATED/' "$MODULE" >"$d/mutant/cuda.sh"
    grep -q "CUDA MUTATED" "$d/mutant/cuda.sh" || log_fail "the mutation did not apply, so this control would pass for the wrong reason"
    with_fake_bin "python pip +cat +chmod +uname" _case_a_mutated_module_changes_what_the_behaviour_cases_see "$d"
    log_pass "a one-line mutation in cuda.sh changes what the behaviour cases observe"
}

_case_already_installed() {
    script_python yes true
    local rc=0
    run_cuda "$1" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "an already-importable flash_attn must return 0"
    assert_eq "$(fake_bin_record pip)" "" "nothing may be installed when it already imports"
}

_case_no_cuda_in_torch() {
    script_python no false
    local rc=0
    run_cuda "$1" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "no CUDA in torch must SKIP, not fail"
    assert_contains "$LAST_OUT" "CUDA not available in torch" "says why it skipped"
    assert_eq "$(fake_bin_record pip)" "" "nothing may be installed without CUDA"
}

_case_no_nvcc() {
    script_python no true
    local rc=0
    run_cuda "$1" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "a missing nvcc must SKIP, not fail"
    assert_contains "$LAST_OUT" "nvcc not found" "says which tool the source build needs"
    assert_eq "$(fake_bin_record pip)" "" "nothing may be installed without a compiler"
}

_case_installs_when_supported() {
    script_python no true
    local rc=0
    run_cuda "$1" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "the supported path must return 0"
    local pip_calls
    pip_calls="$(fake_bin_record pip)"
    assert_contains "$pip_calls" "install --upgrade packaging ninja" "build deps come first"
    assert_contains "$pip_calls" "install flash-attn --no-build-isolation" "flash-attn is built without isolation"
    assert_eq "$(fake_bin_record nvcc)" "" "nvcc is PROBED with command -v, never executed"
}

_case_install_failure_is_a_warning_not_a_death() {
    script_python no true
    local rc=0
    run_cuda "$1" "install_flash_attn_if_supported" || rc=$?
    assert_exit_code 0 "$rc" "a failed accelerator install must not fail the pipeline"
    assert_contains "$LAST_OUT" "flash-attn install failed" "says the install failed"
    assert_contains "$LAST_OUT" "continuing without it" "and says the pipeline continues"
}

test_all_four_exits() {
    local d="$1"
    with_fake_bin "python pip +cat +chmod +uname" _case_already_installed "$d"
    with_fake_bin "python pip +cat +chmod +uname" _case_no_cuda_in_torch "$d"
    # nvcc deliberately NOT in the spec: absent is the condition under test.
    with_fake_bin "python pip +cat +chmod +uname" _case_no_nvcc "$d"
    with_fake_bin "python pip nvcc +cat +chmod +uname" _case_installs_when_supported "$d"
    log_pass "already-installed, no-CUDA, no-nvcc and supported all reach their own exit"
}

test_a_failing_install_only_warns() {
    local d="$1"
    with_fake_bin "python pip!1 nvcc +cat +chmod +uname" _case_install_failure_is_a_warning_not_a_death "$d"
    log_pass "a failed flash-attn install warns and returns 0, so the pipeline survives it"
}

log_test "test-media-cuda"
test_this_module_solely_owns_the_moved_function
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_a_planted_mutation_is_visible_to_the_behaviour_cases
with_temp_dir test_all_four_exits
with_temp_dir test_a_failing_install_only_warns
echo ""
log_pass "all tests passed"
