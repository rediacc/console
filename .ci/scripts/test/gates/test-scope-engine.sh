#!/bin/bash
# Unit test for the pure core of the CI scope engine:
# .ci/scripts/ci/scope-map.cjs and .ci/scripts/ci/scope-engine.cjs.
#
# WHAT THIS GUARDS. The engine will replace detect-pointer-bump.sh (defect D9:
# its ancestor walk aborted on the refs/pull/N/merge commit and NEVER fired)
# and will eventually decide which CI jobs a PR may skip. The one rule that
# makes that safe is fail-CLOSED classification: every ambiguous input, an
# unknown path, an empty delta, a malformed line, resolves to FULL CI. A false
# full run costs 70 minutes; a false reduced run merges untested code.
#
# Every case here is CONTROL-PROVEN: for each rule asserted there is also an
# input that produces the OPPOSITE outcome, so a classifier hardcoded to
# "always full" (or "always reduced") fails this file. A validator that passes
# when given nothing is broken by definition.
#
# Edge-case numbers cite the Wave B edge-case matrix (17, 19-24 are covered
# here; the baseline cases 1/2/4/5 via the exported pure helpers).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ENGINE="$REPO_ROOT/.ci/scripts/ci/scope-engine.cjs"
MAP="$REPO_ROOT/.ci/scripts/ci/scope-map.cjs"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# plan  -- run the real CLI on stdin, capture the JSON plan
plan() { node "$ENGINE" --classify >"$WORK/plan.json"; }

# pget <js-expr over `p`> -- read a field out of the captured plan
pget() {
    node -e '
const plan = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const get = new Function("p", "return (" + process.argv[2] + ");");
const v = get(plan);
process.stdout.write(typeof v === "string" ? v : JSON.stringify(v));
' "$WORK/plan.json" "$1"
}

# ---------------------------------------------------------------------------

test_unclassified_path_fails_closed() {
    # Edge case 17, the single most important behaviour: a path matching NO
    # rule yields full with the diagnostic pinned, so a new subtree can never
    # silently skip anything.
    printf 'totally/new/tree/file.bin\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "an unmatched path must force full CI"
    assert_contains "$(pget 'p.full_reasons')" "unclassified:totally/new/tree/file.bin" \
        "with the unclassified:<path> diagnostic pinned"
    # CONTROL: full is not the constant answer. A classified docs path must
    # come out reduced, or the fail-closed verdict above proves nothing.
    printf 'docs/ci-overhaul/notes.md\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a classified docs path must NOT force full"
    log_pass "an unclassified path fails closed to full, and only then (case 17)"
}

test_empty_delta_is_full_never_reduced() {
    # Edge case 22: an empty delta means the computation upstream failed.
    printf '' | plan
    assert_eq "$(pget 'p.mode')" "full" "an empty file list must yield full"
    assert_contains "$(pget 'p.full_reasons')" "empty-delta" "named as empty-delta"
    # CONTROL: emptiness is the trigger, not a constant: one docs line flips it.
    printf 'docs/a.md\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "the same pipeline with one docs line is reduced"
    log_pass "an empty delta yields full, never reduced (case 22)"
}

test_deletion_classifies_like_modification() {
    # Edge case 19: deletion is a change. Fed as a real diff-tree raw D line,
    # the parser must extract the path, not treat the line as opaque.
    printf ':100644 000000 abc1234 0000000 D\tpackages/cli/src/gone.ts\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a deleted cli file is a cli change, not full"
    assert_eq "$(pget 'p.modules')" '["cli"]' "and classifies to the cli module"
    # CONTROL: the raw line was actually parsed. Had the parser kept the line
    # opaque it would be unclassified = full and this reason would be absent.
    assert_contains "$(pget 'p.reasons')" "packages/cli/src/gone.ts -> cli" \
        "the D line's path was extracted by the raw parser"
    log_pass "a deleted file classifies exactly like a modified one (case 19)"
}

