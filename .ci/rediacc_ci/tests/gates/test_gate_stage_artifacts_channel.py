"""Port of `.ci/scripts/test/gates/test-stage-artifacts-channel.sh`.

Unit test for the channel gating of the APT/RPM metadata assertions in
`.ci/scripts/release/validate-stage-artifacts.sh`.

WHAT BROKE. The script asserted APT and RPM repository metadata unconditionally.
That metadata is CHANNEL-SCOPED and is built by cd-stage.yml's "Build package
repositories" step, which self-gates on `inputs.channel != ''`. The channel is
empty for any event that is not push or pull_request -- i.e. for the nightly,
deliberately, so a scheduled run cannot orphan ~5 GB of R2 bytes. So on every
nightly the metadata was correctly absent and the validator failed the stage
anyway:

  run 30237524399 (2026-07-27), Stage Artifacts:
    ##[error]No APT metadata files found
    ##[error]No RPM metadata files found

One of the three breaks behind twelve consecutive red nightlies.

THE DANGEROUS DIRECTION. A channel gate is a WEAKENED CHECK, and the whole reason
this bug survived is that nobody was watching a weakened signal. So the tests that
matter most here are the ones proving the skip is NARROW: the assertions must still
fire on a real release channel, and every other artifact assertion must still fire
when the channel is empty.

THE PORT BUILDS ITS FIXTURE PER TEST rather than once per file. The twin shares one
`$FIXTURE` and each case re-seeds it, which is the only isolation a flat shell
script can offer; a fixture here is cheap and removes the ordering coupling
entirely. No case's inputs change, so no case's verdict changes.
"""

import pathlib
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-stage-artifacts-channel.sh"

VALIDATOR_SRC = paths.from_root(".ci", "scripts", "release", "validate-stage-artifacts.sh")
COMMON_SRC = paths.from_root(".ci", "scripts", "lib", "common.sh")


class Stage:
    """A fixture repo root holding the validator, its lib, and a staged dist/.

    `get_repo_root()` resolves from the SCRIPT's own path (.ci/scripts/lib -> up 3),
    not from cwd, so the fixture has to mirror the tree layout rather than just being
    a directory with a dist/ in it.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        (root / ".ci" / "scripts" / "release").mkdir(parents=True)
        (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
        shutil.copy(VALIDATOR_SRC, root / ".ci" / "scripts" / "release" / VALIDATOR_SRC.name)
        shutil.copy(COMMON_SRC, root / ".ci" / "scripts" / "lib" / COMMON_SRC.name)
        self.validator = root / ".ci" / "scripts" / "release" / VALIDATOR_SRC.name
        self.summary = root / "summary.md"
        self.last_output = ""

    def seed_dist(self) -> None:
        """A COMPLETE staged tree, so each case can remove exactly one thing."""
        dist = self.root / "dist"
        shutil.rmtree(dist, ignore_errors=True)
        for sub in ("cli", "packages", "pages", "repos/apt/dists", "repos/rpm/repodata"):
            (dist / sub).mkdir(parents=True)
        (dist / "cli" / "rdc-linux-x64").touch()
        # Two of each: the validator asserts >= 2 per package format.
        for i in (1, 2):
            for ext in ("deb", "rpm", "apk", "pkg.tar.zst"):
                (dist / "packages" / ("pkg%d.%s" % (i, ext))).touch()
        (dist / "pages" / "index.html").touch()
        (dist / "repos" / "apt" / "dists" / "Release").touch()
        (dist / "repos" / "rpm" / "repodata" / "repomd.xml").touch()

    def drop_metadata(self) -> None:
        shutil.rmtree(self.root / "dist" / "repos", ignore_errors=True)

    def validate(self, event: str, channel: str) -> str:
        """-> "PASS" or "FAIL". The validator's own output lands in `last_output`."""
        self.summary.write_text("", encoding="utf-8")
        result = harness.run(
            ["bash", str(self.validator)],
            env={
                "EVENT_NAME": event,
                "CHANNEL": channel,
                "NEXT_VERSION": "1.2.3",
                "GITHUB_STEP_SUMMARY": str(self.summary),
                "GITHUB_OUTPUT": str(self.root / "output.txt"),
            },
        )
        self.last_output = result.combined
        return "PASS" if result.rc == 0 else "FAIL"


@pytest.fixture
def stage(tmp_path):
    return Stage(tmp_path / "fixture")


