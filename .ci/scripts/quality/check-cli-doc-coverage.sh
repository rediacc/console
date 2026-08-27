#!/usr/bin/env bash
# Gate: every CLI flag a script actually has is taught in its canonical doc.
#
# Why this exists. check-ci-watch-recipe.sh's Check G did this for exactly one
# pair (ci-trace.py / ci-watch's SKILL.md) and immediately found two real,
# previously-invisible gaps (--until-final, --timeout) the moment it ran.
# Generalized here (2026-08-27) to a second real pair found by the same sweep:
# scripts/ci-runner/run.ts's hand-rolled `switch (arg) { case '--flag': }`
# parser against docs/agent-reference/ci-gates.md's flag table, which was
# ALSO missing three real flags (--heavy-limit, --manifest, --list) the moment
# this ran against it.
#
# Deliberately NOT folded into every self-improving skill: `testing`
# (.claude/skills/testing/SKILL.md) is a pure router across six docs with no
# single script whose CLI surface it owns, so there is nothing to flag-diff
# there. And `rdc`'s CLI docs already have their own, different mechanism
# (scripts/check-cli-docs.ts, generation-based, checks the OPPOSITE direction
# -- no stale flag mentioned that doesn't exist) -- not reinvented here.
#
# Extraction is genuinely per-script-family: Python argparse and this repo's
# own hand-rolled TS switch/case parser look nothing alike on the page, so
# each PAIRS row names which extractor reads it, rather than one regex
# pretending to cover both.
#
# Controls are built by CONSTRUCTION (a real doc copy with one real flag's
# mention stripped), never by pattern-substituting real source, so rewording
# a target cannot silently void them -- check-control-vacuity.sh exists to
# catch a control that cannot fire.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# label|script_rel|doc_rel|extractor
PAIRS=(
    "ci-trace|.ci/scripts/ci/ci-trace.py|.claude/skills/ci-watch/SKILL.md|python_argparse"
    "ci-runner|scripts/ci-runner/run.ts|docs/agent-reference/ci-gates.md|ts_switch_case"
)

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

# extract_python_argparse <script> -- flags on stdout, one per line, sorted.
#
# Scoped to the line AFTER each `add_argument(` call, not every quoted
# `--flag` in the file: a bare `grep -oE '"--[a-z-]+"'` over the whole script
# also matches internal subprocess flags the script shells out to (git's
# `--abbrev-ref`, gh's `--repo`), which are not the script's own CLI surface
# at all. Verified against ci-trace.py directly before trusting it.
extract_python_argparse() {
    grep -A1 "add_argument(" "$1" | grep -oE '"--[a-z][a-z-]*"' | tr -d '"' | sort -u
}

# extract_ts_switch_case <script> -- flags on stdout, one per line, sorted.
#
# Matches this repo's OWN hand-rolled `switch (arg) { case '--flag': ... }`
# CLI parsers (no Commander/yargs in this codebase's own tooling scripts).
extract_ts_switch_case() {
    grep -oE "case '--[a-zA-Z][a-zA-Z-]*'" "$1" | sed "s/^case '//; s/'\$//" | sort -u
}

# check_pair <label> <script_rel> <doc_rel> <extractor> -- one check + one
# construction-built control, both against files under $ROOT.
check_pair() {
    local label="$1" script_rel="$2" doc_rel="$3" extractor="$4"
    local script="$ROOT/$script_rel" doc="$ROOT/$doc_rel"

    if [ ! -f "$script" ]; then
        fail "$label: $script_rel is missing"
        return
    fi
    if [ ! -f "$doc" ]; then
        fail "$label: $doc_rel is missing"
        return
    fi

    local flags=() flag
    while IFS= read -r flag; do
        [ -n "$flag" ] || continue
        flags+=("$flag")
    done < <("extract_$extractor" "$script")

    if [ "${#flags[@]}" -eq 0 ]; then
        fail "$label: found ZERO flags in $script_rel -- the extraction broke, not the script"
        return
    fi

    local missing=()
    for flag in "${flags[@]}"; do
        grep -qF -- "$flag" "$doc" || missing+=("$flag")
    done
    if [ "${#missing[@]}" -eq 0 ]; then
        pass "$label: every one of ${#flags[@]} CLI flag(s) in $script_rel is taught in $doc_rel"
    else
        fail "$label: $doc_rel does not mention: ${missing[*]} -- a flag that exists but is" \
            "never taught is invisible to any session reading only the doc"
    fi

    # CONTROL, built by construction: a REAL copy of the doc with one real
    # flag's only mention replaced, not a synthetic fixture -- the extraction
    # above must fire on it, or this check proves nothing.
    local fixture="$TMP/$label-doc-missing-flag"
    cp "$doc" "$fixture"
    local target=""
    for flag in "${flags[@]}"; do
        if grep -qF -- "$flag" "$fixture"; then
            target="$flag"
            break
        fi
    done
    if [ -z "$target" ]; then
        fail "$label control: no flag found in the doc to remove -- the fixture cannot test anything"
        return
    fi
    sed -i "s/${target//-/\\-}/REDACTED/g" "$fixture"
    local ctrl_missing=()
    for flag in "${flags[@]}"; do
        grep -qF -- "$flag" "$fixture" || ctrl_missing+=("$flag")
    done
    if [[ " ${ctrl_missing[*]} " == *" $target "* ]]; then
        pass "$label control: removing $target's only mention is detected"
    else
        fail "$label control: removing $target's only mention was NOT detected -- the check cannot fail"
    fi
}

if [ "${#PAIRS[@]}" -eq 0 ]; then
    fail "PAIRS is empty -- the registry broke, not the docs"
fi

for row in "${PAIRS[@]}"; do
    IFS='|' read -r label script_rel doc_rel extractor <<<"$row"
    check_pair "$label" "$script_rel" "$doc_rel" "$extractor"
done

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} cli-doc-coverage: ${#PAIRS[@]} pair(s) clean."
    echo "  Blind spot: this checks that a flag's NAME is mentioned somewhere in the"
    echo "  doc, not that the mention is accurate, current, or in the right place."
    exit 0
fi
echo "${RED}✗${NC} cli-doc-coverage: $fails failure(s)."
exit 1
