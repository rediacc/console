#!/usr/bin/env bash
# Gate: on a `bump-none` merge the R2 uploaders must write NOTHING on a release
# channel -- and must keep writing everything the moment the signal is absent.
#
# WHY THIS EXISTS. `cli/edge/manifest.json` advertised 1.3.1 for days with no
# v1.3.1 tag, no GitHub Release and no cli/v1.3.1/.released. Two `bump-none`
# merges (PR #573, #574) had run the upload loop anyway, so the same "immutable"
# cli/v1.3.1/ URL served two different builds and every `rdc` on edge
# auto-updated to a version whose release notes 404. `bump-none` was honoured
# only in finalize-release-sentinel, structurally too late to reach the uploader.
#
# WHAT IT ASSERTS, by driving the REAL scripts against a fake `aws` recorder:
#   1. FIRES        --skip-release/SKIP_RELEASE on `edge` writes ZERO aws calls.
#   2. SILENT-WHEN-CLEAN  the same run WITHOUT the signal writes the channel
#                   pointer and the versioned prefix. This is the more important
#                   half: a silently withheld release is worse than the bug.
#   3. NARROW       a pr-N channel is unaffected even with the signal set.
#   4. ANTI-VACUITY zero fixture binaries, or an empty recorder log in (2),
#                   FAILS outright. The observed call count is printed.
#
# CONTROL-FIRST. Three mutants are assembled BY CONSTRUCTION (head + a literal
# replacement block written here + tail, split on the guard's anchor comments),
# never by pattern-substituting a live source line, and each assembly PROVES the
# plant landed (anchor gone AND mutant differs from source) before it is trusted.
#
# STATED BLIND SPOT: this test cannot see whether any workflow actually PASSES
# --skip-release / SKIP_RELEASE to these scripts. A flag nobody passes would
# still make every case here green. That wiring is T2's subject
# (.ci/scripts/security/check-ci-workflow-invariants.sh).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
REAL_UPLOAD="$REPO_ROOT/.ci/scripts/deploy/upload-to-r2.sh"
REAL_REPOS="$REPO_ROOT/.ci/scripts/deploy/upload-repos-to-r2.sh"
VERSION="9.9.9"

log_test "bump-none withholds the R2 channel pointer (and only then)"

for f in "$REAL_UPLOAD" "$REAL_REPOS"; do
    [[ -f "$f" ]] || {
        log_fail "target not found: $f"
        exit 1
    }
done

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
ROOT="$TEMP/root"
FAKEBIN="$TEMP/bin"
AWSLOG="$TEMP/aws.log"
PURGELOG="$TEMP/purge.log"

# --- sandbox ---------------------------------------------------------------
# A fake repo root whose .ci/scripts/lib and .ci/config are SYMLINKS to the real
# ones, so get_repo_root() (which derives the root from common.sh's own
# BASH_SOURCE) resolves to the sandbox and upload-repos-to-r2.sh's `cd
# "$(get_repo_root)"` lands on the fixture instead of the working tree.
mkdir -p "$ROOT/.ci/scripts/deploy" "$ROOT/.ci/scripts/lib" "$ROOT/.ci/config" \
    "$ROOT/dist/cli" "$ROOT/dist/repos/apt/dists" "$ROOT/dist/pages" "$FAKEBIN"
