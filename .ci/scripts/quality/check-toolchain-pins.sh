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

# --- A8. a WORKFLOW must not invoke a pinned tool directly -------------------
#
# A2 catches unpinned ACQUISITION (`@latest`). This catches unpinned USE: a
# workflow step that runs `shfmt -d .` itself, instead of running the gate
# script that resolves the tool at the pin, would silently lint with whatever
# the runner image happens to ship. Nothing does that today; this exists so
# nothing starts.
#
# NOTE ON SHAPE, because it is the opposite of what it may look like: a workflow
# invoking a gate SCRIPT directly (`run: .ci/scripts/security/shfmt.sh`) is the
# REQUIRED pattern here -- scripts/check-ci-parity.ts enforces three-point wiring
# in which the workflow step names the script. It is invoking the TOOL that is
# forbidden, not invoking the script.
wf_direct=()
while IFS= read -r hit; do
    [[ -n "$hit" ]] && wf_direct+=("$hit")
done < <(
    grep -nE "^[[:space:]]*(run:|-)?[[:space:]]*[^#]*(^|[;&|[:space:]])(${GATED_TOOLS})[[:space:]]+-" \
        "$ROOT"/.github/workflows/*.yml 2>/dev/null |
        grep -vE "\.sh|install|--version|uvx|name:|#" || true
)
if [[ ${#wf_direct[@]} -eq 0 ]]; then
    pass "A8. no workflow invokes a pinned tool directly"
else
    fail "A8. a workflow runs a pinned tool itself instead of via its gate script:"
    printf '     %s\n' "${wf_direct[@]}" >&2
fi

# A8 controls, by construction. mkdir first: the shared fixture dir is created
# in the controls section further down, and writing before it exists made these
# silently write nothing -- the control then reported DID NOT FIRE, which is the
# correct direction for that mistake to fail in.
mkdir -p "$TMP/c"
printf '        run: shfmt -d .\n' >"$TMP/c/wf-direct.yml"
if grep -qE "(^|[;&|[:space:]])(${GATED_TOOLS})[[:space:]]+-" "$TMP/c/wf-direct.yml"; then
    pass "A8 control: a workflow running the tool directly is detected"
else
    fail "A8 CONTROL DID NOT FIRE: a direct tool invocation went undetected"
fi
printf '        run: .ci/scripts/security/shfmt.sh\n' >"$TMP/c/wf-script.yml"
if grep -E "(^|[;&|[:space:]])(${GATED_TOOLS})[[:space:]]+-" "$TMP/c/wf-script.yml" |
    grep -qvE "\.sh|install|--version|uvx"; then
    fail "A8 IS OVER-BROAD: running the gate SCRIPT was flagged, and that is the required pattern"
else
    pass "A8 control: invoking the gate script is not flagged"
fi

# --- A6. a gate that runs a pinned tool acquires it --------------------------
# The host is where this matters: nobody controls PATH there, so a bare
# `command -v` as the last word lets a stale binary decide the verdict.
missing_acq=()
# DISCOVERED, not hardcoded. This named shfmt.sh and shellcheck.sh literally,
# so a THIRD gate invoking a pinned tool escaped the rule entirely -- the
# assertion kept passing while the invariant rotted. Tracked AND untracked,
# because `git ls-files` alone is blind to a gate not yet committed: proven by
# planting one, which A6 then said nothing about. Same blind spot
# .ci/scripts/security/shellcheck.sh:68 documents for its own enumerator.
while IFS= read -r g; do
    [[ -n "$g" ]] || continue
    [[ -f "$ROOT/$g" ]] || continue
    is_exempt "$g" && continue
    # PROSE IS NOT AN INVOCATION, and an echoed string is prose too. Comments
    # were already stripped for exactly this reason ("judge the code, not the
    # words describing it"); a line whose command is `echo`/`printf` only PRINTS
    # the tool's name -- as advice in a failure message, or into a control
    # fixture -- and running it invokes nothing.
    #
    # Measured 2026-08-26 (run 32907xxx, Quality / Code): A6 flagged
    # check-shell-size.sh, whose only two matches were
    #   echo "         # shellcheck extended-analysis=false"
    #   echo '# shellcheck extended-analysis=false'
    # i.e. the directive it TELLS you to add. It never runs shellcheck at all,
    # so demanding it acquire shellcheck at the pin was incoherent.
    #
    # Only a line whose FIRST word is echo/printf and that carries no command
    # separator is dropped: `echo x; shfmt y` still gets scrutinised, so this
    # narrows the false-positive without opening a bypass.
    grep -vE '^[[:space:]]*#' "$ROOT/$g" |
        grep -vE '^[[:space:]]*(echo|printf)[[:space:]][^;&|]*$' |
        grep -qE "(^|[;&|(]|[[:space:]])(${GATED_TOOLS})[[:space:]]" || continue
    # RESOLVING at a pin, not merely NAMING one. The first version accepted any
    # `*_VERSION` mention, and check-python-lint.sh passed it while still taking
    # an unversioned `command -v ruff` from PATH -- the assertion was satisfied
    # by a variable that the acquisition path never consulted.
    grep -qE 'toolchain_acquire|toolchain_check|ensure_actionlint' "$ROOT/$g" ||
        missing_acq+=("$g")
done < <(
    git -C "$ROOT" ls-files '.ci/scripts/quality/*.sh' '.ci/scripts/security/*.sh' 2>/dev/null
    git -C "$ROOT" ls-files --others --exclude-standard '.ci/scripts/quality/*.sh' '.ci/scripts/security/*.sh' 2>/dev/null
)
if [[ ${#missing_acq[@]} -eq 0 ]]; then
    pass "A6. each pinned-tool gate acquires its tool at the pin"
else
    fail "A6. these trust PATH instead of acquiring at the pin: ${missing_acq[*]}"
fi

# --- A9. a pin must RESOLVE, not merely exist --------------------------------
# A1-A8 are source scans, and every one of them was green while this was broken:
# toolchain_pin_for printed "" AND RETURNED 0 whenever the pins had not been
# loaded, because sourcing toolchain.sh does not populate them. The empty value
# then travelled into a download URL. Measured 2026-08-26 in a fresh shell:
#
#   .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404
#
# The 404 names GitHub, so the symptom points away from the cause. No textual
# assertion could have caught this: the source looked correct and the defect
# lived in what the function RETURNED. So A9 executes it, in a subshell that
# sources nothing but the library -- which is exactly the caller that broke.
a9_bad=()
for t in shfmt shellcheck ruff actionlint go node; do
    v="$(bash -c "source '$ROOT/.ci/scripts/lib/toolchain.sh'; toolchain_pin_for $t" 2>/dev/null || true)"
    [[ -n "$v" ]] || a9_bad+=("$t")
done
if [[ ${#a9_bad[@]} -eq 0 ]]; then
    pass "A9. every pin resolves to a non-empty value from a bare source"
else
    fail "A9. these pins resolve EMPTY (did toolchain_load run?): ${a9_bad[*]}"
fi

# A9 control, BY CONSTRUCTION: a copy of the library plus an APPENDED no-op
# override of toolchain_load. Appending cannot silently fail to apply the way a
# pattern substitution can when the targeted line is later reworded.
mkdir -p "$TMP/a9"
cp "$ROOT/.ci/scripts/lib/toolchain.sh" "$TMP/a9/toolchain.sh"
printf '\ntoolchain_load() { return 0; }\n' >>"$TMP/a9/toolchain.sh"
if grep -q 'toolchain_load() { return 0; }' "$TMP/a9/toolchain.sh"; then
    ctl="$(bash -c "source '$TMP/a9/toolchain.sh'; toolchain_pin_for shellcheck" 2>/dev/null || true)"
    if [[ -z "$ctl" ]]; then
        pass "A9 control: a library that skips the load is detectable"
    else
        fail "A9 CONTROL DID NOT FIRE: the mutant still resolved a pin ('$ctl')"
    fi
else
    fail "A9 CONTROL WAS NOT PLANTED: the mutant library is unmodified"
fi

# --- A10. all THREE readers must still READ the pins -------------------------
# A3 proves the file is PARSEABLE by three readers. Nothing proved they still
# read it. Delete the `. toolchain.env` from constants.sh, or the COPY from the
# Dockerfile, or the --env step from the workflow, and every assertion above
# stays green while the pins go back to being decorative -- which is the exact
# state this whole file exists to end. The three-point wiring is the invariant;
# asserting the parts individually never asserted the unit.
#
# Each reader is checked for the mechanism it actually uses, not for the string
# "toolchain.env": a COMMENT mentioning the file would otherwise satisfy the
# rule, and every one of these three files has several such comments.
a10_bad=()
CONSTS="$ROOT/.ci/config/constants.sh"
DOCKERFILE="$ROOT/.devcontainer/Dockerfile"

# bash: constants.sh must SOURCE it, not merely name it.
[[ -f "$CONSTS" ]] || a10_bad+=("constants.sh is missing entirely")
if [[ -f "$CONSTS" ]]; then
    grep -vE '^[[:space:]]*#' "$CONSTS" |
        grep -qE '(\.|source)[[:space:]]+"?\$\{?_REDIACC_TOOLCHAIN_ENV' ||
        a10_bad+=("constants.sh no longer sources the pins file")
fi

# Docker: the image must COPY it in, or the container's tools are unpinned.
[[ -f "$DOCKERFILE" ]] || a10_bad+=("Dockerfile is missing entirely")
if [[ -f "$DOCKERFILE" ]]; then
    grep -vE '^[[:space:]]*#' "$DOCKERFILE" |
        grep -qE '^[[:space:]]*COPY[[:space:]]+toolchain\.env' ||
        a10_bad+=("Dockerfile no longer COPYs toolchain.env into the image")
fi

# Actions: some workflow must feed the pins into $GITHUB_ENV. Via --env, never
# a bare `cat`: $GITHUB_ENV accepts only KEY=value and would choke on the
# comments, which is why the emitter exists at all.
grep -rlE 'toolchain\.sh[[:space:]]+--env[[:space:]]*>>[[:space:]]*"?\$\{?GITHUB_ENV' \
    "$ROOT/.github/workflows" >/dev/null 2>&1 ||
    a10_bad+=("no workflow feeds the pins into \$GITHUB_ENV via toolchain.sh --env")

if [[ ${#a10_bad[@]} -eq 0 ]]; then
    pass "A10. all three readers (bash, Docker, Actions) still read the pins"
else
    fail "A10. a pin reader went dark, so the pins are decorative for that lane:"
    printf '         %s\n' "${a10_bad[@]}"
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
# A6 control, by construction: an unpinned invoker is caught, a pinned one is not.
printf '#!/usr/bin/env bash\nshellcheck -S warning foo.sh\n' >"$TMP/c/unpinned-gate.sh"
if grep -vE '^[[:space:]]*#' "$TMP/c/unpinned-gate.sh" |
    grep -qE "(^|[;&|(]|[[:space:]])(${GATED_TOOLS})[[:space:]]" &&
    ! grep -qE 'toolchain_acquire|toolchain_check|[A-Z]+_VERSION' "$TMP/c/unpinned-gate.sh"; then
    pass "A6 control: a gate invoking a tool with no pin is detected"
else
    fail "A6 CONTROL DID NOT FIRE: an unpinned tool invocation went undetected"
fi
printf '#!/usr/bin/env bash\nBIN="$(toolchain_acquire shellcheck)"\n' >"$TMP/c/pinned-gate.sh"
if grep -qE 'toolchain_acquire|toolchain_check|[A-Z]+_VERSION' "$TMP/c/pinned-gate.sh"; then
    pass "A6 control: a gate that resolves at the pin is not flagged"
else
    fail "A6 IS OVER-BROAD: a correctly pinned gate was flagged"
fi

# A10 controls, by construction: a reader that only MENTIONS the pins file in a
# comment must not satisfy the rule, and a real one must not be flagged.
mkdir -p "$TMP/a10"
printf '# we load .devcontainer/toolchain.env somewhere else\necho hi\n' >"$TMP/a10/fake-consts.sh"
if grep -vE '^[[:space:]]*#' "$TMP/a10/fake-consts.sh" |
    grep -qE '(\.|source)[[:space:]]+"?\$\{?_REDIACC_TOOLCHAIN_ENV'; then
    fail "A10 CONTROL DID NOT FIRE: a comment mentioning the pins file counted as reading it"
else
    pass "A10 control: a comment mentioning the pins file does not count as reading it"
fi
printf '# real\n. "${_REDIACC_TOOLCHAIN_ENV}"\n' >"$TMP/a10/real-consts.sh"
if grep -vE '^[[:space:]]*#' "$TMP/a10/real-consts.sh" |
    grep -qE '(\.|source)[[:space:]]+"?\$\{?_REDIACC_TOOLCHAIN_ENV'; then
    pass "A10 control: a genuine source line is recognised"
else
    fail "A10 IS OVER-BROAD: a real source of the pins file was not recognised"
fi
printf '# COPY toolchain.env -- described, not done\nRUN true\n' >"$TMP/a10/Dockerfile"
if grep -vE '^[[:space:]]*#' "$TMP/a10/Dockerfile" | grep -qE '^[[:space:]]*COPY[[:space:]]+toolchain\.env'; then
    fail "A10 CONTROL DID NOT FIRE: a commented-out COPY counted as copying"
else
    pass "A10 control: a commented-out COPY does not count"
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
