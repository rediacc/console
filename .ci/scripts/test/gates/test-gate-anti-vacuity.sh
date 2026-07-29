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
    # Against an empty tree every oracle is unavailable, so the run is vacuous
    # and must FAIL rather than report "every entry is still load-bearing".
    "check-suppression-liveness.ts|vacuous"
    # A bash gate, reachable only since this harness learned to run .sh. It used
    # to `exit 0` when private/renet was absent, silently taking govulncheck,
    # deadcode and golangci-lint with it.
    ".ci/scripts/private/run-renet.sh|required"
    # NOT registered here: .ci/breakpoint/scripts/check-breakpoint-drift.sh.
    # This harness's fixture copies scripts/ and .ci/scripts/ but not
    # .ci/breakpoint/, so the drift gate would fail with "No such file or
    # directory" -- non-zero for a reason that has nothing to do with vacuity,
    # which is precisely the false signal the REGISTRY POLICY above warns about.
    # Its missing-manifest behaviour is proven in test-breakpoint-portability.sh
    # instead, where an isolated copy of the folder genuinely exists.
    # The harness fixture copies scripts/ and .ci/scripts/ but nothing that
    # REFERENCES them (no workflows, no docs, no allowlist), so the gate must
    # report the resulting orphans loudly rather than pass. The "ZERO shell
    # files" guard covers the stricter case of no shell tree at all.
    "check-dead-bash.ts|dead shell symbol"
    # Both of its checks walk .github/workflows. The empty tree has no workflow
    # YAML, so every invariant it asserts is over an empty set. It used to
    # `exit 0` on a missing directory, which meant renaming the workflow tree
    # would silently retire the gate.
    ".ci/scripts/security/check-workflow-gates.sh|blind"
    # The empty tree has no .github/workflows, so there is no gate census to
    # compare against the chain. It used to die with a raw ENOENT stack trace,
    # which reads as a crash rather than a verdict.
    "check-ci-chain-parity.ts|blind"
    # The scope engine's workflow closure is computed by ITERATING
    # `uses: ./.github/workflows/*` at runtime, never by matching names, so the
    # test asserts a real closure over the real tree. On the empty fixture that
    # closure is {} and the assertion must fail: registering it pins the fact
    # that moving or renaming the workflow tree cannot silently turn the
    # closure test into a tautology over an empty set.
    ".ci/scripts/test/gates/test-scope-engine.sh|closure"
    # A DIFF gate with no baseline and no ledger measures nothing, and
    # "measured nothing" must never read as "found nothing". Against the empty
    # fixture both its inputs are gone, so it must refuse to run. Its first
    # draft did the opposite: a wrong ledger path made the protected set empty,
    # so it reported OK on a planted fabrication. Only a control caught that.
    "check-locale-only-edits.ts|Refusing to run"
    "check-gate-reachability.ts|Refusing to run"
    "check-jq-boolean-default.ts|Refusing to run"
    ".ci/scripts/security/check-autopilot-workflow-invariants.sh|INVARIANT-FAIL"
    # Its DOCS_DIR is a hardcoded path constant, so this is root pattern 1
    # verbatim: point it at a tree without packages/www/src/content/docs and
    # the glob returns zero files, every loop iterates zero times, and it
    # printed "All external links are valid". Measured on the empty fixture
    # before the guard was added, not inferred from reading it.
    "check-external-links.ts|Refusing to run"
    # NOT registered here: .ci/scripts/test/gates/test-skip-plan-reconcile.sh.
    # Measured, not assumed: it passes all 55 assertions against the empty tree,
    # because it is a pure unit test that builds every fixture it needs (its
    # plans and job lists are constructed in-test, and it reads scope-map only
    # for the job-key list, which .ci/scripts carries into the fixture). Passing
    # with the repo absent is CORRECT for it rather than vacuous, so an entry
    # here could never fail and would be exactly the dead assertion this
    # harness exists to catch. Its anti-vacuity controls are inline instead.
    #
    # NOT registered here either: .ci/scripts/test/gates/test-scope-baseline-attest.sh,
    # for the same reason and measured the same way: all 75 assertions pass
    # against the empty tree (exit 0), because it too builds every fixture it
    # needs. It drives the real createRepoIo with an INJECTED `run`, so it makes
    # no git call, no gh call and no network call; the only repo files it reads
    # are the three .ci/scripts/ci/*.cjs modules this harness copies in anyway.
    # Passing with the source tree absent is CORRECT for it, so an entry here
    # would assert nothing. Its controls are inline instead, one per planted
    # defect, plus three engine mutants run by hand during authoring (drop the
    # `delete plan.reconciled`, drop the cheap-first mode gate, restore the
    # one-green-run-per-sha pick) each of which flips a different case red.
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
    # .ci/scripts too, so BASH gates can be registered. Without this the harness
    # could only ever test scripts/*.ts, which excluded ~30 shell gates -- and
    # the worst real instance of a vacuous gate lived in one of them
    # (.ci/scripts/private/run-renet.sh used to exit 0, silently taking
    # govulncheck, deadcode and golangci-lint with it).
    mkdir -p "$TEMP/.ci"
    cp -r "$REPO_ROOT/.ci/scripts" "$TEMP/.ci/scripts"
    [[ -d "$REPO_ROOT/.ci/config" ]] && cp -r "$REPO_ROOT/.ci/config" "$TEMP/.ci/config"
    # node_modules resolution walks upward from the script, so link the real
    # one in; the point of the fixture is an empty SOURCE tree, not a broken
    # runtime.
    ln -s "$REPO_ROOT/node_modules" "$TEMP/node_modules"

    local out rc=0
    # Registry entries are relative to the repo root and may be .ts (run via
    # tsx) or .sh (run directly).
    # CI=true on purpose: a gate is being judged on what it does IN CI, and some
    # deliberately soften to a warning locally (require_submodule in
    # .ci/scripts/lib/common.sh does exactly that, so a fresh clone without
    # --recursive stays workable while CI still fails loudly).
    if [[ "$script" == *.sh ]]; then
        out="$(cd "$TEMP" && CI=true bash "$script" 2>&1)" || rc=$?
    else
        out="$(cd "$TEMP" && CI=true npx tsx "scripts/$script" 2>&1)" || rc=$?
    fi
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
        # .sh entries are repo-root-relative; .ts entries are relative to scripts/.
        if [[ "$script" == *.sh ]]; then
            [[ -f "$REPO_ROOT/$script" ]] ||
                log_fail "registry names $script, which does not exist -- the registry has gone stale"
        elif [[ ! -f "$REPO_ROOT/scripts/$script" ]]; then
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
