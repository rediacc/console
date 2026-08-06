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
    # The probe gate's subject is a single library file. Against an empty tree
    # that file is absent, and "nothing to check" must be a FAILURE: a liveness
    # gate that silently passes when it cannot reach the probe would recreate
    # the very class it exists to catch (a check that cannot tell absent from
    # present). It also refuses when python3 is missing, because its control
    # listener could not fire.
    ".ci/scripts/quality/check-account-probes.sh|nothing to check"
    # NOT registered: .ci/scripts/quality/check-drill-verdicts.sh. Its sibling
    # above IS, and the asymmetry is real rather than an oversight. The probe
    # gate's subject is .ci/lib/account.sh, which this harness's fixture does
    # NOT copy, so an empty tree genuinely starves it. The drill-verdict gate's
    # subject is scripts/drills/lib.sh, and the fixture DOES copy scripts/ — so
    # on the "empty" tree its subject is present, all four verdict assertions
    # run for real, and it correctly exits 0. Registering it asserted that a
    # gate must fail when its input exists, which is backwards; the meta-gate
    # caught exactly that on the first run. Its own missing-subject branch is
    # real but unreachable from here.
    # Against an empty tree every oracle is unavailable, so the run is vacuous
    # and must FAIL rather than report "every entry is still load-bearing".
    "check-suppression-liveness.ts|vacuous"
    # A bash gate, reachable only since this harness learned to run .sh. It used
    # to `exit 0` when private/renet was absent, silently taking govulncheck,
    # deadcode and golangci-lint with it.
    ".ci/scripts/private/run-renet.sh|required"
    # Same submodule, same failure mode: with private/renet absent it would run
    # `go test` over nothing and report that the licence tier map covers the
    # function registry. The CLI now derives its licence-issuance class from
    # that map, so a vacuous green here would launder a console defect too.
    ".ci/scripts/quality/check-renet-tier-map.sh|required"
    # Same shape again: `require_submodule ... || exit 0` becomes a hard fail
    # under CI=true (which this harness sets), so an empty tree is a loud
    # "required in CI but missing" rather than a green diff of nothing.
    ".ci/scripts/quality/check-renet-types.sh|required"
    # Python lint. Against an empty tree `git ls-files` enumerates nothing and
    # `ruff check` with no paths exits 0 -- indistinguishable from a clean repo,
    # which is the exact shape this harness exists to catch. The input floor is
    # therefore checked BEFORE the linter is even resolved, so the empty-tree
    # failure is about VACUITY and not about a missing binary: an absent ruff
    # would be an ENVIRONMENT failure wearing a vacuity failure's exit code, and
    # pinning that would assert nothing about the gate.
    ".ci/scripts/quality/check-python-lint.sh|VACUOUS INPUT"
    # Same shape, different subject: against an empty tree `git ls-files` returns
    # no JS/TS at all and the detector would report "no inline Python" over zero
    # files -- indistinguishable from a clean repo. The MIN_FILES floor turns
    # that into a loud refusal. Its own detector controls run first and abort
    # separately, so a control failure cannot masquerade as this one.
    ".ci/scripts/quality/check_inline_python.py|VACUOUS INPUT"
    # Against an empty tree there are no locale files at all, so every comparison
    # is over an empty set and the gate would exit 0 reporting that every value
    # matches. The MIN_PAIRS floor turns that into a loud refusal.
    ".ci/scripts/quality/check_i18n_value_types.py|VACUOUS INPUT"
    # NOT registered here: .ci/breakpoint/scripts/check-breakpoint-drift.sh.
    # This harness's fixture copies scripts/ and .ci/scripts/ but not
    # .ci/breakpoint/, so the drift gate would fail with "No such file or
    # directory" -- non-zero for a reason that has nothing to do with vacuity,
    # which is precisely the false signal the REGISTRY POLICY above warns about.
    # Its missing-manifest behaviour is proven in test-breakpoint-portability.sh
    # instead, where an isolated copy of the folder genuinely exists.
    # NOT registered here either: .ci/scripts/quality/check-autopilot-no-bypass.sh.
    # Its sibling check-autopilot-workflow-invariants.sh IS registered below, and
    # the asymmetry is deliberate rather than an oversight. That one reads the
    # workflow tree, so an empty fixture makes it vacuous and it must say so.
    # This one never touches the tree at all: it is three `gh api` calls against
    # the live ruleset (:52, :71). An empty-tree run would exit non-zero on the
    # absent AUTOPILOT_APP_ID, which is an ENVIRONMENT failure wearing a vacuity
    # failure's exit code, and pinning it would assert nothing about the gate.
    # Verified live instead, 2026-07-30: with AUTOPILOT_APP_ID=4409539 it exits 0
    # and reports ruleset 12344707 bypass actors [RepositoryRole:5,
    # Integration:2772000] with autopilot absent, which is the property it exists
    # to defend.
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
    # The empty tree has no package.json and no .github/workflows, so there is
    # no gate census on either side and every one of its seven assertions would
    # be over an empty set. It replaced check-ci-chain-parity.ts and
    # check-gate-reachability.ts, which were registered here separately for the
    # same property; both are gone.
    "check-ci-parity.ts|Refusing to run"
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
    "check-jq-boolean-default.ts|Refusing to run"
    ".ci/scripts/security/check-autopilot-workflow-invariants.sh|INVARIANT-FAIL"
    # Its DOCS_DIR is a hardcoded path constant, so this is root pattern 1
    # verbatim: point it at a tree without packages/www/src/content/docs and
    # the glob returns zero files, every loop iterates zero times, and it
    # printed "All external links are valid". Measured on the empty fixture
    # before the guard was added, not inferred from reading it.
    "check-external-links.ts|Refusing to run"
    # Root pattern 1 with a baseline bolted on, which makes it worse: with the locale
    # trees absent it finds zero contamination AND every one of its 379 baselined
    # findings looks fixed, so an unguarded version would either print a checkmark or
    # fail for the wrong reason. It must refuse instead.
    "check-locale-de-contamination.ts|Refusing to run"
    # Its sibling, and root pattern 1 again: three hardcoded locale-root constants, so a
    # tree without any of them made it walk zero locales and print a checkmark. It was
    # NOT registered here while it carried a second, subtler vacuity inside itself --
    # `if (!STOPWORDS[locale]) continue` silently skipped ar/ja/ko/ru/zh/et, which is how
    # 379 German values lived in account-web's ar/ja/ru/zh under a green gate. That skip
    # is now a hard error naming the locale, so the only way left to make this gate
    # assert nothing is to take its input away -- which is exactly what this entry pins.
    "check-i18n-cross-locale.ts|Refusing to run"
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
    #
    # NOT registered here either: .ci/scripts/test/gates/test-scope-gate-outputs.sh,
    # measured the same way and with the same result: all 6 cases pass against
    # the empty tree (exit 0). It BUILDS the tree it needs -- it copies
    # .ci/scripts/ci into a temp dir, `git init`s a repository there with the
    # branch shape a baseline walk requires, and shims `gh` on PATH -- so the
    # only repo input it has is the .ci/scripts/ tree this harness copies in
    # anyway. It reads no packages/, no private/, no .github/. Passing with the
    # source tree absent is CORRECT for it, so an entry here could never fail.
    # Its controls are inline, one per case, and the emitter control was proven
    # by a planted defect during authoring (suppress the run_*=false push in
    # scope-shadow.sh's emitter and case (a) goes red naming the dead emitter;
    # restore and it goes green). That same planted defect also caught a defect
    # in the TEST: collecting the lines before the control check made the failing
    # run exit silently with an empty log, which is a right exit code and a dead
    # diagnostic. The control now runs first.
    #
    # NOT registered here either: .ci/scripts/test/gates/test-watchdog-supersession.sh,
    # and the same measurement was taken rather than reasoned: all 9 assertions
    # pass against the empty tree (exit 0). Its only repo dependency is
    # .ci/scripts/ci/watchdog-monitor.cjs, which this harness copies in, and
    # every input to the decision under test is a literal in the test itself.
    # Passing with the source tree absent is CORRECT for it, so an entry here
    # could never fail. Its controls are inline and were proven by hand during
    # authoring: relaxing the predicate to drop `noFailures` flips
    # "a real failure is never laundered as supersession" red, and relaxing
    # `newerRunExists === true` to `Boolean(newerRunExists)` flips
    # "newerRunExists is compared strictly" red. Both directions were run, not
    # assumed. Its sibling test-watchdog-schedule-exemption.sh is unregistered
    # on the same grounds.
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
    # .sh and .py are repo-root-relative and run directly; everything else is a
    # .ts under scripts/, run via tsx. The else-branch used to be the ONLY
    # alternative to .sh, which silently resolved any new language to
    # "scripts/<path>" and failed as a stale-registry error rather than as an
    # unsupported one -- the first .py entry hit exactly that.
    if [[ "$script" == *.sh ]]; then
        out="$(cd "$TEMP" && CI=true bash "$script" 2>&1)" || rc=$?
    elif [[ "$script" == *.py ]]; then
        out="$(cd "$TEMP" && CI=true python3 "$script" 2>&1)" || rc=$?
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
        # .sh and .py entries are repo-root-relative; .ts entries are relative
        # to scripts/.
        if [[ "$script" == *.sh || "$script" == *.py ]]; then
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
