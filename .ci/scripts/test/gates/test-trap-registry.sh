#!/bin/bash
# Tests for .ci/scripts/quality/check-trap-registry.sh and for the corpus parser
# it shares with the stop hook (.claude/hooks/stop/wl_store.py).
#
# THE GATE IS CONTROL-FIRST, so the thing most worth testing is that its own
# controls are not decorative: it refuses to judge the real tree when any of
# them misbehaves, and its verdict line says how many fired. Two of the gate's
# controls found real bugs in it while it was being written (an empty Residue
# collapsing because TAB is IFS whitespace in bash, and a manifest block scan
# that could not see a single-line entry), which is the argument for keeping
# them in front of every run rather than behind a flag.
#
# THE PLANTS BELOW GO INTO A COPY OF THE REAL CORPUS, never the tracked file:
# a killed command must not strand a mutated TRAPS.md in a shared checkout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/.ci/scripts/quality/check-trap-registry.sh"
CORPUS="$REPO_ROOT/docs/agent-reference/TRAPS.md"
STOP_DIR="$REPO_ROOT/.claude/hooks/stop"
[ -x "$GATE" ] || log_fail "gate not executable: $GATE"
[ -f "$CORPUS" ] || log_fail "corpus missing: $CORPUS"

LAST=""
# Scan one corpus with every OTHER resolution source left real, so a plant is
# judged against the live manifest, dispatcher, hook suite and settings.
scan_corpus() {
    local rc=0
    LAST="$(TRAP_CORPUS="$1" bash "$GATE" --scan-only 2>&1)" || rc=$?
    return "$rc"
}

test_real_tree_is_green_and_the_controls_fired() {
    # Seam-free: the real invocation, real corpus, real everything.
    local rc=0
    LAST="$(bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real corpus must pass the registry gate (output: $LAST)"
    assert_contains "$LAST" "planted defects red" "the verdict must state that its controls fired, not merely that the tree is clean"
    assert_contains "$LAST" "clean fixtures green" "the controls must include the converse direction"
    assert_contains "$LAST" "entries (floor" "the verdict must print the SHAPE, so a reader can see the population did not collapse"
    log_pass "real corpus green, controls fired in both directions, shape printed"
}

test_a_missing_trap_id_is_caught() {
    local d="$1"
    sed '/^Trap-Id: cancelled-run-not-passed$/d' "$CORPUS" >"$d/p.md"
    cmp -s "$CORPUS" "$d/p.md" && log_fail "the plant did not land: the corpus is unchanged"
    local rc=0
    scan_corpus "$d/p.md" || rc=$?
    assert_exit_code 1 "$rc" "an entry with no Trap-Id must red (F2)"
    assert_contains "$LAST" "has no Trap-Id" "the finding must name the missing field"
    log_pass "F2: a stripped Trap-Id reds, and the message names it"
}

test_a_dangling_gate_pointer_is_caught() {
    local d="$1"
    sed 's|^Enforced-By: gate:check:ci-go-module-sync$|Enforced-By: gate:check:does-not-exist|' \
        "$CORPUS" >"$d/p.md"
    cmp -s "$CORPUS" "$d/p.md" && log_fail "the plant did not land: the corpus is unchanged"
    local rc=0
    scan_corpus "$d/p.md" || rc=$?
    assert_exit_code 1 "$rc" "a gate: pointer at a non-existent id must red (F4)"
    assert_contains "$LAST" "check:does-not-exist" "the finding must name the pointer that does not resolve"
    log_pass "F4: a dangling gate: pointer reds against the live manifest"
}

test_a_scheduled_but_unrun_gate_is_caught() {
    # build:packages is a REAL manifest entry that is deliberately `gate: false`
    # (a prerequisite node that validates nothing). Naming it would be the
    # cheapest way to look covered, which is exactly what F5 exists to refuse.
    local d="$1"
    sed 's|^Enforced-By: gate:check:ci-go-module-sync$|Enforced-By: gate:build:packages|' \
        "$CORPUS" >"$d/p.md"
    cmp -s "$CORPUS" "$d/p.md" && log_fail "the plant did not land: the corpus is unchanged"
    local rc=0
    scan_corpus "$d/p.md" || rc=$?
    assert_exit_code 1 "$rc" "a pointer at a manifest entry with gate:false must red (F5)"
    assert_contains "$LAST" "never schedules it" "the finding must say the gate is not run, not merely that it exists"
    log_pass "F5: a real-but-unscheduled gate id reds"
}

test_a_deleted_entry_is_caught() {
    local d="$1"
    awk 'BEGIN{skip=0} /^## /{skip = ($0 ~ /git branch --merged/) ? 1 : 0} !skip' \
        "$CORPUS" >"$d/p.md"
    cmp -s "$CORPUS" "$d/p.md" && log_fail "the plant did not land: the corpus is unchanged"
    local rc=0
    scan_corpus "$d/p.md" || rc=$?
    assert_exit_code 1 "$rc" "a shrinking corpus must red (F1)"
    assert_contains "$LAST" "below the floor" "the finding must name the floor"
    log_pass "F1: deleting an entry drops below the floor and reds"
}

