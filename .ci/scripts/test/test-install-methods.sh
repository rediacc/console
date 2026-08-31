#!/bin/bash
# Test all documented installation methods
# Usage:
#   test-install-methods.sh [--dry-run] [--method <method>] [--version <ver>]
#
# Options:
#   --dry-run            Print commands without executing. A dry run VERIFIES
#                        NOTHING, so every test it "runs" is counted as a SKIP,
#                        never as a pass.
#   --method <method>    Test specific method: binary, verify, update, promote,
#                        docker, apt, dnf, apk, pacman, homebrew, npm, quick,
#                        all (default: all)
#   --version <ver>      Version to test (default: latest)
#   --platform <plat>    Platform: linux, mac, win (default: auto-detect)
#   --arch <arch>        Architecture: x64, arm64 (default: auto-detect)
#   --local-artifacts DIR  Test with locally-built artifacts instead of downloading
#
# Every argument is validated. An unknown flag, an unknown --method/--platform/
# --arch value, or a flag with no value is a hard error (exit 2), and a run that
# executes zero tests is a failure (exit 1). See the notes on usage_error() and
# on the summary block for the incidents that motivated both.
#
# Examples:
#   ./test-install-methods.sh --dry-run
#   ./test-install-methods.sh --method apt --version 0.4.58
#   ./test-install-methods.sh --method binary --platform linux --arch arm64
#   ./test-install-methods.sh --local-artifacts dist/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# =============================================================================
# Argument Parsing
# =============================================================================

DRY_RUN=false
METHOD="all"
VERSION="latest"
PLATFORM=""
ARCH=""
LOCAL_ARTIFACTS=""

VALID_METHODS="binary verify update promote docker apt dnf apk pacman homebrew npm quick all"

# Every unrecognised argument is fatal.
#
# The parser used to end with a bare `*) shift ;;`, which SWALLOWED anything it
# did not recognise -- including a typo'd --method value, because METHOD was
# assigned without ever being validated. The result was a run that matched no
# test block, executed nothing, and exited 0. Reproduced live 2026-08-07:
#
#   .ci/scripts/test/test-install-methods.sh --dry-run --method bogus --version 1.2.17
#   -> "Results: 0 passed, 0 failed, 0 skipped (total 0)"   EXIT=0
#
# A green tick that verified nothing is the exact failure mode this whole file
# is being hardened against, so a mistyped invocation must stop the run and say
# what the valid values are.
usage_error() {
    log_error "$1"
    log_error "  usage: test-install-methods.sh [--dry-run] [--method <method>] [--version <ver>]"
    log_error "                                 [--platform linux|mac|win] [--arch x64|arm64]"
    log_error "                                 [--local-artifacts <dir>]"
    log_error "  valid --method values: ${VALID_METHODS// /, }"
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --method)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage_error "--method requires a value"
            METHOD="$2"
            shift 2
            ;;
        --version)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage_error "--version requires a value"
            VERSION="$2"
            shift 2
            ;;
        --platform)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage_error "--platform requires a value"
            PLATFORM="$2"
            shift 2
            ;;
        --arch)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage_error "--arch requires a value"
            ARCH="$2"
            shift 2
            ;;
        --local-artifacts)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage_error "--local-artifacts requires a value"
            LOCAL_ARTIFACTS="$2"
            shift 2
            ;;
        *)
            usage_error "unknown argument: '$1'"
            ;;
    esac
done

case " $VALID_METHODS " in
    *" $METHOD "*) ;;
    *) usage_error "unknown --method '$METHOD'" ;;
esac

# Auto-detect platform and arch if not specified
if [[ -z "$PLATFORM" ]]; then
    case "$(detect_os)" in
        linux) PLATFORM="linux" ;;
        macos) PLATFORM="mac" ;;
        windows) PLATFORM="win" ;;
        *) PLATFORM="linux" ;;
    esac
fi

if [[ -z "$ARCH" ]]; then
    ARCH="$(detect_arch)"
fi

# An unsupported platform or arch would match no test block and produce the same
# silent zero-total run as a typo'd --method. detect_arch() genuinely returns
# "unknown" on a machine that is neither x86_64 nor aarch64, so this also stops
# such a host from reporting a clean run.
case "$PLATFORM" in
    linux | mac | win) ;;
    *) usage_error "unknown --platform '$PLATFORM' (expected linux, mac, or win)" ;;
esac

case "$ARCH" in
    x64 | arm64) ;;
    *) usage_error "unknown --arch '$ARCH' (expected x64 or arm64; detect_arch reports 'unknown' on an unsupported machine)" ;;
esac

# =============================================================================
# Configuration
# =============================================================================

DOCKER_IMAGE="ghcr.io/rediacc/rdc"
SITE_URL="${SITE_URL:-https://www.rediacc.com}"
# RELEASES_BASE_URL is set by constants.sh (sourced via common.sh) as readonly
# REPO_CHANNEL: channel path segment ("stable", "edge", "pr-<n>"), or EMPTY
# meaning THIS RUN STAGED NO ARTIFACTS (schedule / workflow_dispatch, whose
# stage-artifacts step never writes R2).
#
# Empty deliberately does NOT default to "stable". That was tried on
# 2026-08-08 to cure the nightly's apt/quick-install 404s and reverted the
# same day: test_binary_download's comment already names the reason -- a
# nightly downloading stable turns MAIN's nightly red when a past RELEASE
# breaks, and those two signals must not be conflated. The 404s' actual
# cause was that the apt and quick-install tests LACKED the channel-less
# skip guard the binary/update/verify tests have carried all along, so
# they fetched root urls (/apt/gpg.key, /cli/install.sh) that the
# <dir>/<channel>/ layout has never published, while promote-r2-to-stable
# had in fact published every stable file (verified 200 live). The fix is
# the same `return 77` guard on those tests, not a default that changes
# what a red nightly means.
REPO_CHANNEL="${REPO_CHANNEL:-}"
# Build repo URL: ${RELEASES_BASE_URL}/apt[/${REPO_CHANNEL}] etc.
if [[ -n "$REPO_CHANNEL" ]]; then
    REPO_URL="${RELEASES_BASE_URL}"
    REPO_CHANNEL_SUFFIX="/${REPO_CHANNEL}"
