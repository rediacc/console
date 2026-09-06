#!/bin/bash
# Tests for .ci/media/venv.sh -- the generative Python environment.
#
# TWO KINDS OF ASSERTION, and they answer different questions.
#
#   OWNERSHIP. Every function here was moved out of run.sh, and phase 2 deleted run.sh's
#   copies. While both existed the claim to check was byte-identity, and it was; with one
#   copy left, the claim that means something is that there IS one copy: exactly one file
#   defines each name, it is this module, run.sh and media.sh define none of them, and
#   sourcing media-entry.sh resolves each name to this file's body. A second definition
#   reappearing anywhere -- a merge against the pre-cutover run.sh is the obvious way --
#   is then red rather than discovered later by whichever copy happens to run.
#
#   BEHAVIOUR. What the module does when its dependencies are missing, which is the only
#   part CI can actually drive. Every case below runs with PATH emptied and refilled by
#   name, so python3, ffmpeg, sox, apt-get, sudo, pip, docker, node and the network are
#   absent unless the case says otherwise.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/venv.sh"

MOVED=(
    ensure_generative_repo
    ensure_python_installed
    ensure_audio_system_deps
    install_generative_python_deps
    ensure_generative_venv
)

# cuda.sh is sourced alongside venv.sh in every case below because
# install_generative_python_deps calls into it. That cross-module edge is real, so it is
# exercised rather than stubbed away: if it broke, the pip case would die with
# "install_flash_attn_if_supported: command not found".
MODULES="cuda.sh venv.sh"

run_venv() {
    media_run_module "$1" "$MODULES" "$2"
}

test_every_moved_function_is_solely_owned_by_this_module() {
    media_assert_module_owns venv.sh "${MOVED[@]}"
}

test_the_ownership_assertion_can_fail() {
    # CONTROL. An assertion that has never been seen to fail is one nobody has checked,
    # and "nothing defines it, so nothing else defines it either" is the specific way this
    # one could go quiet -- the same vacuity the byte-identity helper it replaced was
    # built around. The shared control drives all four arms; see verify.sh for what they
    # are and why the fourth, a missing origin, was the one nothing covered.
    media_assert_ownership_control "$1" venv.sh ensure_generative_repo
}

_case_a_mutated_module_changes_what_the_behaviour_cases_see() {
    # CONTROL FOR THE BEHAVIOUR CASES BELOW, which assert diagnoses by their exact
    # wording. Change one of those messages in a copy of the module and the assertion
    # that names it must stop holding; if it still held, the cases would be reading
    # something other than the module under test.
    local d="$1"
    local MEDIA_MODULE_DIR="$d/mutant"
    local rc=0
    run_venv "$d/empty" "ensure_generative_repo" || rc=$?
    assert_exit_code 1 "$rc" "the mutated copy still fails on a missing checkout; only its wording changed"
    media_assert_mutation_swapped "$LAST_OUT" "Missing private/generative directory" "MUTATED" "diagnosis"
}

test_a_planted_mutation_is_visible_to_the_behaviour_cases() {
    local d="$1"
    mkdir -p "$d/empty" "$d/mutant"
    sed 's/log_error "Missing private\/generative directory"/log_error "MUTATED"/' \
        "$MODULE" >"$d/mutant/venv.sh"
    cp "$ROOT/.ci/media/cuda.sh" "$d/mutant/cuda.sh"
    grep -q 'log_error "MUTATED"' "$d/mutant/venv.sh" || log_fail "the mutation did not apply, so this control would pass for the wrong reason"
    with_fake_bin "+uname" _case_a_mutated_module_changes_what_the_behaviour_cases_see "$d"
    log_pass "a one-line mutation in venv.sh changes what the behaviour cases observe"
}

_case_missing_generative_dir() {
    local d="$1"
    local rc=0
    run_venv "$d/empty" "ensure_generative_repo" || rc=$?
    assert_exit_code 1 "$rc" "a missing private/generative must fail"
    assert_contains "$LAST_OUT" "Missing private/generative directory" "names what is missing"
    assert_contains "$LAST_OUT" "not a submodule" "keeps the diagnosis that git submodule cannot fix this"
}

_case_generative_dir_without_git() {
    local d="$1"
    local rc=0
    run_venv "$d/nogit" "ensure_generative_repo" || rc=$?
    assert_exit_code 1 "$rc" "a private/generative that is not a checkout must fail"
    assert_contains "$LAST_OUT" "is not a git checkout" "distinguishes 'absent' from 'not a checkout'"
}

_case_generative_dir_present() {
    local d="$1"
    local rc=0
    run_venv "$d/good" "ensure_generative_repo" || rc=$?
    assert_exit_code 0 "$rc" "a real checkout must pass (output: $LAST_OUT)"
}

