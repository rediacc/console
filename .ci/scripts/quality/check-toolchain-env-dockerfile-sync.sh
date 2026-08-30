#!/usr/bin/env bash
# Gate: GO_VERSION and NODE_VERSION in toolchain.env and the devcontainer
# Dockerfile's matching ARG lines must be identical.
#
# WHY THIS EXISTS. check-toolchain-pins.sh's A1 (one definition per pin) deliberately
# EXEMPTS GO_VERSION and NODE_VERSION from its single-source check, because both also
# appear as bare majors in third-party action inputs and go.mod -- values this repo
# does not own and must not try to unify. That exemption is correct for THOSE
# call sites, but it has a side effect: it also removes ANY check between the two
# files that ARE supposed to carry the identical value on purpose --
# .devcontainer/toolchain.env (the pin) and .devcontainer/Dockerfile's `ARG
# GO_VERSION=`/`ARG NODE_VERSION=` (consumed at image-build time). Nothing currently
# asserts these two stay equal; a bump to one without the other would build a
# devcontainer image running a DIFFERENT Go/Node than the pin file claims, silently.
#
# WHAT THIS CHECKS. For GO_VERSION and NODE_VERSION: the value in
# .devcontainer/toolchain.env must equal the value of the matching `ARG <KEY>=`
# line in .devcontainer/Dockerfile. Nothing else -- this is a narrow, two-file,
# two-key check, not a reopening of the broader exemption.
#
# CONTROL-FIRST. Builds fixtures by construction (a temp toolchain.env + temp
# Dockerfile with a deliberately mismatched value), never by substituting into
# real source, so rewording a real file cannot silently void the control.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

RED=''
GREEN=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    NC=$'\033[0m'
fi
fails=0
fail() {
    echo "${RED}✗${NC} $*" >&2
    fails=$((fails + 1))
}
pass() { echo "${GREEN}ok${NC}   $*"; }

# Extract KEY's value from a toolchain.env-shaped file, or empty if absent.
env_value() {
    grep -E "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2-
}

# Extract KEY's value from an `ARG KEY=value` line in a Dockerfile, or empty.
arg_value() {
    grep -oP "^ARG[[:space:]]+$1=\K.*" "$2" 2>/dev/null | head -1
}

check_pair() {
    local key="$1" env_file="$2" dockerfile="$3" label="$4"
    local env_val arg_val
    env_val="$(env_value "$key" "$env_file")"
    arg_val="$(arg_value "$key" "$dockerfile")"
    if [[ -z "$env_val" ]]; then
        fail "$label: $key not found in $env_file"
        return
    fi
    if [[ -z "$arg_val" ]]; then
        fail "$label: ARG $key not found in $dockerfile"
        return
    fi
    if [[ "$env_val" != "$arg_val" ]]; then
        fail "$label: $key mismatch -- $env_file has '$env_val', $dockerfile ARG has '$arg_val'"
        return
    fi
    pass "$label: $key='$env_val' matches in both files"
}

run_controls() {
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN

    # CONTROL: a real mismatch is caught.
    printf 'GO_VERSION=1.26.6\n' >"$tmp/toolchain.env"
    printf 'ARG GO_VERSION=1.26.5\n' >"$tmp/Dockerfile"
    local out
    out="$(check_pair GO_VERSION "$tmp/toolchain.env" "$tmp/Dockerfile" CONTROL 2>&1)"
    if [[ "$out" == *"mismatch"* ]]; then
        pass "control: a real GO_VERSION mismatch is detected"
    else
        fail "control: a planted mismatch was NOT detected -- $out"
    fi

    # CONTROL: matching values pass cleanly.
    printf 'GO_VERSION=1.26.6\n' >"$tmp/toolchain.env"
    printf 'ARG GO_VERSION=1.26.6\n' >"$tmp/Dockerfile"
    out="$(check_pair GO_VERSION "$tmp/toolchain.env" "$tmp/Dockerfile" CONTROL 2>&1)"
    if [[ "$out" == *"matches"* ]]; then
        pass "control: matching values pass"
    else
        fail "control: matching values were wrongly flagged -- $out"
    fi

    # CONTROL: a missing ARG line is a failure, not a silent skip.
    printf 'GO_VERSION=1.26.6\n' >"$tmp/toolchain.env"
    printf '# no ARG line here\n' >"$tmp/Dockerfile"
    out="$(check_pair GO_VERSION "$tmp/toolchain.env" "$tmp/Dockerfile" CONTROL 2>&1)"
    if [[ "$out" == *"not found"* ]]; then
        pass "control: a missing ARG line is flagged, not silently skipped"
    else
        fail "control: a missing ARG line was not flagged -- $out"
    fi
}

echo "Toolchain env/Dockerfile sync (GO_VERSION, NODE_VERSION)"
run_controls
if [[ $fails -gt 0 ]]; then
    echo "${RED}x the rule itself is broken, so no verdict it produces means anything.${NC}" >&2
    exit 1
fi

ENV_FILE="$ROOT/.devcontainer/toolchain.env"
DOCKERFILE="$ROOT/.devcontainer/Dockerfile"
[[ -r "$ENV_FILE" ]] || {
    fail "required subject missing: $ENV_FILE"
    exit 1
}
[[ -r "$DOCKERFILE" ]] || {
    fail "required subject missing: $DOCKERFILE"
    exit 1
}

check_pair GO_VERSION "$ENV_FILE" "$DOCKERFILE" "devcontainer"
check_pair NODE_VERSION "$ENV_FILE" "$DOCKERFILE" "devcontainer"

if [[ $fails -gt 0 ]]; then
    echo "${RED}x $fails toolchain-env/Dockerfile mismatch(es)${NC}" >&2
    exit 1
fi

echo "${GREEN}✓ toolchain.env and Dockerfile agree on GO_VERSION and NODE_VERSION${NC}"
