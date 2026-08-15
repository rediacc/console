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
    assert_eq "$(find "$WORK" -maxdepth 1 -name 'called-*' | wc -l || true)" "0" \
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

    # GREENLIGHT-ONLY REDUCTION, the defect that made this engine inert. A run
    # whose every key either ran or carries greenlight evidence covered the
    # work, whatever the aggregate label says; a run that skipped a key as
    # out-of-scope did not, and case 1 still refuses it. Both plans below carry
    # the identical `mode: "reduced"`, so only the per-key reading separates
    # them -- which is the whole point of the pair.
    local greenlit_plan='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "unit":{"run":true,"reason":"full"},
      "renet":{"run":false,"reason":"greenlight:30968082228"}}}}'
    assert_eq "$(verdict "$greenlit_plan")" "true:full-green-attested" \
        "a run reduced ONLY by greenlight evidence is a usable baseline"
    local scoped_plan='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "unit":{"run":true,"reason":"full"},
      "renet":{"run":false,"reason":"out-of-scope"}}}}'
    assert_eq "$(verdict "$scoped_plan")" "false:reduced-baseline" \
        "a run that SCOPE-skipped a key is still not a baseline (case 1 intact)"
    # And the reason string must be the real shape, not any string starting
    # with the word: a hand-written 'greenlight:maybe' proves nothing.
    local forged_plan='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "renet":{"run":false,"reason":"greenlight:probably-fine"}}}}'
    assert_eq "$(verdict "$forged_plan")" "false:reduced-baseline" \
        "a greenlight reason without an evidence run id does not count"
    assert_eq "$(verdict '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{}}}')" \
        "false:reduced-baseline" "an empty jobs vector proves nothing"

    # MALFORMED ENTRIES MUST READ AS "NOT COVERED", and the asymmetry is why
    # this block exists. Reading garbage as coverage reduces a round on
    # evidence nobody checked; reading it as a gap costs one full round. An
    # earlier form of this predicate asked `run !== false`, and every case
    # below answered COVERS under it -- the first one most dangerously,
    # because a dropped `run` key beside an out-of-scope skip is exactly the
    # scope-chaining case 1 forbids, wearing a shape that looked benign.
    local no_run_key='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "renet":{"reason":"out-of-scope"}}}}'
    assert_eq "$(verdict "$no_run_key")" "false:reduced-baseline" \
        "an entry with NO run key is not coverage, whatever its reason says"
    local string_false='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "renet":{"run":"false","reason":"out-of-scope"}}}}'
    assert_eq "$(verdict "$string_false")" "false:reduced-baseline" \
        "the STRING \"false\" is a malformed entry, not a truthy run"
    local zero_run='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{
      "renet":{"run":0,"reason":"out-of-scope"}}}}'
    assert_eq "$(verdict "$zero_run")" "false:reduced-baseline" \
        "and so is 0: only a real boolean true is an executed key"
    # An ARRAY is not the jobs map. Object.values would happily walk it, so the
    # refusal has to be explicit rather than incidental.
    local array_jobs='{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":[
      {"run":true,"reason":"full"}]}}'
    assert_eq "$(verdict "$array_jobs")" "false:reduced-baseline" \
        "an array jobs vector is a shape no producer emits, so it covers nothing"

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

