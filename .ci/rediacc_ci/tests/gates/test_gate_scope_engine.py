"""Port of `.ci/scripts/test/gates/test-scope-engine.sh`.

Unit test for the pure core of the CI scope engine: `.ci/scripts/ci/scope-map.cjs` and `.ci/scripts/ci/scope-engine.cjs`.

WHAT THIS GUARDS. The engine replaces `detect-pointer-bump.sh` (defect D9: its ancestor walk aborted on the `refs/pull/N/merge` commit and NEVER fired) and decides which CI jobs a PR may skip. The one rule that makes that safe is fail-CLOSED classification: every ambiguous input, an unknown path, an empty delta, a malformed
line, resolves to FULL CI. A false full run costs 70 minutes; a false reduced run
merges untested code.

Every case here is CONTROL-PROVEN: for each rule asserted there is also an input that produces the OPPOSITE outcome, so a classifier hardcoded to "always full" (or "always reduced") fails this file. A validator that passes when given nothing is broken by definition.

Edge-case numbers cite the Wave B edge-case matrix (17, 19-24 here; the baseline
cases 1/2/4/5 via the exported pure helpers).

WHAT THE PORT CHANGES, and it is one thing. The twin reads plan fields through a `pget` helper that evaluates a JS expression against the parsed plan in a nested
`node`; here the plan is parsed by Python and the predicates are Python. That removes
one interpreter hop per assertion and nothing else: the plan itself is still produced by the REAL `node .ci/scripts/ci/scope-engine.cjs --classify`, and every assertion whose subject is a JS export (`computeWorkflowClosure`, `evaluateBaselineCandidate`, `resolveBaseline`, `isBaseUnchanged`, `validateJobSurfaces`, `JOB_SURFACES`) still shells out to node, because those cannot be
reimplemented without becoming a second copy of the thing under test.

ONE DETAIL THAT IS EASY TO GET WRONG AND WAS. Where the twin greps a stringified
array, this port stringifies with `ensure_ascii=False`. Python's default escapes
`ü` to `\\u00fc` while JS's `JSON.stringify` does not, so the hostile-path case would have looked for a needle that could never appear and passed vacuously in the `assert_not_contains` direction.

THE ORDER OF DEFINITION IS LOAD-BEARING IN THE TWIN and is preserved here. `test-gate-anti-vacuity.sh` registers the twin with the pattern `closure`: run against an empty fixture tree the twin must fail AND say "closure", which is `test_workflow_closure_is_computed_not_name_matched`, seventh in the call order, and `log_fail` exits on the first failure. A table placed ahead of it
would fail first
with a message containing no "closure" and quietly retire that registration.
"""

import json
import os
import pathlib
import stat
import subprocess

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-scope-engine.sh"

ENGINE = paths.from_root(".ci", "scripts", "ci", "scope-engine.cjs")
MAP = paths.from_root(".ci", "scripts", "ci", "scope-map.cjs")


def node_bin() -> str:
    return harness.require_tool(
        "node", "install Node 22 (the subject is a .cjs module run by node)"
    )


def classify(paths_in: list[str], *, env: dict[str, str] | None = None) -> dict:
    """The real CLI on stdin, parsed. `plan()` plus `pget` in the twin."""
    result = harness.run(
        [node_bin(), str(ENGINE), "--classify"],
        stdin="".join("%s\n" % p for p in paths_in),
        env=env,
        timeout=120,
    )
    if result.rc != 0:
        raise harness.GateAssertionError(
            "scope-engine --classify exited %d, so no plan was produced.\n--- stderr ---\n%s"
            % (result.rc, result.err)
        )
    return json.loads(result.out)


