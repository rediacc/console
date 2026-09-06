#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: none
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# Tests for the ARGUMENT PARSING in .ci/media/tutorials.sh, and for .ci/media/teaser.sh.
#
# WHY THESE TWO SHARE A FILE. What is left in tutorials.sh after the venv, the GPU probe,
# the render pool, the bridge and the R2 cache moved out is control flow and option
# parsing. Option parsing is the half of it a test can drive end to end -- the other half
# ends in a real render -- and it is also the half that fails silently: a `--lang` routed
# into the wrong bucket does not error, it just narrates the wrong set. teaser.sh is the
# same kind of surface for the private/growth side; media.sh is now three lines of
# delegation into it.
#
# Every case replaces the downstream work with recorders after sourcing the module, so
# nothing here runs npm, node, python or a render. The parsers are what is under test.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

TUTORIALS="$ROOT/.ci/media/tutorials.sh"
TEASER="$ROOT/.ci/media/teaser.sh"

TUTORIAL_MOVED=(
    _grand_env_is_wildcard
    _tutorial_script_hash
    www_tutorials_record
    www_tutorials_extract
    www_tutorials_scaffold_locales
    www_tutorials_generate
    www_tutorials_video
    _tutorial_media_producer
    www_tutorials_media
    _tutorial_watch_producer
    www_tutorials_watch
    www_tutorials_validate
    www_tutorials_all
    www_all
)

TEASER_MOVED=(die pass_owns venv_for)

# STUBS_BASE is prepended to every parser case: the preflight steps and the leaves the
# parsers hand their work to, all replaced by recorders. Nothing below runs npm, node,
# python or a render.
STUBS_BASE='
check_node_version() { :; }
ensure_deps() { :; }
ensure_packages_built() { :; }
ensure_audio_system_deps() { :; }
ensure_generative_repo() { :; }
ensure_python_installed() { :; }
ensure_generative_venv() { echo "venv: $*"; }
www_tutorial_audio_restore() { echo "restore"; }
www_tutorial_audio_upload() { echo "upload"; }
_tutorial_render_pairs() { printf "installation\ten\n"; }
_tutorial_auto_jobs() { echo 3; }
_tutorial_video_pool() { echo "pool: $*"; while read -r _; do :; done; }
_tutorial_media_producer() { echo "producer: $*" >&2; }
'

# STUBS_STEPS additionally replaces the www_tutorials_* verbs themselves. It is used ONLY
# by the www_tutorials_all case, which is about ROUTING and therefore needs each step to
# report what reached it -- and it is deliberately NOT in STUBS_BASE, because stubbing a
# verb while testing that same verb is how an argument-validation case comes back green
# having exercised a two-line echo. That happened here on the first run:
# `www_tutorials_video --jobs abc` reported exit 0 because the stub, not the parser, is
# what answered.
STUBS_STEPS='
www_tutorials_record() { echo "record: $*"; }
www_tutorials_extract() { echo "extract"; }
www_tutorials_scaffold_locales() { echo "scaffold"; }
www_tutorials_generate() { echo "generate: $*"; }
www_tutorials_video() { echo "video: $*"; }
www_tutorials_validate() { echo "validate"; }
'

run_tutorials() {
    media_run_module "$1" "tutorials.sh" "$STUBS_BASE
$2"
}

run_tutorials_all() {
    media_run_module "$1" "tutorials.sh" "$STUBS_BASE
$STUBS_STEPS
$2"
}

run_teaser() {
    media_run_module "$1" "teaser.sh" "$2"
}

test_every_moved_tutorial_function_is_solely_owned_by_this_module() {
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all fourteen
    # and this compared the bodies byte for byte. run.sh has no copies now, so the claim
    # worth asserting is ownership: one definition per name, here, with run.sh and
    # media.sh carrying none, and media-entry.sh resolving each name to this file.
    media_assert_module_owns tutorials.sh "${TUTORIAL_MOVED[@]}"
}

