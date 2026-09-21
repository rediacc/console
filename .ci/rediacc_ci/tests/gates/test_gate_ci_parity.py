"""Port of `.ci/scripts/test/gates/test-ci-parity.sh`.

Subject: `scripts/gates/check-ci-parity.ts`, the meta-gate whose promise is that the local gate set and the CI quality surface agree in BOTH directions -- a local run catches CI failures before a push, and nothing runs locally that CI never enforces. It replaced two gates that each covered one direction; the third relation (locally-run, never CI-run) had no gate at all, which is
rediacc/console#549.

WHY CASE 3 IS THE IMPORTANT ONE, transcribed from the twin because it is the reason the whole file exists. The analysis this gate came from first reported ZERO findings, because it matched whole workflow FILE TEXT for `npm run <key>` and a step NAME contained the literal `npm run ci`. That made the entire gate set look CI-executed and the reverse direction vacuously empty -- a gate
built that way reports perfect parity forever. `test_step_name_is_not_an_invocation` pins the defect as a regression case, on a fixture whose step name names the very gate its `run:` block does not run.

HOW IT IS DRIVEN, and why the port is a transcription rather than a reimplementation. Every case builds a throwaway repository under a temp dir and points the subject at it through `CI_PARITY_ROOT` / `CI_PARITY_MANIFEST`. The subject stays the real TypeScript gate, invoked exactly as the twin invokes it, so what is being compared between the two sides is the FIXTURE and the
ASSERTIONS, never two independent reimplementations of the detector. No tracked file is written by any case here.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP even though no case writes the tree. `gates.lock.json` records `reads: ["tree:repo"]` for `gate-test:ci-parity`, and `real_tree_admission` in `test_twin_parity.py` reads that lock: a twin in the real-tree set that does NOT declare `REAL_TREE_TWIN` is refused, because the parity driver runs the twin itself and would then overlap the
battery with no isolation declared to either scheduler. The declaration is honoured only while this module names no `XDIST_GROUP` of its own, which the same function checks.

THE FIXTURE IS A REAL GIT REPOSITORY, not a directory of files, and that is not tidiness: `loadScripts()` in the subject derives its tracked set from `git ls-files`, so a fixture with no index exercises a code path the gate does not have and every case would fail for the wrong reason.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-ci-parity.sh"

# `gate-test:ci-parity` carries `reads: ["tree:repo"]`. See the docstring.
REAL_TREE_TWIN = True

ROOT = paths.repo_root()
GATE = ROOT / "scripts" / "gates" / "check-ci-parity.ts"

# The script sets a case can give the fixture. Per-case rather than shared because R1 fires on any `check:ci-*` key the manifest does not carry, so a one-size package.json would redden every case for a reason it is not about.
SCRIPTS_ALPHA = '"check:ci-alpha": ".ci/scripts/quality/check-alpha.sh"'
SCRIPTS_BETA = '"check:ci-beta": "tsx scripts/check-beta.ts"'
SCRIPTS_ALPHA_BETA = SCRIPTS_ALPHA + ",\n    " + SCRIPTS_BETA
SCRIPTS_AGGREGATOR = (
    SCRIPTS_ALPHA_BETA + ',\n    "check:i18n": "npm run check:ci-nested",'
    '\n    "check:ci-nested": "tsx scripts/check-nested.ts"'
)

STEP_ALPHA = "      - name: Alpha\n        run: npm run check:ci-alpha"

MANIFEST_ALPHA = (
    '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,\n'
    '  "leaves":[".ci/scripts/quality/check-alpha.sh"],\n'
    '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
    '"job":"lane","step":"Alpha"}}]'
)

CI_YML = """name: ci
on: push
jobs:
  quality:
    uses: ./.github/workflows/ci-quality.yml
  review-gate:
    runs-on: ubuntu-latest
    steps:
      - name: Review threads
        run: echo review
