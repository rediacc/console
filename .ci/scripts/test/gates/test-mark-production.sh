#!/bin/bash
# The production marker must refuse to lie about what is live.
#
# WHY THIS EXISTS. `production` is a moving tag and `--latest` is the badge a
# human reads as "what is in production". Both are claims about reality, so the
# script that writes them has exactly one job beyond writing: refusing when it
# cannot confirm the claim.
#
# The failure this guards is not "it wrote the wrong sha". It is the softer one
# this repo keeps paying for: a probe that could not run being read as a pass.
# `gh` returning 403, or the network dropping, must NOT mark a version as
# production -- "could not tell" is a failure, exactly as in
# assert-edge-tag-exists.sh.
#
# HERMETIC: `gh` is shimmed, so this never touches GitHub and cannot move a real
# tag. A gate that needs the network is a gate that gets skipped on somebody
# else's outage.
#
# WHAT THIS CANNOT SEE: it does not prove promote-stable.yml actually RUNS the
# script, nor that it runs AFTER endpoint verification. That wiring is
# check-ci-workflow-invariants.sh's kind of subject, not this file's.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/release/mark-production.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# make_gh <mode> -- a gh whose RELEASE VIEW behaves per mode; everything else
# succeeds quietly so only the property under test can decide the outcome.
make_gh() {
    local mode="$1" dir="$WORK/bin"
    mkdir -p "$dir"
    cat >"$dir/gh" <<FAKE
#!/bin/bash
mode="$mode"
case "\$*" in
  "release view"*)
      case "\$mode" in
        ok)      echo '{"tagName":"v1.3.1"}' ;;
        missing) echo "release not found" >&2; exit 1 ;;
        cannot)  echo "HTTP 403: Resource not accessible" >&2; exit 1 ;;
      esac
      ;;
  *"git/ref/tags/v"*) echo '{"object":{"sha":"deadbeef","type":"commit"}}' ;;
  *"git/refs"*)       echo '{}' ;;
  *"release edit"*)   echo "edited" ;;
  *)                  echo '{}' ;;
esac
FAKE
    chmod +x "$dir/gh"
    echo "$dir"
}

run_sut() { # run_sut <mode> <version>
    local bin
    bin="$(make_gh "$1")"
    PATH="$bin:$PATH" GITHUB_REPOSITORY="rediacc/console" bash "$SUT" "$2" >/dev/null 2>&1
}

test_a_published_release_is_marked() {
    log_test "a genuinely published version is marked"
    # The anti-vacuity half: if this cannot pass, every refusal below is
    # satisfied trivially by a script that always fails.
    run_sut ok v1.3.1 || log_fail "a published release was refused; the refusals below would prove nothing"
    log_pass "a published release is marked"
}

test_an_unpublished_version_is_refused() {
    log_test "a version with no GitHub Release must be REFUSED"
    if run_sut missing v9.9.9; then
        log_fail "marked a version that was never published -- 'production' would name a release that does not exist"
    fi
    log_pass "an unpublished version is refused"
}

test_could_not_tell_is_a_failure() {
    log_test "a 403 must FAIL, not pass -- a probe that did not run is not a pass"
    if run_sut cannot v1.3.1; then
        log_fail "a 403 was read as permission to mark production; 'could not tell' must never be a pass"
    fi
    log_pass "an unreadable probe fails rather than marking production"
}

test_malformed_versions_never_become_tags() {
    log_test "a malformed version must never become the production tag"
    local bad
    for bad in "" "1.3" "v1.3.1-rc1" "latest" "v1.3.1; rm -rf /"; do
        if run_sut ok "$bad"; then
            log_fail "accepted '$bad' as a version; the production tag is the thing humans trust"
        fi
    done
    log_pass "5 malformed versions rejected"
}

test_control_the_guard_can_be_removed() {
    log_test "CONTROL: delete the release check and the refusals MUST stop firing"
    # By CONSTRUCTION: copy the script and cut the block that verifies the
    # release exists, then require the unpublished case to flip to success. If
    # it does not flip, the assertions above are not reaching the guard.
    local mut="$WORK/mut.sh"
    python3 - "$SUT" "$mut" <<'PY'
import io, sys
src, dst = sys.argv[1], sys.argv[2]
s = io.open(src, encoding="utf-8").read()
start = s.index('if ! out="$(gh release view')
end = s.index('log_info "mark-production: $VERSION is a published release"')
io.open(dst, "w", encoding="utf-8").write(s[:start] + s[end:])
PY
    local bin rc
    bin="$(make_gh missing)"
    PATH="$bin:$PATH" GITHUB_REPOSITORY="rediacc/console" bash "$mut" v9.9.9 >/dev/null 2>&1 && rc=0 || rc=$?
    [[ "$rc" -eq 0 ]] ||
        log_fail "CONTROL DID NOT FIRE: the unpublished case still failed (rc=$rc) with the guard removed, so it is not what refuses"
    log_pass "control fires: without the release check, an unpublished version gets marked"
}

test_a_published_release_is_marked
test_an_unpublished_version_is_refused
test_could_not_tell_is_a_failure
test_malformed_versions_never_become_tags
test_control_the_guard_can_be_removed

echo
log_pass "production marker gate: 5/5"
echo "  Blind spot: does not prove promote-stable.yml runs this script, nor that"
echo "  it runs AFTER endpoint verification; the gh shim also means the API field"
echo "  names are not proven current (a rename surfaces as a refusal, which is safe)."