else
    REPO_URL="${RELEASES_BASE_URL}"
    REPO_CHANNEL_SUFFIX=""
fi
HOMEBREW_TAP="rediacc/tap/rediacc-cli"

# Test counters
PASS=0
FAIL=0
SKIP=0
FAILED_TESTS=()

# Temp directory for test artifacts
TEST_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# =============================================================================
# Test Helpers
# =============================================================================

run_test() {
    local name="$1"
    shift

    log_step "TEST: $name"

    local exit_code=0
    "$@" || exit_code=$?

    if [[ $exit_code -eq 0 && "$DRY_RUN" == "true" ]]; then
        # A dry run downloads nothing, installs nothing and compares no version.
        # It used to be counted as a PASS, which made "N passed, 0 failed"
        # indistinguishable from a real verification in the summary line. It is
        # a SKIP: visible in the summary, which the rule allows, where a silent
        # pass is not.
        log_warn "SKIP: $name - dry-run, nothing was verified"
        ((SKIP++)) || true
    elif [[ $exit_code -eq 0 ]]; then
        log_info "PASS: $name"
        ((PASS++)) || true
    elif [[ $exit_code -eq 77 ]]; then
        # Exit code 77 = skip (GNU Automake convention)
        log_warn "SKIP: $name - prerequisites not met"
        ((SKIP++)) || true
    else
        log_error "FAIL: $name"
        ((FAIL++)) || true
        FAILED_TESTS+=("$name")
    fi
}

skip_test() {
    local name="$1"
    local reason="$2"
    log_warn "SKIP: $name - $reason"
    ((SKIP++)) || true
}

docker_run() {
    local image="$1"
    shift
    docker run --rm "$image" bash -c "$*"
}

# Get download URL for binary
get_binary_url() {
    local platform="$1"
    local arch="$2"
    local version="$3"

    local filename
    case "$platform" in
        linux) filename="rdc-linux-${arch}" ;;
        mac) filename="rdc-mac-${arch}" ;;
        win) filename="rdc-win-${arch}.exe" ;;
    esac

    if [[ -n "$REPO_CHANNEL" ]]; then
        echo "${RELEASES_BASE_URL}/cli/${REPO_CHANNEL}/${filename}"
        return 0
    fi

    # There is no channel-less layout in R2. The bucket is
    # `rediacc-releases/cli/{edge,stable}/...`, so the previous fallback here,
    # `cli/v${version}/${filename}`, named a path that has never existed:
    # probed live 2026-07-28, /cli/v1.2.12/rdc-linux-arm64 returns 404 while
    # /cli/stable/ and /cli/edge/ both return 200. It therefore produced a URL
    # guaranteed to 404, which is how the nightly failed at "Test Binary
    # Download" while looking like a network problem.
    #
    # Both callers now skip before reaching this, so an empty channel here is a
    # programming error rather than a runtime condition. Say so instead of
    # handing back a broken URL for someone to debug as a download failure.
    log_error "get_binary_url called with an empty REPO_CHANNEL."
    log_error "  There is no channel-less path in R2; callers must skip when the channel is empty."
    return 1
}

# Verify version output
# There is ALWAYS a version, or this fails. Never a silent pass.
#
# The old body was `echo "$output" | grep -q "$expected"`, which passed in three
# situations where nothing had actually been verified:
#
#   1. EMPTY EXPECTATION. `grep -q ""` matches every line, so an unset or
#      empty $VERSION made every caller succeed unconditionally.
#   2. EMPTY OUTPUT. A binary that failed to execute, or whose stderr was
#      swallowed by `|| true`, produced "" — and with an empty pattern that
#      still matched.
#   3. SUBSTRING AND REGEX MATCH. `grep -q "1.2.1"` matches a binary reporting
#      "1.2.16", so a patch release verified happily against the wrong build.
#      The dots are regex wildcards too, so "1.2.1" also matches "1x2y1".
#
# All three now fail loudly. A caller that legitimately cannot determine a
# version must SKIP (return 77) and say so, not hand an empty string to this.
verify_version() {
    local output="$1"
    local expected="$2"

    if [[ -z "$expected" ]]; then
        log_error "verify_version: expected version is EMPTY — refusing to report a pass. The caller failed to resolve a version."
        return 1
    fi
    if [[ -z "$output" ]]; then
        log_error "verify_version: no version output captured (expected '$expected') — refusing to report a pass. The binary did not run, or its output was discarded."
        return 1
    fi

    if [[ "$expected" == "latest" ]]; then
        # Any well-formed semver satisfies "latest", but it must be well formed.
        grep -qE '^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$' <<<"$output"
        return
    fi

    # Exact token match: dots escaped, and the version may not be flanked by
    # another digit or dot, so 1.2.1 no longer matches 1.2.16 or 11.2.1.
    local want="${expected#v}"
    grep -qE "(^|[^0-9.])v?${want//./\\.}([^0-9.]|\$)" <<<"$output"
}