test_the_recorded_terminal_geometry_lives_here_and_only_here() {
    # TUTORIAL_COLS/TUTORIAL_ROWS are the single source of truth for the cast header and
    # every downstream renderer, and being plain assignments the ownership assertion
    # cannot see them. Assert the same three things by hand: this module defines them,
    # run.sh no longer does, and the values that reach the entry point are these.
    local key in_module in_scope
    for key in TUTORIAL_COLS TUTORIAL_ROWS; do
        in_module="$(grep "^${key}=" "$TUTORIALS")"
        [ -n "$in_module" ] || log_fail "$key is not defined in tutorials.sh -- this assertion has nothing to check"
        media_assert_absent_from_origins "^${key}=" "$ROOT" \
            "an origin still assigns $key -- the cutover left a second source of truth for the cast geometry"
        in_scope="$("$BASH" -c "source '$ROOT/.ci/media/media-entry.sh' >/dev/null 2>&1; printf '%s=%s' '$key' \"\${$key:-}\"")"
        assert_eq "$in_scope" "$in_module" "media-entry.sh must put tutorials.sh's $key in scope with its own value"
    done
    log_pass "TUTORIAL_COLS and TUTORIAL_ROWS are defined only in tutorials.sh and reach the entry point unchanged"
}

test_the_ownership_assertion_can_fail() {
    media_assert_ownership_control "$1" tutorials.sh www_tutorials_record
}

# _absence_verdict <args...>
#
# Runs media_assert_absent_from_origins in a SUBSHELL and reports its verdict as an exit
# status. A control cannot call it directly: log_fail exits, so a finding would take the
# whole gate down instead of being observed.
_absence_verdict() {
    (media_assert_absent_from_origins "$@" >/dev/null 2>&1)
}

test_the_absence_assertion_can_fail() {
    # THE OTHER HALF OF THE CUTOVER PROOF HAS ITS OWN VACUITY, and it is worse than the
    # ownership assertion's because it is invisible: `grep -q pat a b` with b missing
    # exits 2, which reads as "not found". Every arm here plants the pattern in ONE origin
    # and requires a finding, then a fourth removes an origin and requires a finding for
    # that too.
    local d="$1" repo rel
    repo="$(media_chain_sandbox "$d")"

    _absence_verdict '^TUTORIAL_COLS=' "$repo" "control" ||
        log_fail "the absence assertion already reports a finding on a clean sandbox, so the arms below would prove nothing"

    for rel in run.sh media.sh .ci/legacy/run-legacy.sh; do
        printf '\nTUTORIAL_COLS=999\n' >>"$repo/$rel"
        ! _absence_verdict '^TUTORIAL_COLS=' "$repo" "control" ||
            log_fail "the absence assertion passed with $rel assigning TUTORIAL_COLS -- that origin is not being read"
        cp "$ROOT/$rel" "$repo/$rel"
    done

    mv "$repo/media.sh" "$repo/absent-origin"
    ! _absence_verdict '^TUTORIAL_COLS=' "$repo" "control" ||
        log_fail "the absence assertion passed with an origin missing -- a file nobody read cannot testify that the value is not in it"
    mv "$repo/absent-origin" "$repo/media.sh"

    log_pass "the absence assertion fires on a value planted in each of the 3 origins and on an origin that is missing"
}

# THE DELEGATION ITSELF, for the surface that carries almost all of it. Every
# `./run.sh www ...` verb now crosses run.sh's exec into media-entry.sh and lands in this
# module, so the chain is driven for real in a sandbox repo: run.sh, the exec, the case
# tree, tutorials.sh, with a marker planted inside the function body. Two verbs are
# probed rather than one because they take different routes through the case tree --
# `www tutorials <verb>` is two levels deep, `www all` is one.
_case_the_chain_reaches_each_verb() {
    local repo="$1"
    media_chain_run "$repo" run.sh www tutorials record --force installation ||
        log_fail "./run.sh www tutorials record failed in the sandbox: $LAST_CHAIN"
    assert_eq "$LAST_CHAIN" "MEDIA_CHAIN_REACHED:www_tutorials_record:--force installation" \
        "run.sh must reach tutorials.sh's www_tutorials_record with its arguments intact"
}