"""

GOOD_BLOCKER = (
    "# BLOCKER: reads the pull request body through the GitHub API, so there is "
    "nothing for a local checkout to validate before the PR exists"
)


def require_npx() -> str:
    """The `npx` binary, or a LOUD refusal naming the fix.

    A missing toolchain is a FAILURE and never a skip: `npx tsx` is how the subject is executed, so without it not one case below has run, and an unrunnable case folded into "fine" is the vacuity this directory refuses.
    """
    return harness.require_tool(
        "npx",
        "install node (the lane's setup-workspace step provides it); tsx is resolved through npx",
    )


def scaffold(root: pathlib.Path, steps: str, scripts: str = SCRIPTS_ALPHA) -> None:
    """The parity surface every case shares.

    `ci.yml`'s `quality` job calls `ci-quality.yml`, which is where the fixture's steps go, reached by `uses:` iteration exactly as the real surface is -- so `test_parity_surface_is_computed_not_named` gets its shape for free.

    BOTH ENTRY JOBS ARE PRESENT. `paritySurface()` returns the EMPTY surface when one is missing and the preflight then refuses, so a fixture without `review-gate` would make every case refuse instead of assert.
    """
    for sub in (".github/workflows", ".ci/scripts/quality", ".ci/policy", "scripts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    # The gate existence-checks every path-shaped leaf, so the fixture's leaves have to be real files or every case would fail for the wrong reason.
    for leaf in (
        ".ci/scripts/quality/check-alpha.sh",
        "scripts/check-beta.ts",
        "scripts/check-nested.ts",
    ):
        (root / leaf).write_text("", encoding="utf-8")
    (root / "package.json").write_text(
        '{\n  "name": "fixture",\n  "scripts": {\n    %s\n  }\n}\n' % scripts, encoding="utf-8"
    )
    (root / ".github/workflows/ci.yml").write_text(CI_YML, encoding="utf-8")
    (root / ".github/workflows/ci-quality.yml").write_text(
        "name: quality\non: workflow_call\njobs:\n  lane:\n    runs-on: ubuntu-latest\n"
        "    steps:\n%s\n" % steps,
        encoding="utf-8",
    )
    git_init(root)


def git_init(root: pathlib.Path) -> None:
    """`git init` + `git add -A`, with the tool probed rather than assumed.

    An empty tracked set silently stops `python3 -m <module>` resolving in the subject, which is the one thing that set is for, so this is not optional scaffolding.
    """
    git = harness.require_tool("git", "install git; the fixture must be a real repository")
    harness.run([git, "-C", str(root), "init", "--quiet"])
    harness.run([git, "-C", str(root), "add", "-A"])


def manifest(root: pathlib.Path, body: str) -> None:
    (root / "manifest.json").write_text(body + "\n", encoding="utf-8")


def exempt(root: pathlib.Path, body: str) -> None:
    (root / ".ci/policy/.ci-parity-exempt").write_text(body, encoding="utf-8")


def run_gate(root: pathlib.Path) -> harness.RunResult:
    """Drive the real subject against the fixture.

    The streams are merged by the CALLER through `.combined`, mirroring the twin's `2>&1`: these assertions are about which message appeared, and the twin makes no claim about which stream carried it.
    """
    return harness.run(
        [require_npx(), "tsx", str(GATE)],
        cwd=ROOT,
        env={"CI_PARITY_ROOT": str(root), "CI_PARITY_MANIFEST": str(root / "manifest.json")},
        timeout=300,
    )


def assert_manifest_is_json(gate, body: str) -> None:
    """A fixture manifest that is not parseable JSON makes the subject refuse for a reason no case is about, and the refusal looks like a finding."""
    try:
        json.loads(body)
    except ValueError as exc:
        gate.log_fail(
            "the fixture manifest is not valid JSON (%s); the case would test nothing" % exc
        )


# ---------------------------------------------------------------------------


def test_declared_step_that_really_runs_it_passes(gate):
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA)
        assert_manifest_is_json(gate, MANIFEST_ALPHA)
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "a manifest gate whose declared step really runs it must pass"
        )
        gate.assert_contains(
            result.combined, "agree in both directions", "reports the clean verdict"
        )
    gate.log_pass("a manifest gate whose declared CI step really runs it passes")


def test_chain_only_gate_fails(gate):
    """The #549 control: a gate the local set runs that no workflow step does."""
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA, SCRIPTS_ALPHA_BETA)
        manifest(
            d,
            '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,\n'
            '  "leaves":[".ci/scripts/quality/check-alpha.sh"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"Alpha"}},\n'
            '  {"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,\n'
            '  "leaves":["scripts/check-beta.ts"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"Beta"}}]',
        )
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a gate no workflow step runs must fail")
        gate.assert_contains(result.combined, "check:ci-beta", "names the chain-only gate")
        gate.assert_contains(result.combined, "R3", "reports it in the local-only direction")
    gate.log_pass("a gate that runs locally and in no workflow step fails (the #549 control)")