test_rename_classifies_both_sides_union_wins() {
    # Edge case 20: a rename across module boundaries classifies BOTH sides.
    printf ':100644 100644 abc1234 def5678 R090\tdocs/old.md\tpackages/cli/src/new.ts\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a rename is still classifiable"
    assert_eq "$(pget 'p.modules')" '["cli","docs"]' "both sides classified, union wins"
    assert_eq "$(pget 'p.jobs.unit.run')" "true" "the cli side pulls unit into scope"
    # CONTROL: the union is computed, not hardcoded. A docs-internal rename
    # must NOT drag cli in.
    printf ':100644 100644 abc1234 abc1234 R100\tdocs/a.md\tdocs/b.md\n' | plan
    assert_eq "$(pget 'p.modules')" '["docs"]' "a docs-internal rename stays docs-only"
    assert_eq "$(pget 'p.jobs.unit.run')" "false" "and unit stays out of scope"
    log_pass "a rename classifies both sides and the union wins (case 20)"
}

test_hostile_paths_survive_the_parser() {
    # Edge case 21: spaces, unicode, and git C-quoting (the default
    # core.quotepath form, octal UTF-8 bytes plus escaped quotes).
    {
        printf '%s\n' 'docs/has space.md'
        printf '%s\n' 'docs/übersicht.md'
        printf '%s\n' '"docs/f\303\274r.md"'
        printf '%s\n' '"docs/say \"hi\".md"'
    } | plan
    assert_eq "$(pget 'p.mode')" "reduced" "all four hostile docs paths classify"
    assert_eq "$(pget 'p.modules')" '["docs"]' "to the docs module"
    assert_not_contains "$(pget 'p.full_reasons')" "unclassified" \
        "none of them fell through the parser into unclassified"
    assert_contains "$(pget 'p.reasons')" "docs/für.md -> docs" \
        "the C-quoted octal path was decoded to its real UTF-8 form"
    # CONTROL: unquoting must not LAUNDER unknown paths into a pass. A quoted
    # path outside every rule still fails closed.
    printf '%s\n' '"weird/f\303\274r.bin"' | plan
    assert_eq "$(pget 'p.mode')" "full" "a quoted unknown path still fails closed"
    assert_contains "$(pget 'p.full_reasons')" "unclassified:weird/für.bin" \
        "and its decoded form is named in the diagnostic"
    log_pass "spaces, unicode and quoted paths survive the parser (case 21)"
}

test_ci_lib_forces_full() {
    # Edge case 23: .ci/scripts/lib is sourced by ~150 scripts; touching it
    # invalidates everything, with its own reason, distinct from the generic
    # harness bucket.
    printf '.ci/scripts/lib/common.sh\n' | plan
    assert_eq "$(pget 'p.mode')" "full" ".ci/scripts/lib/** must force full"
    assert_contains "$(pget 'p.full_reasons')" "ci-lib:.ci/scripts/lib/common.sh" \
        "with the ci-lib reason, not a generic one"
    # CONTROL A: the rule is the lib prefix, not all of .ci. Tutorial scripts
    # are a mapped module with a real (ops-only) surface.
    printf '.ci/tutorials/tutorial-backup-restore.sh\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" ".ci/tutorials/** is a mapped module, not blanket full"
    assert_eq "$(pget 'p.jobs.ops.run')" "true" "tutorial scripts pull ops into scope"
    assert_eq "$(pget 'p.jobs.unit.run')" "false" "but not unit"
    # CONTROL B: the reason is specific. A non-lib .ci script is full too, but
    # as harness, so a rule-ordering regression (lib swallowed by the generic
    # rule) shows up here.
    printf '.ci/scripts/build/build-cli.sh\n' | plan
    assert_contains "$(pget 'p.full_reasons')" "harness:.ci/scripts/build/build-cli.sh" \
        "a non-lib .ci path carries the harness reason"
    assert_not_contains "$(pget 'p.full_reasons')" "ci-lib:" \
        "and never the ci-lib one"
    log_pass ".ci/scripts/lib forces full with its own pinned reason (case 23)"
}

