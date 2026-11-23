"""The environment-names gate's scratch-tree seam is bounded, and an empty corpus is never green."""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import paths

GATE = paths.from_root(".ci", "scripts", "quality", "check_environment_names.py")


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ENV_NAMES_")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(GATE)],
        cwd=paths.repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_empty_scratch_corpus_refuses_even_with_a_zero_floor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / ".github" / "workflows").mkdir(parents=True)
        got = _run({"ENV_NAMES_ROOT": tmp, "ENV_NAMES_MIN": "0"})
    assert got.returncode == 1, got.stdout + got.stderr
    assert "VACUOUS: 0 workflow file(s)" in got.stderr


def test_scratch_corpus_with_a_floor_of_zero_still_scans_when_it_has_files() -> None:
    """CONTROL: the seam still works inside the temp directory, so the refusal above is the empty corpus and not a dead seam."""
    with tempfile.TemporaryDirectory() as tmp:
        wf = pathlib.Path(tmp) / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "a.yml").write_text("jobs:\n  a:\n    environment: edge\n", encoding="utf-8")
        got = _run({"ENV_NAMES_ROOT": tmp, "ENV_NAMES_MIN": "0"})
    assert got.returncode == 0, got.stdout + got.stderr
    assert "1 workflow file(s) scanned" in got.stdout


def test_override_outside_the_temp_directory_is_ignored_on_a_plain_run() -> None:
    """A root outside the temp directory, with a zero floor, still scans the repository against the real floor."""
    outside = paths.repo_root() / ".ci" / "cache" / "env-names-empty-root"
    (outside / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    got = _run({"ENV_NAMES_ROOT": str(outside), "ENV_NAMES_MIN": "0"})
    assert got.returncode == 0, got.stdout + got.stderr
    assert "ignored" in got.stderr
    assert "(floor 20)" in got.stdout
