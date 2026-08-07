#!/bin/bash
# Both-ways test for .ci/scripts/version/inject-env.sh --strict.
#
# WHAT THE GUARD IS FOR. --strict is the one guard in the repo against a build
# stamping a placeholder or bogus version into an artifact that CD will later
# publish under a real tag.
#
# WHAT WAS BROKEN. It had ZERO callers -- referenced only by a comment in
# .ci/config/constants.sh and by its own header -- while every build boundary
# spelled `|| '0.0.0-dev'` or `${CLI_VERSION:-0.0.0-dev}` inline instead. A
# guard nothing calls cannot fire. On top of that it compared the resolved
# version against the literal string "0.0.0-dev" and nothing else, so an EMPTY
# version, or a resolver that exited 0 printing nothing, sailed straight
# through the strictest setting the script has.
#
# The empty-resolver case gets a fixture: inject-env.sh finds resolve-version.sh
# next to itself, so the only way to plant "resolver succeeds but prints
# nothing" is to run a copy with a planted sibling.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/version/inject-env.sh"

# run_inject <args...> -> prints "<exit>|<stdout>". Stderr lands in $INJECT_ERR,
# a FILE rather than a variable: run_inject is always called inside a command
# substitution, and a variable set there dies with the subshell.
INJECT_ERR="$(mktemp)"
trap 'rm -f "$INJECT_ERR"' EXIT
run_inject() {
    local out st=0
    out="$("$GATE" "$@" 2>"$INJECT_ERR")" || st=$?
    echo "${st}|${out}"
}
last_stderr() { cat "$INJECT_ERR"; }

test_accepts_a_real_version() {
    log_test "--strict accepts a real version"
    local r
    r="$(run_inject --version 1.2.17 --strict --print)"
    assert_eq "$r" "0|1.2.17" "a real version must pass --strict and print unchanged"
    log_pass "--strict accepts 1.2.17"
}

test_rejects_the_placeholder() {
    log_test "--strict rejects the 0.0.0-dev placeholder"
    local r
    r="$(run_inject --version 0.0.0-dev --strict --print)"
    assert_eq "${r%%|*}" "1" "0.0.0-dev must fail under --strict"
    assert_contains "$(last_stderr)" "0.0.0-dev" "the failure must name the placeholder"
    log_pass "--strict rejects 0.0.0-dev"
}

# THE CONTROL for the hole the original check had: it compared only against the
# literal "0.0.0-dev", so an empty version was "not 0.0.0-dev" and passed.
test_rejects_an_empty_version() {
    log_test "--version with an empty value is refused"
    local r
    r="$(run_inject --version "" --strict --print)"
    assert_eq "${r%%|*}" "1" "an empty --version must fail under --strict"
    assert_contains "$(last_stderr)" "empty" "the failure must say the version was empty"

    # And it is refused without --strict too: an explicitly-supplied empty
    # version used to fall through to the resolver and silently pick up the
    # CURRENT tag, i.e. the version that is already published.
    r="$(run_inject --version "" --print)"
    assert_eq "${r%%|*}" "1" "an empty --version must fail even without --strict"
    log_pass "empty --version is refused, strict or not"
}

test_rejects_a_malformed_version() {
    log_test "--strict rejects a version that is not dotted-numeric"
    local r v
    for v in "1.2.x" "latest" "none" "<html>404</html>"; do
        r="$(run_inject --version "$v" --strict --print)"
        assert_eq "${r%%|*}" "1" "'$v' must fail under --strict"
    done
    # Without --strict the same values still resolve: dev/local builds are not
    # in the business of policing versions.
    r="$(run_inject --version "latest" --print)"
    assert_eq "$r" "0|latest" "non-strict resolution must stay permissive"
    log_pass "--strict rejects malformed versions, non-strict does not"
}

