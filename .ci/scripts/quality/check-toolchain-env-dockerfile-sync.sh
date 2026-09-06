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
# AND ONE MORE PAIR, ADDED LATER: NODE_VERSION_MIN. The paragraph above says
# "narrow, two-file", so the third pair needs its own justification rather than
# quietly widening that sentence.
#
# NODE_VERSION_MIN is the repo's Node FLOOR, and it has three copies by
# necessity, not by sloppiness: .devcontainer/toolchain.env (the pin every shell
# path sources) plus engines.node in package.json and in
# packages/cli/package.json. The manifests cannot read a shell variable and npm
# will not accept one, so the value must be WRITTEN in all three -- which makes
# it the one pin where "single-sourced" is impossible and a comparison is the
# only remaining instrument.
#
# It is the same failure this gate already exists for, one file further out, and
# it had already happened: .ci/config/constants.sh COMPOSED the floor as
# "${NODE_VERSION}.0.0" -> 22.0.0, while both manifests said ">=22.13.0". Nothing
# compared them, so for the whole life of that line ./run.sh setup accepted hosts
# that npm then rejected. Composing a value from another pin passes a
# single-source scan and still drifts; only an equality check catches it.
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

# Extract engines.node from a package.json-shaped file, or empty if absent.
#
# PARSED, NOT GREPPED, unlike env_value/arg_value above, and the asymmetry is
# deliberate. `"node"` is a legal key in more than one place in a manifest -- a
# `volta` block pins a node version, so does a `packageManager`-adjacent stanza,
# and `"@types/node"` is one character away from matching a careless pattern. A
# `grep | head -1` would answer with whichever copy sits highest in the file and
# be right only by luck, and a WRONG answer here does not read as a broken gate:
# it reads as a real floor mismatch and sends someone to edit the wrong number.
#
# node(1) is guaranteed here because this gate runs as an npm script. If it ever
# is not, this returns empty and the caller reports "engines.node not found",
# which is a failure and not a silent skip -- the same direction the missing-ARG
# case already fails in.
engines_node() {
    node -e 'const fs=require("node:fs");let v="";try{v=(JSON.parse(fs.readFileSync(process.argv[1],"utf8")).engines||{}).node||"";}catch{}process.stdout.write(String(v));' "$1" 2>/dev/null
}

