#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: node
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# check:ci-doc-region-parity, proved in both directions against a REAL fixture tree.
#
# WHY A FIXTURE AND NOT THE LIVE TREE. test-docs-gen.sh case A runs the generator against the
# checkout itself and requires a green. That couples a gate test to whether some other session
# has regenerated the docs after adding a gate, and it was RED on this branch at the moment this
# file was written: the manifest had grown and CLAUDE.md still quoted the old totals. A control
# that cannot run until the tree is tidy is a control that gets skipped. So every case here runs
# against a fixture built from the repository's own files, where this test owns every byte and
# can perturb them without touching anything a person is working in.
#
# WHAT EACH CASE PROVES, and why it is here rather than assumed:
#
#   A. the fixture is REAL: every provider the code declares yields rows in it, and the fixture
#      document carries one region per provider. The marker list is derived from `--list`, so a
#      seventh provider is covered here without editing this file.
#   B. GREEN: the gate accepts a freshly generated tree, and prints a PASS line per region. Exit
#      0 with no PASS lines would be the vacuity this whole estate exists to refuse, so the PASS
#      lines are counted rather than trusted.
#   C. RED on one perturbed cell, naming the file, the region and the row.
#   D. restored, and green again. Without D, C only proves the gate can fail, not that it can
#      still pass, and a gate that always fails is removed rather than fixed.
#   E. a REORDER is reported as a MOVE. Same rows, same count, same set: a comparison that is
#      not order-aware sees nothing, and a provider that stopped sorting the way it used to is a
#      different defect from a stale document.
#   F. THE CASE THIS GATE EXISTS FOR. A document that loses its markers keeps its now hand-typed
#      table, and the generator reports success over the documents that remain. This case
#      asserts BOTH halves: gen-docs stays green and this gate reds. If gen-docs ever grows the
#      check itself, F fails and tells us this gate became a strict subset.
#   G. a marker a human reads as a marker but the parser does not is named by line.
#   H. a root with no markdown is a FAILURE. Zero inputs is never a pass.
#   I. --selftest is green and still carries its planted controls BY NAME. Asserting the exit
#      code alone keeps passing after someone deletes the controls.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-doc-region-parity.ts"
GEN="$REPO_ROOT/scripts/gen-docs.ts"
[[ -f "$GATE" ]] || log_fail "scripts/check-doc-region-parity.ts is missing; the gate is gone"
[[ -f "$GEN" ]] || log_fail "scripts/gen-docs.ts is missing; there is nothing to keep faithful"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FIX="$WORK/fixture"
DOC="$FIX/REGISTRY.md"
mkdir -p "$FIX"

# ---- the fixture -----------------------------------------------------------
# Built from the repository's own tracked files, because the providers read real shapes: a
# gates lock they refuse when it is malformed, the hook wiring in .claude/settings.json, files
# carrying `BLOCKER:`, and a `.ci` subtree. Hand-rolled stand-ins would drift from those shapes
# and the test would then be proving something about the stand-ins.
copy_tracked() {
    (cd "$REPO_ROOT" && git ls-files -z -- "$@") |
        tar -c -C "$REPO_ROOT" --null --files-from=- -f - |
        tar -x -C "$FIX"
}
copy_tracked .claude .ci/scripts/lib scripts/ci-runner/gates.lock.json \
    scripts/gen-docs.ts scripts/lib/doc-providers.ts scripts/lib/doc-regions.ts

gate() { (cd "$REPO_ROOT" && npx tsx "$GATE" "$@"); }
# The COPY of the generator, so `--write` can only ever reach the fixture: gen-docs roots itself
# at its own parent directory (scripts/gen-docs.ts:74).
fixgen() { (cd "$REPO_ROOT" && npx tsx "$FIX/scripts/gen-docs.ts" "$@"); }

log_test "A. the fixture is real: every declared provider yields rows in it"
# The index first: every provider enumerates with `git ls-files`, so a fixture that is not yet a
# repository makes them throw rather than report, which reads as a broken gate instead of a
# broken fixture.
git -C "$FIX" init -q .
git -C "$FIX" add -A -- . >/dev/null 2>&1 || log_fail "A. could not stage the fixture"
if ! fixgen --list >"$WORK/list.txt" 2>"$WORK/list.err"; then
    log_error "$(cat "$WORK/list.err")"
    log_error "$(cat "$WORK/list.txt")"
    log_fail "A. a provider scanned the fixture and found nothing, so nothing below would mean anything"
