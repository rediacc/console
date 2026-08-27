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
#   A. INVENTORY IS SHRINK-ONLY. Every block-*.sh in every audited chain appears
#      in the baseline. A guard that leaves the tree fails until the baseline is
#      deliberately drained, so removing a guard is a reviewable diff rather
#      than a side effect.
#   B. BOTH DIRECTIONS COVERED. Each guard needs a case asserting it BLOCKS and
#      one asserting it ALLOWS. Block-only coverage cannot detect over-blocking,
#      and an over-blocking guard is one that gets deleted -- which is how the
#      rule dies. Guards that lack a direction TODAY are listed in the coverage
#      baseline: it can shrink, never grow.
#
# ALL THREE CHAINS ARE AUDITED, and that is a 2026-08-27 repair of a hole this
# gate had from birth. GUARD_DIR was the single literal path .claude/hooks/
# pre-bash, so `pre-edit/` and `pre-ask/` were outside BOTH assertions --
# structurally invisible rather than merely uncovered. An audit found
# pre-edit/block-inline-python.sh sitting at 0 cases in either direction, a guard
# against code injection that this gate could never have flagged. Seven guards
# were in that position. Keys are chain-qualified (`pre-edit/block-x.sh`) so two
# chains can never collide on one basename.
#
# HELPER-DRIVEN CASES COUNT, which is the other half of that repair. The old
# reader grepped the literal string `check 2 pre-bash/<name>`, so the five
# `gh_case` cases for block-second-open-pr.sh and the four `_gc_run` cases for
# block-git-empty-commit.sh were invisible and both guards sat in the coverage
# baseline as gaps they had not been for months. A stale entry is not free: it is
# a slot where the NEXT regression hides. Helpers are resolved by reading the
# suite -- a function whose body names exactly one guard IS a case wrapper for
# that guard -- rather than from a hand-kept list that would rot the same way.
#
# Controls are built by CONSTRUCTION (fixtures written literally), so rewording a
# real guard cannot silently void them -- the failure check-control-vacuity.sh
# exists to catch.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HOOKS="$ROOT/.claude/hooks"
CHAINS=(pre-bash pre-edit pre-ask)
SUITE="$HOOKS/test-hooks.sh"
INV="$ROOT/scripts/data/hook-inventory-baseline.json"
COV="$ROOT/scripts/data/hook-coverage-baseline.json"

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

# covmap <suite-file> <hooks-root> -> lines of "<chain>/<name> <block> <allow>"
#
# Counts, per guard, cases asserting exit 2 and cases asserting exit 0, from
# three sources: direct `check`/`check_out` calls, calls to a helper function
# that wraps exactly one guard, and a dedicated test-<stem>.py|.sh beside the
# guard (which exists to assert both directions, so it counts as both).
covmap() {
    python3 - "$1" "$2" "${CHAINS[@]}" <<'PY'
import os, re, sys
suite_path, hooks_root = sys.argv[1], sys.argv[2]
chains = sys.argv[3:]
try:
    src = open(suite_path, encoding="utf-8", errors="replace").read()
except OSError:
    src = ""
chain_re = "|".join(re.escape(c) for c in chains)
guard_re = r"(?:%s)/[A-Za-z0-9_.-]+\.sh" % chain_re

counts = {}
def bump(guard, rc):
    b, a = counts.get(guard, (0, 0))
    counts[guard] = (b + (rc == "2"), a + (rc == "0"))

# 1. Direct case calls.
for rc, guard in re.findall(r"\b(?:check|check_out)\s+([0-9]+)\s+(%s)" % guard_re, src):
    bump(guard, rc)

# 2. Helper wrappers. A shell function whose body names exactly ONE guard under
#    $DIR is a case wrapper for it; its call sites take the expected rc first,
#    the same shape `check` uses. `check` and `check_out` themselves name their
#    guard through a VARIABLE, so they cannot match here and do not need
#    excluding by name.
for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{(.*?)^\}", src, re.M | re.S):
    fn, body = m.group(1), m.group(2)
    named = set(re.findall(r"\$DIR/(%s)" % guard_re, body))
    if len(named) != 1:
        continue
    guard = named.pop()
    for rc in re.findall(r"^[ \t]*%s\s+([0-9]+)\b" % re.escape(fn), src, re.M):
        bump(guard, rc)

# 3. A dedicated test file covers both directions by definition.
for chain in chains:
    d = os.path.join(hooks_root, chain)
    if not os.path.isdir(d):
        continue
    for name in sorted(os.listdir(d)):
        if not (name.startswith("block-") and name.endswith(".sh")):
            continue
        guard = "%s/%s" % (chain, name)
        b, a = counts.get(guard, (0, 0))
        stem = name[:-3]
        if any(os.path.exists(os.path.join(d, "test-%s%s" % (stem, ext))) for ext in (".py", ".sh")):
            b, a = b + 1, a + 1
        print(guard, b, a)
PY
}