# The floor in the pins file must equal engines.node in EVERY manifest listed.
#
# EVERY, not "a": the failure mode worth catching is one of the two manifests
# moving alone. packages/cli/package.json ships to npm as its own artifact, so a
# floor that is right in the root and stale in the CLI is invisible in this repo
# and wrong for everyone who installs the published package.
check_engines_pair() {
    local key="$1" env_file="$2" label="$3"
    shift 3
    local env_val want pkg got bad=0 n=$#
    env_val="$(env_value "$key" "$env_file")"
    if [[ -z "$env_val" ]]; then
        fail "$label: $key not found in $env_file"
        return
    fi
    # The manifests carry a RANGE, the pin carries a bare version. ">=" is the
    # whole of the translation, and it is asserted rather than parsed: accepting
    # any range that happens to admit the pin (">=22", "^22") would let the two
    # numbers differ while the check stayed green, which is the drift itself.
    want=">=$env_val"
    for pkg in "$@"; do
        got="$(engines_node "$pkg")"
        if [[ -z "$got" ]]; then
            fail "$label: engines.node not found in $pkg"
            bad=1
            continue
        fi
        if [[ "$got" != "$want" ]]; then
            fail "$label: $key floor mismatch -- $env_file has '$env_val' so engines.node must be '$want', but $pkg has '$got'"
            bad=1
        fi
    done
    if [[ $bad -eq 0 ]]; then
        pass "$label: $key='$env_val' matches engines.node '$want' in all $n manifest(s)"
    fi
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

    # --- NODE_VERSION_MIN controls ------------------------------------------
    #
    # BY CONSTRUCTION, and note the fixture floor is 22.44.0 rather than the real
    # one. That is not squeamishness: check-toolchain-pins.sh's A1 greps every
    # .ci/**/*.sh for a literal copy of any value in toolchain.env, so writing
    # the true floor into a fixture here would make THIS file report as a second
    # definition of it. A control that breaks another gate gets deleted.
    printf 'NODE_VERSION_MIN=22.44.0\n' >"$tmp/floor.env"
    printf '{"engines":{"node":">=22.44.0"}}\n' >"$tmp/root.json"
    printf '{"engines":{"node":">=22.44.0"}}\n' >"$tmp/cli.json"

    out="$(check_engines_pair NODE_VERSION_MIN "$tmp/floor.env" CONTROL "$tmp/root.json" "$tmp/cli.json" 2>&1)"
    if [[ "$out" == *"matches"* ]]; then
        pass "control: a floor matching both manifests passes"
    else
        fail "control: agreeing manifests were wrongly flagged -- $out"
    fi

    # CONTROL: the exact bug this pair was added for -- a floor of 22.0.0 in the
    # manifests under a stricter pin. Both manifests are stale together, which is
    # what the composed "${NODE_VERSION}.0.0" line used to produce.
    printf '{"engines":{"node":">=22.0.0"}}\n' >"$tmp/root-old.json"
    printf '{"engines":{"node":">=22.0.0"}}\n' >"$tmp/cli-old.json"
    out="$(check_engines_pair NODE_VERSION_MIN "$tmp/floor.env" CONTROL "$tmp/root-old.json" "$tmp/cli-old.json" 2>&1)"
    if [[ "$out" == *"floor mismatch"* ]]; then
        pass "control: manifests stuck at an older floor are detected"
    else
        fail "control: a planted stale engines.node was NOT detected -- $out"
    fi

    # CONTROL: ONLY packages/cli drifts. The root manifest is what a developer
    # reads, so a check that stopped at the first match, or that only ever looked
    # at the root, would call this tree clean while the PUBLISHED CLI advertised
    # the wrong floor. The message must also name the file that is wrong.
    out="$(check_engines_pair NODE_VERSION_MIN "$tmp/floor.env" CONTROL "$tmp/root.json" "$tmp/cli-old.json" 2>&1)"
    if [[ "$out" == *"floor mismatch"* && "$out" == *"cli-old.json"* ]]; then
        pass "control: one manifest drifting alone is detected, and named"
    else
        fail "control: a cli-only floor drift went undetected or unnamed -- $out"
    fi

    # CONTROL: a `"node"` key OUTSIDE engines must not decide the verdict. This
    # is why engines_node parses instead of grepping; a first-match grep would
    # read the volta pin here and report a mismatch against a correct manifest.
    printf '{"volta":{"node":"18.0.0"},"engines":{"node":">=22.44.0"}}\n' >"$tmp/decoy.json"
    out="$(check_engines_pair NODE_VERSION_MIN "$tmp/floor.env" CONTROL "$tmp/decoy.json" 2>&1)"
    if [[ "$out" == *"matches"* ]]; then
        pass "control: a node version outside engines is not mistaken for the floor"
    else
        fail "control: a decoy node key outside engines changed the verdict -- $out"
    fi

    # CONTROL: a manifest with no engines block is a failure, not a silent skip
    # -- the same direction the missing-ARG case above fails in. Deleting
    # engines.node is exactly how someone would "fix" a red floor check.
    printf '{"name":"no-engines-here"}\n' >"$tmp/bare.json"
    out="$(check_engines_pair NODE_VERSION_MIN "$tmp/floor.env" CONTROL "$tmp/bare.json" 2>&1)"
    if [[ "$out" == *"not found"* ]]; then
        pass "control: a manifest with no engines.node is flagged, not skipped"
    else
        fail "control: a missing engines.node was not flagged -- $out"
    fi
}

echo "Toolchain env/Dockerfile sync (GO_VERSION, NODE_VERSION) + Node floor (NODE_VERSION_MIN)"
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

# The manifests are READ here and never written. This gate reports the drift and
# names the file to edit; it does not reach into package.json, because the two
# manifests are owned by npm tooling that rewrites them wholesale and a gate that
# edits one is a gate that loses a race with `npm pkg set`.
ROOT_PKG="$ROOT/package.json"
CLI_PKG="$ROOT/packages/cli/package.json"
for p in "$ROOT_PKG" "$CLI_PKG"; do
    [[ -r "$p" ]] || {
        fail "required subject missing: $p"
        exit 1
    }
done
check_engines_pair NODE_VERSION_MIN "$ENV_FILE" "node floor" "$ROOT_PKG" "$CLI_PKG"

if [[ $fails -gt 0 ]]; then
    echo "${RED}x $fails toolchain-env/Dockerfile mismatch(es)${NC}" >&2
    echo "  A NODE_VERSION_MIN mismatch is fixed in whichever file is wrong, not by" >&2
    echo "  loosening the pin: .devcontainer/toolchain.env holds the floor, and both" >&2
    echo "  package.json and packages/cli/package.json must carry engines.node" >&2
    echo "  '>=' + that value." >&2
    exit 1
fi

echo "${GREEN}✓ toolchain.env and Dockerfile agree on GO_VERSION and NODE_VERSION,${NC}"
echo "${GREEN}  and NODE_VERSION_MIN agrees with both engines.node floors${NC}"
