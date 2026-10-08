"""Port of `.ci/scripts/test/gates/test-releaseversion-build-version.sh`, retired in W7 P5.

Both-ways test for the two version checks inside `rediacc_ci.build.build_cli_executables` (written against the bash `build-cli-executables.sh`, retired behind its golden, PLAN-retire-bash-oracles B3).

WHAT THEY ARE FOR.
  1. The release guard: on the publishable path (RELEASE_BUILD=true, set by
     ci-build-cli.yml only on push-to-main) a placeholder, empty, or malformed
     version must stop the build before a single byte is stamped.
  2. The doctor smoke test: it runs the binary that was just produced and reads
     its version back. This is the ONLY point in the entire pipeline that reads a
     version out of freshly built bytes.

WHAT WAS BROKEN. Check 2 asserted only `[[ -n "$CLI_VERSION" ]] && [[ ... != "null"
]]` -- it never compared the reported version to the version the build was told to produce, and it parsed the reported value into the SAME variable name that carried the expected one, destroying the only copy. A SEA built as 0.0.0-dev passed with a cheerful "CLI version: 0.0.0-dev", and release 31154305287 published binaries built as 1.2.16 under the label 1.2.17 with this step
green. Check 1 did not exist at all.

HOW THE SMOKE TEST IS EXERCISED. Building a real SEA takes minutes, so the comparison is called on its own: `_check_doctor_json` is the module's own function, run in a child process against planted doctor output, and the planted mutation is made on a COPY of the module's source. A mutation whose pattern stopped matching would plant the FIXED code and report that the fixed code lets a mismatch through, which it does not -- so the plant is asserted to have changed something.

THE BUILD IS DRIVEN AT ITS REAL PATH, as the twin was, because the release guard sits between the `--dry-run` exit and `node bundle.mjs`: a refused build costs a second and writes nothing. `--output` still points into a per-test tmpdir so the one case that gets PAST the guard has nowhere to land but scratch.
"""

import json
import os
import stat
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "rediacc_ci", "build", "build_cli_executables.py")

# The comparison in `_check_doctor_json`, and the pre-fix behaviour: a comparison that compares nothing.
MUTATION_FROM = "if reported_version != expected_version:"
MUTATION_TO = "if False:"