# Guards on disk, chain-qualified. A glob, not `ls`: nothing to parse, and it
# cannot misread an odd filename.
on_disk=()
for _c in "${CHAINS[@]}"; do
    for _f in "$HOOKS/$_c"/block-*.sh; do
        [ -e "$_f" ] && on_disk+=("$_c/$(basename "$_f")")
    done
done

MAP="$TMP/covmap.txt"
covmap "$SUITE" "$HOOKS" >"$MAP"

lookup() { # lookup <chain/name> -> "block allow"
    awk -v g="$1" '$1 == g { print $2, $3; found = 1 } END { if (!found) print 0, 0 }' "$MAP"
}

# ---- A. inventory is shrink-only -------------------------------------------
if [ ${#on_disk[@]} -eq 0 ]; then
    fail "A. found ZERO guards on disk -- this gate is not seeing the tree."
elif [ ! -f "$INV" ]; then
    fail "A. inventory baseline missing: $INV"
else
    missing=()
    while IFS= read -r want; do
        [ -n "$want" ] || continue
        [ -f "$HOOKS/$want" ] || missing+=("$want")
    done < <(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$INV")
    if [ ${#missing[@]} -eq 0 ]; then
        pass "A. all $(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$INV") baselined guard(s) still present (${#on_disk[@]} on disk across ${#CHAINS[@]} chain(s))"
    else
        fail "A. guard(s) in the baseline but GONE from the tree: ${missing[*]}"
        echo "     Removing a guard is a deliberate act: drain the baseline in the same commit and say why." >&2
    fi
    # A guard on disk but absent from the inventory can be DELETED without A
    # noticing, which is the whole point of A. Six guards were in that state on
    # 2026-08-27 because nobody re-ran the baseline after adding them.
    unlisted=()
    listed="$(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$INV")"
    for g in "${on_disk[@]}"; do
        grep -qx "$g" <<<"$listed" || unlisted+=("$g")
    done
    if [ ${#unlisted[@]} -gt 0 ]; then
        fail "A. guard(s) on disk but NOT in the inventory: ${unlisted[*]}"
        echo "     Until listed, each of these can be deleted with no gate noticing." >&2
        echo "     Add them to $INV." >&2
    fi
fi

# ---- B. both directions ------------------------------------------------------
if [ ! -f "$COV" ]; then
    fail "B. coverage baseline missing: $COV"
else
    known="$(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$COV")"
    newly=()
    for g in "${on_disk[@]}"; do
        read -r b a <<<"$(lookup "$g")"
        if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
            continue
        fi
        grep -qx "$g" <<<"$known" || newly+=("$g(block=$b,allow=$a)")
    done
    if [ ${#newly[@]} -eq 0 ]; then
        pass "B. no guard lost a direction ($(grep -c . <<<"$known") known gap(s) still baselined)"
    else
        fail "B. guard(s) newly missing a direction: ${newly[*]}"
        echo "     A guard with only block-cases cannot detect OVER-blocking, and an" >&2
        echo "     over-blocking guard is one that gets deleted. Add the missing case." >&2
    fi
    # Shrink-only: a baselined guard that now has both directions must be drained.
    drained=()
    while IFS= read -r g; do
        [ -n "$g" ] || continue
        [ -f "$HOOKS/$g" ] || continue
        read -r b a <<<"$(lookup "$g")"
        [ "$b" -gt 0 ] && [ "$a" -gt 0 ] && drained+=("$g")
    done <<<"$known"
    if [ ${#drained[@]} -gt 0 ]; then
        fail "B. these now have BOTH directions and must leave the coverage baseline: ${drained[*]}"
        echo "     The baseline is shrink-only; a fixed entry left in it hides the next regression." >&2
    fi
fi

# ---- controls, by construction ----------------------------------------------
mkdir -p "$TMP/hooks/pre-bash" "$TMP/hooks/pre-edit"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/hooks/pre-bash/block-fixture-both.sh"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/hooks/pre-bash/block-fixture-blockonly.sh"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/hooks/pre-bash/block-fixture-helper.sh"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/hooks/pre-edit/block-fixture-editchain.sh"
cat >"$TMP/suite.sh" <<'FIXTURE'
check 2 pre-bash/block-fixture-both.sh "x" "blocks"
check 0 pre-bash/block-fixture-both.sh "y" "allows"
check 2 pre-bash/block-fixture-blockonly.sh "x" "blocks"
check_out 2 pre-edit/block-fixture-editchain.sh "x" "blocks" "needle"
check_out 0 pre-edit/block-fixture-editchain.sh "y" "allows" "needle"
fx_case() {
    local exp="$1"
    bash "$DIR/pre-bash/block-fixture-helper.sh" || true
}
fx_case 2 "wrapped block"
fx_case 0 "wrapped allow"
FIXTURE
covmap "$TMP/suite.sh" "$TMP/hooks" >"$TMP/fixture-map.txt"
fxlook() { awk -v g="$1" '$1 == g { print $2, $3; f = 1 } END { if (!f) print 0, 0 }' "$TMP/fixture-map.txt"; }

read -r b a <<<"$(fxlook pre-bash/block-fixture-both.sh)"
if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
    pass "control: a guard with both directions is recognised as covered"
else
    fail "CONTROL DID NOT FIRE: a both-direction fixture read as uncovered (block=$b allow=$a)"
fi
read -r b a <<<"$(fxlook pre-bash/block-fixture-blockonly.sh)"
if [ "$b" -gt 0 ] && [ "$a" -eq 0 ]; then
    pass "control: a block-only guard is detected as missing the allow direction"
else
    fail "CONTROL DID NOT FIRE: a block-only fixture read as covered, so B proves nothing (block=$b allow=$a)"
fi
# The pre-edit chain, and the check_out spelling, both of which the old reader
# was blind to. Its blindness is the reason this control exists.
read -r b a <<<"$(fxlook pre-edit/block-fixture-editchain.sh)"
if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
    pass "control: a pre-edit guard covered via check_out is seen"
else
    fail "CONTROL DID NOT FIRE: pre-edit/check_out coverage read as absent (block=$b allow=$a), which is exactly the hole this gate was widened to close"
fi
# A helper-wrapped guard. Counting only the literal `check N <guard>` reported
# two well-covered guards as gaps for months.
read -r b a <<<"$(fxlook pre-bash/block-fixture-helper.sh)"
if [ "$b" -gt 0 ] && [ "$a" -gt 0 ]; then
    pass "control: cases routed through a helper function are counted"
else
    fail "CONTROL DID NOT FIRE: helper-driven cases read as absent (block=$b allow=$a)"
fi
# NEGATIVE control: a guard with no case anywhere must read 0/0, or the three
# controls above would pass over a reader that simply says yes to everything.
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/hooks/pre-bash/block-fixture-uncovered.sh"
covmap "$TMP/suite.sh" "$TMP/hooks" >"$TMP/fixture-map.txt"
read -r b a <<<"$(fxlook pre-bash/block-fixture-uncovered.sh)"
if [ "$b" -eq 0 ] && [ "$a" -eq 0 ]; then
    pass "control: a guard with no cases reads 0/0 (the reader is not saying yes to everything)"
else
    fail "CONTROL DID NOT FIRE: an uncovered fixture reported coverage (block=$b allow=$a)"
fi
printf '' >"$TMP/hooks/pre-bash/test-block-fixture-blockonly.py"
covmap "$TMP/suite.sh" "$TMP/hooks" >"$TMP/fixture-map.txt"
read -r b a <<<"$(fxlook pre-bash/block-fixture-blockonly.sh)"
if [ "$a" -gt 0 ]; then
    pass "control: a dedicated test file counts as covering both directions"
else
    fail "CONTROL DID NOT FIRE: a dedicated test file was not counted"
fi

# A's second arm needs its own control, or "everything on disk is listed" is a
# sentence nothing tests. Six guards sat unlisted for weeks precisely because
# nothing asked. Built by construction: a fixture inventory with one name
# REMOVED, so the comparison has a known answer.
inv_unlisted() { # inv_unlisted <inventory-json> <name...> -> unlisted names
    local inv="$1" listed g
    shift
    listed="$(python3 -c 'import json,sys;[print(x) for x in json.load(open(sys.argv[1]))]' "$inv")"
    for g in "$@"; do
        grep -qx "$g" <<<"$listed" || printf '%s\n' "$g"
    done
}
printf '["pre-bash/block-a.sh", "pre-bash/block-b.sh"]\n' >"$TMP/inv-full.json"
printf '["pre-bash/block-a.sh"]\n' >"$TMP/inv-short.json"
if [ -z "$(inv_unlisted "$TMP/inv-full.json" pre-bash/block-a.sh pre-bash/block-b.sh)" ]; then
    pass "control: a complete inventory reports nothing unlisted"
else
    fail "CONTROL DID NOT FIRE: a complete inventory reported a missing entry"
fi
if [ "$(inv_unlisted "$TMP/inv-short.json" pre-bash/block-a.sh pre-bash/block-b.sh)" = "pre-bash/block-b.sh" ]; then
    pass "control: a guard on disk but absent from the inventory is named"
else
    fail "CONTROL DID NOT FIRE: an unlisted guard went unnamed, so A's second arm proves nothing"
fi

# ---- C. the anti-vacuity FLOOR cannot be removed ----------------------------
#
# test-hooks.sh runs sibling modules' `--selftest` and folds their PASS count
# into its own. Without a MINIMUM-COUNT floor, a selftest that prints nothing and
# exits 0 reads as a passing suite -- and that is not hypothetical twice over:
# `wl_git.py` and `wl_admit.py` carried 18 controls each that NOTHING ran for
# months, while `wl_reggate.py --selftest` exits 0 having no selftest at all,
# because running a library module as a script does nothing and succeeds.
#
# The floor is what separates those three states from a real pass, so the floor
# itself is enforcement, and this file's whole premise is that enforcement
# cannot quietly disarm itself. Deleting the floor is a one-line edit that turns
# every orphaned control back into a silent green.
HARNESS="$SUITE"
if [ ! -f "$HARNESS" ]; then
    fail "test-hooks.sh is missing; the selftest floor cannot be checked"
elif ! grep -q 'lt "\$floor"' "$HARNESS"; then
    fail "test-hooks.sh lost its selftest minimum-count FLOOR. Without it a module whose --selftest prints nothing and exits 0 counts as a passing suite, which is how 36 orphaned controls hid for months."
else
    pass "the selftest loop enforces a minimum control count"
fi

# EVERY selftest fold needs a floor, not just one, and counting is not enough to
# know that. A single `lt "$floor"` anywhere satisfied the check above while two
# folds (wl_roundlog, wl_planfid) added a sibling module's PASS count with no
# refusal at all -- the exact vacuous-green shape this section exists to
# prevent, in the very file it protects.
#
# Nor is a `floor` variable the only honest guard: five of the eight folds refuse
# a ZERO count instead (`-gt 0`, `-eq 0`), which is a floor of one and catches
# the same failure. So this looks at each fold SITE and asks whether some count
# refusal stands between the count and the addition. A gate demanding one exact
# spelling would have reported five correct folds as defects, and a gate that
# cries wolf is one the next session learns to route around.
floorcheck() { # floorcheck <harness> -> unfloored fold line numbers, one per line
    python3 - "$1" <<'FLOORPY'
import re, sys
try:
    lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
except OSError:
    sys.exit(0)
# A fold of a VARIABLE count. `PASS + 1` is a single case incrementing itself and
# needs no floor; `PASS + n` folds in a whole sibling suite's self-reported total.
fold = re.compile(r"PASS=\$\(\(PASS \+ ([A-Za-z_][A-Za-z0-9_]*)\)\)")
# A minimum can be a named `floor` or a literal number -- `-lt 12` is exactly
# as much of a floor as `-lt "$floor"`, and demanding the variable reported two
# correctly floored folds as defects the first time this ran. A zero-count
# refusal (`-gt 0`, `-eq 0`) is a floor of one and catches the same failure.
guard = re.compile(r"-lt[ \t]+(\"?\$?\{?floor|[0-9])|-gt[ \t]+0|-eq[ \t]+0|-le[ \t]+0")
for i, line in enumerate(lines):
    if not fold.search(line):
        continue
    window = lines[max(0, i - 12):i]
    if not any(guard.search(w) for w in window):
        print(i + 1)
FLOORPY
}

unfloored="$(floorcheck "$HARNESS")"
if [ -n "$unfloored" ]; then
    fail "test-hooks.sh folds an external PASS count with NO minimum at line(s): $(tr '\n' ' ' <<<"$unfloored")"
    echo "     A fold with no floor counts a selftest that printed nothing as a passing" >&2
    echo "     suite. That is how 36 orphaned controls hid for months." >&2
else
    pass "every external PASS fold refuses a count too low to be real"
fi

# CONTROL, both directions, by construction: a floored fold must read clean and
# an unfloored one must be named. Without the second arm this passes on a reader
# that finds nothing because its regex quietly stopped matching.
cat >"$TMP/floored.sh" <<'FIXTURE'
n=$(count)
if [[ "$n" -lt "$floor" ]]; then
    FAIL=$((FAIL + 1))
else
    PASS=$((PASS + n))
fi
FIXTURE
cat >"$TMP/floored-literal.sh" <<'FIXTURE'
n=$(count)
if [[ "$n" -lt 12 ]]; then
    FAIL=$((FAIL + 1))
else
    PASS=$((PASS + n))
fi
FIXTURE
cat >"$TMP/floored-zero.sh" <<'FIXTURE'
n=$(count)
if [[ $n -gt 0 ]]; then
    PASS=$((PASS + n))
fi
FIXTURE
cat >"$TMP/unfloored.sh" <<'FIXTURE'
n=$(count)
PASS=$((PASS + n))
FIXTURE
if [ -z "$(floorcheck "$TMP/floored.sh")" ]; then
    pass "control: a floored fold is not reported"
else
    fail "CONTROL DID NOT FIRE: a correctly floored fold was reported as unfloored"
fi
# The two OTHER honest spellings. Demanding a `floor` variable reported both as
# defects on this check's first run, and a gate that cries wolf is one the next
# session learns to route around.
if [ -z "$(floorcheck "$TMP/floored-literal.sh")" ]; then
    pass "control: a literal minimum counts as a floor"
else
    fail "CONTROL DID NOT FIRE: a literal '-lt 12' floor was reported as unfloored"
fi
if [ -z "$(floorcheck "$TMP/floored-zero.sh")" ]; then
    pass "control: a zero-count refusal counts as a floor"
else
    fail "CONTROL DID NOT FIRE: a '-gt 0' refusal was reported as unfloored"
fi
if [ -n "$(floorcheck "$TMP/unfloored.sh")" ]; then
    pass "control: an unfloored fold is detected"
else
    fail "CONTROL DID NOT FIRE: an unfloored fold went unnoticed, so the check above proves nothing"
fi

# CONTROL, by construction: strip the floor from a copy and require the check to
# notice. Built by DELETION of a line that is present, not by pattern
# substitution, so it cannot silently produce an identical copy -- the vacuous-
# plant hole check-control-vacuity.sh exists for.
HARNESS_COPY="$(mktemp)"
grep -v 'lt "\$floor"' "$HARNESS" >"$HARNESS_COPY"
if grep -q 'lt "\$floor"' "$HARNESS_COPY"; then
    fail "CONTROL IS VACUOUS: the floor line survived its own removal"
else
    pass "CONTROL: the floor line is detectable, so its absence would be caught"
fi
rm -f "$HARNESS_COPY"

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} hook integrity: ${#on_disk[@]} guard(s) present across ${#CHAINS[@]} chain(s), none newly uncovered."
    echo "  Blind spot, stated so a green is not read as more than it is: this counts"
    echo "  CASES, not their quality. A guard whose two cases are both trivial passes"
    echo "  here; only reading them catches that."
    exit 0
fi
echo "${RED}✗${NC} hook integrity: $fails failure(s)."
exit 1