# =============================================================================
# Container version fencing
# =============================================================================
#
# Seven of the eleven install methods -- apt, dnf, apk, pacman, npm, linuxbrew
# and quick -- used to end their `docker run ... set -e` heredoc with a bare
#
#     ${PKG_BINARY_NAME} --version
#
# whose output was never captured and never compared. $VERSION was referenced
# ZERO times inside any of those functions, so the only thing asserted was "the
# installed binary exits 0" -- which is exactly what a 1.2.16 binary published
# under the label 1.2.17 does. Both ci.yml and ct-install-methods.yml were
# passing `--version <next_version>` into every one of them, so the steps read
# like version checks in the workflow and were not.
#
# The comparison is done on the HOST so it goes through verify_version, the one
# primitive whose silent-pass classes are pinned by tests
# (gates/test-verify-version.sh). That is only safe if we compare the binary's
# own output and nothing else: `apt-get install`, `npm install -g` and
# `brew install` all PRINT the package version themselves, so grepping the whole
# container transcript for the expected version would pass even when the
# installed binary reported something different -- a check that cannot fail,
# swapped in for one that never ran.
#
# So the container fences its version output between two markers, and the host
# extracts only what lies between them.
VERSION_FENCE_BEGIN="__RDC_VERSION_BEGIN__"
VERSION_FENCE_END="__RDC_VERSION_END__"

# Emit the fenced version probe to paste into a container script. The command's
# stderr is folded into stdout INSIDE the container: docker multiplexes stdout
# and stderr as separate streams, so a version printed on stderr could otherwise
# arrive outside the fence.
version_fence_probe() {
    printf 'echo "%s"; %s 2>&1; echo "%s"' "$VERSION_FENCE_BEGIN" "$1" "$VERSION_FENCE_END"
}

# Pull the fenced region out of a container transcript, markers removed.
# Unanchored on purpose: install output that ends without a trailing newline
# would otherwise leave the begin marker glued to the end of another line.
extract_fenced_version() {
    printf '%s\n' "$1" |
        sed -n "/${VERSION_FENCE_BEGIN}/,/${VERSION_FENCE_END}/p" |
        grep -v -e "$VERSION_FENCE_BEGIN" -e "$VERSION_FENCE_END" || true
}

# run_container_version_test <label> <command...>
#
# Runs the command (a `docker run ...` invocation whose script ends in a fenced
# version probe), then requires the fenced output to match $VERSION exactly.
# Fails when the container fails, when no fenced output came back at all, and
# when the version differs. The full transcript is printed on any failure --
# capturing it costs the live streaming the old bare invocation had, so it is
# reprinted whenever it could matter.
run_container_version_test() {
    local label="$1"
    shift

    local raw rc=0
    raw="$("$@" 2>&1)" || rc=$?
    if [[ $rc -ne 0 ]]; then
        log_error "$label: container exited $rc before a version could be verified"
        printf '%s\n' "$raw" >&2
        return 1
    fi

    local reported
    reported="$(extract_fenced_version "$raw")"
    if ! verify_version "$reported" "$VERSION"; then
        log_error "$label: version mismatch - expected '$VERSION', got '$reported'"
        printf '%s\n' "$raw" >&2
        return 1
    fi
    log_info "  $label: version verified ($reported)"
}

# =============================================================================
# Binary Download Tests
# =============================================================================