def test_step_name_is_not_an_invocation(gate):
    """The live defect from the plan's section 1.4, pinned as a regression case: the step NAME contains `npm run check:ci-beta` while its `run:` does not."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: npm run check:ci-beta\n        run: npm run check:ci-alpha",
            SCRIPTS_BETA,
        )
        manifest(
            d,
            '[{"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,\n'
            '  "leaves":["scripts/check-beta.ts"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"npm run check:ci-beta"}}]',
        )
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a step whose NAME names the gate must not count as coverage"
        )
        gate.assert_contains(result.combined, "check:ci-beta", "still reports the uncovered gate")
        gate.assert_contains(
            result.combined, "runs something else", "says the pointed-at step runs something else"
        )
    gate.log_pass("a step name containing an npm invocation is not coverage")


def test_npm_run_ci_in_a_run_block_is_a_tautology(gate):
    with harness.temp_dir() as d:
        scaffold(d, "      - name: Everything\n        run: npm run ci")
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "npm run ci inside the surface must fail")
        gate.assert_contains(result.combined, "tautology", "reports it as a tautology")
        gate.assert_contains(
            result.combined, "vacuous", "explains that it makes every assertion vacuous"
        )
        gate.assert_contains(
            result.combined,
            "check:ci-alpha",
            "and does NOT treat it as coverage for the alpha gate",
        )
    gate.log_pass("npm run ci in a run: block is an error, never coverage")


def test_ci_only_gate_fails(gate):
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Orphan\n        run: .ci/scripts/quality/check-orphan.sh\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a CI-run shell gate with no manifest entry must fail")
        gate.assert_contains(result.combined, "check-orphan.sh", "names the CI-only gate")
        gate.assert_contains(result.combined, "R2", "reports it in the ci-only direction")
    gate.log_pass("a shell gate CI runs with no manifest entry fails")


def test_defined_gate_absent_from_the_manifest_fails(gate):
    """R1: a `check:ci-*` key that exists in package.json but is scheduled by nothing is inert -- it looks present, it greps, it passes review, and it examines nothing."""
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA, SCRIPTS_ALPHA_BETA)
        manifest(
            d,
            '[{"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,\n'
            '  "leaves":["scripts/check-beta.ts"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"Alpha"}}]',
        )
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a defined-but-unlisted check:ci-* key must fail")
        gate.assert_contains(result.combined, "check:ci-alpha", "names the inert gate")
        gate.assert_contains(result.combined, "R1", "reports it as the defined-but-never-run break")
    gate.log_pass("a check:ci-* key absent from the manifest fails")


def test_aggregator_transitivity(gate):
    """`check:ci-nested` is named by no workflow step directly; it is reached through `check:i18n`. A naive substring test over the aggregator reports it as dead and is simply wrong, so the resolver walks the graph."""
    local_only = (
        '"ci":{"kind":"local-only","blocker":"needs release credentials no developer '
        'machine holds, so no workflow can run it"}'
    )
    with harness.temp_dir() as d:
        scaffold(d, "      - name: i18n\n        run: npm run check:i18n", SCRIPTS_AGGREGATOR)
        manifest(
            d,
            '[{"id":"check:ci-nested","run":"npm run check:ci-nested","gate":true,\n'
            '  "leaves":["scripts/check-nested.ts"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"i18n"}},\n'
            '  {"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,\n'
            '  "leaves":[".ci/scripts/quality/check-alpha.sh"],\n  %s},\n'
            '  {"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,\n'
            '  "leaves":["scripts/check-beta.ts"],\n  %s}]' % (local_only, local_only),
        )
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "a gate reached only through an aggregator must count as covered"
        )
    gate.log_pass("coverage through an aggregator resolves transitively")


def test_workspace_scoping(gate):
    """`npm run test:unit -w @rediacc/cli` resolves in that workspace's manifest, not the root one. Without this the key looks undefined and the existence check false-positives."""
    with harness.temp_dir() as d:
        scaffold(d, "      - name: CLI units\n        run: npm run test:unit -w @rediacc/cli")
        (d / "packages/cli").mkdir(parents=True, exist_ok=True)
        (d / "packages/cli/package.json").write_text(
            '{ "name": "@rediacc/cli", "scripts": { "test:unit": "vitest run" } }\n',
            encoding="utf-8",
        )
        manifest(
            d,
            '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,\n'
            '  "leaves":["vitest"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"lane","step":"CLI units"}}]',
        )
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "the declared leaves must not silently match the root manifest"
        )
        gate.assert_contains(
            result.combined, "vitest", "the workspace script resolved to its real leaf"
        )
        gate.assert_contains(
            result.combined,
            "hygiene",
            "and the root-key mismatch is a hygiene finding, not a coverage one",
        )
    gate.log_pass("a workspace-scoped invocation resolves in that workspace's manifest")


