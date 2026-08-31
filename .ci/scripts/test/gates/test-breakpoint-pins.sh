#!/bin/bash
# Static analysis of breakpoint's third-party tool pins. Downloads NOTHING:
# a gate that hits the network to prove a checksum is a gate that goes red on
# somebody else's outage, and it would then get skipped.
#
# WHAT WENT WRONG BEFORE, which is what each assertion below re-checks:
#
#   .ci/scripts/tunnel/start-cloudflare.sh (deleted) curled
#     .../releases/latest/download/cloudflared-linux-amd64.deb
#   straight into `sudo dpkg -i`. Three separate problems in one line: `latest`
#   means the artifact you reviewed is not the artifact you get, there was no
#   checksum at all, and dpkg runs maintainer scripts as ROOT -- in a job that
#   also held release secrets.
#
#   .github/actions/tmate/scripts/install-tmate.sh (deleted) ran
#     `apt-get install -y tmate`
#   FIRST and only fell back to its pinned GitHub release if apt failed. On
#   every Ubuntu runner apt succeeded, so the pinned path was dead code and the
#   binary that actually ran was whatever the distro happened to ship. A pin
#   bypassed on the common path is not a pin, and nothing failed to say so.
#
# The verify-before-use assertion is the load-bearing one: `sha256sum -c` after
# the chmod/extract it is supposed to guard proves nothing at all, and the two
# orderings look identical in review. Comparing LINE NUMBERS is a mechanical
# check that survives someone "simplifying" the installer later.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

BP="$REPO_ROOT/.ci/breakpoint"
VERSIONS="$BP/versions.sh"
INSTALL_CF="$BP/scripts/install-cloudflared.sh"
INSTALL_TMATE="$BP/scripts/install-tmate.sh"

for f in "$VERSIONS" "$INSTALL_CF" "$INSTALL_TMATE"; do
    [[ -f "$f" ]] || log_fail "subject under test is missing: $f"
done

# last_line_matching <file> <ere> -- line number of the LAST match, or empty.
#
# LAST, not first: install-cloudflared.sh verifies twice (once to decide an
# existing binary is intact, once on the fresh download). Taking the first match
# would let someone add a decorative early check and move the real one after the
# chmod without this gate noticing.
last_line_matching() {
    grep -nE "$2" "$1" | tail -1 | cut -d: -f1 || true
}

first_line_matching() {
    grep -nE "$2" "$1" | head -1 | cut -d: -f1 || true
}

# code_of <file> -- the file with whole-line comments stripped. Every "what not
# to do" example in these installers lives in a comment, so a grep for banned
# constructs has to look at code only or it fails on its own documentation.
code_of() {
    grep -vE '^[[:space:]]*#' "$1"
}

# =============================================================================
test_every_sha_constant_is_a_real_sha256() {
    local line name value count=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        name="${line%%=*}"
        name="${name#readonly }"
        value="${line#*=}"
        value="${value//\"/}"
        count=$((count + 1))
        if [[ ! "$value" =~ ^[0-9a-f]{64}$ ]]; then
            log_fail "$name is not 64 lowercase hex chars: '$value' (${#value} chars)"
        fi
    done < <(grep -E '^readonly BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+=' "$VERSIONS" || true)

    # A pinned artifact per (tool, arch): cloudflared x64/arm64 + tmate
    # x64/arm64. Fewer means an arch is silently unpinned, and the installer for
    # it would fail on an empty EXPECTED_SHA rather than on a mismatch.
    assert_eq "$count" "4" "expected one sha256 per (tool, arch) pair"
    log_pass "all $count BREAKPOINT_*_SHA256_* constants are 64 lowercase hex chars"
}

test_every_sha_is_distinct() {
    local total distinct
    total="$(grep -cE '^readonly BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+=' "$VERSIONS")"
    distinct="$(grep -E '^readonly BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+=' "$VERSIONS" |
        cut -d= -f2 | LC_ALL=C sort -u | grep -c .)"
    # A copy-paste that gives two arches the same hash makes one of them
    # permanently unverifiable -- it fails closed, but with a "CHECKSUM
    # MISMATCH" that sends you hunting for a supply-chain attack.
    assert_eq "$distinct" "$total" "every pinned artifact must have its own hash"
    log_pass "all $total pinned checksums are distinct (no copy-paste across arches)"
}

test_constants_are_readonly() {
    local declared bare
    declared="$(grep -cE '^readonly BREAKPOINT_[A-Z_]*(VERSION|SHA256_[A-Z0-9]+)=' "$VERSIONS")"
    ((declared >= 6)) || log_fail "only $declared pinned constants found; versions.sh looks wrong"

    # A pin a later `source` can quietly reassign is not a pin. `readonly` makes
    # the reassignment an error instead of a shrug.
    bare="$(grep -E '^BREAKPOINT_[A-Z_]*(VERSION|SHA256_[A-Z0-9]+)=' "$VERSIONS" || true)"
    assert_eq "$bare" "" "every version and sha constant must be declared readonly"
    log_pass "all $declared version/sha constants are readonly (none reassignable)"
}