_case_the_chain_reaches_www_all() {
    local repo="$1"
    media_chain_run "$repo" run.sh www all installation ||
        log_fail "./run.sh www all failed in the sandbox: $LAST_CHAIN"
    assert_eq "$LAST_CHAIN" "MEDIA_CHAIN_REACHED:www_all:installation" \
        "the shallower www arm reaches tutorials.sh's www_all"
}

_case_the_chain_control_breaks_it() {
    local repo="$1"
    local rc=0
    media_chain_run "$repo" run.sh www tutorials record --force installation || rc=$?
    [ "$rc" -eq 0 ] &&
        log_fail "the chain still succeeded after www_tutorials_record was renamed in tutorials.sh, so the probe proves nothing"
    assert_not_contains "$LAST_CHAIN" "MEDIA_CHAIN_REACHED" "no marker may be reported once the module no longer defines the name"
    assert_contains "$LAST_CHAIN" "www_tutorials_record" "the failure names the function the delegation could not find"
}

test_run_sh_still_reaches_this_module() {
    local d="$1" repo
    repo="$(media_chain_sandbox "$d")"
    media_chain_probe "$repo" tutorials.sh www_tutorials_record
    with_fake_bin "+uname +dirname" _case_the_chain_reaches_each_verb "$repo"
    media_chain_probe "$repo" tutorials.sh www_all
    with_fake_bin "+uname +dirname" _case_the_chain_reaches_www_all "$repo"
    # CONTROL: rename the function the delegation looks for. Nothing else changes.
    media_chain_probe "$repo" tutorials.sh www_tutorials_record
    media_chain_mutate "$repo" .ci/media/tutorials.sh 's/^www_tutorials_record() {/www_tutorials_record_RENAMED() {/'
    with_fake_bin "+uname +dirname" _case_the_chain_control_breaks_it "$repo"
    log_pass "./run.sh www reaches tutorials.sh at both depths of its case tree, and stops reaching it when the module renames the function"
}

_case_grand_env_wildcard_forms() {
    local d="$1"
    run_tutorials "$d" '
        probe() { REDIACC_ALLOW_GRAND_REPO="$1" _grand_env_is_wildcard && echo "WILD" || echo "no"; }
        probe "*"
        probe "repo1,*,repo2"
        probe "  *  "
        probe "repo1,repo2"
        probe ""' || log_fail "the probe failed (output: $LAST_OUT)"
    # while-read, not mapfile: check:ci-shell-commands bans bash-4-only builtins because
    # the ubuntu-slim CI image is not guaranteed to have them.
    local lines=() line
    while IFS= read -r line; do
        lines+=("$line")
    done <<<"$LAST_OUT"
    assert_eq "${lines[0]}" "WILD" "a bare * is a wildcard"
    assert_eq "${lines[1]}" "WILD" "a * mixed into a list is a wildcard"
    assert_eq "${lines[2]}" "WILD" "surrounding whitespace is trimmed"
    assert_eq "${lines[3]}" "no" "a list without * is not a wildcard"
    assert_eq "${lines[4]}" "no" "an empty value is not a wildcard"
}

test_grand_env_wildcard_detection() {
    # The `*` must never be glob-expanded against the cwd, which is why the function uses
    # read -ra. A fixture directory full of files is staged so a regression would produce
    # a filename rather than "WILD".
    local d="$1"
    touch "$d/decoy-one" "$d/decoy-two"
    with_fake_bin "+uname" _case_grand_env_wildcard_forms "$d"
    log_pass "_grand_env_is_wildcard accepts *, a mixed list and padded whitespace, and rejects the rest"
}

