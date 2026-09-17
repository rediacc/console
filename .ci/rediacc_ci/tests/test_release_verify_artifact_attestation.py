"""`rediacc_ci.release.verify_artifact_attestation` against its bash twin.

A SCRATCH TREE, NOT THE REAL REPO ROOT. Both the twin's `get_repo_root()` (three directories up from `common.sh`'s own location) and this port's `_ROOT` (three up from its own `__file__`) derive the repo root from WHERE THE CODE LIVES, not from an env var or cwd -- so proving this port against a controlled `dist/cli`/`dist/packages` means copying both implementations, plus
`common.sh`, into a `tmp_path` scratch tree that plays the role of the repo root for the duration of one test. This is the same shape the ledger's recording script uses (a disposable tree elsewhere), applied per test case instead of per session.

`gh attestation verify` is faked on PATH; it is asked for `2>&1`-merged
output in the twin (`verify_output="$(... 2>&1)"`), so the fake here writes
everything to ONE stream (stderr) to avoid asserting an interleaving order this differential does not otherwise pin down.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN_REL = ".ci/scripts/release/verify-artifact-attestation.sh"
MODULE = "verify_artifact_attestation"

FAKE_GH_TEMPLATE = """#!{python}
import os
import sys

target = sys.argv[3] if len(sys.argv) > 3 else ""
fail_list = os.environ.get("FAKE_GH_FAIL_FILES", "").split(",")
if target in fail_list and target != "":
    sys.stderr.write("gh attestation verify: no matching attestations for " + target + "\\n")
    sys.exit(1)
sys.exit(0)
"""


def _build_scratch_tree(tmp_path: pathlib.Path) -> None:
    root = diff.repo()
    ci_scripts_release = tmp_path / ".ci" / "scripts" / "release"
    ci_scripts_lib = tmp_path / ".ci" / "scripts" / "lib"
    ci_scripts_release.mkdir(parents=True)
    ci_scripts_lib.mkdir(parents=True)
    shutil.copy(os.path.join(root, TWIN_REL), ci_scripts_release / "verify-artifact-attestation.sh")
    shutil.copy(os.path.join(root, ".ci/scripts/lib/common.sh"), ci_scripts_lib / "common.sh")

    rediacc_ci = tmp_path / ".ci" / "rediacc_ci"
    release_pkg = rediacc_ci / "release"
    release_pkg.mkdir(parents=True)
    shutil.copy(os.path.join(root, ".ci/rediacc_ci/__init__.py"), rediacc_ci / "__init__.py")
    shutil.copy(
        os.path.join(root, ".ci/rediacc_ci/release/__init__.py"), release_pkg / "__init__.py"
    )
    shutil.copy(
        os.path.join(root, ".ci/rediacc_ci/release/verify_artifact_attestation.py"),
        release_pkg / "verify_artifact_attestation.py",
    )


def _make_fake_gh(tmp_path: pathlib.Path) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH_TEMPLATE.replace("{python}", sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    tmp_path: pathlib.Path, bindir: pathlib.Path, fail_files: str = ""
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    twin_abs = str(tmp_path / TWIN_REL)
    ci_abs = str(tmp_path / ".ci")
    old_env = diff.env_for(
        GITHUB_REPOSITORY="rediacc/console", PATH=path_with_fake, FAKE_GH_FAIL_FILES=fail_files
    )
    new_env = diff.env_for(
        GITHUB_REPOSITORY="rediacc/console",
        PATH=path_with_fake,
        FAKE_GH_FAIL_FILES=fail_files,
        PYTHONPATH=ci_abs,
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % twin_abs, env=old_env, cwd=str(tmp_path), timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(tmp_path), timeout=30
    )
    return old, new


def test_zero_artifacts_is_a_failure_not_a_pass_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The anti-vacuity case the twin's own header exists for."""
    _build_scratch_tree(tmp_path)
    bindir = _make_fake_gh(tmp_path)
    old, new = run_both(tmp_path, bindir)
    assert old[0] == 1
    assert new[0] == 1
    assert "NOTHING was verified" in old[1]
    assert old[1] == new[1]


def test_all_artifacts_verified_passes_on_both_sides(tmp_path: pathlib.Path) -> None:
    _build_scratch_tree(tmp_path)
    (tmp_path / "dist" / "cli").mkdir(parents=True)
    (tmp_path / "dist" / "cli" / "rdc-linux-x64").write_text("bin")
    (tmp_path / "dist" / "packages").mkdir(parents=True)
    (tmp_path / "dist" / "packages" / "rdc.tgz").write_text("tgz")
    bindir = _make_fake_gh(tmp_path)
    old, new = run_both(tmp_path, bindir)
    assert old == (
        0,
        "Verifying artifact provenance...\n::notice::Build provenance verified for all 2 release artifacts.\n",
        "",
    )
    assert new == old


def test_one_failing_artifact_fails_both_sides_and_names_it(tmp_path: pathlib.Path) -> None:
    _build_scratch_tree(tmp_path)
    (tmp_path / "dist" / "cli").mkdir(parents=True)
    (tmp_path / "dist" / "cli" / "rdc-linux-x64").write_text("bin")
    (tmp_path / "dist" / "cli" / "rdc-darwin-arm64").write_text("bin2")
    bindir = _make_fake_gh(tmp_path)
    old, new = run_both(tmp_path, bindir, fail_files="dist/cli/rdc-darwin-arm64")
    assert old[0] == 1
    assert new[0] == 1
    assert "1 of 2 release artifacts have no valid build attestation" in old[1]
    assert old[1] == new[1]
    assert "rdc-darwin-arm64" in old[2]
    assert "rdc-darwin-arm64" in new[2]


def test_missing_github_repository_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    _build_scratch_tree(tmp_path)
    bindir = _make_fake_gh(tmp_path)
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    twin_abs = str(tmp_path / TWIN_REL)
    ci_abs = str(tmp_path / ".ci")
    old_env = diff.env_for(PATH=path_with_fake)
    new_env = diff.env_for(PATH=path_with_fake, PYTHONPATH=ci_abs, PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % twin_abs, env=old_env, cwd=str(tmp_path), timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(tmp_path), timeout=30
    )
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_REPOSITORY" in old[2]
    assert "GITHUB_REPOSITORY" in new[2]