fi
providers=$(cut -f1 "$WORK/list.txt")
n_providers=$(printf '%s\n' "$providers" | grep -c .)
[[ "$n_providers" -gt 0 ]] || log_fail "A. --list named no provider at all"
{
    echo "# fixture registry"
    echo
    # One region per provider, derived from --list rather than typed here.
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        echo "<!-- >>> gen-docs: $id -->"
        echo "<!-- prose the generator must preserve -->"
        echo "<!-- <<< gen-docs -->"
        echo
    done <<<"$providers"
    echo "hand-written tail"
} >"$DOC"
git -C "$FIX" add -- REGISTRY.md >/dev/null 2>&1 || log_fail "A. could not stage the fixture document"
if ! fixgen --write >"$WORK/write.out" 2>"$WORK/write.err"; then
    log_error "$(cat "$WORK/write.err")"
    log_fail "A. the generator could not write the fixture's regions"
fi
log_pass "A. fixture carries $n_providers region(s), one per provider, all non-empty"
cp "$DOC" "$WORK/doc.orig"

# ---- B. green --------------------------------------------------------------
log_test "B. the gate accepts a freshly generated tree"
if ! gate --root "$FIX" >"$WORK/b.out" 2>"$WORK/b.err"; then
    log_error "$(cat "$WORK/b.err")"
    log_fail "B. the gate red on a tree the generator had just written"
fi
n_pass=$(grep -c '  PASS  ' "$WORK/b.out")
[[ "$n_pass" -gt 0 ]] || log_fail "B. the gate exited 0 with ZERO pass lines, which is vacuous"
grep -q 'region(s) in' "$WORK/b.out" || log_fail "B. the green never printed its shape"
for id in $providers; do
    grep -q "region \`$id\` matches" "$WORK/b.out" ||
        log_fail "B. the green never mentions the region for provider $id"
done
log_pass "B. green with $n_pass pass line(s), one per region plus the structural checks"

# ---- C. red on a perturbed row ---------------------------------------------
log_test "C. one perturbed cell turns it red, and is named"
python3 - "$DOC" >"$WORK/c.plant" <<'PY' || log_fail "C. could not plant the perturbation"
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
# The first DATA row of the first table, found by shape rather than by content so this survives
# every rewording of every provider: the line after a `|---|` separator.
for i, line in enumerate(lines):
    if line.startswith("|---") and i + 1 < len(lines) and lines[i + 1].startswith("| "):
        print(lines[i + 1])
        lines[i + 1] = lines[i + 1].replace("| ", "| PERTURBED ", 1)
        break
else:
    raise SystemExit("no generated table row found to perturb")
open(path, "w", encoding="utf-8").write("\n".join(lines))
PY
if gate --root "$FIX" >"$WORK/c.out" 2>"$WORK/c.err"; then
    log_fail "C. CONTROL DID NOT FIRE: the gate passed over a perturbed generated row"
fi
assert_contains "$(cat "$WORK/c.err")" "REGISTRY.md" "C. the finding never named the file"
assert_contains "$(cat "$WORK/c.err")" "does not match what gen-docs would emit" \
    "C. the finding never said what was wrong"
assert_contains "$(cat "$WORK/c.err")" "$(cat "$WORK/c.plant")" \
    "C. the finding never printed the row the tree actually supports"
log_pass "C. a single perturbed cell is named, with the row it should have been"

# ---- D. and green again ----------------------------------------------------
log_test "D. restoring the document restores the green"
cp "$WORK/doc.orig" "$DOC"
cmp -s "$WORK/doc.orig" "$DOC" || log_fail "D. restore failed; the fixture is not what it was"
gate --root "$FIX" >/dev/null 2>"$WORK/d.err" ||
    log_fail "D. still red after restoring: $(cat "$WORK/d.err")"
log_pass "D. restored, and the gate is green again"

# ---- E. a move is a move ---------------------------------------------------
log_test "E. the same rows in a different ORDER are reported as a MOVE"
python3 - "$DOC" <<'PY' || log_fail "E. could not find two rows to swap"
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
for i, line in enumerate(lines):
    if line.startswith("|---") and i + 2 < len(lines) and lines[i + 2].startswith("| "):
        lines[i + 1], lines[i + 2] = lines[i + 2], lines[i + 1]
        break
else:
    raise SystemExit("no table with two data rows found")
open(path, "w", encoding="utf-8").write("\n".join(lines))
PY
if gate --root "$FIX" >"$WORK/e.out" 2>"$WORK/e.err"; then
    log_fail "E. CONTROL DID NOT FIRE: a reordered table passed"
fi
assert_contains "$(cat "$WORK/e.err")" "MOVED" "E. a reorder was not reported as a move"
assert_not_contains "$(cat "$WORK/e.err")" "the tree has, the doc lacks" \
    "E. a reorder was reported as an add plus a remove, which names the wrong defect"
log_pass "E. a reorder is reported as a move and never as an add plus a remove"
cp "$WORK/doc.orig" "$DOC"