test_baseline_resolution_fails_open_on_every_defect() {
    # resolveBaseline with an INJECTED io: no git, no gh, no network. Each case
    # states the mode and the machine-readable reason, because "full" alone
    # cannot distinguish a correct full round from a permanently stuck one.
    resolve() {
        # $1 = JS expression overriding the default (healthy) io
        # $2 = optional JS expression overriding the default opts
        node -e '
const e = require(process.argv[1]);
const B = "b".repeat(40), H = "h".repeat(40), M = "m".repeat(40), P = "p".repeat(40);
const base = {
  isShallow: () => false,
  firstParent: () => P,
  diffPaths: () => ["docs/x.md"],
  listCandidates: () => [{ sha: B, conclusion: "success", runId: 1,
    plan: { mode: "full", reconciled: true, base_sha: P } }],
};
const io = Object.assign({}, base, eval("(" + process.argv[2] + ")"));
const opts = Object.assign({ head: H, mergeSha: M }, eval("(" + process.argv[3] + ")"));
const r = e.resolveBaseline(opts, io);
process.stdout.write(r.plan.mode + ":" + (r.plan.full_reasons[0] || r.plan.modules.join(",")));
' "$ENGINE" "$1" "${2:-{\}}"
    }

    # CONTROL, and it is the whole point of the mode: a green full attested
    # baseline plus a one-file docs delta MUST reduce. Without this passing,
    # every "full" below would be indistinguishable from a dead mechanism.
    assert_eq "$(resolve '{}')" "reduced:docs" \
        "green+full+reconciled baseline with a docs delta reduces (the headline case)"

    # SHAPE CHECK: it can still see a real source change through the same path.
    assert_eq "$(resolve '{diffPaths:()=>["packages/cli/src/a.ts"]}')" "reduced:cli" \
        "and it still classifies a source change into its module"

    # Fail-open matrix. Every one of these must be full, with its own reason.
    assert_eq "$(resolve '{isShallow:()=>true}')" "full:baseline:shallow-clone" \
        "a shallow clone cannot be walked, so it is full (not a partial walk)"
    assert_eq "$(resolve '{listCandidates:()=>{throw new Error("boom")}}')" \
        "full:baseline:candidate-walk-failed:boom" "a throwing git walk is an answer, never a crash"
    assert_eq "$(resolve '{listCandidates:()=>[]}')" "full:baseline:no-candidates" \
        "no ancestors means full"
    assert_eq "$(resolve '{listCandidates:()=>[{sha:"x",conclusion:"failure",plan:null}]}')" \
        "full:baseline:none-usable" "a red ancestor is not a baseline"
    assert_eq "$(resolve '{diffPaths:()=>{throw new Error("nope")}}')" \
        "full:baseline:diff-failed:nope" "a failed diff is full, never an empty delta"
    assert_eq "$(resolve '{diffPaths:()=>Array.from({length:301},(_,i)=>"docs/f"+i+".md")}')" \
        "full:baseline:diff-truncated:301" "past the 300-file cap the list is incomplete, so full"
    assert_eq "$(resolve '{}' '{mergeSha:null}')" "full:baseline:base-sha-unknown" \
        "an unknown merge parent is never read as an unchanged base"

    # Case 5 fold: main moved, and main's OWN delta must be unioned in or a
    # change that landed on main would be invisible to this round.
    local folded
    folded="$(resolve '{firstParent:()=>"n".repeat(40),diffPaths:(f)=>f==="b".repeat(40)?["docs/x.md"]:["packages/cli/src/leaked.ts"]}')"
    assert_eq "$folded" "reduced:cli,docs" \
        "a moved base folds main's delta in rather than losing it (case 5)"
    log_pass "baseline resolution reduces when it should and fails open on every defect"
}

test_resolve_baseline_needs_a_repo() {
    # A misspelled/absent --repo must be a USAGE error. Failing open to full
    # here would hide a caller bug as a permanently expensive pipeline, which
    # is precisely how D9 stayed false for twelve runs.
    local rc=0
    node "$ENGINE" --resolve-baseline --head deadbeef >/dev/null 2>&1 || rc=$?
    assert_eq "$rc" "2" "--resolve-baseline without --repo exits 2 (usage), not 0 (silent full)"
    log_pass "a caller bug is reported, not absorbed into a full run"
}

# ---------------------------------------------------------------------------
# THE CLASSIFICATION REGRESSION TABLE (2026-08-05).
#
# WHAT IT GUARDS, and why nothing above already did. Every case above tests the
# engine's DECISION MACHINERY -- fail-closed on an unclassified path, the
# baseline-coverage predicate, the walk's bounds. None of them pins the ANSWER
# for a representative delta, which is the half the operator actually
# experienced: "run 30983418337 ran the whole matrix for a commit that is
# documentation". Add a surface to JOB_SURFACES, mistype a glob, or drop a
# module mapping, and every case above stays green while docs-only silently
# goes back to running eighteen jobs.
#
# SETS, NEVER COUNTS, wherever the expectation is a partial run. A count of 14
# passes just as happily when the map swaps two keys for two others, which is
# exactly the rot this table exists to catch.
#
# WHY IT IS CALLED LAST, which is load-bearing and not stylistic.
# test-gate-anti-vacuity.sh registers THIS FILE with the pattern `closure`: run
# against an empty fixture tree, the file must fail AND say "closure". That is
# test_workflow_closure_is_computed_not_name_matched, seventh in the call order,
# and log_fail exits on the first failure. A table placed ahead of it would fail
# first on the empty tree with a message containing no "closure", quietly
# retiring that registration. Verified by running the anti-vacuity gate before
# and after this block was added.
# ---------------------------------------------------------------------------