_case_tutorials_all_splits_args_by_destination() {
    local d="$1"
    run_tutorials_all "$d" "cd '$d' && www_tutorials_all --lang de --keep-temp --clean-venv --force --max-idle-ms 400 installation" ||
        log_fail "www_tutorials_all failed (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "record: --force --max-idle-ms 400 installation" "record gets --force, --max-idle-ms and the positional"
    assert_contains "$LAST_OUT" "generate: --clean-venv --lang de" "generate gets the venv flag and the language"
    assert_contains "$LAST_OUT" "video: --keep-temp --lang de" "video gets --keep-temp and the language"
    assert_not_contains "$LAST_OUT" "record: --lang" "--lang must NOT reach record"
    assert_not_contains "$LAST_OUT" "video: --clean-venv" "--clean-venv must NOT reach video"
    assert_contains "$LAST_OUT" "extract" "extract runs between record and generate"
    assert_contains "$LAST_OUT" "scaffold" "scaffold-locales runs too"
    assert_contains "$LAST_OUT" "validate" "validate closes the pipeline"
}

test_tutorials_all_routes_each_flag_to_the_step_that_understands_it() {
    local d="$1"
    with_fake_bin "+uname" _case_tutorials_all_splits_args_by_destination "$d"
    log_pass "www_tutorials_all splits --lang / --keep-temp / --clean-venv / --force / --max-idle-ms to the right steps"
}

_case_jobs_must_be_a_positive_integer() {
    local d="$1"
    local rc=0
    run_tutorials "$d" "www_tutorials_video --jobs abc" || rc=$?
    assert_exit_code 1 "$rc" "a non-numeric --jobs must be rejected"
    assert_contains "$LAST_OUT" "--jobs must be a positive integer, got: abc" "names the bad value"

    rc=0
    run_tutorials "$d" "www_tutorials_video --jobs 0" || rc=$?
    assert_exit_code 1 "$rc" "--jobs 0 must be rejected"

    rc=0
    run_tutorials "$d" "www_tutorials_video --jobs=2 --lang=fr --debug" || rc=$?
    assert_exit_code 0 "$rc" "the =-joined forms must be accepted (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "pool: 2 " "--jobs=2 reaches the pool"
    assert_contains "$LAST_OUT" "--debug" "a passthrough flag reaches the pool"
}

_case_media_validates_jobs_and_forces_hwenc_off() {
    local d="$1"
    local rc=0
    run_tutorials "$d" "www_tutorials_media --jobs abc" || rc=$?
    assert_exit_code 1 "$rc" "a non-numeric --jobs must be rejected"

    rc=0
    run_tutorials "$d" "RDC_TUTORIAL_HWENC=1 www_tutorials_media --langs en,de --subtitle --debug" || rc=$?
    assert_exit_code 0 "$rc" "the happy path must succeed (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "forcing it to 0 so renders stay off the GPU" "hardware encoding is refused, loudly"
    # THE SPLIT IS THE ASSERTION. --subtitle belongs to the narration process and --debug
    # to the renderer, and the two are collected into different variables by the same
    # while-loop. Checking only that both appear somewhere would pass even if the loop
    # sent both to both, so each line is inspected for the flag it should carry AND for
    # the one it should not.
    local producer_line pool_line
    producer_line="$(printf '%s\n' "$LAST_OUT" | grep '^producer:')"
    pool_line="$(printf '%s\n' "$LAST_OUT" | grep '^pool:')"
    assert_contains "$producer_line" "--subtitle" "--subtitle is a TTS flag"
    assert_not_contains "$producer_line" "--debug" "a render passthrough must not reach the narrator"
    assert_contains "$producer_line" "en de" "--langs is split on commas into the producer's language list"
    assert_contains "$pool_line" "--debug" "--debug is a render passthrough"
    assert_not_contains "$pool_line" "--subtitle" "a TTS flag must not reach the render pool"
    assert_contains "$pool_line" "pool: 3" "an absent --jobs falls back to _tutorial_auto_jobs"
}