# Calls `_check_doctor_json` of the module at argv[1] (the real file or a mutated copy) and prints a refusal the way `main` does.
DRIVER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("build_cli_executables_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    mod._check_doctor_json(sys.argv[3], sys.argv[2])
except mod.Refusal as refusal:
    for line in refusal.lines:
        mod.log.error(line)
    raise SystemExit(refusal.code)
"""


def require_gate(gate) -> str:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    return GATE.read_text(encoding="utf-8")


def run_build(gate, tmp_path, env: dict[str, str]) -> harness.RunResult:
    """The REAL module, at its real path, refused by the guard before it writes."""
    require_gate(gate)
    return harness.run(
        [
            sys.executable,
            str(GATE),
            "--platform",
            "linux",
            "--arch",
            "x64",
            "--output",
            str(tmp_path / "out"),
        ],
        cwd=paths.repo_root(),
        env={"PYTHONPATH": str(paths.from_root(".ci")), **env},
        timeout=300,
    )


def doctor_json(version: str) -> str:
    return json.dumps(
        {
            "Environment": [
                {"name": "Install method", "value": "SEA binary", "status": "ok"},
                {"name": "CLI version", "value": version, "status": "ok"},
                {"name": "Node.js", "value": "v22", "status": "ok"},
            ]
        },
        separators=(",", ":"),
    )


def run_block(gate, tmp_path, expected: str, reported: str, *, mutate: bool = False):
    source = require_gate(gate)
    subject = GATE
    if mutate:
        # THE CONTROL ON THE CONTROL. A mutation that matches nothing plants the FIXED comparison and then asserts it lets a mismatch through.
        if source.count(MUTATION_FROM) == 0:
            gate.log_fail(
                "the planted mutation target %r no longer appears in the module, "
                "so the 'neutered' comparison below is the LIVE one. Re-point the "
                "mutation; do not delete the case." % MUTATION_FROM
            )
        subject = tmp_path / "mutant.py"
        subject.write_text(source.replace(MUTATION_FROM, MUTATION_TO), encoding="utf-8")
    harness.require_tool("jq", "install jq; the comparison reads the doctor JSON with it")
    return harness.run(
        [sys.executable, "-c", DRIVER, str(subject), expected, doctor_json(reported)],
        cwd=paths.repo_root(),
        env={"PYTHONPATH": str(paths.from_root(".ci"))},
        timeout=120,
    )


def test_release_build_refuses_the_placeholder(gate, tmp_path):
    gate.log_test("RELEASE_BUILD=true refuses a 0.0.0-dev version")
    result = run_build(gate, tmp_path, {"RELEASE_BUILD": "true", "CLI_VERSION": "0.0.0-dev"})
    gate.assert_eq(result.rc, 1, "a placeholder version must not build a publishable artifact")
    gate.assert_contains(result.combined, "0.0.0-dev", "the refusal must name the version")
    gate.log_pass("release build refuses 0.0.0-dev")


def test_release_build_refuses_an_empty_version(gate, tmp_path):
    gate.log_test("RELEASE_BUILD=true refuses an empty version")
    result = run_build(gate, tmp_path, {"RELEASE_BUILD": "true", "CLI_VERSION": ""})
    gate.assert_eq(result.rc, 1, "an empty version must not build a publishable artifact")
    gate.assert_contains(
        result.combined, "CLI_VERSION is empty", "the refusal must say the version was empty"
    )
    gate.log_pass("release build refuses an empty version")


def test_release_build_refuses_a_malformed_version(gate, tmp_path):
    gate.log_test("RELEASE_BUILD=true refuses a malformed version")
    result = run_build(gate, tmp_path, {"RELEASE_BUILD": "true", "CLI_VERSION": "1.2.x"})
    gate.assert_eq(result.rc, 1, "a malformed version must not build a publishable artifact")
    gate.assert_contains(result.combined, "not a publishable version", "the refusal must say why")
    gate.log_pass("release build refuses 1.2.x")


def test_dev_build_still_accepts_the_placeholder(gate, tmp_path):
    """THE OTHER DIRECTION: without RELEASE_BUILD the same placeholder is fine, so PR CI and local `./rdc.sh --native` keep working. Proven by letting the build get PAST the guard and die at the bundler instead (a stub node makes that instant and writes nothing)."""
    gate.log_test("a non-release build still accepts 0.0.0-dev")
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "node"
    stub.write_text(
        "#!/bin/bash\n"
        "# Answers --version (the script logs it) and fails anything else, so the run\n"
        "# stops at the bundler -- after the release guard, before any output.\n"
        '[[ "${1:-}" == "--version" ]] && { echo "v22.0.0"; exit 0; }\n'
        'echo "stub node: refusing to run $*" >&2\n'
        "exit 1\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result = run_build(
        gate,
        tmp_path,
        {
            "PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")),
            "CLI_VERSION": "0.0.0-dev",
        },
    )
    out = result.combined
    gate.assert_not_contains(
        out, "refusing to build a publishable artifact", "no release guard without RELEASE_BUILD"
    )
    gate.assert_not_contains(
        out, "not a publishable version", "no release guard without RELEASE_BUILD"
    )
    gate.assert_contains(
        out, "stub node", "the run must have reached the bundler, i.e. passed the guard"
    )
    gate.assert_eq(result.rc, 1, "the stub bundler still fails the run")
    gate.log_pass("the dev path is untouched by the release guard")


def test_the_comparison_is_where_the_mutation_expects_it(gate):
    gate.log_test("the doctor comparison is still in the module")
    source = require_gate(gate)
    gate.assert_contains(
        source, "reported_version", "the reported-version parse must still be in the module"
    )
    gate.assert_contains(
        source, MUTATION_FROM, "the expected-version comparison must still be spelled as planted"
    )
    gate.log_pass("comparison found in the real module")


def test_matching_version_passes(gate, tmp_path):
    gate.log_test("doctor version equal to the build version passes")
    result = run_block(gate, tmp_path, "1.2.17", "1.2.17")
    gate.assert_eq(result.rc, 0, "a matching version must pass")
    gate.assert_contains(result.combined, "matches build version", "and must say so")
    gate.log_pass("1.2.17 built, 1.2.17 reported")


def test_mismatched_version_fails(gate, tmp_path):
    """THE INCIDENT, replayed: release 31154305287 built 1.2.16 and labelled it 1.2.17."""
    gate.log_test("doctor version different from the build version fails")
    result = run_block(gate, tmp_path, "1.2.17", "1.2.16")
    gate.assert_eq(result.rc, 1, "a mismatched version must fail the build")
    gate.assert_contains(
        result.combined, "CLI version mismatch", "the failure must name the mismatch"
    )
    gate.log_pass("1.2.16 reported for a 1.2.17 build is caught")


def test_placeholder_in_the_binary_fails(gate, tmp_path):
    gate.log_test("a binary reporting 0.0.0-dev fails a real-version build")
    result = run_block(gate, tmp_path, "1.2.17", "0.0.0-dev")
    gate.assert_eq(result.rc, 1, "0.0.0-dev in the bytes must fail")
    gate.log_pass("0.0.0-dev in the binary no longer passes cheerfully")


def test_empty_version_still_fails(gate, tmp_path):
    gate.log_test("an unreadable doctor version still fails")
    result = run_block(gate, tmp_path, "1.2.17", "")
    gate.assert_eq(result.rc, 1, "an empty reported version must fail")
    gate.assert_contains(
        result.combined, "CLI version check failed", "the original non-empty check must survive"
    )
    gate.log_pass("empty reported version fails")


def test_planted_noncomparing_check_lets_the_mismatch_through(gate, tmp_path):
    """THE CONTROL. Plant the pre-fix behaviour -- a comparison that compares nothing -- and watch the mismatch sail through. If this planted defect FAILED, `test_mismatched_version_fails` would prove nothing about the comparison."""
    gate.log_test("control: with the comparison neutered, the mismatch passes")
    result = run_block(gate, tmp_path, "1.2.17", "1.2.16", mutate=True)
    gate.assert_eq(
        result.rc, 0, "planted defect must pass (else the real assertion proves nothing)"
    )
    gate.assert_not_contains(
        result.combined, "mismatch", "planted defect must not report a mismatch"
    )
    gate.log_pass("the check demonstrably goes red only because it compares")