test_ensure_generative_repo_diagnoses_all_three_states() {
    local d="$1"
    mkdir -p "$d/empty" "$d/nogit/private/generative" "$d/good/private/generative/.git"
    # No fakes at all: this function shells out to nothing, and proving that is worth an
    # empty PATH. If it ever grows a dependency, this case reports it as not-found.
    with_fake_bin "+uname" _case_missing_generative_dir "$d"
    with_fake_bin "+uname" _case_generative_dir_without_git "$d"
    with_fake_bin "+uname" _case_generative_dir_present "$d"
    log_pass "ensure_generative_repo tells absent, not-a-checkout and present apart, using no external command"
}

_case_python_absent() {
    local d="$1"
    local rc=0
    run_venv "$d" "ensure_python_installed" || rc=$?
    assert_exit_code 1 "$rc" "python3 absent must fail"
    assert_contains "$LAST_OUT" "python3 is required" "says which interpreter is missing"
}

_case_python_present() {
    local d="$1"
    local rc=0
    run_venv "$d" "ensure_python_installed" || rc=$?
    assert_exit_code 0 "$rc" "python3 present must pass (output: $LAST_OUT)"
}

test_ensure_python_installed_keys_on_the_interpreter() {
    local d="$1"
    with_fake_bin "+uname" _case_python_absent "$d"
    with_fake_bin "python3 +uname" _case_python_present "$d"
    log_pass "ensure_python_installed fails without python3 and passes with it"
}

_case_audio_deps_all_present() {
    local d="$1"
    local rc=0
    run_venv "$d" "ensure_audio_system_deps" || rc=$?
    assert_exit_code 0 "$rc" "nothing missing must return 0 (output: $LAST_OUT)"
    assert_eq "$(fake_bin_record apt-get)" "" "nothing may be installed when nothing is missing"
    assert_eq "$(fake_bin_record sudo)" "" "sudo must not be invoked when nothing is missing"
}

_case_audio_deps_missing_without_apt() {
    local d="$1"
    local rc=0
    run_venv "$d" "ensure_audio_system_deps" || rc=$?
    assert_exit_code 1 "$rc" "a missing dep on a host with no apt-get must fail"
    assert_contains "$LAST_OUT" "Missing system deps" "says what is missing"
    assert_contains "$LAST_OUT" "sox" "names the missing package"
}

test_ensure_audio_system_deps_installs_only_what_is_missing() {
    local d="$1"
    # python3 is faked as a success-with-no-output, which is what makes `import ensurepip`
    # succeed and the versioned python<X.Y>-venv package stay out of the missing list.
    with_fake_bin "python3 ffmpeg ffprobe sox apt-get sudo +uname" _case_audio_deps_all_present "$d"
    # ffmpeg/ffprobe present, sox absent, and no apt-get to fix it with.
    with_fake_bin "python3 ffmpeg ffprobe +uname" _case_audio_deps_missing_without_apt "$d"
    log_pass "ensure_audio_system_deps installs nothing when nothing is missing, and names what it cannot fix"
}

_case_python_deps_install_sequence() {
    local d="$1"
    local rc=0
    run_venv "$d" "install_generative_python_deps '$d/gen' '$d/stamp' 'HASH123'" || rc=$?
    assert_exit_code 0 "$rc" "the install must succeed with pip faked (output: $LAST_OUT)"
    assert_eq "$(cat "$d/stamp")" "HASH123" "the content hash is written to the stamp file"
    local pip_calls
    pip_calls="$(fake_bin_record pip)"
    assert_contains "$pip_calls" "install --upgrade pip" "pip is upgraded first"
    assert_contains "$pip_calls" "install -e $d/gen" "the generative package is installed editable"
    assert_contains "$pip_calls" "install qwen-tts" "qwen-tts is installed"
    assert_contains "$pip_calls" "install qwen-asr" "qwen-asr is installed"
    # The cross-module edge: install_flash_attn_if_supported lives in cuda.sh, and with
    # `import flash_attn` succeeding it returns before touching pip again. If the edge
    # were broken the run would have died with "command not found" above.
    assert_not_contains "$pip_calls" "flash-attn" "flash-attn is skipped when it already imports"
}

test_install_generative_python_deps_drives_pip_and_stamps() {
    local d="$1"
    mkdir -p "$d/gen"
    # `cat` is admitted so the assertions can read the stamp file back; python and pip
    # are fakes. No network, no PyPI, no wheel is built.
    with_fake_bin "python pip +cat +uname" _case_python_deps_install_sequence "$d"
    log_pass "install_generative_python_deps runs the four pip installs, defers to cuda.sh, and writes the stamp"
}

log_test "test-media-venv"
test_every_moved_function_is_solely_owned_by_this_module
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_a_planted_mutation_is_visible_to_the_behaviour_cases
with_temp_dir test_ensure_generative_repo_diagnoses_all_three_states
with_temp_dir test_ensure_python_installed_keys_on_the_interpreter
with_temp_dir test_ensure_audio_system_deps_installs_only_what_is_missing
with_temp_dir test_install_generative_python_deps_drives_pip_and_stamps
echo ""
log_pass "all tests passed"
