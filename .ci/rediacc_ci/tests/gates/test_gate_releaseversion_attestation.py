"""Port of `.ci/scripts/test/gates/test-releaseversion-attestation.sh`, retired in W7 P5.

Both-ways test for `rediacc_ci.release.verify_artifact_attestation`, the port of the retired `.ci/scripts/release/verify-artifact-attestation.sh` (PLAN-retire-bash-oracles B3: the bash is gone, so the gate now drives the code CD runs).

WHAT IT IS FOR. cd-v2.yml runs it after downloading the release artifacts and before publishing them. It re-verifies the Sigstore build provenance that cd-stage.yml attached, proving the bytes CD is about to publish are the bytes CI produced.

WHAT WAS BROKEN. Every `gh attestation verify` failure became a `::warning::` and the script had NO failing exit path at all -- it could not fail, for any input, ever. Its header called that a "transition period"; nothing recorded when the period ended, so it never would. Worse, `find` over two absent directories prints nothing, the loop body never runs, and it exited 0 having
verified precisely zero artifacts, indistinguishable from a clean pass.

The module resolves its repo root from its OWN path, so the test runs a copy inside a fixture tree. That keeps planted dist/ artifacts out of the real working tree, which other sessions are using.
"""

import os
import pathlib
import shutil
import stat
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.well_known import GH_REPO

GATE_SRC = paths.from_root(".ci", "rediacc_ci", "release", "verify_artifact_attestation.py")


class Fixture:
    """A minimal repo root holding the module under test and artifacts.

    The module finds the root three directories above itself, so a copy at `.ci/rediacc_ci/release/` judges this fixture's `dist/`, never the shared working tree's.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        (root / ".ci" / "rediacc_ci" / "release").mkdir(parents=True)
        self.script = root / ".ci" / "rediacc_ci" / "release" / GATE_SRC.name
        shutil.copy(GATE_SRC, self.script)
        self.output = ""

    def artifacts(self, *relatives: str) -> None:
        for rel in relatives:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("bytes of %s\n" % rel, encoding="utf-8")

    def fake_gh(self, unattested: str = "") -> pathlib.Path:
        """A `gh` that verifies everything except the named basename."""
        bindir = self.root / "bin"
        bindir.mkdir(exist_ok=True)
        script = bindir / "gh"
        script.write_text(
            "#!/bin/bash\n"
            "# Emulates `gh attestation verify <file> --repo <r>`: $1=attestation $2=verify $3=file.\n"
            'target="${3:-}"\n'
            'if [[ -n "%s" && "$(basename "$target")" == "%s" ]]; then\n'
            '    echo "no attestation found for $target" >&2\n'
            "    exit 1\n"
            "fi\n"
            'echo "Verification succeeded for $target"\n' % (unattested, unattested),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return bindir

    def run_gate(self, bindir: pathlib.Path) -> int:
        result = harness.run(
            [sys.executable, str(self.script)],
            env={
                "PATH": "%s:%s" % (bindir, os.environ.get("PATH", "")),
                "GITHUB_REPOSITORY": GH_REPO,
                "GH_TOKEN": "fake",  # a literal the fake gh never reads
                # The copy imports `rediacc_ci.core.gh_retry`, which the fixture tree does not hold; the real package is on the path, the copy still judges the fixture's dist/.
                "PYTHONPATH": str(paths.from_root(".ci")),
            },
        )
        self.output = result.combined
        return result.rc


@pytest.fixture
def fixture(tmp_path):
    return Fixture(tmp_path / "root")


def test_all_attested_passes(gate, fixture):
    gate.log_test("every artifact attested -> pass")
    fixture.artifacts(
        "dist/cli/rdc-linux-x64", "dist/cli/rdc-linux-x64.sha256", "dist/packages/rdc.deb"
    )
    rc = fixture.run_gate(fixture.fake_gh(""))
    gate.assert_eq(rc, 0, "fully attested artifacts must pass")
    gate.assert_contains(
        fixture.output, "verified for all 3", "the pass must name how many it verified"
    )
    gate.log_pass("3 attested artifacts verified")


def test_one_unattested_fails(gate, fixture):
    # THE DEFECT THIS SCRIPT EXISTS TO CATCH, planted: one artifact whose bytes are not the bytes CI attested. Before the fix this printed a warning and exited 0.
    gate.log_test("one unattested artifact -> fail")
    fixture.artifacts("dist/cli/rdc-linux-x64", "dist/packages/rdc.deb")
    rc = fixture.run_gate(fixture.fake_gh("rdc.deb"))
    gate.assert_eq(rc, 1, "an unattested artifact must fail the release")
    gate.assert_contains(
        fixture.output, "no valid build attestation", "the failure must say what is wrong"
    )
    gate.assert_contains(fixture.output, "rdc.deb", "the failure must name the artifact")
    gate.log_pass("an unattested artifact stops the release")


def test_no_artifacts_fails(gate, fixture):
    # THE OTHER WAY THIS SCRIPT COULD NOT FAIL: nothing to verify at all.
    gate.log_test("nothing to verify -> fail")
    rc = fixture.run_gate(fixture.fake_gh(""))
    gate.assert_eq(rc, 1, "verifying zero artifacts is not a pass")
    gate.assert_contains(
        fixture.output, "NOTHING was verified", "the failure must say nothing was checked"
    )
    gate.log_pass("an empty dist/ stops the release")


def test_planted_warning_only_script_passes(gate, fixture):
    # THE CONTROL. Neuter the failure accounting -- the pre-fix shape, where a failed verification only produced a warning -- and watch the same unattested artifact pass. If this planted defect FAILED, test_one_unattested_fails would not be evidence that the exit path is what makes the check red.
    gate.log_test("control: with failures downgraded to warnings, the bad artifact passes")
    fixture.artifacts("dist/cli/rdc-linux-x64", "dist/packages/rdc.deb")
    body = fixture.script.read_text(encoding="utf-8")
    anchor = "failed_list.append(f)"
    if anchor not in body:
        gate.log_fail(
            "CONTROL could not plant its defect: %r is gone from "
            "verify_artifact_attestation.py, so the mutation below is a no-op and "
            "test_one_unattested_fails proves nothing about the exit path" % anchor
        )
    fixture.script.write_text(body.replace(anchor, "pass"), encoding="utf-8")
    rc = fixture.run_gate(fixture.fake_gh("rdc.deb"))
    gate.assert_eq(rc, 0, "planted warning-only script must pass (else the control proves nothing)")
    gate.log_pass("the check goes red only because failures are counted and acted on")
