#!/usr/bin/env bash
# Gate: a control-first gate that PLANTS its defect by pattern substitution must
# prove the plant landed before trusting the control.
#
# Why. A control-first gate earns its green by re-running its assertions against
# a copy of the source mutated to carry the original defect: if the mutant passes,
# the gate cannot detect what it exists for and fails itself. That argument has a
# hole when the mutation is a PATTERN substitution -- `${SRC//needle/replacement}`
# or `sed 's/needle/replacement/'`. Reword the line the needle matches and the
# substitution silently produces an identical copy. The control then "passes"
# against unmutated source and the gate reports a green that proves nothing.
#
# This is not hypothetical: on 2026-08-24 check-devcontainer-scripts.sh had exactly
# this happen when the line its A-control targeted was rewritten, and the gate
# announced CONTROL IS VACUOUS rather than going green -- because it had the guard
# this check now requires of every sibling.
#
# A control built by CONSTRUCTION rather than substitution (concatenating a known
# bad entry, injecting a key with python) cannot fail to apply, so it is exempt.
# The rule keys on how the mutant is BUILT, not on whether a control exists.
#
# Control-first itself: the control below strips a real gate's guard and requires
# this check to catch it.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
GATE_DIR="$ROOT/.ci/scripts/quality"

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

# Does this file run a control at all?
has_control() { grep -qE "CONTROL DID NOT FIRE|control could not plant|CONTROL IS VACUOUS|control_must_fail|^control\(\)" "$1"; }

# Does it build its control input by PATTERN SUBSTITUTION (the fragile kind)?
builds_by_substitution() {
    # Three shapes in use: bash pattern substitution, an inline `sed 's/…/…/'`,
    # and `sed -i "$expr"` where the expression is held in a variable (so no
    # literal s/// appears on the line). Missing the third mis-exempted the two
    # gates that motivated this check, which is the failure this comment exists
    # to stop repeating.
    # A PREFIX substitution CANNOT go vacuous, so it is not the fragile kind.
    # `s/^/.../` has an EMPTY needle anchored at line start: it always matches,
    # so it can never silently produce an identical copy -- which is the entire
    # failure this gate exists to catch. Two shapes in real use here:
    #   echo "$hits" | sed 's/^/         /'      indenting a message for display
    #   seq 1 N      | sed 's/^/echo /'          GENERATING a fixture from nothing
    # Neither mutates a copy of the subject, so neither has a plant that could
    # fail to land. Flagging them (measured 2026-08-26 on check-devbox-exec.sh
    # and check-shell-size.sh) demanded a proof-of-plant for a plant that does
    # not exist -- the same false-positive family as A6 reading an echoed string
    # as an invocation.
    grep -vE "sed [^&]*[[:punct:]]s[/@|#]\^[/@|#]" "$1" |
        grep -qE '\$\{[A-Za-z_][A-Za-z0-9_]*//|sed [^&]*[[:punct:]]s[/@|#]|sed -i'
}

# Does it prove the plant landed? Either shape counts:
#   [[ "$MUTANT" == "$SRC" ]]   -- substitution produced an identical copy
#   grep -q '<marker>' <mutant> -- the planted marker is present
proves_plant_landed() {
    grep -qE '\[\[ "\$[A-Za-z_][A-Za-z0-9_]*" == "\$[A-Za-z_][A-Za-z0-9_]*" \]\]' "$1" && return 0
    grep -qE 'grep -[a-z]*q[a-z]* .+(\$TMP|\$MUTANT|mutant|broken)' "$1" && return 0
    return 1
}

echo "check-control-vacuity: every pattern-substitution control proves its plant landed"

checked=0
exempt=0
for f in "$GATE_DIR"/check-*.sh; do
    [ -f "$f" ] || continue
    base="$(basename "$f")"
    [ "$base" = "check-control-vacuity.sh" ] && continue
    has_control "$f" || continue

    if ! builds_by_substitution "$f"; then
        exempt=$((exempt + 1))
        continue
    fi

    checked=$((checked + 1))
    if ! proves_plant_landed "$f"; then
        fail "$base builds its control by pattern substitution but never proves the plant landed."
        echo "      Reword the targeted line and its control passes against UNMUTATED source," >&2
        echo "      reporting a green that proves nothing. Add one of:" >&2
        echo "        [[ \"\$MUTANT\" == \"\$SRC\" ]] && fail '...could not plant its defect...'" >&2
        echo "        grep -q '<planted marker>' \"\$TMP/broken.sh\" || fail '...'" >&2
    fi
done

# ANTI-VACUITY, per .claude/skills/testing/gates.md: discovering zero inputs must
# FAIL. A corpus that silently collapses to nothing is exactly how this check
# would stop protecting anything while still printing a tick.
if [ "$checked" -eq 0 ]; then
    fail "no pattern-substitution controls found at all — the corpus collapsed to zero."
    echo "      Either the glob no longer matches the gate directory, or has_control/" >&2
    echo "      builds_by_substitution stopped recognising the shapes in use." >&2
fi

# ---------------------------------------------------------------------------
# CONTROL: strip a real gate's vacuity guard and require this check to catch it.
# Without this, a green above could mean "every gate complies" OR "the detector
# stopped recognising the guard shape", and those look identical.
# ---------------------------------------------------------------------------
CONTROL_TMP="$(mktemp -d)"
trap 'rm -rf "$CONTROL_TMP"' EXIT
CONTROL_SRC="$GATE_DIR/check-review-turn-capacity.sh"
if [ -f "$CONTROL_SRC" ]; then
    # Remove the `[[ "$MUTANT" == "$FN" ]]` guard, leaving the substitution intact.
    sed '/\[\[ "\$MUTANT" == "\$FN" \]\]/,+2d' "$CONTROL_SRC" >"$CONTROL_TMP/stripped.sh"
    if ! grep -qE '\$\{[A-Za-z_][A-Za-z0-9_]*//' "$CONTROL_TMP/stripped.sh"; then
        fail "CONTROL IS VACUOUS: the stripped copy lost its substitution too, so it proves nothing."
    elif proves_plant_landed "$CONTROL_TMP/stripped.sh"; then
        fail "CONTROL DID NOT FIRE: a gate with its vacuity guard removed was still judged compliant, so this check cannot detect the defect it exists for."
    fi
else
    fail "CONTROL SOURCE MISSING: $CONTROL_SRC is gone; repoint the control at another substitution-based gate."
fi

if [ "$fails" -ne 0 ]; then
    echo "" >&2
    echo "${RED}$fails gate(s) have a control that can go vacuous undetected.${NC}" >&2
    exit 1
fi

echo "${GREEN}✓${NC} $checked pattern-substitution control(s) prove their plant landed; $exempt built by construction (exempt)"