def test_manifest_rot_is_reported(gate):
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA)
        manifest(
            d,
            '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,\n'
            '  "leaves":[".ci/scripts/quality/check-alpha.sh"],\n'
            '  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml",'
            '"job":"ghost-lane","step":"Alpha"}}]',
        )
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a pointer naming a job that does not exist must fail")
        gate.assert_contains(result.combined, "ghost-lane", "names the job that is not there")
    gate.log_pass("a stale ci pointer is reported rather than trusted")


def test_exemption_clears_a_finding(gate):
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Orphan\n        run: .ci/scripts/quality/check-orphan.sh\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        exempt(d, "%s\nci-only  .ci/scripts/quality/check-orphan.sh\n" % GOOD_BLOCKER)
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "a direction-tagged BLOCKER exemption must clear the finding"
        )
    gate.log_pass("a valid direction-tagged exemption silences a finding")


def test_low_effort_blocker_is_rejected(gate):
    """The exemption list is a hole in the promise; the reason has to be real."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Orphan\n        run: .ci/scripts/quality/check-orphan.sh\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        exempt(d, "# BLOCKER: tbd\nci-only  .ci/scripts/quality/check-orphan.sh\n")
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a low-effort BLOCKER must be rejected by the shared validator"
        )
        gate.assert_contains(
            result.combined, "BLOCKER validation failed", "names the validator failure"
        )
    gate.log_pass("a low-effort BLOCKER reason is rejected")


def test_missing_direction_tag_is_rejected(gate):
    """The tag is load-bearing: the liveness oracle differs per direction, so an untagged entry cannot be checked for staleness at all."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Orphan\n        run: .ci/scripts/quality/check-orphan.sh\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        exempt(d, "%s\n.ci/scripts/quality/check-orphan.sh\n" % GOOD_BLOCKER)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "an exemption with no direction must be rejected")
        gate.assert_contains(result.combined, "ci-only", "tells the author which directions exist")
    gate.log_pass("an exemption without a direction tag is rejected")


def test_path_in_a_yaml_comment_is_not_an_invocation(gate):
    """Too-loud guard: ci-build-renet.yml carries a comment naming a lint script. Prose is not a step."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      # see .ci/scripts/quality/check-orphan.sh for the rules\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "a script path inside a YAML comment must not count as an invocation"
        )
    gate.log_pass("a path mentioned in a comment is not treated as a gate invocation")


def test_non_gate_scripts_are_not_swept_in(gate):
    """Build, deploy and release helpers are steps, not gates, and have no business in a local gate set."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Upload\n        run: .ci/scripts/deploy/upload-repos-to-r2.sh\n"
            "      - name: Pack\n        run: .ci/scripts/build/pack-cli-npm.sh\n" + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(0, result.rc, "deploy/build helpers must not be treated as gates")
    gate.log_pass("only quality/security check-*.sh and test/test-*.sh count as gates")


