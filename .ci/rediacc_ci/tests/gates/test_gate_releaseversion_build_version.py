"""Port of `.ci/scripts/test/gates/test-releaseversion-build-version.sh`.

Both-ways test for the two version checks inside `.ci/scripts/build/build-cli-executables.sh`.

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

HOW THE SMOKE TEST IS EXERCISED. Building a real SEA takes minutes, so the comparison block is EXTRACTED FROM THE REAL SCRIPT by its own anchors and run against planted doctor output. It is the script's own bytes, not a copy of its
logic; if someone rewrites the block, the anchors stop matching and
`test_block_is_extractable` fails rather than silently testing nothing.

TWO REFUSALS THE PORT ADDS, both guarding controls rather than the subject. An extraction that comes back EMPTY produces a runner that exits 0 having done
nothing, which would turn four cases green for the wrong reason; and the planted
mutation in the last case is asserted to have CHANGED something, because a `sed` whose pattern stopped matching plants the FIXED code and then reports that the fixed code lets a mismatch through, which it does not -- the case would red
while naming the opposite of what happened.

THE BUILD IS DRIVEN AT ITS REAL PATH, unchanged from the twin, because the release guard sits between the `--dry-run` exit and `node bundle.mjs`: a refused build costs a second and writes nothing. `--output` still points into a per-test tmpdir so the one case that gets PAST the guard has nowhere to land but scratch.
"""

import json
import os
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-releaseversion-build-version.sh"

GATE = paths.from_root(".ci", "scripts", "build", "build-cli-executables.sh")

BLOCK_START = 'INSTALL_METHOD=$(echo "$DOCTOR_OUTPUT" | jq -r'
BLOCK_END = 'log_info "CLI version: $REPORTED_CLI_VERSION (matches build version)"'

# The pre-fix behaviour: a comparison that compares nothing.
MUTATION_FROM = '"$REPORTED_CLI_VERSION" != "$EXPECTED_CLI_VERSION"'
MUTATION_TO = "1 -eq 0"


def require_gate(gate) -> str:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    return GATE.read_text(encoding="utf-8")


def run_build(gate, tmp_path, env: dict[str, str]) -> harness.RunResult:
    """The REAL script, at its real path, refused by the guard before it writes."""
    require_gate(gate)
    bash = harness.require_tool("bash", "install bash; the subject IS a bash script")
    return harness.run(
        [
            bash,
            str(GATE),
            "--platform",
            "linux",
            "--arch",
            "x64",
            "--output",
            str(tmp_path / "out"),
        ],
        cwd=paths.repo_root(),
        env=env,
        timeout=300,
    )


def extract_block(gate) -> str:
    source = require_gate(gate)
    kept: list[str] = []
    started = False
    for line in source.splitlines(keepends=True):
        if not started and BLOCK_START in line:
            started = True
        if started:
            kept.append(line)
            if BLOCK_END in line:
                break
    if not kept:
        gate.log_fail(
            "the doctor comparison block could not be extracted from %s: no line contains "
            "%r. The anchors moved, so every case below would be driving an EMPTY script."
            % (paths.relative_to_root(GATE), BLOCK_START)
        )
    return "".join(kept)


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
    block = extract_block(gate)
    if mutate:
        hits = block.count(MUTATION_FROM)
        # THE CONTROL ON THE CONTROL. A mutation that matches nothing plants the FIXED comparison and then asserts it lets a mismatch through.
        if hits == 0:
            gate.log_fail(
                "the planted mutation target %r no longer appears in the extracted block, "
                "so the 'neutered' comparison below is the LIVE one. Re-point the "
                "mutation; do not delete the case." % MUTATION_FROM
            )
        block = block.replace(MUTATION_FROM, MUTATION_TO)
    script = tmp_path / "block.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'log_info() { echo "INFO: $*"; }\n'
        'log_error() { echo "ERROR: $*" >&2; }\n'
        "EXPECTED_CLI_VERSION=%s\n"
        "DOCTOR_OUTPUT=%s\n" % (_sq(expected), _sq(doctor_json(reported))) + block,
        encoding="utf-8",
    )
    bash = harness.require_tool("bash", "install bash; the extracted block is bash")
    return harness.run([bash, str(script)], cwd=paths.repo_root(), timeout=120)


def _sq(value: str) -> str:
    """Single-quote for bash. The twin interpolates unquoted; the doctor JSON has
    no single quotes so both are safe today, and this stays safe if it grows one."""
    return "'%s'" % value.replace("'", "'\\''")


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
    """THE OTHER DIRECTION: without RELEASE_BUILD the same placeholder is fine, so PR
    CI and local `./rdc.sh --native` keep working. Proven by letting the build get PAST the guard and die at the bundler instead (a stub node makes that instant and writes nothing).
    """
    gate.log_test("a non-release build still accepts 0.0.0-dev")
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "node"
    stub.write_text(
        "#!/bin/bash\n"
        "# Answers --version (the script logs it) and fails anything else, so the run\n"
        "# stops at `node bundle.mjs` -- after the release guard, before any output.\n"
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


def test_block_is_extractable(gate):
    gate.log_test("the doctor comparison block is still where the anchors say")
    block = extract_block(gate)
    gate.assert_contains(
        block, "REPORTED_CLI_VERSION", "extraction must capture the reported-version parse"
    )
    gate.assert_contains(
        block, "EXPECTED_CLI_VERSION", "extraction must capture the expected-version comparison"
    )
    gate.log_pass("block extracted from the real script (%d line(s))" % len(block.splitlines()))


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
    """THE CONTROL. Plant the pre-fix behaviour -- a comparison that compares nothing
    -- and watch the mismatch sail through. If this planted defect FAILED, `test_mismatched_version_fails` would prove nothing about the comparison.
    """
    gate.log_test("control: with the comparison neutered, the mismatch passes")
    result = run_block(gate, tmp_path, "1.2.17", "1.2.16", mutate=True)
    gate.assert_eq(
        result.rc, 0, "planted defect must pass (else the real assertion proves nothing)"
    )
    gate.assert_not_contains(
        result.combined, "mismatch", "planted defect must not report a mismatch"
    )
    gate.log_pass("the check demonstrably goes red only because it compares")
