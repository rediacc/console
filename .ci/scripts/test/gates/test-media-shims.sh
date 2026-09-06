#!/bin/bash
# Tests for the two COMPATIBILITY ENTRY POINTS W10 phase 3 left behind, and for the
# interfaces they forward to.
#
# THE PROBLEM THIS FILE EXISTS TO SOLVE. Phase 3 moved the narration wrapper
# (.ci/docker/run-in-tts.sh plus its image context .ci/docker/tts/) and the per-file media
# publish primitive (.ci/scripts/deploy/upload-media-to-r2.sh) into .ci/media. Three of the
# four callers of those two paths live in private/generative and private/growth, which are
# gitignored REPOSITORIES rather than submodules: this checkout cannot open them, cannot
# commit to them, and cannot even read the lines that spell those paths. So the usual
# proof that a relocation is safe -- update the callers, run them -- is not available.
#
# WHAT REPLACES IT, AND WHY IT IS EQUIVALENT. A caller of an exec'd script depends on
# exactly four things, and on nothing else: that the path is there and runnable, that its
# argv arrives unaltered, that its exit status comes back, and that the INTERFACE on the
# far side still accepts what the caller passes. All four are properties of THIS side of
# the boundary, so all four are checked here:
#
#   1. Both old paths exist, are executable, and are exec shims with no logic of their own
#      (a shim that grew argument handling is a second implementation of the contract).
#   2. Driven for real, from an arbitrary cwd, argv arrives on the far side byte for byte
#      -- including empty arguments and arguments containing spaces, which is precisely
#      what a naive `$@` or a stray `shift` destroys -- with stdin still connected and the
#      exit status forwarded.
#   3. The controls plant a broken shim and require every one of those assertions to fire,
#      because a forwarding test that has never been watched failing proves only that
#      something ran.
#   4. The ACCEPTED SURFACE of each relocated program is frozen as a SET: the seven flags
#      upload-r2.sh parses, and the five environment variables run-in-tts.sh reads. This
#      is the half that a path-only test would miss. Renaming --defer-manifest breaks
#      private/growth's publish just as thoroughly as moving the file, and it would be
#      caught by nothing at all; frozen here, it is red in console CI instead of at the
#      next publish run.
#
# Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network. The narration
# wrapper's own REDIACC_NO_DOCKER=1 escape hatch turns it into `exec "$@"`, the publish
# primitive is driven against recorders in a sandbox, and the surface freezes are text.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

# The four paths this file is about. RELOCATED is where the body lives now; SHIM is the
# spelling a caller still uses. They are listed in pairs so a test can loop over both
# relocations rather than repeating itself once per program.
TTS_SHIM=".ci/docker/run-in-tts.sh"
TTS_REAL=".ci/media/tools/run-in-tts.sh"
R2_SHIM=".ci/scripts/deploy/upload-media-to-r2.sh"
R2_REAL=".ci/media/tools/upload-r2.sh"

# The image context moved with the wrapper, because they are one thing: the wrapper's only
# reason to know a path is to build this directory.
TTS_CONTEXT=".ci/media/tts"

# THE FROZEN SURFACES. These two lists ARE the cross-repo contract. A caller in a
# gitignored repository passes these flags and sets these variables, and nothing else
# about this side is visible to it.
#
# Adding an entry is a widening and is fine. REMOVING or RENAMING one is a breaking change
# that has to land in private/generative or private/growth in the same wave, and editing
# this list is where that gets noticed.
UPLOAD_FLAGS_FROZEN="--defer-manifest --engine --field --file --key --kind --lang"
TTS_ENV_FROZEN="RDC_GPU_LOCK_DIR RDC_GPU_LOCK_FILE RDC_HF_CACHE RDC_MODELS_VOLUME REDIACC_NO_DOCKER"

# ---------------------------------------------------------------------------
# The relocation itself
# ---------------------------------------------------------------------------