test_binary_download() {
    local platform="${1:-$PLATFORM}"
    local arch="${2:-$ARCH}"

    local binary_name="rdc"
    [[ "$platform" == "win" ]] && binary_name="rdc.exe"

    local filename
    case "$platform" in
        linux) filename="rdc-linux-${arch}" ;;
        mac) filename="rdc-mac-${arch}" ;;
        win) filename="rdc-win-${arch}.exe" ;;
    esac

    # Local artifacts mode: copy binary directly
    if [[ -n "$LOCAL_ARTIFACTS" ]]; then
        local local_binary="$LOCAL_ARTIFACTS/cli/${filename}"
        if [[ ! -f "$local_binary" ]]; then
            log_warn "Local binary not found: $local_binary"
            return 77
        fi

        local download_dir="$TEST_DIR/binary-${platform}-${arch}"
        mkdir -p "$download_dir"
        cp "$local_binary" "$download_dir/$binary_name"
        chmod +x "$download_dir/$binary_name"

        # Sibling of the download path's Windows hole, fixed in the same pass.
        # This used to `return 0` after copying, so on a Windows runner it
        # asserted nothing about the binary, and on a Linux runner it turned
        # "cannot check" into "passed". Now: verify when powershell is
        # actually present, and SKIP loudly (77) when it is not. A skip is
        # visible in the summary; a bare success is not.
        if [[ "$platform" == "win" ]]; then
            if ! command -v powershell.exe &>/dev/null; then
                log_warn "Local Windows binary copied but no powershell.exe to run it; SKIPPING the version assertion rather than reporting a pass."
                return 77
            fi
            local win_output
            win_output=$(powershell.exe -Command ".\\$download_dir\\$binary_name --version" 2>&1 || true)
            if ! verify_version "$win_output" "$VERSION"; then
                log_error "Version mismatch: expected '$VERSION', got '$win_output'"
                return 1
            fi
            return 0
        fi

        local output
        output=$("$download_dir/$binary_name" --version 2>&1 || true)
        if ! verify_version "$output" "$VERSION"; then
            log_error "Version mismatch: expected '$VERSION', got '$output'"
            return 1
        fi
        return 0
    fi

    # No channel means nothing was staged for this run to validate, so there is
    # no binary to download and this test has no subject. SKIP, loudly.
    #
    # This is what broke the nightly. `ci.yml` sets the channel from the event:
    # `edge` on push, `pr-N` on pull_request, and EMPTY for everything else,
    # which is schedule and the dispatch rehearsal. The R2 layout is
    # `cli/{edge,stable}/...`, so with an empty channel get_binary_url fell
    # through to `cli/v${VERSION}/...`, a path shape that does not exist and
    # never has. Measured 2026-07-28 against the live bucket:
    #
    #   /cli/v1.2.12/rdc-linux-arm64 -> 404
    #   /cli/stable/rdc-linux-arm64  -> 200
    #   /cli/edge/rdc-linux-arm64    -> 200
    #
    # so the fallback 404s on every channel-less run, by construction.
    #
    # Skipping rather than pointing the nightly at `stable` is deliberate: this
    # job validates the artifacts THIS run staged, before they are published. A
    # nightly that downloaded `stable` instead would be a useful check, but a
    # DIFFERENT one, and it would turn main's nightly red when a past RELEASE
    # broke rather than when main broke. Those two signals must not be conflated.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: this run staged no artifacts, so there is no binary to validate."
        log_warn "  Skipping Binary Download (${platform} ${arch}). Expected on schedule and workflow_dispatch."
        return 77
    fi

    local url
    url="$(get_binary_url "$platform" "$arch" "$VERSION")"

    # Stall-aware download flags shared by every platform. The SEA binaries are
    # ~800 MB (they embed renet + the k8s stack for both arches), so a legitimate
    # download takes minutes — we must NOT abort a slow-but-progressing transfer.
    # --speed-limit/--speed-time abort ONLY on a true stall (<1 KB/s for 30s);
    # --max-time is a 25-min safety cap under the job budget; --retry recovers a
    # transient drop or stall. (An earlier Invoke-WebRequest -TimeoutSec attempt
    # was useless: PowerShell 5.1 does not bound an -OutFile body transfer, so a
    # stalled Windows download hung the entire 15-min job budget.)
    local -a dl_flags=(-fsSL --connect-timeout 30 --speed-limit 1024 --speed-time 30
        --max-time 1500 --retry 3 --retry-delay 5 --retry-connrefused)

    if [[ "$platform" == "win" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would download and test Windows binary"
            return 0
        fi

        # Return exit code 77 ("skip", GNU Automake convention) when we're not
        # actually on Windows (no powershell.exe to run the .exe).
        if ! command -v powershell.exe &>/dev/null; then
            return 77
        fi

        # Download with curl (Git-bash on the Windows runner ships it) for real
        # stall detection, then run the .exe through PowerShell to validate it.
        curl "${dl_flags[@]}" "$url" -o "$binary_name"

        # The output is CAPTURED and COMPARED, which it was not until
        # 2026-08-07. This line used to be a bare `powershell.exe -Command
        # ".\rdc.exe --version"`, so it asserted only that the binary could be
        # executed -- any version it printed was accepted. Both Windows
        # platforms therefore reported PASS on release run 31154305287 while
        # Linux and macOS correctly failed the same artifact with
        # "expected 1.2.17, got 1.2.16". A check that cannot fail on the thing
        # it exists to catch is worse than no check: it produced two green
        # ticks that argued the artifact was fine.
        local output
        output=$(powershell.exe -Command ".\\$binary_name --version" 2>&1 || true)
        if ! verify_version "$output" "$VERSION"; then
            log_error "Version mismatch: expected '$VERSION', got '$output'"
            return 1
        fi
    else
        # Linux/macOS test
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would run: curl -fsSL '$url' -o '$binary_name' && chmod +x '$binary_name' && ./'$binary_name' --version"
            return 0
        fi

        local download_dir="$TEST_DIR/binary-${platform}-${arch}"
        mkdir -p "$download_dir"
        cd "$download_dir"

        curl "${dl_flags[@]}" "$url" -o "$binary_name"
        chmod +x "$binary_name"
        local output
        output=$("./$binary_name" --version 2>&1 || true)
        if ! verify_version "$output" "$VERSION"; then
            log_error "Version mismatch: expected '$VERSION', got '$output'"
            return 1
        fi
    fi
}

# =============================================================================
# Update Check Tests
# =============================================================================

test_update_check() {
    if ! command -v jq &>/dev/null; then
        log_warn "jq not available, skipping update check"
        return 77
    fi

    # Without a channel the URL below would be `.../cli//manifest.json`, a path
    # that names nothing. Same reasoning as test_binary_download: a run that
    # staged no artifacts has no manifest to check, and must say so rather than
    # chase a URL that cannot exist.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: there is no channel manifest to check."
        log_warn "  Skipping Update Check. Expected on schedule and workflow_dispatch."
        return 77
    fi

    local manifest_url="${REPO_URL}/cli/${REPO_CHANNEL}/manifest.json"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would fetch manifest from: $manifest_url"
        return 0
    fi

    # Fetch and validate manifest
    local manifest
    manifest=$(curl -fsSL "$manifest_url") || {
        log_error "Failed to fetch manifest from $manifest_url"
        return 1
    }

    # The old structural guard was `jq -e '.version, .binaries'`, which accepts
    # a manifest whose binaries map is EMPTY: `{}` is truthy in jq, and jq -e
    # only fails on false/null. A manifest that named no binary at all therefore
    # passed the structure check, and then passed the reachability check too
    # (see below). Require both fields to be present AND non-empty.
    if ! echo "$manifest" |
        jq -e '(.version | type) == "string" and ((.version | length) > 0)
               and (.binaries | type) == "object" and ((.binaries | length) > 0)' >/dev/null 2>&1; then
        log_error "Invalid manifest structure at $manifest_url:"
        log_error "  .version must be a non-empty string and .binaries a non-empty object."
        echo "$manifest" | head -40 >&2
        return 1
    fi

    # The manifest version was PRINTED and never compared -- $VERSION did not
    # appear anywhere in this function, so a channel still advertising the
    # previous release looked identical to a correctly published one.
    local manifest_ver
    manifest_ver=$(echo "$manifest" | jq -r '.version')
    if ! verify_version "$manifest_ver" "$VERSION"; then
        log_error "Manifest version mismatch at $manifest_url: expected '$VERSION', got '$manifest_ver'"
        return 1
    fi
    log_info "  Manifest version verified: $manifest_ver"

    # This used to read the URL with `// empty` and, when it came back empty,
    # skip the reachability check and return 0 -- "no binary listed" was
    # reported as a pass. An update manifest that lists no linux-x64 binary is
    # broken; say so.
    local binary_url
    binary_url=$(echo "$manifest" | jq -r '.binaries["linux-x64"].url // empty')
    if [[ -z "$binary_url" ]]; then
        log_error "Manifest at $manifest_url has no .binaries[\"linux-x64\"].url"
        return 1
    fi
    if ! curl -fsSL -o /dev/null --head "$binary_url" 2>/dev/null; then
        log_error "Binary URL not reachable: $binary_url"
        return 1
    fi
    log_info "  Binary URL reachable: $binary_url"
}

# =============================================================================
# Promotion Validation Tests
# =============================================================================

test_promotion_config_fixup() {
    if ! command -v jq &>/dev/null; then
        log_warn "jq not available, skipping promotion test"
        return 77
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would validate promotion config fixup"
        return 0
    fi

    # Fetch .repo file from current channel
    local repo_url="${REPO_URL}/rpm${REPO_CHANNEL_SUFFIX}/rediacc.repo"
    local repo_content
    repo_content=$(curl -fsSL "$repo_url" 2>/dev/null) || {
        log_error "Failed to fetch .repo from $repo_url"
        return 1
    }

    # Verify it contains the current channel
    if ! grep -q "${REPO_CHANNEL}" <<<"$repo_content"; then
        log_error ".repo file does not contain channel '${REPO_CHANNEL}'"
        return 1
    fi
    log_info "  .repo contains channel: ${REPO_CHANNEL}"

    # Simulate promotion: sed-replace channel with 'stable'
    local promoted
    promoted=$(echo "$repo_content" | sed "s|/${REPO_CHANNEL}/|/stable/|g")

    if ! grep -q "/stable/" <<<"$promoted"; then
        log_error "Promotion sed-fix failed: /stable/ not found"
        return 1
    fi
    if grep -q "/${REPO_CHANNEL}/" <<<"$promoted"; then
        log_error "Promotion sed-fix incomplete: /${REPO_CHANNEL}/ still present"
        return 1
    fi
    log_info "  Promotion sed-fix validated: ${REPO_CHANNEL} -> stable"
}

# =============================================================================
# Channel Verification Tests
# =============================================================================

test_channel_verify() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would verify channel configuration"
        return 0
    fi

    # Same channel-less case as test_binary_download: with no channel there is
    # no staged artifact, and get_binary_url's fallback names a path that does
    # not exist. A channel-verification test with no channel has no subject.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping channel verification (expected on schedule and workflow_dispatch)."
        return 77
    fi

    # Download binary from channel
    local url
    url="$(get_binary_url "linux" "x64" "$VERSION")"
    local binary="/tmp/rdc-verify-$$"
    # Stall-aware (see dl_flags note in test_binary_download): abort only on a
    # true stall, not on a slow-but-progressing ~800 MB transfer.
    curl -fsSL --connect-timeout 30 --speed-limit 1024 --speed-time 30 \
        --max-time 1500 --retry 3 --retry-delay 5 --retry-connrefused "$url" -o "$binary" || {
        log_error "Failed to download binary from $url"
        return 1
    }
    chmod +x "$binary"

    # Verify binary runs
    local ver_output
    ver_output=$("$binary" --version 2>&1 || true)
    if ! verify_version "$ver_output" "$VERSION"; then
        log_error "Version mismatch: expected '$VERSION', got '$ver_output'"
        rm -f "$binary"
        return 1
    fi
    log_info "  Binary version: $ver_output"

    # Verify channel resolution (via env var, simulating what install.sh configures)
    local doctor_output
    doctor_output=$(REDIACC_UPDATE_CHANNEL="${REPO_CHANNEL}" "$binary" doctor -o json 2>/dev/null || true)
    if [[ -z "$doctor_output" ]] || ! command -v jq &>/dev/null; then
        log_error "Failed to get doctor output or jq not available"
        rm -f "$binary"
        return 1
    fi

    local channel_value
    channel_value=$(echo "$doctor_output" | jq -r '.Environment[] | select(.name == "Update channel") | .value' 2>/dev/null)
    if [[ "$channel_value" != "${REPO_CHANNEL}" ]]; then
        log_error "Channel mismatch: expected '${REPO_CHANNEL}', got '$channel_value'"
        rm -f "$binary"
        return 1
    fi
    log_info "  Channel verified: $channel_value"

    local server_value
    server_value=$(echo "$doctor_output" | jq -r '.Environment[] | select(.name == "Account server") | .value' 2>/dev/null)
    if [[ -z "$server_value" ]]; then
        log_error "Account server not found in doctor output"
        rm -f "$binary"
        return 1
    fi
    log_info "  Account server: $server_value"

    # Verify manifest URL for this channel is reachable
    local manifest_url="${RELEASES_BASE_URL}/cli/${REPO_CHANNEL}/manifest.json"
    if curl -fsSL -o /dev/null --head "$manifest_url" 2>/dev/null; then
        log_info "  Manifest reachable: $manifest_url"
    else
        log_error "Manifest not reachable: $manifest_url"
        rm -f "$binary"
        return 1
    fi

    rm -f "$binary"
}