# classify_verdict <path>... -> "<mode>|<total keys>|<sorted running keys>",
# or a SENTINEL that can never equal an expectation.
#
# The sentinel is the whole point. A classification that produced nothing must
# not read as "no keys to run": here that is the vacuity shape, and it fails
# toward skipping everything. So a dead engine, unparseable bytes and a plan
# with no job vector each answer with a distinct string rather than an empty
# key list, and the `total` field means a zero-key row still has to prove it
# saw all eighteen keys before finding none of them running.
classify_verdict() {
    local out
    if ! out="$(printf '%s\n' "$@" | node "$ENGINE" --classify 2>/dev/null)" || [[ -z "$out" ]]; then
        printf 'ENGINE-PRODUCED-NOTHING'
        return 0
    fi
    printf '%s' "$out" | node -e '
let raw = "";
process.stdin.on("data", (d) => (raw += d)).on("end", () => {
  let p;
  try { p = JSON.parse(raw); } catch { process.stdout.write("PLAN-UNPARSEABLE"); return; }
  const jobs = p && p.jobs;
  if (!jobs || typeof jobs !== "object" || Array.isArray(jobs)) {
    process.stdout.write("PLAN-HAS-NO-JOB-VECTOR");
    return;
  }
  const keys = Object.keys(jobs);
  const running = keys.filter((k) => jobs[k].run === true).sort();
  process.stdout.write([p.mode, keys.length, running.join(" ")].join("|"));
});'
}

