#!/usr/bin/env bash
# Gate: promote-stable must refuse to promote a version that does not fully
# exist -- and must refuse just as loudly when it CANNOT TELL whether it exists.
#
# WHY THIS EXISTS. `cli/edge/manifest.json` advertised 1.3.1 with no v1.3.1 tag,
# no GitHub Release and no cli/v1.3.1/.released. promote-stable.yml would have
# copied those bytes to stable and retagged Docker :stable FIRST (:70-100) and
# only then failed on `ref: v1.3.1` while checking out for the three regional
# deploys (:133, :159) -- a half-applied production release. This drives the
# precondition that turns that ordering into a loud no-op.
#
# WHAT IT ASSERTS, with a fake `gh` and a fake `aws` (no network, no promotion):
#   1. no tag ref                 -> exit 1
#   2. tag, no GitHub Release     -> exit 1
#   3. tag + release, no sentinel -> exit 1
#   4. all three present          -> exit 0   (proves it is not always-red)
#   5. gh answers 403             -> exit 1, NOT 0. A 404 confirms absence; a
#                                    403/5xx/network error means the check did
#                                    not run, and a check that did not run must
#                                    not read as a pass.
#   6. aws cannot authenticate    -> exit 1, same reason on the R2 probe.
#   7. ANTI-VACUITY: the passing case must have actually CALLED all three
#      probes. A script that returns 0 without probing would satisfy 4 alone.
#
# CONTROL-FIRST. A mutant is assembled BY CONSTRUCTION (head + a literal
# replacement arm written here + tail, split on the script's anchor comments) in
# which "could not tell" returns 0 instead of failing. Case 5 must go GREEN
# against it; if it does not, this gate declares itself broken. The mutant is
# also proven LIVE (case 4 still 0, case 1 still 1) so a mutant that merely
# crashes cannot masquerade as a firing control.
#
# STATED BLIND SPOT: this cannot see whether promote-stable.yml actually RUNS
# the script, or whether it runs BEFORE the first promotion write. A precondition
# wired after the promotion is worth nothing. That step-order assertion belongs
# to the workflow-invariant gate (plan T2), not here.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
TARGET="$REPO_ROOT/.ci/scripts/release/assert-edge-tag-exists.sh"

log_test "promote-stable refuses a version that does not exist (or cannot be proven to)"

[[ -f "$TARGET" ]] || {
    log_fail "assert-edge-tag-exists.sh not found at $TARGET"
    exit 1
}

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
FAKEBIN="$TEMP/bin"
mkdir -p "$FAKEBIN"
GHLOG="$TEMP/gh.log"
AWSLOG="$TEMP/aws.log"

# Fake `gh`. TAG_STATE / REL_STATE drive the two probes independently:
#   present  -> exit 0
#   absent   -> the real 404 wording, exit 1
#   forbid   -> a 403, i.e. "the check did not run"
cat >"$FAKEBIN/gh" <<FAKE
#!/bin/bash
printf '%s\n' "\$*" >>"$GHLOG"
state=""
case "\$1 \$2" in
    "api repos"*) state="\${TAG_STATE:-present}" ;;
    "release view") state="\${REL_STATE:-present}" ;;
    *)
        case "\$*" in
            api*) state="\${TAG_STATE:-present}" ;;
            *) state="\${REL_STATE:-present}" ;;
        esac
        ;;
esac
case "\$state" in
    present) echo '{"ok":true}'; exit 0 ;;
    absent)  echo 'gh: Not Found (HTTP 404)' >&2; exit 1 ;;
    forbid)  echo 'gh: Resource not accessible by integration (HTTP 403)' >&2; exit 1 ;;
esac
echo "fake gh: unknown state '\$state'" >&2
exit 9
FAKE
chmod +x "$FAKEBIN/gh"