test_the_relocation_landed_and_the_old_context_is_gone() {
    local rel
    for rel in "$TTS_SHIM" "$TTS_REAL" "$R2_SHIM" "$R2_REAL"; do
        [ -f "$ROOT/$rel" ] || log_fail "$rel does not exist"
        [ -x "$ROOT/$rel" ] || log_fail "$rel is not executable, so a caller's exec would fail with EACCES"
    done
    [ -f "$ROOT/$TTS_CONTEXT/Dockerfile" ] ||
        log_fail "$TTS_CONTEXT/Dockerfile does not exist -- the wrapper builds this directory by name"
    [ -f "$ROOT/$TTS_CONTEXT/generative-pyproject.toml" ] ||
        log_fail "$TTS_CONTEXT/generative-pyproject.toml does not exist -- the Dockerfile COPYs it by name"

    # THE OLD CONTEXT MUST BE GONE, not merely unused. Two build contexts, one of them
    # stale, is how a session spends an hour wondering why an edited Dockerfile changed
    # nothing about the image.
    [ -e "$ROOT/.ci/docker/tts" ] &&
        log_fail ".ci/docker/tts still exists -- the relocated context at $TTS_CONTEXT would be the second copy"

    # And the wrapper must name the NEW context. This is the one line in it that a move
    # silently invalidates: a docker build against a path that no longer exists fails only
    # when somebody without a cached image runs a narration.
    grep -qF "\$ROOT/$TTS_CONTEXT" "$ROOT/$TTS_REAL" ||
        log_fail "$TTS_REAL does not build $TTS_CONTEXT -- the wrapper and its context have come apart"
    log_pass "both programs and the tts image context are at their new paths, the old context is gone, and the wrapper names the new one"
}

test_the_old_paths_are_exec_shims_and_nothing_more() {
    # A SHIM WITH LOGIC IS A SECOND IMPLEMENTATION. The contract these two paths carry is
    # already implemented once; anything here that inspects, rewrites or validates argv is
    # a place for the two copies to disagree, and the disagreement would only show up in a
    # repository this one cannot read.
    local rel code
    for rel in "$TTS_SHIM" "$R2_SHIM"; do
        code="$(grep -vE '^\s*(#|$)' "$ROOT/$rel")"
        local lines
        lines="$(printf '%s\n' "$code" | wc -l)"
        [ "$lines" -le 4 ] ||
            log_fail "$rel has $lines lines of code; a forwarding shim is a shebang, set -e, a root, and an exec"
        printf '%s\n' "$code" | grep -qE '^exec "' ||
            log_fail "$rel does not exec -- a call would fork, and the exit status, signals and terminal would belong to the shim"
        printf '%s\n' "$code" | grep -qE '\bshift\b|\bcase\b|\bwhile\b|\bif\b' &&
            log_fail "$rel handles arguments; a shim that reads argv is a second implementation of a contract that already has one"
    done
    log_pass "both old paths are exec shims: no argument handling, no branching, exec on the last line"
}

# ---------------------------------------------------------------------------
# Forwarding, driven for real
# ---------------------------------------------------------------------------

# shim_sandbox <dir> <shim-relpath> <target-relpath>
#
# Builds the smallest tree in which the shim resolves: the shim at its real relative
# depth, and a RECORDER where the relocated program would be. Prints the sandbox root.
#
# THE TARGET IS A RECORDER, NOT THE REAL PROGRAM, and that is the point. What is under
# test is the forward, and the forward has to be observable independently of whatever the
# far side does with the arguments. The recorder writes what it received, in a form that
# cannot lose an empty argument or a space, and exits with a status nothing else would
# produce.
shim_sandbox() {
    local dir="$1" shim="$2" target="$3" repo="$1/repo"
    mkdir -p "$repo/$(dirname "$shim")" "$repo/$(dirname "$target")"
    cp "$ROOT/$shim" "$repo/$shim"
    chmod +x "$repo/$shim"
    # Bash builtins only: read, printf, exit. The recorder must work with PATH emptied,
    # because a caller of these shims is entitled to any PATH at all.
    cat >"$repo/$target" <<'REC'
#!/bin/bash
rec="$(dirname "${BASH_SOURCE[0]}")/../../../record"
{
    printf 'ARGC=%s\n' "$#"
    for a in "$@"; do printf 'ARG<%s>\n' "$a"; done
    printf 'CWD=%s\n' "$PWD"
    while IFS= read -r line; do printf 'STDIN<%s>\n' "$line"; done
} >"$rec"
exit 43
REC
    chmod +x "$repo/$target"
    printf '%s' "$repo"
}