test_workflow_closure_is_computed_not_name_matched() {
    # Edge case 24: the closure is computed at RUNTIME by iterating
    # `uses: ./.github/workflows/` from ci.yml. The trap this prevents:
    # ci.yml:560 calls cd-stage.yml, so a `cd-*` name exclusion would drop a
    # workflow that IS inside the CI closure.
    local closure
    closure="$(node -e '
const e = require(process.argv[1]);
process.stdout.write([...e.computeWorkflowClosure(process.argv[2])].sort().join("\n"));
' "$ENGINE" "$REPO_ROOT")"
    assert_contains "$closure" ".github/workflows/cd-stage.yml" \
        "cd-stage.yml is IN the closure (the cd-* trap, verified at ci.yml:560)"
    assert_contains "$closure" ".github/workflows/ct-tests.yml" \
        "ct-tests.yml is in the closure"
    # CONTROL: the closure is a computation, not 'every workflow file'.
    assert_not_contains "$closure" "watchdog-monitor.yml" \
        "a workflow ci.yml never calls is NOT in the closure"

    # Both branches classify FULL (fail-closed either way), with distinct
    # reasons proving the runtime closure is what decided.
    printf '.github/workflows/cd-stage.yml\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "an in-closure workflow change forces full"
    assert_contains "$(pget 'p.full_reasons')" "workflow-closure:.github/workflows/cd-stage.yml" \
        "attributed to the closure, where a cd-* pattern would have missed it"
    printf '.github/workflows/watchdog-monitor.yml\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "a non-closure workflow change is still full in v1"
    assert_contains "$(pget 'p.full_reasons')" "workflow-non-closure:" \
        "but attributed as non-closure"

    # Recursion proof on a fixture tree: entry -> zz-a -> zz-b, zz-c orphaned.
    # A glob or name-pattern implementation cannot produce this answer.
    mkdir -p "$WORK/fixture/.github/workflows"
    printf 'jobs:\n  a:\n    uses: ./.github/workflows/zz-a.yml\n' >"$WORK/fixture/.github/workflows/ci.yml"
    printf 'jobs:\n  b:\n    uses: ./.github/workflows/zz-b.yml\n' >"$WORK/fixture/.github/workflows/zz-a.yml"
    printf 'jobs: {}\n' >"$WORK/fixture/.github/workflows/zz-b.yml"
    printf 'jobs: {}\n' >"$WORK/fixture/.github/workflows/zz-c.yml"
    local fixture_closure
    fixture_closure="$(node -e '
const e = require(process.argv[1]);
process.stdout.write([...e.computeWorkflowClosure(process.argv[2])].sort().join("\n"));
' "$ENGINE" "$WORK/fixture")"
    assert_contains "$fixture_closure" "zz-b.yml" "transitive uses: references are followed"
    assert_not_contains "$fixture_closure" "zz-c.yml" "unreferenced workflows stay out"
    log_pass "the workflow closure is iterated at runtime, never name-matched (case 24)"
}

test_vm_e2e_surfaces_carry_the_mandated_inputs() {
    # The 8 VM/E2E jobs check out with submodules:true and run setup-workspace
    # (verified against ct-tests.yml), so their surface must include
    # packages/shared, packages/provisioning and every submodule pointer.
    local check
    check="$(node -e '
const m = require(process.argv[1]);
if (m.VM_E2E_JOB_KEYS.length !== 8) {
  process.stdout.write("expected 8 VM/E2E jobs, got " + m.VM_E2E_JOB_KEYS.length);
  process.exit(0);
}
const required = ["shared", "provisioning", "renet", "account", "elite", "homebrew-tap"];
const missing = [];
for (const job of m.VM_E2E_JOB_KEYS) {
  for (const mod of required) {
    if (!m.JOB_SURFACES[job].includes(mod)) missing.push(job + " lacks " + mod);
  }
}
process.stdout.write(missing.length ? missing.join("; ") : "ok");
' "$MAP")"
    assert_eq "$check" "ok" "every VM/E2E surface carries shared, provisioning and all 4 submodules"
    # CONTROL: the includes-check can fail: docs is deliberately NOT in the VM
    # surface, so a surface check that matches everything would trip here.
    local docs_check
    docs_check="$(node -e '
const m = require(process.argv[1]);
process.stdout.write(String(m.VM_E2E_SURFACE.includes("docs")));
' "$MAP")"
    assert_eq "$docs_check" "false" "docs is not in the VM/E2E surface"

    # package-lock.json reaches those jobs via ROOT_MANIFESTS => full: the
    # lockfile keys setup-workspace's cache for EVERY job.
    printf 'package-lock.json\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "a lockfile change forces full"
    assert_contains "$(pget 'p.full_reasons')" "root-manifest:package-lock.json" \
        "as a root manifest"

    # Behavioural: the vector discriminates. A provisioning-only delta runs
    # the VM legs and skips jobs whose surface lacks provisioning.
    printf 'packages/provisioning/src/vm.ts\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a provisioning-only delta is reduced"
    assert_eq "$(pget 'p.jobs.e2e_workers.run')" "true" "and runs the VM E2E legs"
    assert_eq "$(pget 'p.jobs.account_e2e.run')" "false" "but not account e2e"
    assert_eq "$(pget 'p.jobs.renet.run')" "false" "nor the renet tests"
    log_pass "the 8 VM/E2E surfaces carry shared, provisioning, lockfile-via-full and all pointers"
}