def dumps(value: object) -> str:
    """JS `JSON.stringify` shape: no spaces, and NO \\uXXXX escaping of real UTF-8."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def node_eval(script: str, *args: str) -> str:
    """`node -e <script> <args...>`, stdout only, refusing a nonzero exit loudly."""
    result = harness.run([node_bin(), "-e", script, *args], timeout=120)
    if result.rc != 0:
        raise harness.GateAssertionError(
            "node -e exited %d; the exported helper could not be reached at all.\n"
            "--- stderr ---\n%s" % (result.rc, result.err)
        )
    return result.out


CLOSURE_JS = (
    "const e = require(process.argv[1]);"
    'process.stdout.write([...e.computeWorkflowClosure(process.argv[2])].sort().join("\\n"));'
)


# --- 1 ----------------------------------------------------------------------


def test_unclassified_path_fails_closed(gate):
    """Edge case 17, the single most important behaviour: a path matching NO rule
    yields full with the diagnostic pinned, so a new subtree can never silently skip."""
    plan = classify(["totally/new/tree/file.bin"])
    gate.assert_eq(plan["mode"], "full", "an unmatched path must force full CI")
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "unclassified:totally/new/tree/file.bin",
        "with the unclassified:<path> diagnostic pinned",
    )
    # CONTROL: full is not the constant answer.
    plan = classify(["docs/ci-overhaul/notes.md"])
    gate.assert_eq(plan["mode"], "reduced", "a classified docs path must NOT force full")
    gate.log_pass("an unclassified path fails closed to full, and only then (case 17)")


def test_empty_delta_is_full_never_reduced(gate):
    """Edge case 22: an empty delta means the computation upstream failed."""
    plan = classify([])
    gate.assert_eq(plan["mode"], "full", "an empty file list must yield full")
    gate.assert_contains(dumps(plan["full_reasons"]), "empty-delta", "named as empty-delta")
    # CONTROL: emptiness is the trigger, not a constant.
    plan = classify(["docs/a.md"])
    gate.assert_eq(plan["mode"], "reduced", "the same pipeline with one docs line is reduced")
    gate.log_pass("an empty delta yields full, never reduced (case 22)")


def test_deletion_classifies_like_modification(gate):
    """Edge case 19: deletion is a change, fed as a real diff-tree raw D line."""
    plan = classify([":100644 000000 abc1234 0000000 D\tpackages/cli/src/gone.ts"])
    gate.assert_eq(plan["mode"], "reduced", "a deleted cli file is a cli change, not full")
    gate.assert_eq(dumps(plan["modules"]), '["cli"]', "and classifies to the cli module")
    # CONTROL: the raw line was actually parsed. Kept opaque it would be
    # unclassified = full and this reason would be absent.
    gate.assert_contains(
        dumps(plan["reasons"]),
        "packages/cli/src/gone.ts -> cli",
        "the D line's path was extracted by the raw parser",
    )
    gate.log_pass("a deleted file classifies exactly like a modified one (case 19)")


def test_rename_classifies_both_sides_union_wins(gate):
    """Edge case 20: a rename across module boundaries classifies BOTH sides."""
    plan = classify([":100644 100644 abc1234 def5678 R090\tdocs/old.md\tpackages/cli/src/new.ts"])
    gate.assert_eq(plan["mode"], "reduced", "a rename is still classifiable")
    gate.assert_eq(dumps(plan["modules"]), '["cli","docs"]', "both sides classified, union wins")
    gate.assert_eq(dumps(plan["jobs"]["unit"]["run"]), "true", "the cli side pulls unit into scope")
    # CONTROL: the union is computed, not hardcoded.
    plan = classify([":100644 100644 abc1234 abc1234 R100\tdocs/a.md\tdocs/b.md"])
    gate.assert_eq(dumps(plan["modules"]), '["docs"]', "a docs-internal rename stays docs-only")
    gate.assert_eq(dumps(plan["jobs"]["unit"]["run"]), "false", "and unit stays out of scope")
    gate.log_pass("a rename classifies both sides and the union wins (case 20)")


def test_hostile_paths_survive_the_parser(gate):
    """Edge case 21: spaces, unicode, and git C-quoting (the default core.quotepath
    form, octal UTF-8 bytes plus escaped quotes)."""
    plan = classify(
        [
            "docs/has space.md",
            "docs/\u00fcbersicht.md",
            r'"docs/f\303\274r.md"',
            r'"docs/say \"hi\".md"',
        ]
    )
    gate.assert_eq(plan["mode"], "reduced", "all four hostile docs paths classify")
    gate.assert_eq(dumps(plan["modules"]), '["docs"]', "to the docs module")
    gate.assert_not_contains(
        dumps(plan["full_reasons"]),
        "unclassified",
        "none of them fell through the parser into unclassified",
    )
    gate.assert_contains(
        dumps(plan["reasons"]),
        "docs/f\u00fcr.md -> docs",
        "the C-quoted octal path was decoded to its real UTF-8 form",
    )
    # CONTROL: unquoting must not LAUNDER unknown paths into a pass.
    plan = classify([r'"weird/f\303\274r.bin"'])
    gate.assert_eq(plan["mode"], "full", "a quoted unknown path still fails closed")
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "unclassified:weird/f\u00fcr.bin",
        "and its decoded form is named in the diagnostic",
    )
    gate.log_pass("spaces, unicode and quoted paths survive the parser (case 21)")


def test_ci_lib_forces_full(gate):
    """Edge case 23: `.ci/scripts/lib` is sourced by ~150 scripts, so touching it
    invalidates everything, with its own reason distinct from the harness bucket."""
    plan = classify([".ci/scripts/lib/common.sh"])
    gate.assert_eq(plan["mode"], "full", ".ci/scripts/lib/** must force full")
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "ci-lib:.ci/scripts/lib/common.sh",
        "with the ci-lib reason, not a generic one",
    )
    # CONTROL A: the rule is the lib prefix, not all of .ci.
    plan = classify([".ci/tutorials/tutorial-backup-restore.sh"])
    gate.assert_eq(plan["mode"], "reduced", ".ci/tutorials/** is a mapped module, not blanket full")
    gate.assert_eq(
        dumps(plan["jobs"]["ops"]["run"]), "true", "tutorial scripts pull ops into scope"
    )
    gate.assert_eq(dumps(plan["jobs"]["unit"]["run"]), "false", "but not unit")
    # CONTROL B: the reason is specific, so a rule-ordering regression shows up here.
    plan = classify([".ci/scripts/build/build-cli.sh"])
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "harness:.ci/scripts/build/build-cli.sh",
        "a non-lib .ci path carries the harness reason",
    )
    gate.assert_not_contains(dumps(plan["full_reasons"]), "ci-lib:", "and never the ci-lib one")
    gate.log_pass(".ci/scripts/lib forces full with its own pinned reason (case 23)")


def test_workflow_closure_is_computed_not_name_matched(gate, tmp_path):
    """Edge case 24: the closure is computed at RUNTIME by iterating
    `uses: ./.github/workflows/` from ci.yml. ci.yml:560 calls cd-stage.yml, so a
    `cd-*` name exclusion would drop a workflow that IS inside the CI closure."""
    closure = node_eval(CLOSURE_JS, str(ENGINE), str(paths.repo_root()))
    gate.assert_contains(
        closure,
        ".github/workflows/cd-stage.yml",
        "cd-stage.yml is IN the closure (the cd-* trap, verified at ci.yml:560)",
    )
    gate.assert_contains(
        closure, ".github/workflows/ct-tests.yml", "ct-tests.yml is in the closure"
    )
    # CONTROL: the closure is a computation, not 'every workflow file'.
    gate.assert_not_contains(
        closure, "watchdog-monitor.yml", "a workflow ci.yml never calls is NOT in the closure"
    )

    # Both branches classify FULL (fail-closed either way), with distinct reasons proving the runtime closure is what decided.
    plan = classify([".github/workflows/cd-stage.yml"])
    gate.assert_eq(plan["mode"], "full", "an in-closure workflow change forces full")
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "workflow-closure:.github/workflows/cd-stage.yml",
        "attributed to the closure, where a cd-* pattern would have missed it",
    )
    plan = classify([".github/workflows/watchdog-monitor.yml"])
    gate.assert_eq(plan["mode"], "full", "a non-closure workflow change is still full in v1")
    gate.assert_contains(
        dumps(plan["full_reasons"]), "workflow-non-closure:", "but attributed as non-closure"
    )

    # Recursion proof on a fixture tree: entry -> zz-a -> zz-b, zz-c orphaned. A glob or name-pattern implementation cannot produce this answer.
    workflows = tmp_path / "fixture" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  a:\n    uses: ./.github/workflows/zz-a.yml\n", encoding="utf-8"
    )
    (workflows / "zz-a.yml").write_text(
        "jobs:\n  b:\n    uses: ./.github/workflows/zz-b.yml\n", encoding="utf-8"
    )
    (workflows / "zz-b.yml").write_text("jobs: {}\n", encoding="utf-8")
    (workflows / "zz-c.yml").write_text("jobs: {}\n", encoding="utf-8")
    fixture_closure = node_eval(CLOSURE_JS, str(ENGINE), str(tmp_path / "fixture"))
    gate.assert_contains(fixture_closure, "zz-b.yml", "transitive uses: references are followed")
    gate.assert_not_contains(fixture_closure, "zz-c.yml", "unreferenced workflows stay out")
    gate.log_pass("the workflow closure is iterated at runtime, never name-matched (case 24)")


def test_vm_e2e_surfaces_carry_the_mandated_inputs(gate):
    """The 8 VM/E2E jobs check out with `submodules: true` and run setup-workspace
    (verified against ct-tests.yml), so their surface must include packages/shared,
    packages/provisioning and every submodule pointer."""
    check = node_eval(
        """
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
""",
        str(MAP),
    )
    gate.assert_eq(
        check, "ok", "every VM/E2E surface carries shared, provisioning and all 4 submodules"
    )
    # CONTROL: the includes-check can fail. docs is deliberately NOT in the VM surface.
    docs_check = node_eval(
        "const m = require(process.argv[1]);"
        'process.stdout.write(String(m.VM_E2E_SURFACE.includes("docs")));',
        str(MAP),
    )
    gate.assert_eq(docs_check, "false", "docs is not in the VM/E2E surface")

    # package-lock.json reaches those jobs via ROOT_MANIFESTS => full: the lockfile
    # keys setup-workspace's cache for EVERY job.
    plan = classify(["package-lock.json"])
    gate.assert_eq(plan["mode"], "full", "a lockfile change forces full")
    gate.assert_contains(
        dumps(plan["full_reasons"]), "root-manifest:package-lock.json", "as a root manifest"
    )

    # Behavioural: the vector discriminates.
    plan = classify(["packages/provisioning/src/vm.ts"])
    gate.assert_eq(plan["mode"], "reduced", "a provisioning-only delta is reduced")
    gate.assert_eq(dumps(plan["jobs"]["e2e_workers"]["run"]), "true", "and runs the VM E2E legs")
    gate.assert_eq(dumps(plan["jobs"]["account_e2e"]["run"]), "false", "but not account e2e")
    gate.assert_eq(dumps(plan["jobs"]["renet"]["run"]), "false", "nor the renet tests")
    gate.log_pass(
        "the 8 VM/E2E surfaces carry shared, provisioning, lockfile-via-full and all pointers"
    )


def test_submodule_pointer_classifies_like_content(gate):
    """A gitlink path (`private/renet`, no slash) and expanded submodule content
    (`private/account/web/...`) land in the same module bucket."""
    plan = classify(["private/renet"])
    gate.assert_eq(plan["mode"], "reduced", "a renet pointer bump is classifiable")
    gate.assert_eq(dumps(plan["modules"]), '["renet"]', "to the renet module")
    gate.assert_eq(dumps(plan["jobs"]["e2e_k8s"]["run"]), "true", "renet is in the VM E2E surface")
    gate.assert_eq(dumps(plan["jobs"]["elite_run"]["run"]), "true", "and in elite's")
    gate.assert_eq(dumps(plan["jobs"]["account_e2e"]["run"]), "false", "but not in account e2e's")
    plan = classify(["private/account/web/src/portal.ts"])
    gate.assert_eq(
        dumps(plan["modules"]), '["account"]', "expanded account content classifies to account"
    )
    gate.assert_eq(dumps(plan["jobs"]["account_e2e"]["run"]), "true", "which runs account e2e")
    gate.assert_eq(dumps(plan["jobs"]["elite_run"]["run"]), "false", "and not elite")
    # CONTROL: only the four known submodules match.
    plan = classify(["private/new-submodule"])
    gate.assert_eq(plan["mode"], "full", "an unknown private/ path fails closed")
    gate.assert_contains(
        dumps(plan["full_reasons"]), "unclassified:private/new-submodule", "as unclassified"
    )
    gate.log_pass("submodule pointers and expanded content classify to the same module")


def test_docs_only_delta_reduces_everything(gate):
    """The reduced happy path: docs-only means every scoped job is out of scope.
    migration-test is deliberately not in the vector at all (case 26)."""
    plan = classify(["docs/ci-overhaul/03-something.md", "CLAUDE.md", ".claude/settings.json"])
    gate.assert_eq(plan["mode"], "reduced", "a docs-only delta is reduced")
    gate.assert_eq(
        dumps(all(job["run"] is False for job in plan["jobs"].values())),
        "true",
        "with every scoped job out of scope",
    )
    gate.assert_eq(
        dumps("migration" in plan["jobs"] or "migration_test" in plan["jobs"]),
        "false",
        "migration-test is not in the vector: it stays unconditional (case 26)",
    )
    # CONTROL: one cli line flips the vector, so all-false is earned.
    plan = classify(["docs/ci-overhaul/03-something.md", "packages/cli/src/index.ts"])
    gate.assert_eq(
        dumps(plan["jobs"]["unit"]["run"]), "true", "adding a cli path pulls unit back in"
    )
    gate.log_pass("a docs-only delta reduces every scoped job, and only then")


def test_agent_notes_tree_is_a_zero_job_module(gate):
    """`agent/` is the TRACKED agent working-notes root, and STATE.md is rewritten many
    times per session. Unclassified it would be full CI each time."""
    plan = classify(
        [
            "agent/97604f47/STATE.md",
            "agent/PLAN-agent-folder-migration.md",
            "agent/programs/backup-storage/CHECKLIST.md",
        ]
    )
    gate.assert_eq(plan["mode"], "reduced", "an agent/-only delta is reduced, never full")
    gate.assert_eq(dumps(plan["modules"]), '["agent"]', "and lands in its OWN module, not docs")
    gate.assert_eq(
        dumps(all(job["run"] is False for job in plan["jobs"].values())),
        "true",
        "with every scoped job out of scope (agent is zero-job)",
    )

    # CONTROL A: no JOB_SURFACES entry names it. A surface that picked it up would make this tree expensive again while every assertion above still passed.
    surfaced = node_eval(
        """