# Fake `aws`. SENTINEL_STATE drives head-object.
cat >"$FAKEBIN/aws" <<FAKE
#!/bin/bash
printf '%s\n' "\$*" >>"$AWSLOG"
case "\${SENTINEL_STATE:-present}" in
    present) echo '{"ContentLength":42}'; exit 0 ;;
    absent)  echo 'An error occurred (404) when calling the HeadObject operation: Not Found' >&2; exit 254 ;;
    forbid)  echo 'Unable to locate credentials. You can configure credentials by running "aws configure".' >&2; exit 255 ;;
esac
echo "fake aws: unknown state" >&2
exit 9
FAKE
chmod +x "$FAKEBIN/aws"

RC=0
OUT=""
run_assert() {
    local script="$1" tag="$2" rel="$3" sent="$4"
    : >"$GHLOG"
    : >"$AWSLOG"
    RC=0
    OUT="$(
        env PATH="$FAKEBIN:$PATH" \
            TAG_STATE="$tag" REL_STATE="$rel" SENTINEL_STATE="$sent" \
            GITHUB_REPOSITORY=rediacc/console \
            R2_ENDPOINT=https://example.invalid RELEASES_BUCKET=rediacc-releases \
            bash "$script" --version 1.3.0 </dev/null 2>&1
    )" || RC=$?
}

# --- cases: 0 when the property HOLDS, 1 when violated ---------------------
case_no_tag() {
    run_assert "$1" absent present present
    ((RC == 1)) || {
        echo "    exit $RC (expected 1) for a version with no tag ref"
        return 1
    }
    grep -q 'MISSING' <<<"$OUT" || {
        echo "    failure did not name the missing thing"
        return 1
    }
    return 0
}

case_no_release() {
    run_assert "$1" present absent present
    ((RC == 1)) || {
        echo "    exit $RC (expected 1) for a tag with no GitHub Release"
        return 1
    }
    return 0
}

case_no_sentinel() {
    run_assert "$1" present present absent
    ((RC == 1)) || {
        echo "    exit $RC (expected 1) for a tag+release with no .released sentinel"
        return 1
    }
    return 0
}

case_all_present() {
    run_assert "$1" present present present
    ((RC == 0)) || {
        echo "    exit $RC (expected 0) with all three present:"
        sed 's/^/      /' <<<"$OUT"
        return 1
    }
    # ANTI-VACUITY: a script that returned 0 without probing would pass the line
    # above. Require both probe surfaces to have actually been called.
    local gh_calls aws_calls
    gh_calls="$(wc -l <"$GHLOG")"
    aws_calls="$(wc -l <"$AWSLOG")"
    if ((gh_calls < 2 || aws_calls < 1)); then
        echo "    ANTI-VACUITY: the passing run made $gh_calls gh call(s) and $aws_calls aws call(s); it did not probe all three"
        return 1
    fi
    return 0
}

case_gh_cannot_tell() {
    run_assert "$1" forbid present present
    ((RC == 1)) || {
        echo "    exit $RC (expected 1) when gh answered 403 -- 'could not tell' was read as a pass"
        return 1
    }
    grep -q 'COULD NOT TELL' <<<"$OUT" || {
        echo "    exit 1, but the message does not distinguish 'could not tell' from 'missing'"
        return 1
    }
    return 0
}

case_aws_cannot_tell() {
    run_assert "$1" present present forbid
    ((RC == 1)) || {
        echo "    exit $RC (expected 1) when the R2 probe could not authenticate"
        return 1
    }
    grep -q 'COULD NOT TELL' <<<"$OUT" || {
        echo "    exit 1, but the message does not distinguish 'could not tell' from 'missing'"
        return 1
    }
    return 0
}

FAILURES=0
must_hold() {
    local case_fn="$1" script="$2" label="$3" detail rc=0
    detail="$("$case_fn" "$script")" || rc=$?
    if ((rc == 0)); then
        log_pass "$label"
        return 0
    fi
    log_error "$label"
    [[ -n "$detail" ]] && echo "$detail"
    FAILURES=$((FAILURES + 1))
}

