#!/usr/bin/env bash
# Gate: the enforcement layer cannot quietly disarm itself.
#
# WHY. Everything this repo relies on to stop an agent doing the wrong thing is a
# hook, and until 2026-08-25 nothing guarded the hooks themselves.
# block-protected-files.sh covers settings.json and pre-commit-check.sh only, and
# only against restore/checkout/rm. One session changed 5 hook files across 6
# commits with no friction at all. A session that finds a guard inconvenient can
# weaken it AND delete its controls in the same commit, and CI stays green.
#
# The operator chose gate-plus-warning over blocking the commit (a hard block
# would have fired six times that day on legitimate work), so the teeth are here.
#
# Two assertions:
#
#   A. INVENTORY IS SHRINK-ONLY. Every pre-bash/block-*.sh appears in the
#      baseline. A guard that leaves the tree fails until the baseline is
#      deliberately drained, so removing a guard is a reviewable diff rather
#      than a side effect.
#   B. BOTH DIRECTIONS COVERED. Each guard needs a case asserting it BLOCKS and
#      one asserting it ALLOWS. Block-only coverage cannot detect over-blocking,
#      and an over-blocking guard is one that gets deleted -- which is how the
#      rule dies. Guards that lack a direction TODAY are listed in the coverage
#      baseline: it can shrink, never grow.
#
# Controls are built by CONSTRUCTION (fixtures written literally), so rewording a
# real guard cannot silently void them -- the failure check-control-vacuity.sh
# exists to catch.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
GUARD_DIR="$ROOT/.claude/hooks/pre-bash"
SUITE="$ROOT/.claude/hooks/test-hooks.sh"
INV="$ROOT/scripts/data/hook-inventory-baseline.json"
COV="$ROOT/scripts/data/hook-coverage-baseline.json"

RED=''; GREEN=''; NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'; fi
fails=0
fail() { echo "${RED}✗${NC} $*" >&2; fails=$((fails + 1)); }
pass() { echo "${GREEN}ok${NC}   $*"; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Directions covered for one guard, counting the inline suite AND any dedicated
# test file beside the guard. A guard with its own test-<name>.py is covered in
# both directions by definition -- those files exist to assert exactly that.
directions() { # directions <guard-basename> <suite-file> <guard-dir> -> "block allow"
    local n="$1" suite="$2" gdir="$3" b=0 a=0 stem="${1%.sh}"
    b=$(grep -c "check 2 pre-bash/$n" "$suite" 2>/dev/null || true)
    a=$(grep -c "check 0 pre-bash/$n" "$suite" 2>/dev/null || true)
    if [ -f "$gdir/test-$stem.py" ] || [ -f "$gdir/test-$stem.sh" ]; then b=$((b + 1)); a=$((a + 1)); fi
    echo "$b $a"
}

# ---- A. inventory is shrink-only -------------------------------------------
mapfile -t on_disk < <(cd "$GUARD_DIR" && ls block-*.sh 2>/dev/null | sort)
if [ ${#on_disk[@]} -eq 0 ]; then
    fail "A. found ZERO guards on disk -- this gate is not seeing the tree."
elif [ ! -f "$INV" ]; then
    fail "A. inventory baseline missing: $INV"
else
    missing=()
    while IFS= read -r want; do
        [ -n "$want" ] || continue
        [ -f "$GUARD_DIR/$want" ] || missing+=("$want")
    done < <(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$INV")
    if [ ${#missing[@]} -eq 0 ]; then
        pass "A. all $(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$INV") baselined guard(s) still present (${#on_disk[@]} on disk)"
    else
        fail "A. guard(s) in the baseline but GONE from the tree: ${missing[*]}"
        echo "     Removing a guard is a deliberate act: drain the baseline in the same commit and say why." >&2
    fi
fi

# ---- B. both directions ------------------------------------------------------
if [ ! -f "$COV" ]; then
    fail "B. coverage baseline missing: $COV"
else
    known="$(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$COV")"
    newly=()
    for g in "${on_disk[@]}"; do
        read -r b a <<<"$(directions "$g" "$SUITE" "$GUARD_DIR")"
        if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
            continue
        fi
        grep -qx "$g" <<<"$known" || newly+=("$g(block=$b,allow=$a)")
    done
    if [ ${#newly[@]} -eq 0 ]; then
        pass "B. no guard lost a direction ($(wc -l <<<"$known" | tr -d ' ') known gap(s) still baselined)"
    else
        fail "B. guard(s) newly missing a direction: ${newly[*]}"
        echo "     A guard with only block-cases cannot detect OVER-blocking, and an" >&2
        echo "     over-blocking guard is one that gets deleted. Add the missing case." >&2
    fi
    # Shrink-only: a baselined guard that now has both directions must be drained.
    drained=()
    while IFS= read -r g; do
        [ -n "$g" ] || continue
        [ -f "$GUARD_DIR/$g" ] || continue
        read -r b a <<<"$(directions "$g" "$SUITE" "$GUARD_DIR")"
        [ "$b" -gt 0 ] && [ "$a" -gt 0 ] && drained+=("$g")
    done <<<"$known"
    if [ ${#drained[@]} -gt 0 ]; then
        fail "B. these now have BOTH directions and must leave the coverage baseline: ${drained[*]}"
        echo "     The baseline is shrink-only; a fixed entry left in it hides the next regression." >&2
    fi
fi

# ---- controls, by construction ----------------------------------------------
mkdir -p "$TMP/guards"
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/guards/block-fixture-both.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/guards/block-fixture-blockonly.sh"
{
    echo 'check 2 pre-bash/block-fixture-both.sh "x" "blocks"'
    echo 'check 0 pre-bash/block-fixture-both.sh "y" "allows"'
    echo 'check 2 pre-bash/block-fixture-blockonly.sh "x" "blocks"'
} > "$TMP/suite.sh"

read -r b a <<<"$(directions block-fixture-both.sh "$TMP/suite.sh" "$TMP/guards")"
if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
    pass "control: a guard with both directions is recognised as covered"
else
    fail "CONTROL DID NOT FIRE: a both-direction fixture read as uncovered (block=$b allow=$a)"
fi
read -r b a <<<"$(directions block-fixture-blockonly.sh "$TMP/suite.sh" "$TMP/guards")"
if [ "$a" -eq 0 ]; then
    pass "control: a block-only guard is detected as missing the allow direction"
else
    fail "CONTROL DID NOT FIRE: a block-only fixture read as covered, so B proves nothing"
fi
printf '' > "$TMP/guards/test-block-fixture-blockonly.py"
read -r b a <<<"$(directions block-fixture-blockonly.sh "$TMP/suite.sh" "$TMP/guards")"
if [ "$a" -gt 0 ]; then
    pass "control: a dedicated test file counts as covering both directions"
else
    fail "CONTROL DID NOT FIRE: a dedicated test file was not counted"
fi

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} hook integrity: ${#on_disk[@]} guard(s) present, none newly uncovered."
    echo "  Blind spot, stated so a green is not read as more than it is: this counts"
    echo "  CASES, not their quality. A guard whose two cases are both trivial passes"
    echo "  here; only reading them catches that."
    exit 0
fi
echo "${RED}✗${NC} hook integrity: $fails failure(s)."
exit 1