# =============================================================================
# Docker Tests
# =============================================================================

test_docker_pull_and_run() {
    # DOCKER_TAG selects the image tag. The `${DOCKER_TAG:-${VERSION}}` this
    # replaced could NEVER take its fallback: constants.sh:27 runs
    # `DOCKER_TAG="${DOCKER_TAG:-latest}"` at source time, so DOCKER_TAG is
    # always non-empty here even when the caller passes it through as ''. The
    # arm read as protection and was unreachable, which is how a scheduled CI
    # run ended up pulling the last RELEASED image while asserting the NEXT
    # version. Behavior is unchanged; only the lie is gone.
    local tag="${DOCKER_TAG}"
    local image="${DOCKER_IMAGE}:${tag}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run: docker pull '$image' && docker run --rm '$image' --version"
        return 0
    fi

    docker pull "$image"
    local output
    output=$(docker run --rm "$image" --version 2>&1 || true)
    if ! verify_version "$output" "$VERSION"; then
        log_error "Version mismatch: expected '$VERSION', got '$output'"
        return 1
    fi
}

# =============================================================================
# APT Tests (Docker-based)
# =============================================================================

test_apt_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test APT install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping APT install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    run_container_version_test "APT ($label)" docker run --rm "$distro" bash -c "
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f \"\$f\" ] && sed -i \\
                -e 's|http://archive\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                -e 's|http://security\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                \"\$f\"
        done
        # FALL BACK if the Azure mirror is the thing that is down. The comment
        # above assumed it never is; on 2026-08-19 it refused connections for
        # ninety minutes and took this test down along with four devcontainer
        # builds. Rewriting every source to one host turns a co-location
        # optimisation into a single point of failure.
        if ! apt-get update -qq; then
            echo 'azure mirror unreachable; falling back to archive.ubuntu.com' >&2
            for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
                [ -f \"\$f\" ] && sed -i \\
                    -e 's|http://azure\\.archive\\.ubuntu\\.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' \\
                    \"\$f\"
            done
            apt-get update -qq
        fi
        apt-get install -y -qq curl gnupg ca-certificates >/dev/null 2>&1

        # Add GPG key
        curl -fsSL ${REPO_URL}/apt${REPO_CHANNEL_SUFFIX}/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg

        # Add sources list
        echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] ${REPO_URL}/apt${REPO_CHANNEL_SUFFIX} stable main' > /etc/apt/sources.list.d/rediacc.list

        # Retry apt-get update for transient network flakes on the way to
        # releases.rediacc.com. The underlying cause of the long flake
        # windows we chased in early iterations -- CF edge caching stale
        # Packages.gz -- is now neutralised by the zone-level Cache Rule
        # that bypasses cache for releases.rediacc.com (see
        # .ci/docs/r2-setup.md), so 5x15s is sufficient.
        for attempt in 1 2 3 4 5; do
            if apt-get update -qq -o Acquire::Retries=0; then
                break
            fi
            if [[ \$attempt -eq 5 ]]; then
                echo 'apt-get update failed after 5 attempts' >&2
                exit 1
            fi
            echo \"apt-get update attempt \$attempt failed, retrying in 15s...\" >&2
            sleep 15
        done
        apt-get install -y -qq ${PKG_NAME} >/dev/null 2>&1

        # Verify: fenced so the host compares the BINARY's output, not the
        # version apt-get itself printed while installing the package.
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# DNF Tests (Docker-based)
# =============================================================================

