#!/bin/bash
# Both-ways test for the tag-fetch block in .ci/scripts/ci/initialize.sh.
#
# WHAT IT IS FOR. Tag-based versioning means the version IS the tag list. CI
# checks out shallow, so initialize.sh fetches tags with the app token right
# before it computes next_version.
#
# WHAT WAS BROKEN. The fetch ended in `2>/dev/null || true`. A failed or
# rate-limited fetch left whatever tags the checkout happened to bring,
# resolve-version.sh cannot tell a stale tag list from a current one, and
# next_version came out three lines later looking perfectly plausible and being
# wrong. That is the WRONG-VALUE case, and it is the one assert-artifact-version.sh
# structurally cannot catch: CD's label and CI's label both descend from this
# one command, so they agree with each other and disagree with reality.
#
# The block is EXTRACTED FROM THE REAL SCRIPT by its own anchors and run in a
# throwaway git repo -- initialize.sh as a whole needs submodules, secrets and a
# GitHub token, none of which this behaviour depends on. If the block is
# rewritten the anchors stop matching and test_block_is_extractable fails,
# rather than the gate silently testing nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/ci/initialize.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BLOCK_START='TAG_FETCH_ERR="$(mktemp)"'
BLOCK_END='log_info "Latest tag: $LATEST_TAG"'

extract_block() {
    awk -v s="$BLOCK_START" -v e="$BLOCK_END" '
        index($0, s) { p = 1 }
        p { print }
        p && index($0, e) { exit }
    ' "$GATE"
}

# make_runner <path> [<sed-mutation>] -- a standalone script wrapping the real
# block with logging stubs and a no-op sleep (the retry backoff would otherwise
# cost 15 seconds per failing case).
make_runner() {
    local path="$1" mutation="${2:-}"
    {
        echo '#!/bin/bash'
        echo 'set -euo pipefail'
        echo 'log_info() { echo "INFO: $*"; }'
        echo 'log_warn() { echo "WARN: $*"; }'
        echo 'log_error() { echo "ERROR: $*" >&2; }'
        echo 'sleep() { :; }'
        if [[ -n "$mutation" ]]; then
            extract_block | sed "$mutation"
        else
            extract_block
        fi
        echo 'echo "REACHED_END latest=$LATEST_TAG"'
    } >"$path"
    chmod +x "$path"
}

# run_block <runner> <workdir> <fetch-url> [<extra-path>] -- exit code on
# stdout, combined output in $WORK/run.log
run_block() {
    local runner="$1" dir="$2" url="$3" extra_path="${4:-}"
    local st=0
    (
        cd "$dir"
        if [[ -n "$extra_path" ]]; then
            export PATH="$extra_path:$PATH"
        fi
        export FETCH_URL="$url" GITHUB_PAT="s3cr3t-app-token"
        "$runner"
    ) >"$WORK/run.log" 2>&1 || st=$?
    echo "$st"
}

seed_source_repo() {
    local dir="$1" tag="${2:-}"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" -c user.email=t@t -c user.name=t commit -q --allow-empty -m seed
    if [[ -n "$tag" ]]; then
        git -C "$dir" tag "$tag"
    fi
}

test_block_is_extractable() {
    log_test "the tag-fetch block is still where the anchors say"
    local block
    block="$(extract_block)"
    assert_contains "$block" "git fetch --tags --force" "extraction must capture the fetch"
    assert_contains "$block" "TAG_FETCH_OK" "extraction must capture the success accounting"
    assert_contains "$block" "LATEST_TAG" "extraction must reach the tag read"
    log_pass "block extracted from the real script"
}

test_successful_fetch_yields_the_tag() {
    log_test "a working fetch produces the latest tag"
    seed_source_repo "$WORK/src-tagged" "v1.2.17"
    mkdir -p "$WORK/work-ok" && git -C "$WORK/work-ok" init -q
    make_runner "$WORK/runner.sh"
    assert_eq "$(run_block "$WORK/runner.sh" "$WORK/work-ok" "$WORK/src-tagged")" "0" "a healthy fetch must succeed"
    assert_contains "$(cat "$WORK/run.log")" "REACHED_END latest=v1.2.17" "the fetched tag must be the one used"
    log_pass "fetch succeeds and v1.2.17 is read"
}