# ARGV WITH TEETH. An empty string and an argument holding spaces are the two shapes a
# careless forward destroys, and both are shapes a real caller passes: publish.py passes a
# file path, and an unset --engine used to arrive as an empty string.
SHIM_ARGV=(--kind solutions --key "a slug with spaces" --lang "" --field mp4)

_shim_forwards_everything() {
    # TWO `local`s, NOT ONE. Within a single `local`, `$repo` still names the OUTER scope's
    # variable, so `rec="$repo/record"` on the same line reads whatever the caller happened
    # to have -- which here was the right value by coincidence, and would silently stop
    # being so the moment this probe were called from anywhere else (shellcheck SC2318).
    local repo="$1" shim="$2" rc=0
    local rec="$repo/record"
    # cd somewhere with no relationship to the sandbox: a shim that resolved its target
    # relative to the CALLER's directory instead of its own would pass from the repo root
    # and fail everywhere else, which is the failure mode a cross-repo caller hits first.
    (cd / && "$repo/$shim" "${SHIM_ARGV[@]}" </dev/null) || rc=$?
    assert_exit_code 43 "$rc" "the shim must forward the target's exit status, not invent one"
    [ -f "$rec" ] || log_fail "the target was never reached: $shim did not forward at all"

    local got
    got="$(<"$rec")"
    assert_contains "$got" "ARGC=${#SHIM_ARGV[@]}" "the target must receive exactly the arguments the caller passed, no more and no fewer"
    local a
    for a in "${SHIM_ARGV[@]}"; do
        assert_contains "$got" "ARG<$a>" "argument '$a' did not arrive intact"
    done
    assert_contains "$got" "CWD=/" "the shim must not change the working directory a caller chose"
}

_shim_forwards_stdin() {
    local repo="$1" shim="$2" rc=0
    printf 'a line on stdin\n' | (cd / && "$repo/$shim" one) || rc=$?
    assert_exit_code 43 "$rc" "exit status must survive a piped stdin too"
    assert_contains "$(<"$repo/record")" "STDIN<a line on stdin>" "stdin must still be connected on the far side of the exec"
}

test_both_shims_forward_argv_cwd_stdin_and_status() {
    local d="$1" repo
    repo="$(shim_sandbox "$d/tts" "$TTS_SHIM" "$TTS_REAL")"
    with_fake_bin "+bash +dirname" _shim_forwards_everything "$repo" "$TTS_SHIM"
    with_fake_bin "+bash +dirname" _shim_forwards_stdin "$repo" "$TTS_SHIM"

    repo="$(shim_sandbox "$d/r2" "$R2_SHIM" "$R2_REAL")"
    with_fake_bin "+bash +dirname" _shim_forwards_everything "$repo" "$R2_SHIM"
    with_fake_bin "+bash +dirname" _shim_forwards_stdin "$repo" "$R2_SHIM"
    log_pass "both shims forward argv byte for byte, keep the caller's cwd and stdin, and return the target's exit status"
}