test_dnf_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test DNF install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping DNF install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    run_container_version_test "DNF ($label)" docker run --rm "$distro" bash -c "
        set -e
        # Add repo
        curl -fsSL ${REPO_URL}/rpm${REPO_CHANNEL_SUFFIX}/rediacc.repo -o /etc/yum.repos.d/rediacc.repo

        # Install
        dnf install -y ${PKG_NAME} >/dev/null 2>&1

        # Verify (fenced; see run_container_version_test)
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# APK Tests (Docker-based)
# =============================================================================

test_apk_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test APK install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping APK install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    run_container_version_test "APK ($label)" docker run --rm "$distro" sh -c "
        set -e
        # Add APK repository (apk appends arch automatically)
        echo '${REPO_URL}/apk${REPO_CHANNEL_SUFFIX}' >> /etc/apk/repositories
        apk update --allow-untrusted

        # Install from repo
        apk add --no-cache --allow-untrusted ${PKG_NAME}

        # Verify (fenced; see run_container_version_test)
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# Pacman Tests (Docker-based)
# =============================================================================

test_pacman_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test Pacman install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping Pacman install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    run_container_version_test "Pacman ($label)" docker run --rm "$distro" bash -c "
        set -e
        # Add rediacc repository
        echo '[rediacc]' >> /etc/pacman.conf
        echo 'SigLevel = Optional TrustAll' >> /etc/pacman.conf
        echo 'Server = ${REPO_URL}/archlinux${REPO_CHANNEL_SUFFIX}/\$arch' >> /etc/pacman.conf

        pacman -Sy --noconfirm

        # Install from repo
        pacman -S --noconfirm ${PKG_NAME}

        # Verify (fenced; see run_container_version_test)
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# npm Install Tests
# =============================================================================

test_npm_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test npm install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping npm install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    local npm_url="${RELEASES_BASE_URL}/npm${REPO_CHANNEL_SUFFIX}/rediacc-cli-latest.tgz"

    run_container_version_test "npm ($label)" docker run --rm "$distro" bash -c "
        set -e
        npm install -g '${npm_url}'
        # Fenced: npm prints the package version itself while installing, so an
        # unfenced grep over this transcript would match even if the installed
        # binary reported something else.
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# Homebrew Tests
# =============================================================================

test_homebrew_install() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run: brew tap rediacc/tap && brew install ${HOMEBREW_TAP}"
        return 0
    fi

    # Check if brew is available
    if ! command -v brew &>/dev/null; then
        log_error "Homebrew not available"
        return 1
    fi

    # Tap and install
    brew tap rediacc/tap
    brew install "${HOMEBREW_TAP}"

    # Verify. This one already compared its version, but it failed MUTELY --
    # verify_version's status was returned bare, so the summary said FAIL with
    # no indication of which version was wrong. Every other call site names both.
    local output
    output=$("${PKG_BINARY_NAME}" --version 2>&1 || true)
    if ! verify_version "$output" "$VERSION"; then
        log_error "Version mismatch: expected '$VERSION', got '$output'"
        return 1
    fi
}