# THE DEFECT: the fetch fails. Before the fix this was swallowed and the script
# went on to compute a version from a tag list it could not refresh.
test_failed_fetch_stops_the_run() {
    log_test "a failing fetch stops the run instead of guessing"
    mkdir -p "$WORK/bin-badgit"
    local real_git
    real_git="$(command -v git)"
    # Fails every fetch, and leaks the credentialed URL into stderr the way a
    # non-redacting git would, so the redaction is exercised for real. Every
    # other subcommand goes to the REAL git by absolute path -- resolving it
    # through PATH would find this shim again and recurse forever.
    cat >"$WORK/bin-badgit/git" <<FAKEGIT
#!/bin/bash
if [[ "\${1:-}" == "fetch" ]]; then
    echo "fatal: unable to access 'https://x-access-token:s3cr3t-app-token@github.com/rediacc/console.git/'" >&2
    exit 128
fi
exec "$real_git" "\$@"
FAKEGIT
    chmod +x "$WORK/bin-badgit/git"

    mkdir -p "$WORK/work-bad" && git -C "$WORK/work-bad" init -q
    make_runner "$WORK/runner.sh"
    local st
    st="$(run_block "$WORK/runner.sh" "$WORK/work-bad" "https://x-access-token:s3cr3t-app-token@github.com/rediacc/console.git" "$WORK/bin-badgit")"
    local out
    out="$(cat "$WORK/run.log")"
    assert_eq "$st" "1" "a failing fetch must not produce a version"
    assert_contains "$out" "Could not fetch tags after 3 attempts" "the failure must be explicit"
    assert_not_contains "$out" "REACHED_END" "the run must not continue past the failed fetch"
    log_pass "a failing fetch fails the run"
}

test_failed_fetch_redacts_the_token() {
    log_test "the failure output does not leak the app token"
    local out
    out="$(cat "$WORK/run.log")"
    assert_contains "$out" "***" "git's stderr must be redacted, not suppressed"
    assert_not_contains "$out" "s3cr3t-app-token" "the app token must never reach the log"
    log_pass "token redacted, diagnostics preserved"
}

test_no_tags_after_a_good_fetch_stops_the_run() {
    log_test "a successful fetch that yields no tags stops the run"
    seed_source_repo "$WORK/src-untagged"
    mkdir -p "$WORK/work-untagged" && git -C "$WORK/work-untagged" init -q
    make_runner "$WORK/runner.sh"
    local st
    st="$(run_block "$WORK/runner.sh" "$WORK/work-untagged" "$WORK/src-untagged")"
    assert_eq "$st" "1" "no tags means no version, so the run must stop"
    assert_contains "$(cat "$WORK/run.log")" "no v* tag exists" "the failure must say why"
    log_pass "an untagged repository fails instead of inventing a version"
}

# THE CONTROL. Plant the pre-fix behaviour -- fetch failure swallowed, tag list
# used regardless -- and prove the same failing fetch sails through. Without
# this, test_failed_fetch_stops_the_run might be red for some unrelated reason.
test_planted_swallowed_fetch_continues() {
    log_test "control: with the failure swallowed, the run continues on a stale tag list"
    seed_source_repo "$WORK/src-stale" "v0.0.9"
    mkdir -p "$WORK/work-stale" && git -C "$WORK/work-stale" init -q
    # Give the working tree an old tag, then break the fetch: exactly the shape
    # that shipped a wrong version.
    git -C "$WORK/work-stale" -c user.email=t@t -c user.name=t commit -q --allow-empty -m old
    git -C "$WORK/work-stale" tag v0.0.9

    make_runner "$WORK/runner-old.sh" \
        's|if \[\[ "$TAG_FETCH_OK" != "true" \]\]; then|if false; then|'

    local st
    st="$(run_block "$WORK/runner-old.sh" "$WORK/work-stale" "$WORK/does-not-exist.git" "$WORK/bin-badgit")"
    assert_eq "$st" "0" "planted swallowed fetch must continue (else the control proves nothing)"
    assert_contains "$(cat "$WORK/run.log")" "REACHED_END latest=v0.0.9" "planted version comes from the stale local tag"
    log_pass "the run goes red only because the fetch failure is acted on"
}

test_block_is_extractable
test_successful_fetch_yields_the_tag
test_failed_fetch_stops_the_run
test_failed_fetch_redacts_the_token
test_no_tags_after_a_good_fetch_stops_the_run
test_planted_swallowed_fetch_continues