test_submodule_pointer_classifies_like_content() {
    # A gitlink path (private/renet, no slash) and expanded submodule content
    # (private/account/web/...) land in the same module bucket.
    printf 'private/renet\n' | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a renet pointer bump is classifiable"
    assert_eq "$(pget 'p.modules')" '["renet"]' "to the renet module"
    assert_eq "$(pget 'p.jobs.e2e_k8s.run')" "true" "renet is in the VM E2E surface"
    assert_eq "$(pget 'p.jobs.elite_run.run')" "true" "and in elite's"
    assert_eq "$(pget 'p.jobs.account_e2e.run')" "false" "but not in account e2e's"
    printf 'private/account/web/src/portal.ts\n' | plan
    assert_eq "$(pget 'p.modules')" '["account"]' "expanded account content classifies to account"
    assert_eq "$(pget 'p.jobs.account_e2e.run')" "true" "which runs account e2e"
    assert_eq "$(pget 'p.jobs.elite_run.run')" "false" "and not elite"
    # CONTROL: only the four known submodules match. A new private/ tree is
    # unclassified = full (an added submodule must never skip anything).
    printf 'private/new-submodule\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "an unknown private/ path fails closed"
    assert_contains "$(pget 'p.full_reasons')" "unclassified:private/new-submodule" \
        "as unclassified"
    log_pass "submodule pointers and expanded content classify to the same module"
}

test_docs_only_delta_reduces_everything() {
    # The reduced happy path from the design docs: docs-only means every
    # scoped job is out of scope. migration-test is deliberately not in the
    # vector at all: it stays unconditional (case 26).
    {
        printf 'docs/ci-overhaul/03-something.md\n'
        printf 'CLAUDE.md\n'
        printf '.claude/settings.json\n'
    } | plan
    assert_eq "$(pget 'p.mode')" "reduced" "a docs-only delta is reduced"
    assert_eq "$(pget 'Object.values(p.jobs).every(j => j.run === false)')" "true" \
        "with every scoped job out of scope"
    assert_eq "$(pget '"migration" in p.jobs || "migration_test" in p.jobs')" "false" \
        "migration-test is not in the vector: it stays unconditional (case 26)"
    # CONTROL: one cli line flips the vector, so all-false is earned, not
    # hardcoded.
    {
        printf 'docs/ci-overhaul/03-something.md\n'
        printf 'packages/cli/src/index.ts\n'
    } | plan
    assert_eq "$(pget 'p.jobs.unit.run')" "true" "adding a cli path pulls unit back in"
    log_pass "a docs-only delta reduces every scoped job, and only then"
}

test_full_mode_runs_every_job() {
    # The consumer side of fail-closed: whenever mode is full, the vector must
    # say run for EVERY job, so a consumer reading it can never skip on a
    # forced-full plan.
    printf 'package.json\n' | plan
    assert_eq "$(pget 'p.mode')" "full" "a root manifest forces full"
    assert_eq "$(pget 'Object.values(p.jobs).every(j => j.run === true)')" "true" \
        "and every job in the vector says run"
    log_pass "full mode always emits an all-run vector"
}

test_classify_mode_is_pure() {
    # --classify must never touch git, gh, or the network. Shim all three
    # commands to leave a sentinel and prove no sentinel appears.
    mkdir -p "$WORK/shim"
    local tool
    for tool in git gh curl; do
        printf '#!/bin/bash\ntouch "%s/called-%s"\nexit 1\n' "$WORK" "$tool" >"$WORK/shim/$tool"
        chmod +x "$WORK/shim/$tool"
    done
    # CONTROL: the shim actually intercepts, so the absence below is evidence.
    PATH="$WORK/shim:$PATH" git status >/dev/null 2>&1 || true
    assert_eq "$([[ -f "$WORK/called-git" ]] && echo yes || echo no)" "yes" \
        "the git shim fires when git is invoked"
    rm -f "$WORK"/called-*

    printf 'docs/a.md\n' | PATH="$WORK/shim:$PATH" node "$ENGINE" --classify >"$WORK/plan.json"
    assert_eq "$(pget 'p.mode')" "reduced" "--classify still works under the shims"
    assert_eq "$(find "$WORK" -maxdepth 1 -name 'called-*' | wc -l)" "0" \
        "--classify invoked none of git, gh, curl"
    log_pass "--classify is pure: no git, no gh, no network"
}