def test_complete_tree_on_a_release_channel_passes(gate, stage):
    # Baseline. If this failed, every other case would be meaningless.
    stage.seed_dist()
    gate.assert_eq(
        stage.validate("push", "edge"), "PASS", "a complete staged tree on a real channel validates"
    )
    gate.log_pass("a complete tree on a release channel passes")


def test_metadata_assertions_STILL_FIRE_on_a_release_channel(gate, stage):  # noqa: N802
    # THE CONTROL. The channel gate must not have turned these assertions off
    # for the runs that actually publish. This is the case that proves the fix
    # narrowed the check rather than deleting it.
    stage.seed_dist()
    stage.drop_metadata()
    gate.assert_eq(
        stage.validate("push", "edge"), "FAIL", "missing metadata on a real channel must still fail"
    )
    gate.assert_contains(
        stage.last_output, "No APT metadata files found", "the APT assertion still fires"
    )
    gate.assert_contains(
        stage.last_output, "No RPM metadata files found", "the RPM assertion still fires"
    )
    gate.log_pass("on a release channel the metadata assertions still fail the stage")


def test_pr_channel_also_still_asserts(gate, stage):
    # pr-N is a real channel and does stage package repositories.
    stage.seed_dist()
    stage.drop_metadata()
    gate.assert_eq(
        stage.validate("pull_request", "pr-540"),
        "FAIL",
        "a pr-N channel must still assert metadata",
    )
    gate.log_pass("a pr-N channel still asserts metadata")


def test_empty_channel_skips_only_the_metadata_assertions(gate, stage):
    # THE FIX. This is the exact nightly shape: no channel, so no package
    # repositories were built, so their absence is correct.
    stage.seed_dist()
    stage.drop_metadata()
    gate.assert_eq(stage.validate("schedule", ""), "PASS", "the nightly shape must validate")
    gate.assert_not_contains(
        stage.last_output, "No APT metadata files found", "the APT assertion is skipped"
    )
    gate.assert_not_contains(
        stage.last_output, "No RPM metadata files found", "the RPM assertion is skipped"
    )
    gate.log_pass("an empty channel skips exactly the two metadata assertions")


def test_the_skip_is_announced_not_silent(gate, stage):
    # A silently weakened check is how this class of bug survives. The skip has
    # to be visible in the run summary and as a notice.
    stage.seed_dist()
    stage.drop_metadata()
    stage.validate("schedule", "")
    gate.assert_contains(stage.last_output, "::notice::", "the skip emits a notice")
    gate.assert_contains(
        stage.summary.read_text(encoding="utf-8"),
        "metadata assertions skipped",
        "the skip is recorded in the step summary a human reads",
    )
    gate.log_pass("the skip announces itself in both the log and the step summary")


def test_empty_channel_does_NOT_weaken_the_other_assertions(gate, stage):  # noqa: N802
    # THE OTHER DANGEROUS DIRECTION, and the one a careless fix gets wrong: the
    # channel gate must cover ONLY the two metadata checks. If a nightly stops
    # producing CLI binaries or half the packages, that must still be red --
    # otherwise "fix the nightly" would have quietly become "stop checking it".
    stage.seed_dist()
    stage.drop_metadata()
    (stage.root / "dist" / "cli" / "rdc-linux-x64").unlink()
    gate.assert_eq(
        stage.validate("schedule", ""),
        "FAIL",
        "missing CLI artifacts must still fail on a channel-less run",
    )
    gate.assert_contains(
        stage.last_output, "No CLI artifacts found", "the CLI assertion is untouched"
    )

    stage.seed_dist()
    stage.drop_metadata()
    (stage.root / "dist" / "packages" / "pkg2.deb").unlink()
    gate.assert_eq(
        stage.validate("schedule", ""),
        "FAIL",
        "too few DEBs must still fail on a channel-less run",
    )
    gate.assert_contains(
        stage.last_output, "Expected at least 2 DEB packages", "the DEB assertion is untouched"
    )

    stage.seed_dist()
    stage.drop_metadata()
    (stage.root / "dist" / "packages" / "pkg2.rpm").unlink()
    gate.assert_eq(
        stage.validate("schedule", ""),
        "FAIL",
        "too few RPMs must still fail on a channel-less run",
    )

    stage.seed_dist()
    stage.drop_metadata()
    (stage.root / "dist" / "packages" / "pkg2.pkg.tar.zst").unlink()
    gate.assert_eq(
        stage.validate("schedule", ""),
        "FAIL",
        "too few Arch packages must still fail on a channel-less run",
    )
    gate.log_pass(
        "the channel gate covers ONLY the metadata assertions; every other check is untouched"
    )
