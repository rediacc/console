#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which every gate-test shares and none owns, so no gate-bind region may emit it
# why: Tests for .ci/scripts/quality/check_language_policy.py: the bash surface under .ci and .claude may shrink and may never grow
# ---- end gate ----

# Tests for .ci/scripts/quality/check_language_policy.py.
#
# WHAT THE GATE CLAIMS, and therefore what has to be proven in BOTH directions:
# the set of tracked bash files under .ci and .claude may lose members and may
# never gain one, exemptions are named with a BLOCKER reason and die when they
# stop suppressing anything, and a green from an enumeration that saw nothing is
# refused rather than printed.
#
# HOW IT IS DRIVEN. Every case but the last builds a throwaway git repository and
# points the gate at it through LANGUAGE_POLICY_ROOT / _BASELINE / _ALLOWLIST, so
# no tracked baseline, allowlist or script is touched. `git ls-files` is the
# gate's corpus, which is why the fixture has to be a real repository with a real
# index rather than a directory of files: a fixture that merely looks like a tree
# would exercise a code path the gate does not have.
#
# THE LAST CASE IS SEAM-FREE, against the real repository, because every seam
# above it is a chance for the gate to be correct about a fixture and wrong about
# the tree it ships with.
#
# EVERY FIRE CASE HAS ITS CONTROL: the same fixture with one thing changed and the
# opposite verdict asserted. A gate that cannot be made to fire is not a gate, and
# a gate that fires on everything is not one either.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/.ci/scripts/quality/check_language_policy.py"

# A reason long enough and specific enough to satisfy the canonical validator
# (.ci/scripts/lib/blocker-validator.sh: 30 characters after normalisation, no
# banned phrase). Held in one variable so a case that means to test something
# ELSE cannot fail on the reason by accident.
GOOD_REASON="vendored downstream and drift-locked, so a port here would fork code whose contract is being byte-identical"

LAST_OUT=""

# run_gate <root> [args...] -- returns the gate's exit code, output in $LAST_OUT.
#
# stdout and stderr are merged HERE and only here: these assertions are about
# which message appeared, and the gate's own separation of the two streams is
# asserted by the seam-free case at the bottom, which reads them apart.
run_gate() {
    local root="$1"
    shift
    local rc=0
    LAST_OUT="$(
        LANGUAGE_POLICY_ROOT="$root" \
            LANGUAGE_POLICY_BASELINE="$root/baseline.json" \
            LANGUAGE_POLICY_ALLOWLIST="$root/allowlist" \
            python3 "$GATE" "$@" 2>&1
    )" || rc=$?
    return "$rc"
}

# fixture <dir> -- a real git repository holding a small .ci / .claude tree.
#
# Five bash files: three that must be judged, two under an exempt tree. Plus a
# .py file, which must NOT be judged -- without it a matcher that returned true
# for everything would pass every case below.
fixture() {
    local dir="$1"
    mkdir -p "$dir/.ci/scripts" "$dir/.ci/media" "$dir/.claude/hooks"
    printf '#!/usr/bin/env bash\necho one\n' >"$dir/.ci/scripts/one.sh"
    printf '#!/usr/bin/env bash\necho two\n' >"$dir/.ci/scripts/two.sh"
    printf '#!/usr/bin/env bash\necho hook\n' >"$dir/.claude/hooks/three.sh"
    printf '#!/usr/bin/env bash\necho media\n' >"$dir/.ci/media/render.sh"
    printf '#!/usr/bin/env bash\necho more media\n' >"$dir/.ci/media/upload.sh"
    printf '#!/usr/bin/env python3\nprint(1)\n' >"$dir/.ci/scripts/keeper.py"

    printf '# BLOCKER: %s\ntree:.ci/media/\n' "$GOOD_REASON" >"$dir/allowlist"
    cat >"$dir/baseline.json" <<'JSON'
{
  "note": "fixture",
  "bashFiles": [
    ".ci/scripts/one.sh",
    ".ci/scripts/two.sh",
    ".claude/hooks/three.sh"
  ]
}
JSON

    git -C "$dir" init -q
    git -C "$dir" add -A -- .
}

# ---------------------------------------------------------------------------

test_clean_tree_passes() {
    fixture "$TEMP"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "a tree matching its baseline must pass"
    assert_contains "$LAST_OUT" "5 bash file(s)" "prints the SHAPE, not just a verdict"
    assert_contains "$LAST_OUT" "3 frozen" "says how many are frozen"
    assert_contains "$LAST_OUT" "2 exempt" "says how many are exempt"
    log_pass "a clean tree passes and prints its shape"
}