const m = require(process.argv[1]);
const hits = Object.entries(m.JOB_SURFACES).filter(([, s]) => s.includes("agent")).map(([j]) => j);
process.stdout.write(hits.length ? hits.join(",") : "none");
""",
        str(MAP),
    )
    gate.assert_eq(surfaced, "none", "no job surface names the agent module")

    # CONTROL B: the rule is a PREFIX, not a substring.
    plan = classify(["agents/roster.md"])
    gate.assert_eq(plan["mode"], "full", "a sibling tree named agents/ still fails closed")
    gate.assert_contains(
        dumps(plan["full_reasons"]),
        "unclassified:agents/roster.md",
        "as unclassified, exactly as any new top-level tree does",
    )

    # CONTROL C: zero jobs is earned per-delta, not a constant for this rule.
    plan = classify(["agent/97604f47/STATE.md", "packages/cli/src/index.ts"])
    gate.assert_eq(
        dumps(plan["jobs"]["unit"]["run"]),
        "true",
        "a cli path beside the notes pulls unit back in",
    )
    gate.log_pass("the tracked agent/ notes tree is its own zero-job module (and only that tree)")


def test_full_mode_runs_every_job(gate):
    """The consumer side of fail-closed: whenever mode is full, the vector must say run
    for EVERY job, so a consumer reading it can never skip on a forced-full plan."""
    plan = classify(["package.json"])
    gate.assert_eq(plan["mode"], "full", "a root manifest forces full")
    gate.assert_eq(
        dumps(all(job["run"] is True for job in plan["jobs"].values())),
        "true",
        "and every job in the vector says run",
    )
    gate.log_pass("full mode always emits an all-run vector")


def test_classify_mode_is_pure(gate, tmp_path):
    """`--classify` must never touch git, gh, or the network. Shim all three commands
    to leave a sentinel and prove no sentinel appears."""
    shim = tmp_path / "shim"
    shim.mkdir()
    for tool in ("git", "gh", "curl"):
        target = shim / tool
        target.write_text(
            '#!/bin/bash\ntouch "%s/called-%s"\nexit 1\n' % (tmp_path, tool), encoding="utf-8"
        )
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    shimmed_path = "%s%s%s" % (shim, os.pathsep, os.environ.get("PATH", ""))

    # CONTROL: the shim actually intercepts, so the absence below is evidence.
    subprocess.run(
        ["git", "status"],
        env={**os.environ, "PATH": shimmed_path},
        capture_output=True,
        check=False,
    )
    gate.assert_eq(
        "yes" if (tmp_path / "called-git").is_file() else "no",
        "yes",
        "the git shim fires when git is invoked",
    )
    for sentinel in tmp_path.glob("called-*"):
        sentinel.unlink()

    plan = classify(["docs/a.md"], env={"PATH": shimmed_path})
    gate.assert_eq(plan["mode"], "reduced", "--classify still works under the shims")
    gate.assert_eq(
        len(list(tmp_path.glob("called-*"))), 0, "--classify invoked none of git, gh, curl"
    )
    gate.log_pass("--classify is pure: no git, no gh, no network")


def test_baseline_helpers_refuse_weak_baselines(gate):
    """The exported baseline decision logic, edge cases 1/2/4/5."""

    def verdict(payload: str) -> str:
        return node_eval(
            """