# ---- F. the gap this gate exists to close ----------------------------------
log_test "F. a document that LOSES its markers: the generator stays green, this gate reds"
python3 - "$DOC" <<'PY' || log_fail "F. could not remove a marker pair"
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
opens = [i for i, l in enumerate(lines) if l.startswith("<!-- >>> gen-docs:")]
closes = [i for i, l in enumerate(lines) if l.startswith("<!-- <<< gen-docs")]
if not opens or not closes:
    raise SystemExit("the fixture carries no region to strip")
o = opens[0]
c = min(i for i in closes if i > o)
# Only the two marker lines go. Every generated row stays exactly where it was, so a reader
# sees no difference at all: the table is simply hand-typed from now on.
del lines[c]
del lines[o]
open(path, "w", encoding="utf-8").write("\n".join(lines))
PY
if ! fixgen >"$WORK/f.gen.out" 2>"$WORK/f.gen.err"; then
    log_error "$(cat "$WORK/f.gen.err")"
    log_fail "F. gen-docs went red on the stripped document. If it grew this check, this gate is now a strict subset and should be re-argued rather than kept"
fi
grep -q '^ok ' "$WORK/f.gen.out" ||
    log_fail "F. gen-docs exited 0 without naming a target, which is a different defect"
if gate --root "$FIX" >"$WORK/f.out" 2>"$WORK/f.err"; then
    log_fail "F. CONTROL DID NOT FIRE: the gate passed over a provider no region uses"
fi
assert_contains "$(cat "$WORK/f.err")" "used by NO region" \
    "F. the finding never said the provider had lost its region"
log_pass "F. the generator is green over a hand-typed table; this gate names the provider"
cp "$WORK/doc.orig" "$DOC"

# ---- G. a marker the parser cannot see -------------------------------------
log_test "G. a marker a human reads but the parser refuses is named by line"
python3 - "$DOC" <<'PY' || log_fail "G. could not indent a marker"
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
lines = text.split("\n")
for i, l in enumerate(lines):
    if l.startswith("<!-- >>> gen-docs:"):
        lines[i] = "  " + l
        break
else:
    raise SystemExit("no marker to indent")
open(path, "w", encoding="utf-8").write("\n".join(lines))
PY
if gate --root "$FIX" >"$WORK/g.out" 2>"$WORK/g.err"; then
    log_fail "G. CONTROL DID NOT FIRE: an indented marker passed as if it were a region"
fi
assert_contains "$(cat "$WORK/g.err")" "does not parse as one" \
    "G. the near-miss marker was not reported"
log_pass "G. an indented marker is reported as a region the generator cannot see"
cp "$WORK/doc.orig" "$DOC"
gate --root "$FIX" >/dev/null 2>&1 || log_fail "G. the fixture did not come back to green"

# ---- H. zero inputs is a failure -------------------------------------------
log_test "H. a root with no markdown at all is a failure, not a pass"
EMPTY="$WORK/empty"
mkdir -p "$EMPTY"
git -C "$EMPTY" init -q .
echo "not markdown" >"$EMPTY/readme.txt"
git -C "$EMPTY" add -- readme.txt >/dev/null 2>&1
if gate --root "$EMPTY" >"$WORK/h.out" 2>"$WORK/h.err"; then
    log_fail "H. CONTROL DID NOT FIRE: the gate was green over a tree with nothing to check"
fi
assert_contains "$(cat "$WORK/h.err")" "VACUOUS" "H. the refusal never said why"
log_pass "H. an empty subject is refused rather than counted as a pass"

# ---- I. the selftest still carries its controls ----------------------------
log_test "I. --selftest is green and still plants its defects"
if ! gate --selftest >"$WORK/i.out" 2>"$WORK/i.err"; then
    log_error "$(cat "$WORK/i.out")"
    log_fail "I. the gate's own selftest failed"
fi
grep -q '  FAIL  ' "$WORK/i.out" && log_fail "I. --selftest exited 0 with FAIL lines in its output"
# Named controls, not a count: a count survives someone deleting one control and adding another.
for want in \
    'REORDERED rows are reported as a MOVE' \
    'the counts a naive check would compare are EQUAL across that move' \
    'planted: an INDENTED marker is a near miss' \
    'planted: a provider DECLARED but never registered' \
    'planted: a truncated source reads as fewer ids' \
    'CONTROL: a marker QUOTED inside a table cell is neither' \
    'the rendered body has the exact shape gen-docs writes'; do
    grep -qF "$want" "$WORK/i.out" || log_fail "I. the selftest no longer runs the control: $want"
done
log_pass "I. --selftest is green with $(grep -c '  PASS  ' "$WORK/i.out") control(s) present"

echo "All doc-region-parity cases passed."