test_new_bash_file_fires() {
    fixture "$TEMP"
    printf '#!/usr/bin/env bash\necho new\n' >"$TEMP/.ci/scripts/four.sh"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a NEW non-exempt bash file must be refused"
    assert_contains "$LAST_OUT" ".ci/scripts/four.sh" "names the offending file"
    assert_contains "$LAST_OUT" "Write it in Python instead" "says what to do about it"
    log_pass "a new non-exempt bash file fires"
}

test_new_file_under_exempt_tree_is_silent() {
    # THE CONTROL FOR THE CASE ABOVE. Without it, a gate that fired on any change
    # at all would pass that test, and the exemption would be proving nothing.
    fixture "$TEMP"
    printf '#!/usr/bin/env bash\necho new\n' >"$TEMP/.ci/media/four.sh"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "a new file under an EXEMPT tree must be silent"
    assert_contains "$LAST_OUT" "3 exempt" "counts it as exempt, and says so"
    log_pass "CONTROL: a new file under an exempt tree does not fire"
}

test_new_py_file_is_silent() {
    # The other half of the same control: the gate must be blind to Python, or it
    # is a file-count gate wearing a language gate's name.
    fixture "$TEMP"
    printf '#!/usr/bin/env python3\nprint(2)\n' >"$TEMP/.ci/scripts/ported.py"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "adding a PYTHON file is the goal state, not a finding"
    log_pass "CONTROL: a new Python file does not fire"
}

test_shebang_without_extension_is_caught() {
    # The rule may not be evadable by dropping the extension.
    fixture "$TEMP"
    printf '#!/bin/bash\necho sneaky\n' >"$TEMP/.ci/scripts/helper"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a shebang'd file with no .sh must still be caught"
    assert_contains "$LAST_OUT" ".ci/scripts/helper" "names it"
    log_pass "dropping the .sh extension does not evade the rule"
}

test_drained_file_demands_a_ratchet() {
    fixture "$TEMP"
    git -C "$TEMP" rm -qf "$TEMP/.ci/scripts/two.sh"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a ported file must demand the baseline be ratcheted"
    assert_contains "$LAST_OUT" ".ci/scripts/two.sh" "names the drained file"
    assert_contains "$LAST_OUT" "--write-baseline" "gives the exact drain command"
    log_pass "a ported file demands the baseline be ratcheted down"
}

test_composition_trap_on_the_read_path() {
    # Delete one, add one. The TOTAL is unchanged, so a count-based gate goes
    # green here. This is the exact case the plan's "set-based, never a count"
    # requirement exists for.
    fixture "$TEMP"
    git -C "$TEMP" rm -qf "$TEMP/.ci/scripts/two.sh"
    printf '#!/usr/bin/env bash\necho swapped\n' >"$TEMP/.ci/scripts/four.sh"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "one out and one in must be refused, though the count is equal"
    assert_contains "$LAST_OUT" ".ci/scripts/four.sh" "names the file that was ADDED"
    log_pass "swapping one file for another is caught, though the total is unchanged"
}

test_composition_trap_on_the_write_path() {
    # The same trap, on --write-baseline, which is where it actually bites: a
    # drain that absorbs a new finding prints a SMALLER number and looks like
    # progress. Refusing on the read path alone does not close this.
    fixture "$TEMP"
    git -C "$TEMP" rm -qf "$TEMP/.ci/scripts/two.sh"
    printf '#!/usr/bin/env bash\necho swapped\n' >"$TEMP/.ci/scripts/four.sh"
    git -C "$TEMP" add -A -- .
    local rc=0
    run_gate "$TEMP" --write-baseline || rc=$?
    assert_exit_code 1 "$rc" "a reseed that ABSORBS a new file must be refused"
    assert_contains "$LAST_OUT" "would GAIN" "says the set would grow"
    assert_contains "$LAST_OUT" ".ci/scripts/four.sh" "names what it would have absorbed"
    assert_contains "$LAST_OUT" "LOOKS like progress" "explains why the totals lie"
    # AND THE FILE MUST BE UNTOUCHED. A refusal that still writes is not a refusal.
    assert_not_contains "$(cat "$TEMP/baseline.json")" "four.sh" "refused write left no trace"
    log_pass "the write path refuses a reseed that would absorb a new file"
}