const e = require(process.argv[1]);
const v = e.evaluateBaselineCandidate(JSON.parse(process.argv[2]));
process.stdout.write(v.usable + ":" + v.reason);
""",
            str(ENGINE),
            payload,
        )

    # CONTROL first: the helper CAN say yes, so every refusal below is a decision rather than a stuck constant.
    gate.assert_eq(
        verdict('{"conclusion":"success","plan":{"mode":"full","reconciled":true}}'),
        "true:full-green-attested",
        "a green, full, reconciled run is a usable baseline",
    )
    gate.assert_eq(
        verdict('{"conclusion":"success","plan":{"mode":"reduced","reconciled":true}}'),
        "false:reduced-baseline",
        "a reduced green run is not a baseline (case 1: no evidence chains)",
    )
    gate.assert_eq(
        verdict('{"conclusion":"success"}'),
        "false:no-skip-plan",
        "a green run without an attested plan proves nothing (case 2)",
    )
    gate.assert_eq(
        verdict('{"conclusion":"success","plan":{"mode":"full"}}'),
        "false:unreconciled-outcome",
        "intent without reconciled outcome is not enough (case 4)",
    )
    gate.assert_eq(
        verdict('{"conclusion":"failure","plan":{"mode":"full","reconciled":true}}'),
        "false:not-green",
        "a red run is never a baseline",
    )

    # GREENLIGHT-ONLY REDUCTION, the defect that made this engine inert. Both plans below carry the identical `mode: "reduced"`, so only the per-key reading separates them, which is the whole point of the pair.
    greenlit = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"unit":{"run":true,"reason":"full"},'
        '"renet":{"run":false,"reason":"greenlight:30968082228"}}}}'
    )
    gate.assert_eq(
        verdict(greenlit),
        "true:full-green-attested",
        "a run reduced ONLY by greenlight evidence is a usable baseline",
    )
    scoped = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"unit":{"run":true,"reason":"full"},'
        '"renet":{"run":false,"reason":"out-of-scope"}}}}'
    )
    gate.assert_eq(
        verdict(scoped),
        "false:reduced-baseline",
        "a run that SCOPE-skipped a key is still not a baseline (case 1 intact)",
    )
    forged = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"renet":{"run":false,"reason":"greenlight:probably-fine"}}}}'
    )
    gate.assert_eq(
        verdict(forged),
        "false:reduced-baseline",
        "a greenlight reason without an evidence run id does not count",
    )
    gate.assert_eq(
        verdict('{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{}}}'),
        "false:reduced-baseline",
        "an empty jobs vector proves nothing",
    )

    # MALFORMED ENTRIES MUST READ AS "NOT COVERED", and the asymmetry is why this block exists. Reading garbage as coverage reduces a round on evidence nobody
    # checked; reading it as a gap costs one full round. An earlier form asked
    # `run !== false`, and every case below answered COVERS under it.
    no_run_key = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"renet":{"reason":"out-of-scope"}}}}'
    )
    gate.assert_eq(
        verdict(no_run_key),
        "false:reduced-baseline",
        "an entry with NO run key is not coverage, whatever its reason says",
    )
    string_false = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"renet":{"run":"false","reason":"out-of-scope"}}}}'
    )
    gate.assert_eq(
        verdict(string_false),
        "false:reduced-baseline",
        'the STRING "false" is a malformed entry, not a truthy run',
    )
    zero_run = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":{'
        '"renet":{"run":0,"reason":"out-of-scope"}}}}'
    )
    gate.assert_eq(
        verdict(zero_run),
        "false:reduced-baseline",
        "and so is 0: only a real boolean true is an executed key",
    )
    # An ARRAY is not the jobs map. Object.values would happily walk it, so the refusal has to be explicit rather than incidental.
    array_jobs = (
        '{"conclusion":"success","plan":{"mode":"reduced","reconciled":true,"jobs":['
        '{"run":true,"reason":"full"}]}}'
    )
    gate.assert_eq(
        verdict(array_jobs),
        "false:reduced-baseline",
        "an array jobs vector is a shape no producer emits, so it covers nothing",
    )

    def moved(plan_base: str, merge_parent: str = "") -> str:
        return node_eval(
            """