def test_test_dir_gates_are_swept_in(gate):
    """The widened rule, and the reason it was widened: two test-dir gates ran in Quality/Static and nowhere else, and the old quality|security-only pattern could not see either (plan finding F3)."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Write-once guard\n        run: .ci/scripts/test/test-write-once-guard.sh\n"
            + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a .ci/scripts/test/test-*.sh gate CI runs must be swept in"
        )
        gate.assert_contains(result.combined, "test-write-once-guard.sh", "names the test-dir gate")
    gate.log_pass("a .ci/scripts/test/test-*.sh gate counts as gate-shaped (F3)")


def test_ported_python_gates_are_swept_in(gate):
    """THE WIDENING THIS SUITE DID NOT PIN. On 2026-09-08 `GATE_SHAPED` went from `check-[\\w.-]+\\.sh` to `check[-_][\\w.-]+\\.(?:sh|py)`, because W7 P4 repoints these very workflow lines at Python ports and the old spelling stopped judging a gate the moment it was ported -- silently, since a matcher that stops matching reports nothing."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Ported gate\n        run: .ci/scripts/quality/check_planted_port.py\n"
            + STEP_ALPHA,
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(1, result.rc, "a ported check_*.py gate CI runs must be swept in")
        gate.assert_contains(result.combined, "check_planted_port.py", "names the ported gate")
    gate.log_pass(
        "a .ci/scripts/quality/check_*.py gate counts as gate-shaped (the W7 P4 widening)"
    )


def test_empty_manifest_refuses(gate):
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA)
        manifest(d, "[]")
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "an empty manifest means nothing asserted, which must fail"
        )
        gate.assert_contains(
            result.combined, "Refusing to run", "refuses rather than reporting a clean run"
        )
    gate.log_pass("an empty manifest refuses to run (anti-vacuity)")


def test_empty_workflow_tree_refuses(gate):
    with harness.temp_dir() as d:
        (d / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(
            '{ "name": "fixture", "scripts": { "check:ci-alpha": "echo alpha" } }\n',
            encoding="utf-8",
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "an empty workflow tree means nothing asserted, which must fail"
        )
        gate.assert_contains(
            result.combined, "Refusing to run", "refuses rather than reporting a clean run"
        )
    gate.log_pass("an empty workflow tree refuses to run (anti-vacuity)")


def test_missing_entry_job_collapses_the_surface(gate):
    """Renaming ci.yml's `quality` job must not silently shrink the surface to nothing while still reporting a clean run. That is the vacuity failure the whole gate exists to prevent, so it refuses instead."""
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA)
        ci = d / ".github/workflows/ci.yml"
        text = ci.read_text(encoding="utf-8")
        # A CONSTRUCTION, not a pattern: the replacement is asserted to have landed, so a reworded scaffold cannot leave this case testing the unmodified fixture and passing for the wrong reason.
        if "\n  quality:\n" not in text:
            gate.log_fail("the scaffold no longer declares a `quality:` job; the plant cannot land")
        ci.write_text(text.replace("\n  quality:\n", "\n  quality-renamed:\n"), encoding="utf-8")
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a missing entry job must refuse, not report a clean run"
        )
        gate.assert_contains(
            result.combined, "Refusing to run", "refuses rather than passing over an empty surface"
        )
        gate.assert_contains(
            result.combined, "parity surface is empty", "says which input went missing"
        )
    gate.log_pass("renaming ci.yml's quality job collapses the surface and refuses")