test_homebrew_linuxbrew() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test Homebrew install in homebrew/brew:latest container"
        return 0
    fi

    run_container_version_test "Homebrew (Linuxbrew)" docker run --rm homebrew/brew:latest bash -c "
        set -e
        brew tap rediacc/tap
        brew install ${HOMEBREW_TAP}
        # Fenced: brew prints the formula version while installing.
        $(version_fence_probe "${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# Quick Install Tests
# =============================================================================

test_quick_install() {
    local distro="$1"
    local label="$2"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would test quick install on $label"
        return 0
    fi

    # Same channel-less case as test_binary_download: this run staged no
    # artifacts, and the channel URL this test fetches names a path that
    # does not exist (the layout is <dir>/<channel>/; there is no root
    # tree). Before 2026-08-08 this family had NO such guard, so every
    # schedule run 404ed here and the nightly stayed red for days while
    # the release pipeline was blamed -- promote-r2-to-stable had in
    # fact published every stable file. AFTER the DRY_RUN block on
    # purpose: dry-run output stays unchanged for the args gate.
    if [[ -z "$REPO_CHANNEL" ]]; then
        log_warn "No REPO_CHANNEL: skipping quick install (expected on schedule and workflow_dispatch)."
        return 77
    fi

    local expected_channel="${REPO_CHANNEL:-stable}"

    run_container_version_test "Quick Install ($label)" docker run --rm \
        -e "REDIACC_RELEASES_URL=${RELEASES_BASE_URL}" \
        -e "REDIACC_CHANNEL=${REPO_CHANNEL:-stable}" \
        "$distro" bash -c "
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f \"\$f\" ] && sed -i \\
                -e 's|http://archive\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                -e 's|http://security\\.ubuntu\\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \\
                \"\$f\"
        done
        # FALL BACK if the Azure mirror is the thing that is down. The comment
        # above assumed it never is; on 2026-08-19 it refused connections for
        # ninety minutes and took this test down along with four devcontainer
        # builds. Rewriting every source to one host turns a co-location
        # optimisation into a single point of failure.
        if ! apt-get update -qq; then
            echo 'azure mirror unreachable; falling back to archive.ubuntu.com' >&2
            for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
                [ -f \"\$f\" ] && sed -i \\
                    -e 's|http://azure\\.archive\\.ubuntu\\.com/ubuntu|http://archive.ubuntu.com/ubuntu|g' \\
                    \"\$f\"
            done
            apt-get update -qq
        fi
        apt-get install -y -qq curl ca-certificates >/dev/null 2>&1

        # Fetch install script and verify its baked default channel matches
        # the channel under test. Catches regressions where channel rewriting
        # (worker or R2 upload) silently falls back to 'stable'.
        script=\$(curl -fsSL ${REPO_URL}/cli${REPO_CHANNEL_SUFFIX}/install.sh)
        if ! echo \"\$script\" | grep -q 'REDIACC_CHANNEL:-${expected_channel}'; then
            echo 'FAIL: install.sh default channel is not ${expected_channel}' >&2
            echo \"\$script\" | grep -E 'REDIACC_CHANNEL' >&2 || true
            exit 1
        fi

        # Run install script from channel
        echo \"\$script\" | bash

        # Verify (install.sh puts binary in ~/.local/bin), fenced so the host
        # compares the binary's output and not the version install.sh echoed.
        # \$HOME rather than ~: the path is built as a string here and expanded
        # by the container's shell, where a tilde inside a string would not.
        $(version_fence_probe "\$HOME/.local/bin/${PKG_BINARY_NAME} --version")
    "
}

# =============================================================================
# Main Test Execution
# =============================================================================

# Resolve "latest" version from R2
if [[ "$VERSION" == "latest" && -z "$LOCAL_ARTIFACTS" && "$DRY_RUN" == "false" ]]; then
    LATEST_JSON=$(curl -fsSL "${RELEASES_BASE_URL}/cli/${REPO_CHANNEL:-edge}/latest.json" 2>/dev/null || echo "")
    if [[ -n "$LATEST_JSON" ]] && command -v jq &>/dev/null; then
        RESOLVED=$(echo "$LATEST_JSON" | jq -r '.version' 2>/dev/null)
        if [[ -n "$RESOLVED" && "$RESOLVED" != "null" ]]; then
            VERSION="$RESOLVED"
        fi
    fi
fi

log_step "Installation Method Tests"
log_info "  Method: $METHOD"
log_info "  Version: $VERSION"
log_info "  Platform: $PLATFORM"
log_info "  Arch: $ARCH"
log_info "  Dry-run: $DRY_RUN"
if [[ -n "$LOCAL_ARTIFACTS" ]]; then
    log_info "  Local artifacts: $LOCAL_ARTIFACTS"
fi
echo ""

# Validate requirements
if [[ "$DRY_RUN" == "false" ]]; then
    case "$METHOD" in
        docker | apt | dnf | apk | pacman | quick | all)
            require_cmd docker
            ;;
    esac
fi

# Binary download tests
if [[ "$METHOD" == "binary" || "$METHOD" == "all" ]]; then
    log_step "Binary Download Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Binary Download (Linux ${ARCH})" test_binary_download linux "$ARCH"
    elif [[ "$PLATFORM" == "mac" ]]; then
        run_test "Binary Download (macOS ${ARCH})" test_binary_download mac "$ARCH"
    elif [[ "$PLATFORM" == "win" ]]; then
        run_test "Binary Download (Windows ${ARCH})" test_binary_download win "$ARCH"
    fi
    echo ""
fi

# Channel verification tests (binary + channel resolution + manifest)
if [[ "$METHOD" == "verify" || "$METHOD" == "all" ]]; then
    log_step "Channel Verification Tests"
    if [[ "$PLATFORM" == "linux" && -n "$REPO_CHANNEL" ]]; then
        run_test "Channel Verify (${REPO_CHANNEL})" test_channel_verify
    elif [[ "$PLATFORM" != "linux" ]]; then
        # Registering a skip rather than silently registering nothing: with
        # `--method verify` on a non-Linux runner this block used to fall
        # through without a single counter moving, so the run reported
        # "total 0" and exited 0.
        skip_test "Channel Verify" "channel verification runs on Linux only (platform: $PLATFORM)"
    else
        skip_test "Channel Verify" "no REPO_CHANNEL: this run staged no artifacts"
    fi
    echo ""
fi

# Update check tests (manifest + binary URL reachability)
if [[ "$METHOD" == "update" || "$METHOD" == "all" ]]; then
    log_step "Update Check Tests"
    run_test "Update Check (manifest)" test_update_check
    echo ""
fi

# Promotion validation tests
if [[ "$METHOD" == "promote" || "$METHOD" == "all" ]]; then
    log_step "Promotion Validation Tests"
    run_test "Promotion Config Fixup" test_promotion_config_fixup
    echo ""
fi

# Docker tests
if [[ "$METHOD" == "docker" || "$METHOD" == "all" ]]; then
    log_step "Docker Tests"

    if [[ "$PLATFORM" == "linux" || "$PLATFORM" == "mac" ]]; then
        run_test "Docker Pull and Run" test_docker_pull_and_run
    else
        skip_test "Docker Pull and Run" "Docker tests not supported on Windows runners"
    fi
    echo ""
fi

# APT tests
if [[ "$METHOD" == "apt" || "$METHOD" == "all" ]]; then
    log_step "APT Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "APT Install (Ubuntu 22.04)" test_apt_install "ubuntu:22.04" "Ubuntu 22.04"
        run_test "APT Install (Ubuntu 24.04)" test_apt_install "ubuntu:24.04" "Ubuntu 24.04"
        run_test "APT Install (Debian 12)" test_apt_install "debian:12" "Debian 12"
    else
        skip_test "APT Install" "APT tests require Linux with Docker"
    fi
    echo ""
fi

# DNF tests
if [[ "$METHOD" == "dnf" || "$METHOD" == "all" ]]; then
    log_step "DNF Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "DNF Install (Fedora 40)" test_dnf_install "fedora:40" "Fedora 40"
        run_test "DNF Install (Rocky Linux 9)" test_dnf_install "rockylinux:9" "Rocky Linux 9"
    else
        skip_test "DNF Install" "DNF tests require Linux with Docker"
    fi
    echo ""
fi

# APK tests
if [[ "$METHOD" == "apk" || "$METHOD" == "all" ]]; then
    log_step "APK Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "APK Install (Alpine 3.20)" test_apk_install "alpine:3.20" "Alpine 3.20"
    else
        skip_test "APK Install" "APK tests require Linux with Docker"
    fi
    echo ""
fi

# Pacman tests
if [[ "$METHOD" == "pacman" || "$METHOD" == "all" ]]; then
    log_step "Pacman Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Pacman Install (Arch Linux)" test_pacman_install "archlinux:latest" "Arch Linux"
    else
        skip_test "Pacman Install" "Pacman tests require Linux with Docker"
    fi
    echo ""
fi

# Homebrew tests
if [[ "$METHOD" == "homebrew" || "$METHOD" == "all" ]]; then
    log_step "Homebrew Tests"

    if [[ "$PLATFORM" == "mac" ]]; then
        run_test "Homebrew Install (macOS)" test_homebrew_install
    elif [[ "$PLATFORM" == "linux" ]]; then
        if command -v brew &>/dev/null; then
            run_test "Homebrew Install (Linuxbrew)" test_homebrew_install
        else
            run_test "Homebrew Install (Linuxbrew Docker)" test_homebrew_linuxbrew
        fi
    else
        skip_test "Homebrew Install" "Homebrew not available on Windows"
    fi
    echo ""
fi

# npm install tests
if [[ "$METHOD" == "npm" || "$METHOD" == "all" ]]; then
    log_step "npm Install Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "npm Install (Node 22)" test_npm_install "node:22" "Node 22"
    else
        skip_test "npm Install" "npm tests require Linux with Docker"
    fi
    echo ""
fi

# Quick install tests
if [[ "$METHOD" == "quick" || "$METHOD" == "all" ]]; then
    log_step "Quick Install Tests"

    if [[ "$PLATFORM" == "linux" ]]; then
        run_test "Quick Install (Ubuntu 22.04)" test_quick_install "ubuntu:22.04" "Ubuntu 22.04"
        run_test "Quick Install (Ubuntu 24.04)" test_quick_install "ubuntu:24.04" "Ubuntu 24.04"
        run_test "Quick Install (Debian 12)" test_quick_install "debian:12" "Debian 12"
    else
        skip_test "Quick Install" "Quick install tests require Linux with Docker"
    fi
    echo ""
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
TOTAL=$((PASS + FAIL + SKIP))
log_step "Results: $PASS passed, $FAIL failed, $SKIP skipped (total $TOTAL)"

if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    log_error "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
        log_error "  - $t"
    done
fi

# Success used to be defined as "nothing failed", which is also true of a run
# that did nothing at all -- and that is not a hypothetical: a typo'd --method
# produced exactly that, "0 passed, 0 failed, 0 skipped (total 0)" with EXIT=0.
# Success is "something was accounted for".
#
# An ALL-SKIPPED run is deliberately still a success. Every skip is printed as
# "SKIP: <name> - <reason>" and counted in the line above, so a run that could
# not verify anything says so where a human and the CI log both see it; that is
# the visible-skip half of the rule. A zero-TOTAL run says nothing at all, which
# is the half that must never pass.
if ((TOTAL == 0)); then
    log_error "This run executed ZERO tests, so it verified NOTHING."
    log_error "  method='$METHOD' platform='$PLATFORM' arch='$ARCH' channel='${REPO_CHANNEL:-<empty>}'"
    log_error "  No test block matched that combination. Refusing to report success."
    exit 1
fi

[[ $FAIL -eq 0 ]] || exit 1