# expect_classify <label> <"mode|total|keys"> <path>...
#
# Named expect_ rather than assert_ deliberately: the assertion census at the
# foot of this file counts lines matching ^\s*assert_, so a helper called
# assert_classify would count its own definition and inflate the total by one.
expect_classify() {
    local label="$1" expected="$2"
    shift 2
    local actual
    actual="$(classify_verdict "$@")"
    # Spelled as an if rather than `[[ ... ]] && return 0`: under this file's
    # `set -e` the AND-list form happens to be safe (bash exempts every command
    # in a && list but the last), and a reader should not have to know that to
    # trust the failure path runs.
    if [[ "$actual" == "$expected" ]]; then
        return 0
    fi
    # An ACTIONABLE failure. A legitimate JOB_SURFACES change must be a
    # one-line edit here, not a stare at two fourteen-item blobs looking for
    # the difference: a regression test that is a puzzle to update is a
    # regression test that gets suppressed instead of updated.
    local want got missing unexpected
    want="$(tr ' ' '\n' <<<"${expected##*|}" | sed '/^$/d' | sort -u)"
    got="$(tr ' ' '\n' <<<"${actual##*|}" | sed '/^$/d' | sort -u)"
    missing="$(comm -23 <(printf '%s\n' "$want") <(printf '%s\n' "$got") | tr '\n' ' ')"
    unexpected="$(comm -13 <(printf '%s\n' "$want") <(printf '%s\n' "$got") | tr '\n' ' ')"
    log_fail "$label: expected '$expected', got '$actual' (missing: ${missing:-none}| unexpected: ${unexpected:-none})"
}

test_representative_deltas_classify_to_pinned_verdicts() {
    # Each partial set is named ONCE and reused by every row that expects it,
    # so a legitimate map change edits one line rather than several rows. The
    # sets are the measured truth as of 2026-08-05, taken from the real
    # --classify path rather than read off JOB_SURFACES by hand.
    local cli_keys="drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode e2e_migrate e2e_workers fork_isolation install_methods ops package_tests unit update_flow"
    local renet_keys="drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode e2e_migrate e2e_workers elite_run fork_isolation install_methods license_enforcement ops package_tests renet update_flow"
    local account_keys="account_e2e drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode e2e_migrate e2e_workers fork_isolation ops"

    # -- the rows that must skip the heavy matrix entirely -------------------
    expect_classify "docs only" "reduced|18|" 'docs/ci-overhaul/06-progress.md'
    expect_classify "agent tooling only" "reduced|18|" '.claude/commands/pr-babysit.md'
    # THE REPORTED CASE (commit bcc4f1ee1, 2026-08-06): an Apache-2.0
    # attribution-URL check that ran the ceph fork test, because scripts/**
    # was a single blanket harness rule. Kept recognisable as the incident.
    expect_classify "gate source only" "reduced|18|" 'scripts/check-embed-credits.ts'
    expect_classify "gate lib only" "reduced|18|" 'scripts/lib/blocker-validator.ts'
    expect_classify "ci-runner only" "reduced|18|" 'scripts/ci-runner/manifest.ts'
    # The over-eager-skip direction: a gate source must not SUPPRESS a real
    # module that another file in the same delta pulls in.
    expect_classify "MIXED gate source + one cli file" "reduced|18|$cli_keys" \
        'scripts/check-cli-docs.ts' 'packages/cli/src/commands/repo.ts'
    # THE REPORTED CASE, kept recognisable as the report it came from: the
    # exact four paths of push 1d172438f..208c8a2d9, whose run 30983418337 ran
    # all eighteen keys. A regression test for a real incident should be
    # readable as that incident.
    expect_classify "the reported push (run 30983418337)" "reduced|18|" \
        '.claude/agents/pr-babysitter.md' \
        '.claude/commands/pr-babysit.md' \
        '.claude/hooks/stop/wl_judge.py' \
        'docs/agent/main/REPORT-licensing-bigbang-2026-08-04.md'

    # -- the rows that must run a specific, named set -----------------------
    expect_classify "cli source" "reduced|18|$cli_keys" 'packages/cli/src/commands/repo.ts'
    expect_classify "renet source" "reduced|18|$renet_keys" 'private/renet/pkg/license/keys.go'
    expect_classify "account source" "reduced|18|$account_keys" 'private/account/src/index.ts'

    # THE ROW THAT CATCHES AN OVER-EAGER SKIP, which is the direction that
    # costs correctness rather than money: docs alongside one cli file must
    # still run every cli key. An engine that let the docs classification win
    # would pass every zero-key row above and be catastrophically wrong here.
    expect_classify "MIXED docs + one cli file" "reduced|18|$cli_keys" \
        'docs/ci-overhaul/06-progress.md' 'packages/cli/src/commands/repo.ts'

    # -- the rows that must force full --------------------------------------
    # Asserted STRUCTURALLY (mode, every key running, the pinned reason) rather
    # than as a literal eighteen-name list. Naming all eighteen in three more
    # rows would make a legitimate key addition an eighteen-line diff in a file
    # that is not about the key list, and "every key runs" is the property that
    # actually matters for a forced-full round.
    local full_row
    for full_row in \
        '.github/workflows/ci.yml|workflow-closure:.github/workflows/ci.yml' \
        '.audit-allowlist|root-manifest:.audit-allowlist' \
        '.ci/lib/common.sh|harness:.ci/lib/common.sh' \
        'scripts/drills/lib.sh|harness:scripts/drills/lib.sh' \
        'scripts/generate-third-party-licenses.ts|harness:scripts/generate-third-party-licenses.ts'; do
        local path="${full_row%%|*}" reason="${full_row##*|}"
        printf '%s\n' "$path" | plan
        assert_eq "$(pget 'p.mode')" "full" "$path forces full CI"
        assert_eq "$(pget 'Object.values(p.jobs).every(j => j.run === true)')" "true" \
            "and every key in the vector runs for $path"
        assert_contains "$(pget 'p.full_reasons')" "$reason" \
            "naming $reason as the reason"
    done

    # -- the block's own anti-vacuity control -------------------------------
    # It cannot borrow this file's registered one: that fires seven tests
    # earlier and never reaches here. So prove the sentinel is live, or every
    # zero-key row above could be passing on an engine that ran at all.
    local saved_engine="$ENGINE"
    ENGINE="$WORK/definitely-not-an-engine.cjs"
    assert_eq "$(classify_verdict 'docs/ci-overhaul/06-progress.md')" "ENGINE-PRODUCED-NOTHING" \
        "a classification that could not run must never read as 'no keys to run'"
    ENGINE="$saved_engine"
    # CONTROL for the control: the real engine still answers, so the sentinel
    # above is a dead engine rather than a helper stuck at its error string.
    assert_eq "$(classify_verdict 'docs/ci-overhaul/06-progress.md')" "reduced|18|" \
        "and the same call against the real engine answers normally"
    log_pass "representative deltas classify to their pinned verdicts, as sets"
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
test_baseline_resolution_fails_open_on_every_defect
test_resolve_baseline_needs_a_repo
test_surface_table_is_self_validating
# LAST, deliberately: see the block comment above classify_verdict. The
# anti-vacuity registration for this file expects the empty-tree run to die in
# the closure test, which is seventh.
test_representative_deltas_classify_to_pinned_verdicts
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
# The classification rows assert through expect_classify, which the census
# above cannot see. Counted separately so the table cannot silently shrink
# either. The trailing space keeps the helper's own definition out of the
# count, so this is call sites and nothing else.
echo "classification rows: $(grep -cE '^[[:space:]]*expect_classify ' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