test_verify_before_use() {
    local verify_ln use_ln

    # cloudflared: the checksum must be verified before the file is made
    # executable. Afterwards would mean an unverified binary is already runnable
    # in the state dir.
    verify_ln="$(last_line_matching "$INSTALL_CF" 'sha256sum -c')"
    use_ln="$(first_line_matching "$INSTALL_CF" '^[[:space:]]*chmod \+x')"
    [[ -n "$verify_ln" ]] || log_fail "install-cloudflared.sh has NO sha256sum -c at all"
    [[ -n "$use_ln" ]] || log_fail "install-cloudflared.sh has no chmod +x to guard"
    if ((verify_ln >= use_ln)); then
        log_fail "install-cloudflared.sh verifies at line $verify_ln but chmods at line $use_ln (verify must come FIRST)"
    fi
    log_pass "install-cloudflared.sh verifies (L$verify_ln) before chmod +x (L$use_ln)"

    # tmate: before EXTRACT, which is the stronger requirement -- tar on an
    # attacker-controlled archive is code execution's near neighbour, and it
    # happens before any chmod would.
    verify_ln="$(last_line_matching "$INSTALL_TMATE" 'sha256sum -c')"
    use_ln="$(first_line_matching "$INSTALL_TMATE" '(^|[^a-z])tar -')"
    [[ -n "$verify_ln" ]] || log_fail "install-tmate.sh has NO sha256sum -c at all"
    [[ -n "$use_ln" ]] || log_fail "install-tmate.sh has no tar extraction to guard"
    if ((verify_ln >= use_ln)); then
        log_fail "install-tmate.sh verifies at line $verify_ln but extracts at line $use_ln (verify must come FIRST)"
    fi
    log_pass "install-tmate.sh verifies (L$verify_ln) before tar extraction (L$use_ln)"
}

test_no_pipe_to_interpreter_or_sudo() {
    local f name code
    for f in "$INSTALL_CF" "$INSTALL_TMATE"; do
        name="$(basename "$f")"
        code="$(code_of "$f")"
        # `curl | bash` is the shape the deleted installer had in spirit:
        # bytes go from the network into an interpreter with nothing in
        # between where a checksum could be. The word-boundary form is
        # deliberate -- a naive '| sh' also matches '| sha256sum'.
        if grep -qE '\|[[:space:]]*(bash|sh|sudo)([[:space:]]|$)' <<<"$code"; then
            echo "$code" | grep -nE '\|[[:space:]]*(bash|sh|sudo)([[:space:]]|$)' >&2 || true
            log_fail "$name pipes into an interpreter or sudo"
        fi
        # No sudo at all: the raw binary needs only chmod +x, and dropping sudo
        # is what makes this work in a container and on a laptop.
        assert_not_contains "$code" "sudo " "$name must not need sudo"
        assert_not_contains "$code" "dpkg" "$name must not install a .deb (dpkg runs maintainer scripts as root)"
    done
    log_pass "neither installer pipes to bash/sh/sudo, uses sudo, or touches dpkg"
}

test_no_unpinned_download_urls() {
    local f name code
    for f in "$INSTALL_CF" "$INSTALL_TMATE" "$VERSIONS"; do
        name="$(basename "$f")"
        code="$(code_of "$f")"
        # `latest` in any form defeats the checksum: the bytes you hashed are
        # not the bytes you will get tomorrow.
        assert_not_contains "$code" "@latest" "$name must not resolve @latest"
        assert_not_contains "$code" "releases/latest/download" "$name must not use a releases/latest URL"
        assert_not_contains "$code" "/latest/" "$name must not resolve any /latest/ path"
    done

    # Control: the URLs that ARE there must interpolate the pinned version, or
    # the assertions above are satisfied by a file with no download in it.
    assert_contains "$(cat "$INSTALL_CF")" 'releases/download/${BREAKPOINT_CLOUDFLARED_VERSION}' \
        "install-cloudflared.sh must download the PINNED version"
    assert_contains "$(cat "$INSTALL_TMATE")" 'releases/download/${VER}' \
        "install-tmate.sh must download the PINNED version"
    log_pass "no @latest / releases-latest URLs; both installers fetch the pinned version"
}

test_tmate_has_no_apt_fallback() {
    local code hits
    code="$(code_of "$INSTALL_TMATE")"

    # THE regression this file exists for. An apt path here is not a harmless
    # convenience: apt SUCCEEDS on every Ubuntu runner, so its mere presence
    # makes the pinned, verified path dead code on the common path while the
    # file still reads as if it pins something.
    hits="$(echo "$code" | grep -nE 'apt-get|apt install|apt-cache|add-apt-repository' || true)"
    assert_eq "$hits" "" "install-tmate.sh must have NO apt path (apt succeeds and makes the pin dead code)"

    # Same for cloudflared, which had the equivalent problem via dpkg.
    hits="$(code_of "$INSTALL_CF" | grep -nE 'apt-get|apt install|apt-cache|add-apt-repository' || true)"
    assert_eq "$hits" "" "install-cloudflared.sh must have no apt path either"
    log_pass "neither installer has an apt/dpkg fallback that would bypass the pin"
}

test_every_pinned_sha_is_actually_consumed() {
    local const
    # A constant nothing reads is a pin that verifies nothing -- and it is the
    # exact residue an "unpinning" edit leaves behind, because deleting the
    # usage is easier than deleting the declaration.
    while IFS= read -r const; do
        [[ -z "$const" ]] && continue
        if ! grep -qF "\$$const" "$INSTALL_CF" "$INSTALL_TMATE"; then
            log_fail "$const is declared in versions.sh but never read by either installer"
        fi
    done < <(grep -oE 'BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+' "$VERSIONS" | LC_ALL=C sort -u)
    log_pass "every declared sha256 constant is actually read by an installer"
}

test_every_sha_constant_is_a_real_sha256
test_every_sha_is_distinct
test_constants_are_readonly
test_verify_before_use
test_no_pipe_to_interpreter_or_sudo
test_no_unpinned_download_urls
test_tmate_has_no_apt_fallback
test_every_pinned_sha_is_actually_consumed