test_pure_drain_is_allowed() {
    # CONTROL for the case above. If --write-baseline refused everything the
    # backlog could never shrink, and the gate would be a freeze rather than a
    # ratchet.
    fixture "$TEMP"
    git -C "$TEMP" rm -qf "$TEMP/.ci/scripts/two.sh"
    local rc=0
    run_gate "$TEMP" --write-baseline || rc=$?
    assert_exit_code 0 "$rc" "a pure drain must be allowed"
    assert_contains "$LAST_OUT" "1 drained, 0 added" "reports the composition of the write"
    assert_not_contains "$(cat "$TEMP/baseline.json")" "two.sh" "the drained file is gone"
    rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "and the tree is green afterwards"
    log_pass "CONTROL: a pure drain is written, and the tree is green after it"
}

test_missing_baseline_refuses_a_blind_reseed() {
    fixture "$TEMP"
    rm "$TEMP/baseline.json"
    local rc=0
    run_gate "$TEMP" --write-baseline || rc=$?
    assert_exit_code 1 "$rc" "reseeding with no previous set must be refused"
    assert_contains "$LAST_OUT" "--first-seed" "names the flag that would allow it"
    rc=0
    run_gate "$TEMP" --write-baseline --first-seed || rc=$?
    assert_exit_code 0 "$rc" "CONTROL: --first-seed permits a genuine first seed"
    log_pass "deleting the baseline is not a way to reseed it blind"
}

test_missing_baseline_is_strict_not_silent() {
    fixture "$TEMP"
    rm "$TEMP/baseline.json"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "no baseline means STRICT, never 'no debt recorded'"
    assert_contains "$LAST_OUT" "STRICT" "says which mode it is in"
    assert_contains "$LAST_OUT" "3 bash file(s)" "counts what strict mode refuses"
    log_pass "an absent baseline is the strict flip, not an escape hatch"
}

test_strict_mode_passes_when_only_exempt_bash_remains() {
    # W1 P6's goal state, proven reachable rather than assumed: no baseline file,
    # and every surviving bash file named in the allowlist.
    fixture "$TEMP"
    rm "$TEMP/baseline.json"
    git -C "$TEMP" rm -qf "$TEMP/.ci/scripts/one.sh" "$TEMP/.ci/scripts/two.sh" \
        "$TEMP/.claude/hooks/three.sh"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "strict mode must be reachable, or the flip cannot land"
    assert_contains "$LAST_OUT" "STRICT" "says so"
    assert_contains "$LAST_OUT" "goal state" "and names it as the goal state"
    log_pass "CONTROL: strict mode is green once only allowlisted bash remains"
}

test_missing_blocker_is_refused() {
    fixture "$TEMP"
    printf 'tree:.ci/media/\n' >"$TEMP/allowlist"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "an exemption with no BLOCKER must be refused"
    assert_contains "$LAST_OUT" "missing a '# BLOCKER:" "says what is missing"
    log_pass "an allowlist entry with no BLOCKER reason is refused"
}

test_low_effort_blocker_is_refused() {
    # This is also the control that the CANONICAL validator is really consulted.
    # "tbd" is on .ci/scripts/lib/blocker-validator.sh's banned-phrase list and
    # nowhere in this gate's own source, so a passing verdict here would mean the
    # subprocess never ran.
    fixture "$TEMP"
    printf '# BLOCKER: tbd\ntree:.ci/media/\n' >"$TEMP/allowlist"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a placeholder BLOCKER must be refused"
    assert_contains "$LAST_OUT" "low-effort placeholder" "quotes the canonical validator"
    log_pass "a low-effort BLOCKER is refused BY the canonical validator"
}

test_short_blocker_is_refused() {
    fixture "$TEMP"
    printf '# BLOCKER: it is vendored\ntree:.ci/media/\n' >"$TEMP/allowlist"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a BLOCKER under the 30-character floor must be refused"
    assert_contains "$LAST_OUT" "too short" "names the rule it broke"
    log_pass "a BLOCKER under the length floor is refused"
}

test_dead_tree_entry_is_refused() {
    fixture "$TEMP"
    printf '# BLOCKER: %s\ntree:.ci/gone/\n' "$GOOD_REASON" >"$TEMP/allowlist"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "an exemption that suppresses nothing must be refused"
    assert_contains "$LAST_OUT" "covers no bash file" "says why the entry is dead"
    log_pass "an exemption that covers nothing is reported dead"
}