for f in "$REPO_ROOT"/.ci/scripts/lib/*; do ln -s "$f" "$ROOT/.ci/scripts/lib/$(basename "$f")"; done
for f in "$REPO_ROOT"/.ci/config/*; do ln -s "$f" "$ROOT/.ci/config/$(basename "$f")"; done
# constants.sh resolves .devcontainer/toolchain.env RELATIVE TO THE ROOT it is
# sourced from and hard-fails without it. Omitting this link made every mutant
# die during startup, which the controls below then happily read as "the
# planted defect was detected" -- a control firing for a reason that has nothing
# to do with its plant. The liveness probe in assemble_mutant() is what makes
# that class of mistake impossible to repeat silently.
ln -s "$REPO_ROOT/.devcontainer" "$ROOT/.devcontainer"

# Fixture artifacts. Two binaries + a manifest is the shape stage-artifacts hands
# the uploader.
printf 'ELF-ish\n' >"$ROOT/dist/cli/rdc-linux-x64"
printf 'ELF-ish\n' >"$ROOT/dist/cli/rdc-darwin-arm64"
printf '{"version":"%s"}\n' "$VERSION" >"$ROOT/dist/cli/manifest.json"
printf 'Package: rdc\n' >"$ROOT/dist/repos/apt/dists/Packages"
printf 'REDIACC_CHANNEL:-stable\n' >"$ROOT/dist/pages/install.sh"

FIXTURE_BINARIES=$(find "$ROOT/dist/cli" -name 'rdc-*' -type f | wc -l)
if ((FIXTURE_BINARIES == 0)); then
    log_fail "ANTI-VACUITY: the fixture yielded zero rdc-* binaries; every upload assertion below would be trivially satisfiable"
    exit 1
fi

# Fake `aws`: a pure recorder. Every invocation is one line in $AWSLOG.
cat >"$FAKEBIN/aws" <<FAKE
#!/bin/bash
printf '%s\n' "\$*" >>"$AWSLOG"
case "\$1 \$2" in
    "s3api head-object") exit 254 ;;  # no .released sentinel -> guard says PROCEED
    "s3api list-objects-v2") echo 0 ;;
    # A cp whose SOURCE is - is fed on stdin (r2_put); consume it. A cp whose
    # DESTINATION is - (r2_get) reads nothing, and consuming stdin there blocks
    # forever on an inherited terminal -- a hang, not a failure, and a hang in
    # CI reads as a timeout with no verdict. No backticks in this heredoc: the
    # delimiter is unquoted, so they would run as command substitution while the
    # fake is being written.
    "s3 cp") [[ "\$3" == "-" ]] && cat >/dev/null ;;
esac
exit 0
FAKE
chmod +x "$FAKEBIN/aws"
# Fake cf-purge-urls.sh in the sandbox: upload-repos-to-r2.sh calls it by a
# repo-relative path after cd'ing to get_repo_root().
cat >"$ROOT/.ci/scripts/deploy/cf-purge-urls.sh" <<FAKE
#!/bin/bash
cat >>"$PURGELOG"
FAKE
chmod +x "$ROOT/.ci/scripts/deploy/cf-purge-urls.sh"

# The pristine copy of upload-repos-to-r2.sh must be BYTE-IDENTICAL to the real
# script -- the sandbox exists to relocate its repo root, not to re-implement it.
cp "$REAL_REPOS" "$ROOT/.ci/scripts/deploy/upload-repos-to-r2.sh"
cmp -s "$REAL_REPOS" "$ROOT/.ci/scripts/deploy/upload-repos-to-r2.sh" || {
    log_fail "sandbox copy of upload-repos-to-r2.sh is not byte-identical to the real script"
    exit 1
}
SANDBOX_REPOS="$ROOT/.ci/scripts/deploy/upload-repos-to-r2.sh"

# --- mutant assembly -------------------------------------------------------
# BY CONSTRUCTION: head-up-to-anchor + a replacement block written literally
# here + tail-after-anchor. No pattern substitution of any live source line, so
# a reworded guard cannot silently produce an identical "mutant".
assemble_mutant() {
    local src="$1" out="$2" repl="$3" b e
    b="$(grep -n 'SKIP_RELEASE_GUARD_BEGIN' "$src" | head -1 | cut -d: -f1)"
    e="$(grep -n 'SKIP_RELEASE_GUARD_END' "$src" | head -1 | cut -d: -f1)"
    if [[ -z "$b" || -z "$e" ]] || ((e <= b)); then
        log_fail "CONTROL COULD NOT PLANT: guard anchors not found in $src (begin='$b' end='$e')"
        exit 1
    fi
    {
        head -n "$((b - 1))" "$src"
        [[ -n "$repl" ]] && printf '%s\n' "$repl"
        tail -n "+$((e + 1))" "$src"
    } >"$out"
    chmod +x "$out"
    if grep -q 'SKIP_RELEASE_GUARD_BEGIN' "$out"; then
        log_fail "CONTROL COULD NOT PLANT: anchor survived in $out"
        exit 1
    fi
    if cmp -s "$src" "$out"; then
        log_fail "CONTROL COULD NOT PLANT: $out is identical to $src"
        exit 1
    fi
    # LIVENESS. A mutant that dies during startup (a missing sandbox file, a bad
    # splice) exits non-zero for a reason unrelated to its plant, and every
    # control below would read that as "the defect was detected". Prove the
    # mutant still loads and runs before trusting anything it says. The probe is
    # chosen to be independent of the plant: it exercises argument handling,
    # which sits ABOVE the spliced region in both scripts.
    local probe rc=0
    if grep -q 'upload-repos-to-r2.sh: CHANNEL must be set' "$out"; then
        probe="$(env -u CHANNEL -u SKIP_RELEASE PATH="$FAKEBIN:$PATH" bash "$out" 2>&1)" || rc=$?
        grep -q 'CHANNEL must be set' <<<"$probe" || {
            log_fail "MUTANT IS NOT LIVE: $out did not reach its CHANNEL check (exit $rc): $probe"
            exit 1
        }
    else
        probe="$(env -u SKIP_RELEASE PATH="$FAKEBIN:$PATH" bash "$out" --help 2>&1)" || rc=$?
        if ((rc != 0)) || ! grep -q 'Usage:' <<<"$probe"; then
            log_fail "MUTANT IS NOT LIVE: $out --help exited $rc without a usage line: $probe"
            exit 1
        fi
    fi
}

MUT_UNCONDITIONAL='skip_release_requested() { return 0; }
if skip_release_requested; then
    echo "MUTANT: guard is unconditional"
    exit 0
fi'
MUT_CHANNEL_BLIND='skip_release_requested() {
    case "${SKIP_RELEASE:-}" in
        true | 1 | yes | y | on) return 0 ;;
        *) return 1 ;;
    esac
}
if skip_release_requested; then
    echo "MUTANT: guard ignores CHANNEL"
    exit 0
fi'

assemble_mutant "$REAL_UPLOAD" "$ROOT/.ci/scripts/deploy/mutant-a-noguard.sh" ""
assemble_mutant "$REAL_UPLOAD" "$ROOT/.ci/scripts/deploy/mutant-b-uncond.sh" "$MUT_UNCONDITIONAL"
assemble_mutant "$REAL_UPLOAD" "$ROOT/.ci/scripts/deploy/mutant-c-blind.sh" "$MUT_CHANNEL_BLIND"
assemble_mutant "$SANDBOX_REPOS" "$ROOT/.ci/scripts/deploy/mutant-r-noguard.sh" ""
assemble_mutant "$SANDBOX_REPOS" "$ROOT/.ci/scripts/deploy/mutant-r-uncond.sh" "$MUT_UNCONDITIONAL"
assemble_mutant "$SANDBOX_REPOS" "$ROOT/.ci/scripts/deploy/mutant-r-blind.sh" "$MUT_CHANNEL_BLIND"

# --- drivers ---------------------------------------------------------------
RC=0
OUT=""
run_upload() {
    local script="$1" skip="$2" channel="$3"
    : >"$AWSLOG"
    RC=0
    OUT="$(
        env -u SKIP_RELEASE PATH="$FAKEBIN:$PATH" \
            ${skip:+SKIP_RELEASE="$skip"} \
            R2_ACCESS_KEY_ID=k R2_SECRET_ACCESS_KEY=s R2_ENDPOINT=https://example.invalid \
            NPM_DIR="$ROOT/dist/npm-absent" \
            bash "$script" --version "$VERSION" --channel "$channel" --cli-dir "$ROOT/dist/cli" </dev/null 2>&1
    )" || RC=$?
}

run_repos() {
    local script="$1" skip="$2" channel="$3"
    : >"$AWSLOG"
    : >"$PURGELOG"
    RC=0
    OUT="$(
        env -u SKIP_RELEASE PATH="$FAKEBIN:$PATH" \
            ${skip:+SKIP_RELEASE="$skip"} \
            CHANNEL="$channel" \
            R2_ACCESS_KEY_ID=k R2_SECRET_ACCESS_KEY=s R2_ENDPOINT=https://example.invalid \
            CLOUDFLARE_ZONE_ID=zone CLOUDFLARE_API_TOKEN=tok \
            bash "$script" </dev/null 2>&1
    )" || RC=$?
}

calls() { wc -l <"$AWSLOG" | tr -d ' '; }

# --- cases. Each returns 0 when the property HOLDS, 1 when it is violated. ---
# They are called twice: once against the real script (must hold) and once
# against the mutant that breaks exactly that property (must be violated).
case_skip_writes_nothing() {
    run_upload "$1" true edge
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    if [[ -s "$AWSLOG" ]]; then
        echo "    $(calls) aws call(s) were made on a skipped edge release:"
        sed 's/^/      /' "$AWSLOG"
        return 1
    fi
    grep -q 'bump-none' <<<"$OUT" || {
        echo "    output does not name bump-none"
        return 1
    }
    return 0
}

case_clean_writes_pointer() {
    run_upload "$1" "" edge
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    if [[ ! -s "$AWSLOG" ]]; then
        echo "    ANTI-VACUITY: a clean edge upload made ZERO aws calls"
        return 1
    fi
    local want
    for want in "cli/edge/manifest.json" "cli/edge/latest.json" "cli/v${VERSION}/"; do
        grep -qF "$want" "$AWSLOG" || {
            echo "    a clean edge upload never wrote $want"
            return 1
        }
    done
    return 0
}

case_pr_channel_unaffected() {
    run_upload "$1" true pr-7
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    grep -qF "cli/pr-7/latest.json" "$AWSLOG" || {
        echo "    SKIP_RELEASE suppressed a pr-7 upload; the guard is not channel-scoped"
        return 1
    }
    return 0
}

case_repos_skip_writes_nothing() {
    run_repos "$1" 1 edge
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    if [[ -s "$AWSLOG" || -s "$PURGELOG" ]]; then
        echo "    $(calls) aws call(s) / $(wc -l <"$PURGELOG") purge URL(s) on a skipped edge release"
        return 1
    fi
    grep -q 'bump-none' <<<"$OUT" || {
        echo "    output does not name bump-none"
        return 1
    }
    return 0
}

case_repos_clean_writes() {
    run_repos "$1" "" edge
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    if [[ ! -s "$AWSLOG" ]]; then
        echo "    ANTI-VACUITY: a clean edge repo upload made ZERO aws calls"
        return 1
    fi
    local want
    for want in "apt/edge/" "cli/edge/install.sh"; do
        grep -qF "$want" "$AWSLOG" || {
            echo "    a clean edge repo upload never wrote $want"
            return 1
        }
    done
    [[ -s "$PURGELOG" ]] || {
        echo "    no Cloudflare purge was requested for a clean edge upload"
        return 1
    }
    return 0
}

case_repos_pr_unaffected() {
    run_repos "$1" 1 pr-7
    ((RC == 0)) || {
        echo "    exit $RC (expected 0)"
        return 1
    }
    grep -qF "apt/pr-7/" "$AWSLOG" || {
        echo "    SKIP_RELEASE suppressed a pr-7 repo upload; the guard is not channel-scoped"
        return 1
    }
    return 0
}

FAILURES=0
# The recorder count is read AFTER the case runs, never interpolated into the
# label at call time: a count captured before the run reports the PREVIOUS
# case's log and would hide exactly the collapse anti-vacuity exists to expose.
OBSERVED=0
must_hold() {
    local case_fn="$1" script="$2" label="$3" detail rc=0
    detail="$("$case_fn" "$script")" || rc=$?
    local n
    n="$(calls)"
    OBSERVED=$((OBSERVED + n))
    if ((rc == 0)); then
        log_pass "$label [${n} aws call(s)]"
        return 0
    fi
    log_error "$label [${n} aws call(s)]"
    [[ -n "$detail" ]] && echo "$detail"
    FAILURES=$((FAILURES + 1))
}
control_must_fail() {
    local case_fn="$1" script="$2" label="$3"
    if "$case_fn" "$script" >/dev/null 2>&1; then
        log_error "CONTROL DID NOT FIRE: $label -- the planted defect went undetected, so this assertion proves nothing"
        FAILURES=$((FAILURES + 1))
        return 1
    fi
    log_pass "control fires: $label"
}

D="$ROOT/.ci/scripts/deploy"

echo "-- upload-to-r2.sh (real script at $REAL_UPLOAD)"
must_hold case_skip_writes_nothing "$REAL_UPLOAD" "1. --skip-release on edge writes NOTHING to R2"
must_hold case_clean_writes_pointer "$REAL_UPLOAD" "2. no flag on edge still writes the channel pointer + cli/v${VERSION}/"
must_hold case_pr_channel_unaffected "$REAL_UPLOAD" "3. SKIP_RELEASE is ignored on pr-7"

echo "-- upload-repos-to-r2.sh (byte-identical copy, relocated repo root)"
must_hold case_repos_skip_writes_nothing "$SANDBOX_REPOS" "4. SKIP_RELEASE on edge writes NOTHING (no upload, no purge)"
must_hold case_repos_clean_writes "$SANDBOX_REPOS" "5. no signal on edge still publishes the repos + install scripts"
must_hold case_repos_pr_unaffected "$SANDBOX_REPOS" "6. SKIP_RELEASE is ignored on pr-7"

echo "-- controls (each mutant is assembled by construction and proven to have landed)"
control_must_fail case_skip_writes_nothing "$D/mutant-a-noguard.sh" "a. guard deleted -> edge pointer is written on a skipped release"
control_must_fail case_clean_writes_pointer "$D/mutant-b-uncond.sh" "b. guard unconditional -> a CLEAN edge release is silently withheld"
control_must_fail case_pr_channel_unaffected "$D/mutant-c-blind.sh" "c. guard ignores CHANNEL -> pr-7 stops uploading"
control_must_fail case_repos_skip_writes_nothing "$D/mutant-r-noguard.sh" "a'. repos guard deleted"
control_must_fail case_repos_clean_writes "$D/mutant-r-uncond.sh" "b'. repos guard unconditional -> clean edge silently withheld"
control_must_fail case_repos_pr_unaffected "$D/mutant-r-blind.sh" "c'. repos guard ignores CHANNEL"

if ((FAILURES > 0)); then
    log_fail "$FAILURES assertion(s) failed"
    exit 1
fi

log_pass "6 properties + 6 controls; ${FIXTURE_BINARIES} fixture binaries; recorder observed ${OBSERVED} aws call(s) across the 6 property runs"
echo "BLIND SPOT: this cannot see whether any workflow PASSES --skip-release/SKIP_RELEASE."
echo "            A flag nobody passes would leave every case above green. That wiring is"
echo "            check-ci-workflow-invariants.sh's subject (plan T2), not this file's."