_case_watch_rejects_what_it_does_not_understand() {
    local d="$1"
    local rc=0
    run_tutorials "$d" "www_tutorials_watch --nope" || rc=$?
    assert_exit_code 1 "$rc" "an unknown watch option must be rejected rather than treated as a name"
    assert_contains "$LAST_OUT" "Unknown watch option: --nope" "names the option it refused"

    rc=0
    run_tutorials "$d" "www_tutorials_watch --poll abc" || rc=$?
    assert_exit_code 1 "$rc" "a non-numeric --poll must be rejected"
    assert_contains "$LAST_OUT" "--poll must be a positive integer" "says what --poll must be"
}

test_the_numeric_options_are_validated_before_any_work_starts() {
    local d="$1"
    mkdir -p "$d/packages/www/src/data/tutorial-timeline/en" "$d/artifacts"
    with_fake_bin "+rm +uname" _case_jobs_must_be_a_positive_integer "$d"
    with_fake_bin "+rm +basename +grep +uname" _case_media_validates_jobs_and_forces_hwenc_off "$d"
    with_fake_bin "+mkdir +date +flock +rm +tee +uname" _case_watch_rejects_what_it_does_not_understand "$d"
    log_pass "--jobs and --poll are validated, unknown watch options are refused, and hardware encoding is forced off"
}

# ---------------------------------------------------------------------------
# teaser.sh
# ---------------------------------------------------------------------------

test_the_teaser_functions_are_solely_owned_by_this_module() {
    # WHAT THIS REPLACED. media.sh kept its own run/teaser/luma bodies until the cutover,
    # and byte-identity between the two was UNREACHABLE (media.sh sat outside
    # check:ci-shell-format, so `die` on one line and an arithmetic expansion's inner
    # spacing differed by construction), which is why phase 1 compared what bash's own
    # parser made of each instead. media.sh defines nothing now -- it is three lines that
    # exec into media-entry.sh -- so both the comparison and the reason it had to be an
    # equivalence are gone, and what is left to assert is ownership.
    media_assert_module_owns teaser.sh "${TEASER_MOVED[@]}"
}

test_the_teaser_ownership_assertion_can_fail() {
    # `die` is the name this control uses because media.sh wrote it in the ONE-LINE
    # `die() { ...; }` form, and the shared control plants that spelling into media.sh
    # specifically. A block-only search would report the re-planted copy as absent and
    # pass, so this is also the case that proves fidelity_extract_any is wired in.
    media_assert_ownership_control "$1" teaser.sh die
}

test_the_teaser_archaeology_is_here_and_nowhere_else() {
    # The incident prose is what makes these three functions the shape they are, and it is
    # the part no structural assertion can see. It was checked against media.sh's own copy
    # while both existed; now the check is that teaser.sh carries every sentence and that
    # media.sh does NOT carry a second, forkable copy of any of them.
    local sentence
    for sentence in \
        "a guard that blocks everything gets switched off" \
        "exits only the SUBSHELL" \
        "so this teaser will" \
        "the pre-palette artifacts measure 30 to 50"; do
        grep -qF "$sentence" "$TEASER" || log_fail "the incident comment is missing from teaser.sh: $sentence"
        grep -qF "$sentence" "$ROOT/media.sh" && log_fail "media.sh carries a second copy of this comment, which will fork: $sentence"
    done
    log_pass "every incident comment lives in teaser.sh, and media.sh keeps no second copy to drift from"
}

# THE DELEGATION FOR THE private/growth SIDE. `./media.sh run|teaser|luma` is now three
# lines that exec into media-entry.sh's `growth` arm; this drives that whole path with a
# marker planted inside growth_run's body.
_case_media_sh_reaches_the_teaser_module() {
    local repo="$1"
    media_chain_run "$repo" media.sh run video_pipeline --step 8000 ||
        log_fail "./media.sh run failed in the sandbox: $LAST_CHAIN"
    assert_eq "$LAST_CHAIN" "MEDIA_CHAIN_REACHED:growth_run:video_pipeline --step 8000" \
        "media.sh must reach teaser.sh's growth_run with its arguments intact"
}