const e = require(process.argv[1]);
process.stdout.write(String(e.isBaseUnchanged({planBaseSha: process.argv[2], mergeParentSha: process.argv[3]})));
""",
            str(ENGINE),
            plan_base,
            merge_parent,
        )

    gate.assert_eq(moved("aaa", "aaa"), "true", "an unchanged base passes (control)")
    gate.assert_eq(moved("aaa", "bbb"), "false", "a moved base means full (case 5)")
    gate.assert_eq(moved("aaa"), "false", "a missing merge parent means full, not a pass")
    gate.log_pass(
        "baseline helpers refuse reduced, unattested and unreconciled baselines (cases 1/2/4/5)"
    )


def test_baseline_resolution_fails_open_on_every_defect(gate):
    """`resolveBaseline` with an INJECTED io: no git, no gh, no network. Each case
    states the mode AND the machine-readable reason, because "full" alone cannot
    distinguish a correct full round from a permanently stuck one."""

    def resolve(io_override: str, opts_override: str = "{}") -> str:
        return node_eval(
            """
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
""",
            str(ENGINE),
            io_override,
            opts_override,
        )

    # CONTROL, and it is the whole point of the mode. Without this passing, every "full" below would be indistinguishable from a dead mechanism.
    gate.assert_eq(
        resolve("{}"),
        "reduced:docs",
        "green+full+reconciled baseline with a docs delta reduces (the headline case)",
    )
    gate.assert_eq(
        resolve('{diffPaths:()=>["packages/cli/src/a.ts"]}'),
        "reduced:cli",
        "and it still classifies a source change into its module",
    )

    gate.assert_eq(
        resolve("{isShallow:()=>true}"),
        "full:baseline:shallow-clone",
        "a shallow clone cannot be walked, so it is full (not a partial walk)",
    )
    gate.assert_eq(
        resolve('{listCandidates:()=>{throw new Error("boom")}}'),
        "full:baseline:candidate-walk-failed:boom",
        "a throwing git walk is an answer, never a crash",
    )
    gate.assert_eq(
        resolve("{listCandidates:()=>[]}"),
        "full:baseline:no-candidates",
        "no ancestors means full",
    )
    gate.assert_eq(
        resolve('{listCandidates:()=>[{sha:"x",conclusion:"failure",plan:null}]}'),
        "full:baseline:none-usable",
        "a red ancestor is not a baseline",
    )
    gate.assert_eq(
        resolve('{diffPaths:()=>{throw new Error("nope")}}'),
        "full:baseline:diff-failed:nope",
        "a failed diff is full, never an empty delta",
    )
    gate.assert_eq(
        resolve('{diffPaths:()=>Array.from({length:301},(_,i)=>"docs/f"+i+".md")}'),
        "full:baseline:diff-truncated:301",
        "past the 300-file cap the list is incomplete, so full",
    )
    gate.assert_eq(
        resolve("{}", "{mergeSha:null}"),
        "full:baseline:base-sha-unknown",
        "an unknown merge parent is never read as an unchanged base",
    )

    # Case 5 fold: main moved, and main's OWN delta must be unioned in or a change that landed on main would be invisible to this round.
    folded = resolve(
        '{firstParent:()=>"n".repeat(40),'
        'diffPaths:(f)=>f==="b".repeat(40)?["docs/x.md"]:["packages/cli/src/leaked.ts"]}'
    )
    gate.assert_eq(
        folded,
        "reduced:cli,docs",
        "a moved base folds main's delta in rather than losing it (case 5)",
    )
    gate.log_pass("baseline resolution reduces when it should and fails open on every defect")


def test_resolve_baseline_needs_a_repo(gate):
    """A misspelled/absent --repo must be a USAGE error. Failing open to full here
    would hide a caller bug as a permanently expensive pipeline, which is precisely
    how D9 stayed false for twelve runs."""
    result = harness.run(
        [node_bin(), str(ENGINE), "--resolve-baseline", "--head", "deadbeef"], timeout=120
    )
    gate.assert_eq(
        result.rc, 2, "--resolve-baseline without --repo exits 2 (usage), not 0 (silent full)"
    )
    gate.log_pass("a caller bug is reported, not absorbed into a full run")


def test_surface_table_is_self_validating(gate):
    """A surface naming a module the table cannot produce would be a job that never
    re-enters scope. The load-time validator must throw on it."""
    out = node_eval(
        """