test_the_forwarding_assertion_can_fail() {
    # CONTROL, in the three ways a forward breaks. Each mutates the sandbox rather than the
    # checkout, and each must be observed failing; a forwarding test that has never failed
    # proves only that something ran.
    local d="$1" repo rc

    # 1. The target is not there. This is what a relocation without a shim update looks
    #    like, and it is the failure the cross-repo callers would hit.
    repo="$(shim_sandbox "$d/gone" "$TTS_SHIM" "$TTS_REAL")"
    rm -f "$repo/$TTS_REAL"
    rc=0
    (cd / && "$repo/$TTS_SHIM" one </dev/null) >/dev/null 2>&1 || rc=$?
    [ "$rc" -ne 0 ] || log_fail "the shim succeeded with its target deleted, so reaching the target is not what is being measured"

    # 2. The target is there but the shim mangles argv. A stray `shift` is the classic
    #    version and it is silent: the call still runs, with the first flag eaten.
    repo="$(shim_sandbox "$d/shift" "$TTS_SHIM" "$TTS_REAL")"
    media_chain_mutate "$repo" "$TTS_SHIM" 's|^exec "\$ROOT|shift\nexec "$ROOT|'
    rc=0
    (cd / && "$repo/$TTS_SHIM" "${SHIM_ARGV[@]}" </dev/null) >/dev/null 2>&1 || rc=$?
    assert_exit_code 43 "$rc" "the mutated shim still reaches the target; only its argv changed"
    assert_not_contains "$(<"$repo/record")" "ARGC=${#SHIM_ARGV[@]}" "a shim that shifts must NOT satisfy the argv assertion, or that assertion is measuring nothing"

    # 3. The exit status is swallowed. `"$ROOT/..." "$@"` without exec, followed by a
    #    successful last command, is how a wrapper reports success for a failed run.
    repo="$(shim_sandbox "$d/swallow" "$TTS_SHIM" "$TTS_REAL")"
    media_chain_mutate "$repo" "$TTS_SHIM" 's|^exec "\$ROOT\(.*\)$|"$ROOT\1 \|\| true|'
    rc=0
    (cd / && "$repo/$TTS_SHIM" one </dev/null) >/dev/null 2>&1 || rc=$?
    [ "$rc" -eq 0 ] || log_fail "the swallowing mutation did not apply, so this control would pass for the wrong reason"
    log_pass "the forwarding assertions fire on a missing target, on a shifted argv and on a swallowed exit status"
}

# ---------------------------------------------------------------------------
# The real chain, once, with everything absent
# ---------------------------------------------------------------------------

_real_tts_chain_execs_the_command() {
    local rc=0 out
    # REDIACC_NO_DOCKER=1 is the wrapper's own host escape hatch, documented in its header.
    # It is what makes this drivable with docker absent, and it exercises the whole file
    # down to the exec rather than a special test path.
    out="$(cd / && REDIACC_NO_DOCKER=1 "$ROOT/$TTS_SHIM" /bin/sh -c 'printf "REACHED:%s\n" "$*"' sh "a b" c 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the host path must succeed"
    assert_contains "$out" "REACHED:a b c" "the real chain must run the command it was given, with its arguments intact"
}

test_the_real_tts_chain_runs_with_docker_absent() {
    with_fake_bin "+bash +dirname" _real_tts_chain_execs_the_command
    log_pass "the old .ci/docker/run-in-tts.sh path still runs a command end to end with docker absent"
}

_real_r2_chain_reaches_the_relocated_body() {
    local rc=0 out
    # An invalid --kind is refused by the relocated script's own first validation, before
    # any credential is read and long before aws is called. The message is that script's,
    # so seeing it is proof the shim landed in the real body rather than anywhere else.
    out="$(cd / && "$ROOT/$R2_SHIM" --kind not-a-kind 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "an invalid --kind must be refused"
    assert_contains "$out" "--kind must be 'tutorials' or 'solutions', got 'not-a-kind'" \
        "the diagnosis must come from the relocated body, which is what proves the shim reached it"
}

test_the_real_r2_chain_reaches_the_relocated_body() {
    with_fake_bin "+bash +dirname +uname" _real_r2_chain_reaches_the_relocated_body
    log_pass "the old .ci/scripts/deploy/upload-media-to-r2.sh path still lands in .ci/media/tools/upload-r2.sh, with aws and the network absent"
}

# ---------------------------------------------------------------------------
# The frozen cross-repo surfaces
# ---------------------------------------------------------------------------

