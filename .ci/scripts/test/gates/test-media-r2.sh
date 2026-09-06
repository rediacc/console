#!/bin/bash
# Tests for .ci/media/r2.sh -- the tutorial-narration cache in R2.
#
# THE BEHAVIOUR THAT MATTERS IS THE ABSENT-CREDENTIALS ONE. Regenerating narration costs
# real TTS GPU time, which is why this cache exists at all; but a developer without R2
# credentials must still be able to run the pipeline, so both functions warn and return 0
# rather than failing. Get that backwards and a fresh checkout either cannot generate
# tutorials at all, or silently re-pays for every mp3.
#
# Both directions are driven here with aws, curl and the network absent, and the sync
# scripts replaced by recorders at the fixture root. No bucket is touched, and no
# credential is read: the three CLOUDFLARE_R2_MEDIA_* variables are set to obvious
# placeholders in the credentials-present case.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/r2.sh"

MOVED=(
    www_tutorial_audio_restore
    www_tutorial_audio_upload
)

run_r2() {
    media_run_module "$1" "r2.sh" "$2"
}

# stage_sync_scripts <fixture-root> [exit-code]
#
# The two functions call the sync scripts by ABSOLUTE path under $ROOT_DIR, not through
# PATH, so the seam is a fixture tree rather than a fake binary.
stage_sync_scripts() {
    local d="$1" code="${2:-0}" name
    mkdir -p "$d/.ci/scripts/deploy"
    for name in sync-media-from-r2.sh sync-media-to-r2.sh; do
        printf '#!/bin/bash\nprintf "%%s\\n" "%s $*" >>"%s/sync-calls"\nexit %s\n' \
            "$name" "$d" "$code" >"$d/.ci/scripts/deploy/$name"
        chmod +x "$d/.ci/scripts/deploy/$name"
    done
    : >"$d/sync-calls"
}

test_this_module_solely_owns_the_moved_functions() {
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of both functions
    # and this asserted the two were byte-identical. run.sh has no copy now, so the
    # question became ownership: exactly one file defines each name, it is this module,
    # run.sh and media.sh define neither, and media-entry.sh resolves both names here.
    media_assert_module_owns r2.sh "${MOVED[@]}"
}

test_the_ownership_assertion_can_fail() {
    media_assert_ownership_control "$1" r2.sh www_tutorial_audio_restore
}

_case_a_mutated_module_changes_what_the_behaviour_cases_see() {
    # CONTROL FOR THE CASES BELOW. --audio-only is the flag that keeps this from syncing
    # the whole media bucket, and the credentialed case asserts it by name. Drop it in a
    # copy of the module and that assertion must stop holding; if it still held, the case
    # would be reading something other than the module under test.
    local d="$1"
    local MEDIA_MODULE_DIR="$d/mutant"
    local rc=0
    run_r2 "$d" "export CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=placeholder-key
        export CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=placeholder-secret
        export CLOUDFLARE_R2_MEDIA_ENDPOINT=https://example.invalid
        www_tutorial_audio_restore" || rc=$?
    assert_exit_code 0 "$rc" "the mutated copy still runs; only its flag changed"
    local calls
    calls="$(<"$d/sync-calls")"
    media_assert_mutation_swapped "$calls" "sync-media-from-r2.sh --audio-only" "sync-media-from-r2.sh --all" "flag"
}

test_a_planted_mutation_is_visible_to_the_behaviour_cases() {
    local d="$1"
    mkdir -p "$d/mutant"
    sed 's/--audio-only/--all/' "$MODULE" >"$d/mutant/r2.sh"
    grep -q -- "--all" "$d/mutant/r2.sh" || log_fail "the mutation did not apply, so this control would pass for the wrong reason"
    stage_sync_scripts "$d"
    with_fake_bin "+cat +uname" _case_a_mutated_module_changes_what_the_behaviour_cases_see "$d"
    log_pass "swapping --audio-only for --all in r2.sh changes what the behaviour cases observe"
}

_case_no_credentials_skips_without_failing() {
    local d="$1"
    local rc=0
    run_r2 "$d" "unset CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY CLOUDFLARE_R2_MEDIA_ENDPOINT
        www_tutorial_audio_restore
        www_tutorial_audio_upload" || rc=$?
    assert_exit_code 0 "$rc" "no credentials must SKIP, never fail the pipeline"
    assert_contains "$LAST_OUT" "skipping tutorial-audio cache restore" "says the restore was skipped"
    assert_contains "$LAST_OUT" "skipping tutorial-audio cache upload" "says the upload was skipped"
    assert_eq "$(<"$d/sync-calls")" "" "no sync script may run without credentials"
}

_case_credentials_present_syncs_audio_only() {
    local d="$1"
    local rc=0
    run_r2 "$d" "export CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=placeholder-key
        export CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=placeholder-secret
        export CLOUDFLARE_R2_MEDIA_ENDPOINT=https://example.invalid
        www_tutorial_audio_restore
        www_tutorial_audio_upload" || rc=$?
    assert_exit_code 0 "$rc" "the credentialed path must succeed (output: $LAST_OUT)"
    local calls
    calls="$(<"$d/sync-calls")"
    assert_contains "$calls" "sync-media-from-r2.sh --audio-only" "restore pulls only the audio prefix"
    assert_contains "$calls" "sync-media-to-r2.sh --audio-only" "upload pushes only the audio prefix"
}

_case_a_failing_sync_is_a_warning_not_a_death() {
    local d="$1"
    local rc=0
    run_r2 "$d" "export CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=placeholder-key
        export CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=placeholder-secret
        export CLOUDFLARE_R2_MEDIA_ENDPOINT=https://example.invalid
        www_tutorial_audio_restore
        www_tutorial_audio_upload" || rc=$?
    assert_exit_code 0 "$rc" "a failed cache sync must not fail the pipeline"
    assert_contains "$LAST_OUT" "Audio cache restore failed, continuing without it" "the restore failure is a warning"
    assert_contains "$LAST_OUT" "Audio cache upload failed" "the upload failure is a warning"
}

test_the_cache_is_optional_in_both_directions() {
    local d="$1"
    stage_sync_scripts "$d"
    with_fake_bin "+cat +uname" _case_no_credentials_skips_without_failing "$d"
    with_fake_bin "+cat +uname" _case_credentials_present_syncs_audio_only "$d"
    log_pass "no credentials skips both directions; credentials sync the audio prefix and nothing else"
}

test_a_broken_sync_never_fails_the_pipeline() {
    local d="$1"
    stage_sync_scripts "$d" 1
    with_fake_bin "+cat +uname" _case_a_failing_sync_is_a_warning_not_a_death "$d"
    log_pass "a sync script that exits non-zero produces a warning and a zero exit"
}

log_test "test-media-r2"
test_this_module_solely_owns_the_moved_functions
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_a_planted_mutation_is_visible_to_the_behaviour_cases
with_temp_dir test_the_cache_is_optional_in_both_directions
with_temp_dir test_a_broken_sync_never_fails_the_pipeline
echo ""
log_pass "all tests passed"