test_an_unchanged_copy_is_green() {
    # THE CONVERSE. Without it every assertion above is satisfied by a gate that
    # reds on everything, including a correct corpus.
    local d="$1"
    cp "$CORPUS" "$d/clean.md"
    local rc=0
    scan_corpus "$d/clean.md" || rc=$?
    assert_exit_code 0 "$rc" "an unmodified copy of the corpus must stay green (output: $LAST)"
    log_pass "CONTROL: an unmodified copy of the corpus is green"
}

# ---------------------------------------------------------------------------
# The stop hook's parser. wl_store.trap_headings was a bare startswith("## ")
# with no fence state: latent while no trap body carried a fenced heading, and
# activated the moment the registry required an id per entry.
# ---------------------------------------------------------------------------
test_stop_hook_parser_ignores_fenced_headings() {
    local d="$1" out
    mkdir -p "$d/fence/docs/agent-reference" "$d/plain/docs/agent-reference"
    cat >"$d/fence/docs/agent-reference/TRAPS.md" <<'EOF'
# Traps

## A real entry
Trap-Id: a-real-entry
Enforced-By: JUDGMENT-ONLY
Residue: the residue sentence.

```markdown
## Not A Trap
```

~~~
## Also Not A Trap
~~~
EOF
    # The SAME line unfenced must be seen, or the case above proves only that
    # the parser ignores things.
    cat >"$d/plain/docs/agent-reference/TRAPS.md" <<'EOF'
# Traps

## A real entry
Trap-Id: a-real-entry
Enforced-By: JUDGMENT-ONLY
Residue: the residue sentence.

## Not A Trap
EOF
    out="$(
        cd "$REPO_ROOT" && python3 - "$STOP_DIR" "$d" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import wl_store as S  # noqa: E402

base = sys.argv[2]
fenced = S.trap_headings(base + "/fence")
plain = S.trap_headings(base + "/plain")
checks = [
    ("fenced-headings-are-not-entries", fenced == ["A real entry"]),
    ("CONTROL-the-same-line-unfenced-is-an-entry",
     plain == ["A real entry", "Not A Trap"]),
]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
PY
    )"
    assert_not_contains "$out" "FAIL" "wl_store fence handling: $out"
    log_pass "wl_store.trap_headings skips fenced ## examples and still sees unfenced ones"
}

test_prompt_filter_keeps_only_the_residue() {
    local d="$1" out
    mkdir -p "$d/filter/docs/agent-reference"
    cat >"$d/filter/docs/agent-reference/TRAPS.md" <<'EOF'
# Traps

## Fully mechanized
Trap-Id: fully-mechanized
Enforced-By: gate:check:ci-breakpoint-drift
Residue:

body

## Mechanized with residue
Trap-Id: mechanized-with-residue
Enforced-By: gate:check:ci-breakpoint-drift
Residue: the part the gate does not reach.

body

## Judgment only
Trap-Id: judgment-only-entry
Enforced-By: JUDGMENT-ONLY
Residue: nothing watches this.

body

## Unclassified legacy entry

body
EOF
    out="$(
        cd "$REPO_ROOT" && python3 - "$STOP_DIR" "$d" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import wl_store as S  # noqa: E402

got = S.trap_prompt_lines(sys.argv[2] + "/filter")
checks = [
    # A trap something already watches leaves the prompt entirely.
    ("mechanized-entry-is-dropped", "Fully mechanized" not in got),
    # Residue is what costs attention, and it renders as the SENTENCE.
    ("residue-is-kept", "the part the gate does not reach." in got),
    ("judgment-only-is-kept", "nothing watches this." in got),
    # Unknown is never folded into fine.
    ("unclassified-entry-is-kept", "Unclassified legacy entry" in got),
    ("nothing-else-leaked", len(got) == 3),
]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
PY
    )"
    assert_not_contains "$out" "FAIL" "prompt filter: $out"
    log_pass "prompt filter keeps residue and judgment-only, drops mechanized, keeps unclassified"
}

test_real_tree_is_green_and_the_controls_fired
with_temp_dir test_a_missing_trap_id_is_caught
with_temp_dir test_a_dangling_gate_pointer_is_caught
with_temp_dir test_a_scheduled_but_unrun_gate_is_caught
with_temp_dir test_a_deleted_entry_is_caught
with_temp_dir test_an_unchanged_copy_is_green
with_temp_dir test_stop_hook_parser_ignores_fenced_headings
with_temp_dir test_prompt_filter_keeps_only_the_residue

log_pass "all tests passed"