# upload_flags <file> -- every long flag the argument loop accepts, sorted and unique.
upload_flags() {
    grep -oE '^ +--[a-z-]+\)' "$1" | tr -d ' )' | sort -u | tr '\n' ' ' | sed 's/ $//'
}

# tts_env_names <file> -- every REDIACC_/RDC_ variable the CODE reads, sorted and unique.
# Comment lines are stripped first: the header discusses these names at length, and a
# freeze that counted prose would be pinned to the documentation rather than the interface.
tts_env_names() {
    grep -vE '^\s*#' "$1" | grep -oE '\b(REDIACC|RDC)_[A-Z0-9_]+' | sort -u | tr '\n' ' ' | sed 's/ $//'
}

test_the_cross_repo_surfaces_are_frozen() {
    assert_eq "$(upload_flags "$ROOT/$R2_REAL")" "$UPLOAD_FLAGS_FROZEN" \
        "the flag set upload-r2.sh accepts has changed; a caller in private/growth passes these by name"
    assert_eq "$(tts_env_names "$ROOT/$TTS_REAL")" "$TTS_ENV_FROZEN" \
        "the environment run-in-tts.sh reads has changed; a caller in private/generative sets these by name"
    log_pass "the seven upload flags and the five narration environment variables match their frozen sets"
}

test_the_surface_freeze_can_fail() {
    # CONTROL. A set comparison against a list somebody typed is exactly the shape that
    # goes quiet: rename the flag AND the list in one edit and it stays green, which is
    # correct, but drop the flag alone and it must not. Both extractors are driven against
    # a mutated copy so the failure is observed rather than assumed.
    local d="$1"
    mkdir -p "$d/mut"

    sed 's/^        --defer-manifest)/        --renamed-manifest)/' "$ROOT/$R2_REAL" >"$d/mut/upload-r2.sh"
    grep -q -- '--renamed-manifest' "$d/mut/upload-r2.sh" ||
        log_fail "the flag mutation did not apply, so this control would pass for the wrong reason"
    [ "$(upload_flags "$d/mut/upload-r2.sh")" != "$UPLOAD_FLAGS_FROZEN" ] ||
        log_fail "renaming --defer-manifest did not change the extracted flag set, so the freeze is measuring nothing"

    sed 's/RDC_HF_CACHE/RDC_HF_CACHE_RENAMED/g' "$ROOT/$TTS_REAL" >"$d/mut/run-in-tts.sh"
    grep -q 'RDC_HF_CACHE_RENAMED' "$d/mut/run-in-tts.sh" ||
        log_fail "the variable mutation did not apply, so this control would pass for the wrong reason"
    [ "$(tts_env_names "$d/mut/run-in-tts.sh")" != "$TTS_ENV_FROZEN" ] ||
        log_fail "renaming RDC_HF_CACHE did not change the extracted variable set, so the freeze is measuring nothing"

    # AND THE OTHER DIRECTION: the extractors must not be blind to everything. An extractor
    # that returned the empty string would satisfy neither assertion above and would fail
    # the live test, but it would fail it for the wrong reason, so say so here.
    [ -n "$(upload_flags "$ROOT/$R2_REAL")" ] || log_fail "the flag extractor found nothing at all"
    [ -n "$(tts_env_names "$ROOT/$TTS_REAL")" ] || log_fail "the variable extractor found nothing at all"
    log_pass "both surface freezes fire on a renamed flag and a renamed variable, and neither extractor is empty"
}

log_test "test-media-shims"
test_the_relocation_landed_and_the_old_context_is_gone
test_the_old_paths_are_exec_shims_and_nothing_more
with_temp_dir test_both_shims_forward_argv_cwd_stdin_and_status
with_temp_dir test_the_forwarding_assertion_can_fail
test_the_real_tts_chain_runs_with_docker_absent
test_the_real_r2_chain_reaches_the_relocated_body
test_the_cross_repo_surfaces_are_frozen
with_temp_dir test_the_surface_freeze_can_fail
echo ""
log_pass "all tests passed"