test_baseline_helpers_refuse_weak_baselines() {
    # The exported (not yet wired) baseline decision logic, edge cases 1/2/4/5.
    verdict() {
        node -e '
const e = require(process.argv[1]);
const v = e.evaluateBaselineCandidate(JSON.parse(process.argv[2]));
process.stdout.write(v.usable + ":" + v.reason);
' "$ENGINE" "$1"
    }
    # CONTROL first: the helper CAN say yes, so every refusal below is a
    # decision, not a stuck constant.
    assert_eq "$(verdict '{"conclusion":"success","plan":{"mode":"full","reconciled":true}}')" \
        "true:full-green-attested" "a green, full, reconciled run is a usable baseline"
    assert_eq "$(verdict '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true}}')" \
        "false:reduced-baseline" "a reduced green run is not a baseline (case 1: no evidence chains)"
    assert_eq "$(verdict '{"conclusion":"success"}')" \
        "false:no-skip-plan" "a green run without an attested plan proves nothing (case 2)"
    assert_eq "$(verdict '{"conclusion":"success","plan":{"mode":"full"}}')" \
        "false:unreconciled-outcome" "intent without reconciled outcome is not enough (case 4)"
    assert_eq "$(verdict '{"conclusion":"failure","plan":{"mode":"full","reconciled":true}}')" \
        "false:not-green" "a red run is never a baseline"

    moved() {
        node -e '
const e = require(process.argv[1]);
process.stdout.write(String(e.isBaseUnchanged({planBaseSha: process.argv[2], mergeParentSha: process.argv[3]})));
' "$ENGINE" "$1" "${2:-}"
    }
    assert_eq "$(moved aaa aaa)" "true" "an unchanged base passes (control)"
    assert_eq "$(moved aaa bbb)" "false" "a moved base means full (case 5)"
    assert_eq "$(moved aaa)" "false" "a missing merge parent means full, not a pass"
    log_pass "baseline helpers refuse reduced, unattested and unreconciled baselines (cases 1/2/4/5)"
}

test_surface_table_is_self_validating() {
    # A surface naming a module the table cannot produce would be a job that
    # never re-enters scope. The load-time validator must throw on it.
    local out
    out="$(node -e '
const m = require(process.argv[1]);
try {
  m.validateJobSurfaces({ bad_job: ["no-such-module"] }, m.KNOWN_MODULES);
  process.stdout.write("no-throw");
} catch (e) {
  process.stdout.write(e.message);
}
' "$MAP")"
    assert_contains "$out" "no-such-module" "the validator fires on an unknown module"
    # CONTROL: it accepts the real table (which module load already ran, but
    # prove it explicitly so a future load-order change cannot hollow this out).
    out="$(node -e '
const m = require(process.argv[1]);
m.validateJobSurfaces(m.JOB_SURFACES, m.KNOWN_MODULES);
process.stdout.write("ok");
' "$MAP")"
    assert_eq "$out" "ok" "and accepts the real JOB_SURFACES"
    log_pass "the job-surface table is validated against the known modules"
}

log_test "test-scope-engine"
test_unclassified_path_fails_closed
test_empty_delta_is_full_never_reduced
test_deletion_classifies_like_modification
test_rename_classifies_both_sides_union_wins
test_hostile_paths_survive_the_parser
test_ci_lib_forces_full
test_workflow_closure_is_computed_not_name_matched
test_vm_e2e_surfaces_carry_the_mandated_inputs
test_submodule_pointer_classifies_like_content
test_docs_only_delta_reduces_everything
test_full_mode_runs_every_job
test_classify_mode_is_pure
test_baseline_helpers_refuse_weak_baselines
test_surface_table_is_self_validating
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