test_shim_entry_that_grew_is_refused() {
    fixture "$TEMP"
    # A genuine one-line shim first: shebang, comment, `set`, one command.
    printf '#!/usr/bin/env bash\n# a note\nset -euo pipefail\nexec other "$@"\n' \
        >"$TEMP/.ci/scripts/one.sh"
    printf '# BLOCKER: %s\ntree:.ci/media/\n\n# BLOCKER: %s\nshim:.ci/scripts/one.sh\n' \
        "$GOOD_REASON" "$GOOD_REASON" >"$TEMP/allowlist"
    git -C "$TEMP" add -A -- .
    # It is exempt now, so the baseline that still lists it is one entry stale.
    printf '{"note":"f","bashFiles":[".ci/scripts/two.sh",".claude/hooks/three.sh"]}\n' \
        >"$TEMP/baseline.json"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 0 "$rc" "CONTROL: a genuine one-line shim is exempt"

    # Now grow it. The justification was "one-line shim" and that stopped being
    # true without the file being deleted, which is the half a
    # does-the-file-exist oracle would miss entirely.
    printf '#!/usr/bin/env bash\nset -euo pipefail\nfoo\nbar\n' >"$TEMP/.ci/scripts/one.sh"
    git -C "$TEMP" add -A -- .
    rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a shim that grew into a program must be refused"
    assert_contains "$LAST_OUT" "effective lines" "counts what it actually found"
    log_pass "a shim: entry whose file grew past one line is refused by name"
}

test_malformed_entry_is_named_not_dropped() {
    fixture "$TEMP"
    printf '# BLOCKER: %s\ntree:.ci/media\n' "$GOOD_REASON" >"$TEMP/allowlist"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 1 "$rc" "a tree: entry with no trailing slash must be refused"
    assert_contains "$LAST_OUT" "must end in a slash" "explains the widening it prevents"
    log_pass "a malformed allowlist entry is named rather than silently dropped"
}

test_empty_tree_fails() {
    # ANTI-VACUITY. An enumeration that found nothing is the failure this gate
    # would otherwise report as the cleanest run in its history.
    mkdir -p "$TEMP/empty"
    git -C "$TEMP/empty" init -q
    printf '# BLOCKER: %s\ntree:.ci/media/\n' "$GOOD_REASON" >"$TEMP/empty/allowlist"
    printf '{"note":"f","bashFiles":[]}\n' >"$TEMP/empty/baseline.json"
    local rc=0
    run_gate "$TEMP/empty" || rc=$?
    assert_exit_code 1 "$rc" "zero files scanned is a FAILURE, never a pass"
    assert_contains "$LAST_OUT" "VACUOUS" "says the corpus was empty"
    log_pass "an empty corpus fails (anti-vacuity), it does not pass silently"
}

test_corrupt_baseline_is_not_an_empty_one() {
    fixture "$TEMP"
    printf 'not json at all\n' >"$TEMP/baseline.json"
    local rc=0
    run_gate "$TEMP" || rc=$?
    assert_exit_code 77 "$rc" "a corrupt baseline is CANNOT RUN, not a verdict"
    assert_contains "$LAST_OUT" "CANNOT RUN" "says it could not reach a verdict"
    log_pass "a corrupt baseline is refused rather than read as an empty set"
}

test_missing_git_is_cannot_run_not_a_verdict() {
    fixture "$TEMP"
    local python3_bin
    python3_bin="$(command -v python3)"
    local rc=0
    LAST_OUT="$(
        PATH="$TEMP/nothing-here" \
            LANGUAGE_POLICY_ROOT="$TEMP" \
            LANGUAGE_POLICY_BASELINE="$TEMP/baseline.json" \
            LANGUAGE_POLICY_ALLOWLIST="$TEMP/allowlist" \
            "$python3_bin" "$GATE" 2>&1
    )" || rc=$?
    assert_exit_code 77 "$rc" "a missing toolchain must be 77, never a pass and never a red"
    assert_contains "$LAST_OUT" "CANNOT RUN" "says so in those words"
    assert_contains "$LAST_OUT" "git is not on PATH" "names the missing tool"
    assert_not_contains "$LAST_OUT" "Traceback" "and does not answer with a stack trace"
    log_pass "a missing git is exit 77 with the cause named, not a traceback"
}

