#!/bin/bash
# Meta-gate: a validator that PASSES when given nothing is broken by definition.
#
# WHY THIS EXISTS
# ---------------
# This repo accumulated ~12 quality gates that were green because they could
# not fail. Two root patterns, both reproducible by simply removing the input:
#
#   1. Dead path constant. The tree a gate walked was deleted (PR #513 removed
#      packages/web, packages/desktop, packages/e2e). The glob returned zero
#      files, the gate iterated zero times, and printed a checkmark.
#      check-www-only-translations.ts compared two empty sets for months.
#   2. Assertion disabled when its input is absent. Guarding the real assertion
#      behind `if (existsSync(DIR))` means the assertion never runs in an
#      environment where DIR is gitignored -- e.g. the R2-hosted tutorial audio
#      tree, whose per-file check has never once executed in CI.
#
# Both collapse to one testable property: point the validator at an EMPTY tree
# and it must exit NON-ZERO, complaining that its input is missing. If it exits
# 0, it is asserting nothing and its green run in CI means nothing.
#
# REGISTRY POLICY
# ---------------
# The registry below is explicit and hand-verified, NOT auto-discovered.
# Auto-discovery would sweep in generators, one-shot scripts and validators
# whose input genuinely is optional, producing exactly the kind of noise that
# gets a gate suppressed. Add a validator here only after confirming by hand
# that "no input" is a real failure for it rather than a legitimate no-op.
#
# Seeded with check-translation-hashes.ts and check-translation-completeness.ts,
# which were just hardened to assert their declared locale sets exist. They are
# known-good positives, so a green run of THIS file is evidence the harness
# itself works rather than evidence of another vacuous check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

# REGISTRY -- one entry per line: "<script-relative-to-scripts/>|<expected substring>"
# The substring pins the DIAGNOSTIC, not just the exit code: a validator that
# fails for an unrelated reason (a crashed import, a missing dependency) is not
# evidence that it detects a missing input.
REGISTRY=(
    "check-translation-hashes.ts|locale"
    "check-translation-completeness.ts|locale"
)

# run_against_empty_tree <script> -- execute <script> with scripts/ copied into
# an otherwise empty directory, so every `__dirname/../packages/...` and
# `__dirname/../private/...` lookup resolves to nothing.
#
# Copying scripts/ (rather than deleting the real trees) is what makes this
# safe to run against a working tree holding other sessions' uncommitted work.
run_against_empty_tree() {
    local script="$1"
    local TEMP
    TEMP="$(mktemp -d)"
    # BLOCKER: expanding TEMP now binds the specific temp path into the trap at set-time so RETURN removes the correct directory even if TEMP is reassigned
    # shellcheck disable=SC2064
    trap "rm -rf '$TEMP'" RETURN

    cp -r "$REPO_ROOT/scripts" "$TEMP/scripts"
    # node_modules resolution walks upward from the script, so link the real
    # one in; the point of the fixture is an empty SOURCE tree, not a broken
    # runtime.
    ln -s "$REPO_ROOT/node_modules" "$TEMP/node_modules"

    local out rc=0
    out="$(cd "$TEMP" && npx tsx "scripts/$script" 2>&1)" || rc=$?
    printf '%s\n' "$out"
    return "$rc"
}

test_validator_rejects_empty_tree() {
    local script="$1" needle="$2"
    local out rc=0
    out="$(run_against_empty_tree "$script")" || rc=$?

    if [[ "$rc" -eq 0 ]]; then
        printf '%s\n' "$out" >&2
        log_fail "$script exited 0 on an EMPTY tree -- it asserts nothing (vacuous gate)"
    fi
    # Case-insensitive: the diagnostic must be about the missing input.
    if ! printf '%s\n' "$out" | grep -qi -- "$needle"; then
        printf '%s\n' "$out" >&2
        log_fail "$script failed on an empty tree, but its message never mentions '$needle' -- it may be crashing for an unrelated reason"
    fi
    log_pass "$script rejects an empty tree (exit $rc)"
}

test_registry_is_not_empty() {
    # Control for this file itself: an empty registry would make every
    # assertion below vacuous -- the precise failure mode being policed.
    if [[ "${#REGISTRY[@]}" -eq 0 ]]; then
        log_fail "REGISTRY is empty -- this meta-gate would assert nothing"
    fi
    log_pass "registry holds ${#REGISTRY[@]} validator(s)"
}

test_registry_entries_exist() {
    local entry script
    for entry in "${REGISTRY[@]}"; do
        script="${entry%%|*}"
        if [[ ! -f "$REPO_ROOT/scripts/$script" ]]; then
            log_fail "registry names scripts/$script, which does not exist -- the registry has gone stale"
        fi
    done
    log_pass "every registered validator exists"
}

test_harness_catches_a_vacuous_validator() {
    # Control: prove this file can FAIL. A synthetic validator that ignores its
    # input and exits 0 -- the exact shape of the bugs being policed -- must be
    # reported. Without this, a harness that silently never asserts would look
    # identical to a clean run.
    local fixture="$REPO_ROOT/scripts/.gate-anti-vacuity-fixture.ts"
    # BLOCKER: expanding fixture now binds the specific path into the trap so cleanup fires even if the variable is later reassigned
    # shellcheck disable=SC2064
    trap "rm -f '$fixture'" RETURN
    printf 'console.log("locale check passed");\nprocess.exit(0);\n' >"$fixture"

    # log_fail exits, so run the assertion in a subshell and inspect its status.
    local out rc=0
    out="$(test_validator_rejects_empty_tree ".gate-anti-vacuity-fixture.ts" "locale" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "harness must reject a validator that exits 0 on an empty tree"
    assert_contains "$out" "asserts nothing" "failure message must name the vacuity"
    log_pass "harness catches a vacuous validator (control case)"
}

log_test "test-gate-anti-vacuity"
test_harness_catches_a_vacuous_validator
test_registry_is_not_empty
test_registry_entries_exist
for registry_entry in "${REGISTRY[@]}"; do
    test_validator_rejects_empty_tree "${registry_entry%%|*}" "${registry_entry#*|}"
done
echo ""
log_pass "all tests passed"