test_reads_the_VERSION_env() {
    log_test "\$VERSION is honoured and still policed"
    local err st=0 out
    err="$(mktemp)"
    out="$(VERSION=1.4.0 "$GATE" --strict --print 2>"$err")" || st=$?
    rm -f "$err"
    assert_eq "${st}|${out}" "0|1.4.0" "VERSION env must be used when no --version is given"

    st=0
    err="$(mktemp)"
    VERSION=0.0.0-dev "$GATE" --strict --print >/dev/null 2>"$err" || st=$?
    rm -f "$err"
    assert_eq "$st" "1" "VERSION=0.0.0-dev must fail under --strict"
    log_pass "\$VERSION path is policed the same way"
}

# THE CONTROL for the second half of the same hole: a resolver that exits 0
# printing nothing produced an EMPTY resolved version, which --strict accepted.
# Planted in a fixture because inject-env.sh resolves its sibling by path.
test_empty_resolver_output_is_not_a_version() {
    log_test "a resolver that prints nothing does not yield a version"
    local fixture
    fixture="$(mktemp -d)"
    mkdir -p "$fixture/version"
    cp "$GATE" "$fixture/version/inject-env.sh"
    cat >"$fixture/version/resolve-version.sh" <<'STUB'
#!/bin/bash
# Exits 0, prints nothing: the shape --strict used to accept as a version.
exit 0
STUB
    chmod +x "$fixture/version/resolve-version.sh"

    local st=0
    (cd "$fixture" && ./version/inject-env.sh --strict --print) >/dev/null 2>&1 || st=$?
    assert_eq "$st" "1" "an empty resolver result must not pass --strict"

    # Non-strict must degrade to the documented dev placeholder, not to "".
    local out
    out="$(cd "$fixture" && ./version/inject-env.sh --print 2>/dev/null)"
    assert_eq "$out" "0.0.0-dev" "non-strict must fall back to the placeholder, not an empty string"

    rm -rf "$fixture"
    log_pass "empty resolver output is refused, and non-strict degrades to the placeholder"
}

# THE OTHER HALF OF FINDING 8, and the half that made the guard worthless: it
# had no callers. A --strict that nothing invokes is indistinguishable from no
# guard at all, which is what shipped for the whole life of the flag.
strict_callers() {
    local root="$1" n=0 f
    for f in \
        ".github/workflows/ci-build-cli.yml" \
        ".github/workflows/ci-build-docker.yml" \
        ".ci/scripts/build/build-cli-executables.sh" \
        ".ci/scripts/build/build-cli-musl.sh"; do
        if grep -q -- '--strict' "$root/$f" 2>/dev/null; then
            n=$((n + 1))
        fi
    done
    echo "$n"
}

test_guard_is_reachable_from_the_release_path() {
    log_test "every release-path build boundary invokes --strict"
    assert_eq "$(strict_callers "$REPO_ROOT")" "4" "all four release-path build boundaries must call inject-env.sh --strict"

    # PROVE THIS COUNT CAN FALL: strip the invocations in a copy and watch it
    # drop to zero -- the exact state the repo was in before this wave.
    local fixture f
    fixture="$(mktemp -d)"
    for f in \
        ".github/workflows/ci-build-cli.yml" \
        ".github/workflows/ci-build-docker.yml" \
        ".ci/scripts/build/build-cli-executables.sh" \
        ".ci/scripts/build/build-cli-musl.sh"; do
        mkdir -p "$fixture/$(dirname "$f")"
        grep -v -- '--strict' "$REPO_ROOT/$f" >"$fixture/$f" || true
    done
    local planted
    planted="$(strict_callers "$fixture")"
    rm -rf "$fixture"
    assert_eq "$planted" "0" "planted no-caller tree must count zero (else this control proves nothing)"
    log_pass "the guard is reachable, and the check notices when it is not"
}

test_accepts_a_real_version
test_rejects_the_placeholder
test_rejects_an_empty_version
test_rejects_a_malformed_version
test_reads_the_VERSION_env
test_empty_resolver_output_is_not_a_version
test_guard_is_reachable_from_the_release_path
