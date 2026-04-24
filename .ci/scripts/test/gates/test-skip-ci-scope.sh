#!/bin/bash
# Integration test for .ci/scripts/quality/check-skip-ci-scope.sh.
#
# Creates a series of temp git repositories with known commit shapes and
# verifies the validator accepts allowlisted scopes and rejects the rest.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR="$REPO_ROOT/.ci/scripts/quality/check-skip-ci-scope.sh"

# Helper: create a temp git repo with a single commit that touches given
# paths (absolute paths written inside the repo dir), commit message as given.
# Returns path to the repo dir (caller cleans up).
init_repo_with_commit() {
    local repo_dir="$1" msg="$2"
    shift 2
    git init -q -b main "$repo_dir"
    git -C "$repo_dir" config user.email test@example.com
    git -C "$repo_dir" config user.name test
    # Seed an initial commit so HEAD^ resolves.
    echo "seed" >"$repo_dir/seed.txt"
    git -C "$repo_dir" add seed.txt
    git -C "$repo_dir" -c commit.gpgsign=false commit -q -m "seed"
    # Apply requested file ops.
    for op in "$@"; do
        # op format: <create|modify|delete>:<relpath>:<content>
        local verb path content
        verb="${op%%:*}"
        local rest="${op#*:}"
        path="${rest%%:*}"
        content="${rest#*:}"
        case "$verb" in
            create | modify)
                mkdir -p "$(dirname "$repo_dir/$path")"
                printf '%s' "$content" >"$repo_dir/$path"
                git -C "$repo_dir" add "$path"
                ;;
            delete)
                git -C "$repo_dir" rm -q "$path"
                ;;
            *) log_fail "unknown op verb: $verb" ;;
        esac
    done
    git -C "$repo_dir" -c commit.gpgsign=false commit -q -m "$msg"
}

# Add a fake submodule at the given path (mode 160000 entry without actually
# cloning a submodule — git accepts update-index --add --cacheinfo for this).
add_fake_submodule_pointer() {
    local repo_dir="$1" path="$2" sha="$3"
    # 40-char hex SHA required
    git -C "$repo_dir" update-index --add --cacheinfo "160000,$sha,$path"
}

run_validator() {
    local repo_dir="$1"
    shift
    (cd "$repo_dir" && "$VALIDATOR" "$@")
}

test_no_skip_ci_marker_is_skipped() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" "chore: normal commit" "create:foo.txt:hello"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "non-skip-ci commit must exit 0"
    assert_contains "$out" "does not contain a skip-ci marker" "explains why it skipped"
    log_pass "non-skip-ci commit is skipped cleanly"
}

test_submodule_pointer_only_passes() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    git init -q -b main "$TEMP"
    git -C "$TEMP" config user.email test@example.com
    git -C "$TEMP" config user.name test
    echo seed >"$TEMP/seed.txt"
    git -C "$TEMP" add seed.txt
    add_fake_submodule_pointer "$TEMP" "private/homebrew-tap" "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "seed"
    # Now bump the pointer
    add_fake_submodule_pointer "$TEMP" "private/homebrew-tap" "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "chore(release): update homebrew-tap [skip ci]"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "submodule-pointer-only skip-ci commit must exit 0"
    assert_contains "$out" "scope OK" "success message printed"
    log_pass "submodule-pointer-only skip-ci commit passes"
}

test_foreign_file_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" \
        "chore: sneaky [skip ci]" \
        "create:src/app.ts:console.log('hi')"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "non-allowlisted file must fail"
    assert_contains "$out" "outside the allowlist" "error names the problem"
    assert_contains "$out" "src/app.ts" "offending path is named"
    log_pass "non-allowlisted file in skip-ci commit is rejected"
}

test_csproj_bump_passes() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" \
        "chore: csproj bump [skip ci]" \
        "create:src/App.csproj:<Project><Version>1.0.1</Version></Project>"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "*.csproj-only skip-ci commit must exit 0"
    log_pass "*.csproj-only skip-ci commit passes"
}

test_changelog_passes() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" \
        "docs: changelog [skip ci]" \
        "create:CHANGELOG.md:# 1.0.1"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "CHANGELOG-only skip-ci commit must exit 0"
    log_pass "CHANGELOG-only skip-ci commit passes"
}

test_package_json_version_only_passes() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    git init -q -b main "$TEMP"
    git -C "$TEMP" config user.email test@example.com
    git -C "$TEMP" config user.name test
    # Seed with a package.json already committed
    printf '{\n  "name": "x",\n  "version": "1.0.0"\n}\n' >"$TEMP/package.json"
    git -C "$TEMP" add package.json
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "seed"
    # Bump only the version field
    printf '{\n  "name": "x",\n  "version": "1.0.1"\n}\n' >"$TEMP/package.json"
    git -C "$TEMP" add package.json
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "chore: bump [skip ci]"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "package.json version-only skip-ci commit must exit 0"
    log_pass "package.json version-only skip-ci commit passes"
}

test_package_json_non_version_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    git init -q -b main "$TEMP"
    git -C "$TEMP" config user.email test@example.com
    git -C "$TEMP" config user.name test
    printf '{\n  "name": "x",\n  "version": "1.0.0"\n}\n' >"$TEMP/package.json"
    git -C "$TEMP" add package.json
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "seed"
    # Change name, not version
    printf '{\n  "name": "y",\n  "version": "1.0.0"\n}\n' >"$TEMP/package.json"
    git -C "$TEMP" add package.json
    git -C "$TEMP" -c commit.gpgsign=false commit -q -m "chore: name change [skip ci]"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "package.json non-version skip-ci commit must fail"
    assert_contains "$out" "non-'version' field changed" "error names the problem"
    log_pass "package.json non-version-only skip-ci commit is rejected"
}

test_multiple_allowlisted_files_pass() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" \
        "release: multi [skip ci]" \
        "create:CHANGELOG.md:# new" \
        "create:src/App.csproj:<Project><Version>2.0.0</Version></Project>"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "multi-allowlisted-file skip-ci commit must exit 0"
    log_pass "multiple allowlisted files pass together"
}

test_ci_skip_alias_also_gated() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    init_repo_with_commit "$TEMP" \
        "sneaky [ci skip]" \
        "create:src/app.ts:1"
    local out rc=0
    out=$(run_validator "$TEMP" HEAD 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "[ci skip] marker must also trigger the gate"
    log_pass "[ci skip] alias is also caught"
}

log_test "test-skip-ci-scope"
test_no_skip_ci_marker_is_skipped
test_submodule_pointer_only_passes
test_foreign_file_fails
test_csproj_bump_passes
test_changelog_passes
test_package_json_version_only_passes
test_package_json_non_version_fails
test_multiple_allowlisted_files_pass
test_ci_skip_alias_also_gated
echo ""
log_pass "all tests passed"