test_selftest_can_fail() {
    # THE CONTROL ON THE CONTROLS. A selftest that cannot go red is decoration,
    # and this gate refuses its own verdict when the controls fail (exit 2), so
    # that refusal has to be demonstrated rather than assumed.
    #
    # Built by CONSTRUCTION: the copy has one function body replaced wholesale,
    # not a pattern substituted, so the mutation cannot silently fail to apply.
    fixture "$TEMP"
    local mutant="$TEMP/mutant.py"
    python3 - "$GATE" "$mutant" <<'PY'
import sys

src = open(sys.argv[1], encoding="utf-8").read()
needle = "    known = set(old)\n    return [entry for entry in new if entry not in known]\n"
if needle not in src:
    raise SystemExit("CONTROL COULD NOT PLANT: baseline_additions body not found as written")
open(sys.argv[2], "w", encoding="utf-8").write(src.replace(needle, "    return []\n"))
PY
    assert_contains "$(diff "$GATE" "$mutant" || true)" "return []" "the mutation landed"

    # The copy sits outside the tree, so the things it can no longer derive from
    # its own location are handed to it explicitly: the package it imports its control
    # runner from, and the canonical BLOCKER validator. Everything else it must work
    # out for itself, or the control would be testing the environment.
    #
    # `.ci/scripts/quality` IS ON THAT LIST AS OF 2026-09-09, and it was not before.
    # 73bd8f7ec routed 81 gate entry points through `import _cipath`, a
    # side-effect module that lives BESIDE them and is found only because a
    # path invocation puts the script's own directory on sys.path[0]. A copy in
    # a tmpdir has a different sys.path[0], so the mutant died with
    # `ModuleNotFoundError: No module named '_cipath'` before reaching a single
    # assertion, and this control reported "COMPOSITION TRAP not in <traceback>"
    # -- a control failing for a reason that has nothing to do with what it
    # controls. Handing over the entry-point directory restores the import.
    local rc=0
    LAST_OUT="$(
        PYTHONPATH="$REPO_ROOT/.ci:$REPO_ROOT/.ci/scripts/quality" \
            LANGUAGE_POLICY_VALIDATOR="$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh" \
            LANGUAGE_POLICY_ROOT="$TEMP" \
            python3 "$mutant" --selftest 2>&1
    )" || rc=$?
    assert_exit_code 1 "$rc" "a broken shrink-only guard must fail the selftest"
    assert_contains "$LAST_OUT" "COMPOSITION TRAP" "and names the control that caught it"

    rc=0
    LAST_OUT="$(
        PYTHONPATH="$REPO_ROOT/.ci:$REPO_ROOT/.ci/scripts/quality" \
            LANGUAGE_POLICY_VALIDATOR="$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh" \
            LANGUAGE_POLICY_ROOT="$TEMP" \
            LANGUAGE_POLICY_BASELINE="$TEMP/baseline.json" \
            LANGUAGE_POLICY_ALLOWLIST="$TEMP/allowlist" \
            python3 "$mutant" 2>&1
    )" || rc=$?
    assert_exit_code 2 "$rc" "and the gate refuses to give a verdict at all"
    assert_contains "$LAST_OUT" "every verdict below would be meaningless" "saying why"
    log_pass "the selftest goes red when the guard is broken, and the gate then refuses"
}

test_real_tree_seam_free() {
    # NO SEAMS. Every case above could be right about a fixture and wrong about
    # the repository this gate ships with.
    local out err rc=0
    out="$TEMP/out"
    err="$TEMP/err"
    (cd "$REPO_ROOT" && python3 "$GATE") >"$out" 2>"$err" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must be green: $(cat "$err")"
    assert_contains "$(cat "$out")" "control(s) passed" "controls ran before the verdict"
    assert_contains "$(cat "$out")" "language policy:" "and a verdict was printed"
    # The streams are SEPARATE, and a clean run says nothing on stderr. A gate
    # whose progress text lands on stderr is invisible until something parses it.
    assert_eq "$(wc -c <"$err")" "0" "a green run writes nothing to stderr"
    log_pass "the real tree is green, seam-free, with both streams read apart"
}

log_test "language policy gate"

with_temp_dir test_clean_tree_passes
with_temp_dir test_new_bash_file_fires
with_temp_dir test_new_file_under_exempt_tree_is_silent
with_temp_dir test_new_py_file_is_silent
with_temp_dir test_shebang_without_extension_is_caught
with_temp_dir test_drained_file_demands_a_ratchet
with_temp_dir test_composition_trap_on_the_read_path
with_temp_dir test_composition_trap_on_the_write_path
with_temp_dir test_pure_drain_is_allowed
with_temp_dir test_missing_baseline_refuses_a_blind_reseed
with_temp_dir test_missing_baseline_is_strict_not_silent
with_temp_dir test_strict_mode_passes_when_only_exempt_bash_remains
with_temp_dir test_missing_blocker_is_refused
with_temp_dir test_low_effort_blocker_is_refused
with_temp_dir test_short_blocker_is_refused
with_temp_dir test_dead_tree_entry_is_refused
with_temp_dir test_shim_entry_that_grew_is_refused
with_temp_dir test_malformed_entry_is_named_not_dropped
with_temp_dir test_empty_tree_fails
with_temp_dir test_corrupt_baseline_is_not_an_empty_one
with_temp_dir test_missing_git_is_cannot_run_not_a_verdict
with_temp_dir test_selftest_can_fail
with_temp_dir test_real_tree_seam_free

echo
echo "All language-policy gate tests passed"
