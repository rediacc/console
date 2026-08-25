#!/usr/bin/env bash
# Gate: every gate-tool version is defined ONCE, and nothing acquires unpinned.
#
# Why this exists. Measured 2026-08-25, before .devcontainer/toolchain.env: ruff
# was pinned in two places, PyYAML in four, and shfmt and shellcheck in none at
# all -- so the same gate reached different verdicts in different lanes. The
# host had shellcheck 0.9.0, the image had none, and CI used whatever the runner
# shipped. shfmt agreed across lanes only by luck.
#
#   A1  a pin's value appears in exactly one place
#   A2  nothing acquires a gate tool unpinned (@latest / releases/latest)
#   A3  the pins file itself is well-formed and non-trivial
#   A6  a gate that runs a pinned tool acquires it, rather than trusting PATH
#
# Controls are built by CONSTRUCTION -- fixtures written literally into a temp
# dir, never by substituting into real source -- so rewording a real file cannot
# silently void them (see .ci/scripts/quality/check-control-vacuity.sh).

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PINS="$ROOT/.devcontainer/toolchain.env"

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Files that may legitimately restate a pin: the pins file itself, and anything
# whose job is to talk ABOUT pins (this gate, its test, the resolver).
is_exempt() {
    case "$1" in
        .devcontainer/toolchain.env) return 0 ;;
        .ci/scripts/quality/check-toolchain-pins.sh) return 0 ;;
        .ci/scripts/test/gates/test-toolchain*.sh) return 0 ;;
        .ci/scripts/lib/toolchain.sh) return 0 ;;
        *) return 1 ;;
    esac
}

# --- A3 first: a malformed or tiny pins file makes everything else vacuous ----
if [[ ! -r "$PINS" ]]; then
    fail "A3. pins file missing: $PINS"
else
    n_keys="$(grep -cE '^[A-Z][A-Z0-9_]*=' "$PINS")"
    if [[ "$n_keys" -lt 5 ]]; then
        fail "A3. pins file defines only $n_keys key(s) -- a shrinking file must not read as a clean tree"
    elif grep -qE '^[A-Z][A-Z0-9_]*=.*[ "'"'"'$]' "$PINS"; then
        fail "A3. a pin value contains a quote, space or \$ -- the Dockerfile and \$GITHUB_ENV readers cannot parse that"
    else
        pass "A3. pins file defines $n_keys keys, all plain KEY=value"
    fi
fi

# --- A1. one definition per pin ----------------------------------------------
scan_corpus() {
    git -C "$ROOT" ls-files \
        '.github/workflows/*.yml' '.devcontainer/*' '.ci/**/*.sh' 'run.sh' 2>/dev/null
}

dupes=()
while IFS='=' read -r key value; do
    [[ -n "$key" && -n "$value" ]] || continue
    # NODE_VERSION/GO_VERSION are also expressed as bare majors by third-party
    # actions (actions/setup-node) and by go.mod, which are not ours to unify.
    case "$key" in NODE_VERSION | GO_VERSION) continue ;; esac
    while IFS= read -r rel; do
        [[ -n "$rel" ]] || continue
        is_exempt "$rel" && continue
        [[ -f "$ROOT/$rel" ]] || continue
        # A line that names the KEY is reading the pin, not restating it.
        # COMMENTS ARE NOT DEFINITIONS. An earlier draft flagged this gate's own
        # measurement notes and a checksum URL containing the version -- prose
        # ABOUT a pin, not a second copy of it. Flagging prose would push someone
        # to delete the evidence for a rule in order to satisfy the rule, so
        # comment lines are stripped before the comparison.
        if grep -F "$value" "$ROOT/$rel" 2>/dev/null |
            grep -vE '^[[:space:]]*#' | grep -qvF "$key"; then
            dupes+=("$rel restates $key=$value")
        fi
    done < <(scan_corpus)
done < <(grep -E '^[A-Z][A-Z0-9_]*=' "$PINS")

scanned="$(scan_corpus | wc -l | tr -d ' ')"
if [[ "$scanned" -eq 0 ]]; then
    fail "A1. scanned ZERO files -- the glob matched nothing, so this assertion is vacuous"