_case_the_teaser_chain_control_breaks_it() {
    local repo="$1"
    local rc=0
    media_chain_run "$repo" media.sh run video_pipeline --step 8000 || rc=$?
    [ "$rc" -eq 0 ] &&
        log_fail "the chain still succeeded after growth_run was renamed in teaser.sh, so the probe proves nothing"
    assert_not_contains "$LAST_CHAIN" "MEDIA_CHAIN_REACHED" "no marker may be reported once the module no longer defines the name"
    assert_contains "$LAST_CHAIN" "growth_run" "the failure names the function the delegation could not find"
}

test_media_sh_still_reaches_this_module() {
    local d="$1" repo
    repo="$(media_chain_sandbox "$d")"
    media_chain_probe "$repo" teaser.sh growth_run
    with_fake_bin "+uname +dirname" _case_media_sh_reaches_the_teaser_module "$repo"
    media_chain_mutate "$repo" .ci/media/teaser.sh 's/^growth_run() {/growth_run_RENAMED() {/'
    with_fake_bin "+uname +dirname" _case_the_teaser_chain_control_breaks_it "$repo"
    log_pass "./media.sh run reaches teaser.sh's growth_run, and stops reaching it when the module renames it"
}

_case_teaser_refuses_what_it_cannot_run() {
    local d="$1"
    local rc=0
    run_teaser "$d" "growth_run" || rc=$?
    assert_exit_code 1 "$rc" "growth_run with no pipeline must die"
    assert_contains "$LAST_OUT" "usage: ./media.sh run" "prints the usage line"

    rc=0
    run_teaser "$d" "growth_run nosuchpipeline" || rc=$?
    assert_exit_code 1 "$rc" "an unknown pipeline must die"
    assert_contains "$LAST_OUT" "no such pipeline: nosuchpipeline" "names the pipeline it could not find"

    rc=0
    run_teaser "$d" "venv_for video_pipeline" || rc=$?
    assert_exit_code 1 "$rc" "a pipeline with no venv must die"
    assert_contains "$LAST_OUT" "no venv for pipeline 'video_pipeline'" "names the pipeline and where it looked"

    rc=0
    run_teaser "$d" "growth_usage" || rc=$?
    assert_exit_code 0 "$rc" "the usage text must print cleanly"
    assert_contains "$LAST_OUT" "cwd = private/growth" "the usage states the invariant the wrapper exists for"
}

test_teaser_dies_before_it_can_half_finish() {
    local d="$1"
    mkdir -p "$d/private/growth/video_pipeline"
    # python3 and ffmpeg are deliberately absent: every case here must be refused BEFORE
    # anything is executed, which is the property that keeps a tree from being left
    # mid-operation with its sentinels already deleted.
    with_fake_bin "+cat +uname" _case_teaser_refuses_what_it_cannot_run "$d"
    log_pass "growth_run and venv_for refuse a bad invocation before running anything"
}

log_test "test-media-args"
test_every_moved_tutorial_function_is_solely_owned_by_this_module
test_the_recorded_terminal_geometry_lives_here_and_only_here
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_the_absence_assertion_can_fail
with_temp_dir test_run_sh_still_reaches_this_module
with_temp_dir test_grand_env_wildcard_detection
with_temp_dir test_tutorials_all_routes_each_flag_to_the_step_that_understands_it
with_temp_dir test_the_numeric_options_are_validated_before_any_work_starts
test_the_teaser_functions_are_solely_owned_by_this_module
with_temp_dir test_the_teaser_ownership_assertion_can_fail
test_the_teaser_archaeology_is_here_and_nowhere_else
with_temp_dir test_media_sh_still_reaches_this_module
with_temp_dir test_teaser_dies_before_it_can_half_finish
echo ""
log_pass "all tests passed"