echo "-- the real script"
must_hold case_no_tag "$TARGET" "1. no git tag ref -> exit 1"
must_hold case_no_release "$TARGET" "2. tag but no GitHub Release -> exit 1"
must_hold case_no_sentinel "$TARGET" "3. tag + release but no cli/v1.3.0/.released -> exit 1"
must_hold case_all_present "$TARGET" "4. all three present -> exit 0, having probed all three"
must_hold case_gh_cannot_tell "$TARGET" "5. gh 403 -> exit 1, NOT 0 (could not tell is a failure)"
must_hold case_aws_cannot_tell "$TARGET" "6. R2 credentials unusable -> exit 1, distinguishably"

# --- control ---------------------------------------------------------------
# BY CONSTRUCTION: head + a literal arm written here + tail, split on the
# script's anchors. No pattern substitution of a live line, so a reworded arm
# cannot silently yield an identical "mutant".
# The mutant lives in a sandbox that mirrors the real layout, because the script
# resolves its library with "$SCRIPT_DIR/../lib/common.sh": a mutant dropped in a
# bare temp dir dies at its source line, which the liveness probe below would
# (correctly) refuse to accept as a firing control.
mkdir -p "$TEMP/sb/.ci/scripts/release" "$TEMP/sb/.ci/scripts/lib"
for f in "$REPO_ROOT"/.ci/scripts/lib/*; do ln -s "$f" "$TEMP/sb/.ci/scripts/lib/$(basename "$f")"; done
MUTANT="$TEMP/sb/.ci/scripts/release/mutant-403-passes.sh"
b="$(grep -n 'COULD_NOT_TELL_ARM_BEGIN' "$TARGET" | head -1 | cut -d: -f1)"
e="$(grep -n 'COULD_NOT_TELL_ARM_END' "$TARGET" | head -1 | cut -d: -f1)"
if [[ -z "$b" || -z "$e" ]] || ((e <= b)); then
    log_fail "CONTROL COULD NOT PLANT: could-not-tell anchors not found in $TARGET (begin='$b' end='$e')"
    exit 1
fi
{
    head -n "$((b - 1))" "$TARGET"
    cat <<'ARM'
        unknown:*)
            log_warn "MUTANT: treating an unprovable probe as a pass -- ${what}"
            return 0
            ;;
ARM
    tail -n "+$((e + 1))" "$TARGET"
} >"$MUTANT"
chmod +x "$MUTANT"
grep -q 'COULD_NOT_TELL_ARM_BEGIN' "$MUTANT" && {
    log_fail "CONTROL COULD NOT PLANT: anchor survived in the mutant"
    exit 1
}
cmp -s "$TARGET" "$MUTANT" && {
    log_fail "CONTROL COULD NOT PLANT: mutant is identical to the source"
    exit 1
}
# LIVENESS: a mutant that merely crashes exits non-zero for reasons unrelated to
# the plant, and case 5 would "still fail" for the wrong reason. Prove the mutant
# both runs (case 4 -> 0) and still detects genuine absence (case 1 -> 1).
if ! case_all_present "$MUTANT" >/dev/null 2>&1 || ! case_no_tag "$MUTANT" >/dev/null 2>&1; then
    log_fail "MUTANT IS NOT LIVE: the planted copy no longer runs its unmutated cases"
    exit 1
fi
if case_gh_cannot_tell "$MUTANT" >/dev/null 2>&1; then
    log_error "CONTROL DID NOT FIRE: the mutant treats a 403 as a pass and case 5 still went green -- assertion 5 proves nothing"
    FAILURES=$((FAILURES + 1))
else
    log_pass "control fires: 403-arm-returns-0 mutant is caught by case 5 (and is proven live)"
fi

if ((FAILURES > 0)); then
    log_fail "$FAILURES assertion(s) failed"
    exit 1
fi

log_pass "6 properties + 1 live control; the passing run probed gh twice and aws once"
echo "BLIND SPOT: this cannot see whether promote-stable.yml runs this script, nor whether"
echo "            it runs BEFORE the first promotion write. That step-order assertion is the"
echo "            workflow-invariant gate's subject (plan T2), not this file's."
