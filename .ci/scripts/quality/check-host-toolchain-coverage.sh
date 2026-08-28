#!/usr/bin/env bash
# Every pinned gate tool must have a RUNTIME guard, not just a definition.
#
# WHY THIS EXISTS. check-toolchain-pins.sh's A6 rule guarantees a GATE that
# invokes a pinned tool acquires it at the pin rather than trusting PATH -- but
# that is definition-time coverage of the tools GATED_TOOLS already names. It
# says nothing about whether the SEPARATE runtime guard that routes a session
# away from a host lacking one of those tools
# (.claude/hooks/pre-bash/block-host-toolchain-run.sh's BARE_TOOLS/NPX_TOOLS
# arrays) actually knows about all of them. Those two lists are maintained
# independently as literal bash arrays in two different files, with nothing
# keeping them in sync.
#
# Measured 2026-08-28: exactly this drift was live and undetected. The runtime
# guard's arrays existed only because a session found the gap by hand
# (`npx --yes ruff format` failing was misdiagnosed as "ruff is missing", when
# ruff was on PATH the whole time and the bug was routing/detection, not
# pinning) -- nothing would have caught GATED_TOOLS growing a fifth entry that
# the runtime guard never learns about. That is the class this gate closes: an
# assertion checked only at DEFINITION (GATED_TOOLS), with no check that the
# runtime guard's CALL SITES (BARE_TOOLS, NPX_TOOLS) still cover every member.
#
# SCOPE. `go` is deliberately allowed to be a BARE_TOOLS/NPX_TOOLS member with
# no GATED_TOOLS counterpart: go is not part of the toolchain-pins convention
# (its own go.mod/GOTOOLCHAIN resolves versions), so the runtime guard covering
# it is a superset, not a gap. The direction that matters is GATED_TOOLS ->
# BARE_TOOLS/NPX_TOOLS, checked here; the reverse is not required.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT" || exit 1

RED=''
GREEN=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    NC=$'\033[0m'
fi
FAIL=0
pass() { printf '%sok%s   %s\n' "$GREEN" "$NC" "$1"; }
fail() {
    printf '%s✗%s   %s\n' "$RED" "$NC" "$1" >&2
    FAIL=$((FAIL + 1))
}

# extract_gated_tools <check-toolchain-pins.sh path>
# Reads the GATED_TOOLS='a|b|c' literal and prints one tool per line.
extract_gated_tools() {
    grep -oE "^GATED_TOOLS='[^']*'" "$1" 2>/dev/null |
        sed -E "s/^GATED_TOOLS='([^']*)'$/\\1/" |
        tr '|' '\n' | sed '/^$/d' | sort -u
}

# extract_array <file> <array-name>
# Reads `NAME=(a b c)` and prints one tool per line.
extract_array() {
    grep -oE "^${2}=\\([^)]*\\)" "$1" 2>/dev/null |
        sed -E "s/^${2}=\\(([^)]*)\\)$/\\1/" |
        tr ' ' '\n' | sed '/^$/d' | sort -u
}

# --- controls first: a gate nobody has watched fail is not a gate ------------
CTL="$(mktemp -d)"
trap 'rm -rf "$CTL"' EXIT

cat >"$CTL/pins-bad.sh" <<'FIX'
GATED_TOOLS='shfmt|shellcheck|ruff|actionlint|newlypinned'
FIX
cat >"$CTL/guard-missing.sh" <<'FIX'
NPX_TOOLS=(ruff go shfmt shellcheck actionlint)
BARE_TOOLS=(ruff go shfmt shellcheck actionlint)
FIX
missing="$(comm -23 <(extract_gated_tools "$CTL/pins-bad.sh") <(extract_array "$CTL/guard-missing.sh" NPX_TOOLS))"
if [ -z "$missing" ]; then
    fail "CONTROL FAILED: a pinned tool absent from the runtime guard's NPX_TOOLS was NOT detected."
    exit 1
fi
[ "$missing" = "newlypinned" ] || {
    fail "CONTROL FAILED: the wrong tool was flagged (got '$missing', wanted 'newlypinned')."
    exit 1
}

cat >"$CTL/pins-good.sh" <<'FIX'
GATED_TOOLS='shfmt|shellcheck|ruff|actionlint'
FIX
cat >"$CTL/guard-full.sh" <<'FIX'
NPX_TOOLS=(ruff go shfmt shellcheck actionlint)
BARE_TOOLS=(ruff go shfmt shellcheck actionlint)
FIX
still_missing="$(comm -23 <(extract_gated_tools "$CTL/pins-good.sh") <(extract_array "$CTL/guard-full.sh" NPX_TOOLS))"
if [ -n "$still_missing" ]; then
    fail "CONTROL FAILED: full coverage was reported as missing ('$still_missing')."
    exit 1
fi
pass "control: a pinned tool absent from the runtime guard is detected"
pass "control: full coverage reports nothing missing"

# --- the real scan -------------------------------------------------------------
PINS="$ROOT/.ci/scripts/quality/check-toolchain-pins.sh"
GUARD="$ROOT/.claude/hooks/pre-bash/block-host-toolchain-run.sh"

if [ ! -f "$PINS" ]; then
    fail "the pinned-tools source is gone: $PINS"
    exit 1
fi
if [ ! -f "$GUARD" ]; then
    fail "the runtime guard is gone: $GUARD"
    exit 1
fi

gated="$(extract_gated_tools "$PINS")"
if [ -z "$gated" ]; then
    fail "GATED_TOOLS could not be read from $PINS -- this gate is not seeing its input, so its green would mean nothing."
    exit 1
fi
n_gated=$(printf '%s\n' "$gated" | grep -c .)

npx_tools="$(extract_array "$GUARD" NPX_TOOLS)"
bare_tools="$(extract_array "$GUARD" BARE_TOOLS)"
if [ -z "$npx_tools" ] || [ -z "$bare_tools" ]; then
    fail "NPX_TOOLS or BARE_TOOLS could not be read from $GUARD -- the runtime guard's arrays moved or were renamed."
    exit 1
fi

missing_npx="$(comm -23 <(printf '%s\n' "$gated") <(printf '%s\n' "$npx_tools"))"
missing_bare="$(comm -23 <(printf '%s\n' "$gated") <(printf '%s\n' "$bare_tools"))"

if [ -n "$missing_npx" ]; then
    fail "pinned tool(s) missing from NPX_TOOLS in $GUARD: $(printf '%s' "$missing_npx" | tr '\n' ' ')"
    echo "     A bare 'npx <tool>' for these will fail with a confusing npm error instead of the actionable npx-cannot-run-this message." >&2
fi
if [ -n "$missing_bare" ]; then
    fail "pinned tool(s) missing from BARE_TOOLS in $GUARD: $(printf '%s' "$missing_bare" | tr '\n' ' ')"
    echo "     A direct invocation of these on a host that lacks them will not be routed to the devbox." >&2
fi

if [ "$FAIL" -eq 0 ]; then
    pass "$n_gated pinned tool(s) all covered by the runtime guard's NPX_TOOLS and BARE_TOOLS"
    echo "${GREEN}✓${NC} host-toolchain runtime guard covers every pinned tool ($n_gated)."
    exit 0
fi
echo "${RED}✗${NC} the pinned-tools definition and the runtime guard have drifted." >&2
echo "  Fix: add the missing tool(s) to NPX_TOOLS and BARE_TOOLS in $GUARD." >&2
exit 1