const m = require(process.argv[1]);
try {
  m.validateJobSurfaces({ bad_job: ["no-such-module"] }, m.KNOWN_MODULES);
  process.stdout.write("no-throw");
} catch (e) {
  process.stdout.write(e.message);
}
""",
        str(MAP),
    )
    gate.assert_contains(out, "no-such-module", "the validator fires on an unknown module")
    # CONTROL: it accepts the real table. Module load already ran it, but prove it explicitly so a future load-order change cannot hollow this out.
    out = node_eval(
        """
const m = require(process.argv[1]);
m.validateJobSurfaces(m.JOB_SURFACES, m.KNOWN_MODULES);
process.stdout.write("ok");
""",
        str(MAP),
    )
    gate.assert_eq(out, "ok", "and accepts the real JOB_SURFACES")
    gate.log_pass("the job-surface table is validated against the known modules")


# --- the classification regression table (2026-08-05) -----------------------
#
# WHAT IT GUARDS, and why nothing above already does. Every case above tests the engine's DECISION MACHINERY. None of them pins the ANSWER for a representative delta, which is the half the operator actually experienced: "run 30983418337 ran the whole matrix for a commit that is documentation". Add a surface to JOB_SURFACES, mistype a glob, or drop a module mapping, and every case
# above stays green while docs-only silently goes back to running eighteen jobs.
#
# SETS, NEVER COUNTS, wherever the expectation is a partial run. A count of 14 passes just as happily when the map swaps two keys for two others.

VERDICT_JS = """
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
});
"""


def classify_verdict(engine: pathlib.Path, *file_paths: str) -> str:
    """`<mode>|<total keys>|<sorted running keys>`, or a SENTINEL that can never
    equal an expectation.

    The sentinel is the whole point. A classification that produced nothing must not read as "no keys to run": here that is the vacuity shape, and it fails toward skipping everything. So a dead engine, unparseable bytes and a plan with no job vector each answer with a distinct string rather than an empty key list, and the `total` field means a zero-key row still has to prove it saw
    all eighteen keys before finding none of them running.

    The reducing half stays in JS, run over the engine's raw stdout, so the port and the twin read the plan through the identical expression.
    """
    first = harness.run(
        [node_bin(), str(engine), "--classify"],
        stdin="".join("%s\n" % p for p in file_paths),
        timeout=120,
    )
    if first.rc != 0 or not first.out:
        return "ENGINE-PRODUCED-NOTHING"
    return harness.run([node_bin(), "-e", VERDICT_JS], stdin=first.out, timeout=120).out


def expect_classify(gate, label: str, expected: str, *file_paths: str) -> None:
    """An ACTIONABLE failure. A legitimate JOB_SURFACES change must be a one-line edit
    here, not a stare at two fourteen-item blobs: a regression test that is a puzzle to
    update is a regression test that gets suppressed instead of updated."""
    actual = classify_verdict(ENGINE, *file_paths)
    gate.assertions += 1
    if actual == expected:
        return
    want = set(expected.rsplit("|", 1)[-1].split())
    got = set(actual.rsplit("|", 1)[-1].split())
    gate.log_fail(
        "%s: expected '%s', got '%s' (missing: %s| unexpected: %s)"
        % (
            label,
            expected,
            actual,
            " ".join(sorted(want - got)) or "none",
            " ".join(sorted(got - want)) or "none",
        )
    )


def test_representative_deltas_classify_to_pinned_verdicts(gate, tmp_path):
    """Each partial set is named ONCE and reused by every row that expects it, so a
    legitimate map change edits one line rather than several rows. The sets are the measured truth as of 2026-08-05, taken from the real --classify path rather than
    read off JOB_SURFACES by hand."""
    cli_keys = (
        "drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode e2e_migrate "
        "e2e_workers fork_isolation install_methods ops package_tests unit update_flow"
    )
    renet_keys = (
        "drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode e2e_migrate "
        "e2e_workers elite_run fork_isolation install_methods license_enforcement ops "
        "package_tests renet update_flow"
    )
    account_keys = (
        "account_e2e drills e2e_ceph e2e_ceph_workers e2e_k8s e2e_k8s_ceph e2e_k8s_multinode "
        "e2e_migrate e2e_workers fork_isolation ops"
    )

    # -- the rows that must skip the heavy matrix entirely -------------------
    expect_classify(gate, "docs only", "reduced|18|", "docs/ci-overhaul/06-progress.md")
    expect_classify(gate, "agent tooling only", "reduced|18|", ".claude/commands/pr-babysit.md")
    # THE REPORTED CASE (commit bcc4f1ee1, 2026-08-06): an Apache-2.0 attribution-URL check that ran the ceph fork test, because scripts/** was a single blanket rule.
    expect_classify(gate, "gate source only", "reduced|18|", "scripts/gates/check-embed-credits.ts")
    expect_classify(gate, "gate lib only", "reduced|18|", "scripts/lib/blocker-validator.ts")
    expect_classify(gate, "ci-runner only", "reduced|18|", "scripts/ci-runner/manifest.ts")
    # The tracked agent/ notes root. STATE.md is rewritten many times per session, so this row decides whether a session costs nothing or seventy minutes a write.
    expect_classify(gate, "agent session state only", "reduced|18|", "agent/97604f47/STATE.md")
    expect_classify(
        gate,
        "agent plan + program suite",
        "reduced|18|",
        "agent/PLAN-agent-folder-migration.md",
        "agent/programs/backup-storage/CHECKLIST.md",
    )
    # The over-eager-skip direction for the same tree.
    expect_classify(
        gate,
        "MIXED agent notes + one cli file",
        "reduced|18|%s" % cli_keys,
        "agent/97604f47/STATE.md",
        "packages/cli/src/commands/repo.ts",
    )
    expect_classify(
        gate,
        "MIXED gate source + one cli file",
        "reduced|18|%s" % cli_keys,
        "scripts/gates/check-cli-docs.ts",
        "packages/cli/src/commands/repo.ts",
    )
    # THE REPORTED CASE, kept recognisable: the exact four paths of push 1d172438f..208c8a2d9, whose run 30983418337 ran all eighteen keys.
    expect_classify(
        gate,
        "the reported push (run 30983418337)",
        "reduced|18|",
        ".claude/agents/pr-babysitter.md",
        ".claude/commands/pr-babysit.md",
        ".claude/hooks/stop/wl_judge.py",
        "docs/agent/main/REPORT-licensing-bigbang-2026-08-04.md",
    )

    # -- the rows that must run a specific, named set -----------------------
    expect_classify(
        gate, "cli source", "reduced|18|%s" % cli_keys, "packages/cli/src/commands/repo.ts"
    )
    expect_classify(
        gate, "renet source", "reduced|18|%s" % renet_keys, "private/renet/pkg/license/keys.go"
    )
    expect_classify(
        gate, "account source", "reduced|18|%s" % account_keys, "private/account/src/index.ts"
    )

    # THE ROW THAT CATCHES AN OVER-EAGER SKIP, the direction that costs correctness rather than money. An engine that let the docs classification win would pass every zero-key row above and be catastrophically wrong here.
    expect_classify(
        gate,
        "MIXED docs + one cli file",
        "reduced|18|%s" % cli_keys,
        "docs/ci-overhaul/06-progress.md",
        "packages/cli/src/commands/repo.ts",
    )

    # -- the rows that must force full -------------------------------------- Asserted STRUCTURALLY rather than as a literal eighteen-name list: naming all eighteen in three more rows would make a legitimate key addition an eighteen-line diff in a file that is not about the key list.
    for path, reason in (
        (".github/workflows/ci.yml", "workflow-closure:.github/workflows/ci.yml"),
        (".ci-trigger", "root-manifest:.ci-trigger"),
        (".ci/policy/.audit-allowlist", "harness:.ci/policy/.audit-allowlist"),
        (".ci/lib/common.sh", "harness:.ci/lib/common.sh"),
        ("scripts/drills/lib.sh", "harness:scripts/drills/lib.sh"),
        (
            "scripts/gen/generate-third-party-licenses.ts",
            "harness:scripts/gen/generate-third-party-licenses.ts",
        ),
    ):
        plan = classify([path])
        gate.assert_eq(plan["mode"], "full", "%s forces full CI" % path)
        gate.assert_eq(
            dumps(all(job["run"] is True for job in plan["jobs"].values())),
            "true",
            "and every key in the vector runs for %s" % path,
        )
        gate.assert_contains(
            dumps(plan["full_reasons"]), reason, "naming %s as the reason" % reason
        )

    # -- the block's own anti-vacuity control ------------------------------- It cannot borrow this file's registered one: that fires seven tests earlier and never reaches here. So prove the sentinel is live, or every zero-key row above could be passing on an engine that ran at all.
    gate.assert_eq(
        classify_verdict(
            tmp_path / "definitely-not-an-engine.cjs", "docs/ci-overhaul/06-progress.md"
        ),
        "ENGINE-PRODUCED-NOTHING",
        "a classification that could not run must never read as 'no keys to run'",
    )
    # CONTROL for the control: the real engine still answers, so the sentinel above is a dead engine rather than a helper stuck at its error string.
    gate.assert_eq(
        classify_verdict(ENGINE, "docs/ci-overhaul/06-progress.md"),
        "reduced|18|",
        "and the same call against the real engine answers normally",
    )
    gate.log_pass("representative deltas classify to their pinned verdicts, as sets")