def test_parity_surface_is_computed_not_named(gate):
    """A lane workflow reachable only through `uses:` is in the surface without being named anywhere in the gate. A hand-listed surface could be silently retired by renaming a file; a computed closure cannot."""
    with harness.temp_dir() as d:
        scaffold(d, STEP_ALPHA)
        with (d / ".github/workflows/ci-quality.yml").open("a", encoding="utf-8") as fh:
            fh.write("  extra:\n    uses: ./.github/workflows/ci-brand-new-lane.yml\n")
        (d / ".github/workflows/ci-brand-new-lane.yml").write_text(
            "name: brand new lane\non: workflow_call\njobs:\n  lane:\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Orphan in a lane nothing names\n"
            "        run: .ci/scripts/quality/check-brand-new.sh\n",
            encoding="utf-8",
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a gate in a transitively reachable lane must be in scope"
        )
        gate.assert_contains(
            result.combined, "check-brand-new.sh", "names the gate from the new lane"
        )
        gate.assert_contains(
            result.combined, "ci-brand-new-lane.yml", "and the lane is in the computed surface"
        )
    gate.log_pass("the parity surface is computed by uses: iteration, not by naming files")


def test_external_wrapper_is_transparent(gate):
    """`run-external-gate.sh` executes its arguments and only changes what a failure MEANS (soft on schedule, hard on a PR). The resolver must see through it to the wrapped gate, or every external gate's CI pointer breaks the moment it adopts the wrapper."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Alpha\n"
            "        run: .ci/scripts/quality/run-external-gate.sh npm run check:ci-alpha",
        )
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            0, result.rc, "a gate wrapped in run-external-gate.sh must still count as CI-covered"
        )
    gate.log_pass("run-external-gate.sh is transparent to leaf resolution")


def test_unknown_wrapper_is_not_transparent(gate):
    """CONTROL for the case above: transparency is specific to the known wrapper. An arbitrary wrapper script hiding the same command must still fail the pointer check, or any indirection would count as coverage."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Alpha\n"
            "        run: .ci/scripts/quality/run-mystery-wrapper.sh npm run check:ci-alpha",
        )
        (d / ".ci/scripts/quality/run-mystery-wrapper.sh").write_text("", encoding="utf-8")
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "an unknown wrapper must not count as running the wrapped gate"
        )
        gate.assert_contains(result.combined, "runs something else", "reports the pointer mismatch")
    gate.log_pass("an unknown wrapper is not transparent (the transparency cannot leak)")


def test_battery_equality_is_enforced(gate):
    """Without this, flattening the battery recreates #549 once per test: a new test would run in CI via the battery and never locally."""
    with harness.temp_dir() as d:
        scaffold(
            d,
            "      - name: Quality-gate unit tests\n        run: .ci/rediacc_ci/battery.py\n"
            + STEP_ALPHA,
        )
        (d / ".ci/scripts/test/gates").mkdir(parents=True, exist_ok=True)
        (d / ".ci/scripts/test/gates/test-only-on-disk.sh").write_text("", encoding="utf-8")
        manifest(d, MANIFEST_ALPHA)
        result = run_gate(d)
        gate.assert_exit_code(
            1, result.rc, "a battery test on disk with no manifest entry must fail"
        )
        gate.assert_contains(
            result.combined, "test-only-on-disk.sh", "names the unscheduled battery test"
        )
        gate.assert_contains(result.combined, "battery", "reports it as a battery-equality break")
    gate.log_pass("a battery test on disk with no qualityGateTest entry fails")


def test_the_subject_and_its_seams_still_exist(gate):
    """ADDED BY THE PORT, and it is the case that keeps every other one honest.

    Every case above points the subject at a fixture through two environment variables. If the subject were renamed, or either seam removed, `npx tsx` would fail identically for all 23 cases and several of them EXPECT a non-zero exit -- so a subject that no longer exists would satisfy them. Naming the seams in the source is the cheap refutation of that.
    """
    if not GATE.is_file():
        gate.log_fail(
            "%s is gone; every case above drives it, and the ones expecting rc=1 would "
            "pass on the failure to launch it" % paths.relative_to_root(GATE)
        )
    source = GATE.read_text(encoding="utf-8")
    for seam in ("CI_PARITY_ROOT", "CI_PARITY_MANIFEST"):
        gate.assert_contains(
            source, seam, "%s is how every case points the subject at its fixture" % seam
        )
    gate.log_pass("the subject exists (%d bytes) and still reads both fixture seams" % len(source))