elif [[ ${#dupes[@]} -eq 0 ]]; then
    pass "A1. no pin value is restated across $scanned file(s)"
else
    fail "A1. a pin is defined in more than one place:"
    printf '     %s\n' "${dupes[@]}" >&2
fi

# --- A2. nothing acquires a gate tool unpinned -------------------------------
# Only the tools a GATE depends on. Editor tooling (gopls, dlv, staticcheck,
# golangci-lint, goimports) is deliberately out: nothing gates on its output, so
# pinning it would buy churn rather than consistency.
GATED_TOOLS='shfmt|shellcheck|ruff|actionlint'
unpinned=()
while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    is_exempt "$rel" && continue
    [[ -f "$ROOT/$rel" ]] || continue
    while IFS= read -r line; do
        case "$line" in \#*) continue ;; esac
        unpinned+=("$rel: ${line#"${line%%[![:space:]]*}"}")
    done < <(grep -hE "(${GATED_TOOLS})[^ ]*@latest|releases/latest/download[^ ]*(${GATED_TOOLS})" "$ROOT/$rel" 2>/dev/null)
done < <(scan_corpus)

if [[ ${#unpinned[@]} -eq 0 ]]; then
    pass "A2. no gate tool is acquired unpinned"
else
    fail "A2. a gate tool is acquired without a version:"
    printf '     %s\n' "${unpinned[@]}" >&2
fi

# --- A6. a gate that runs a pinned tool acquires it --------------------------
# The host is where this matters: nobody controls PATH there, so a bare
# `command -v` as the last word lets a stale binary decide the verdict.
missing_acq=()
for g in .ci/scripts/security/shfmt.sh .ci/scripts/security/shellcheck.sh; do
    [[ -f "$ROOT/$g" ]] || continue
    grep -q 'toolchain_acquire' "$ROOT/$g" || missing_acq+=("$g")
done
if [[ ${#missing_acq[@]} -eq 0 ]]; then
    pass "A6. each pinned-tool gate acquires its tool at the pin"
else
    fail "A6. these trust PATH instead of acquiring at the pin: ${missing_acq[*]}"
fi

# --- controls, by construction ------------------------------------------------
mkdir -p "$TMP/c"
printf 'RUFF_VERSION=9.9.9\n' >"$TMP/c/pins.env"
printf 'run: pip install "ruff==9.9.9"\n' >"$TMP/c/restates.yml"
if grep -F '9.9.9' "$TMP/c/restates.yml" | grep -qvF 'RUFF_VERSION'; then
    pass "control: a restated pin value is detectable"
else
    fail "A1 CONTROL DID NOT FIRE: a restated value went undetected"
fi
printf 'run: pip install "ruff==${RUFF_VERSION}"\n' >"$TMP/c/reads.yml"
if grep -F '9.9.9' "$TMP/c/reads.yml" | grep -qvF 'RUFF_VERSION'; then
    fail "A1 IS OVER-BROAD: a line READING the pin was flagged as restating it"
else
    pass "control: a line reading the pin is not flagged"
fi
printf 'go install mvdan.cc/sh/v3/cmd/shfmt@latest\n' >"$TMP/c/unpinned.sh"
if grep -qE "(${GATED_TOOLS})[^ ]*@latest" "$TMP/c/unpinned.sh"; then
    pass "control: an unpinned gate-tool install is detectable"
else
    fail "A2 CONTROL DID NOT FIRE: @latest went undetected"
fi
printf 'go install golang.org/x/tools/gopls@latest\n' >"$TMP/c/editor.sh"
if grep -qE "(${GATED_TOOLS})[^ ]*@latest" "$TMP/c/editor.sh"; then
    fail "A2 IS OVER-BROAD: editor tooling was flagged as a gate tool"
else
    pass "control: editor tooling at @latest is not flagged"
fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "${GREEN}✓${NC} toolchain pins: single-sourced across $scanned file(s)."
    echo "  Blind spot, stated so a green is not read as more than it is: A1 is a"
    echo "  LITERAL scan, so a pin written 0.16 against a value of 0.16.1 escapes it."
    exit 0
fi
echo "${RED}✗${NC} toolchain pins: $fails failure(s)."
exit 1
