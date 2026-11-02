"""`.ci/bootstrap.sh`'s agg rungs (`resolve_agg`, `which agg [--pin]`, `install agg`), run from a scratch copy of the three files bootstrap reads so the cache rung is the scratch tree's and no network is touched.

The download itself is not exercised here (it needs GitHub). What is: the refusals that must hold BEFORE any download, and the pinned-cache resolution that makes `install agg` idempotent.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
COPIED = (".ci/bootstrap.sh", ".ci/scripts/lib/toolchain.sh", ".devcontainer/toolchain.env")
BASH = shutil.which("bash") or "/bin/bash"
FAKE = "#!/bin/sh\necho 'agg {version}'\n"


def _pin() -> str:
    found = re.search(
        r"^AGG_VERSION=(\S+)$",
        (ROOT / ".devcontainer/toolchain.env").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if found is None:
        raise AssertionError("AGG_VERSION is not pinned in .devcontainer/toolchain.env")
    return found.group(1)


PIN = _pin()


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "root"
    for rel in COPIED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    return root


def _run(
    root: pathlib.Path, *args: str, home: pathlib.Path, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "NO_COLOR": "1", **(env_extra or {})}
    return subprocess.run(
        [BASH, str(root / ".ci/bootstrap.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _fake_cache(root: pathlib.Path, version: str) -> pathlib.Path:
    binary = root / ".ci/cache/toolchain/agg" / PIN / "agg"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(FAKE.format(version=version), encoding="utf-8")
    binary.chmod(0o755)
    return binary


def test_which_agg_pin_answers_the_cache_at_the_pin(
    tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    binary = _fake_cache(tree, PIN)
    got = _run(tree, "which", "agg", "--pin", home=tmp_path / "home")
    assert got.returncode == 0, got.stderr
    assert got.stdout.strip() == str(binary)


def test_a_cache_agg_off_the_pin_is_not_the_pin(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """CONTROL: the version check can fail, so the previous test is not vacuous."""
    _fake_cache(tree, "0.0.1")
    got = _run(tree, "which", "agg", "--pin", home=tmp_path / "home")
    assert got.returncode == 1


def test_absent_everywhere_is_a_refusal(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    assert _run(tree, "which", "agg", home=tmp_path / "home").returncode == 1


def test_agg_bin_that_is_not_executable_is_refused(
    tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    got = _run(
        tree, "which", "agg", home=tmp_path / "home", env_extra={"AGG_BIN": str(tmp_path / "nope")}
    )
    assert got.returncode == 1
    assert "AGG_BIN" in got.stderr


@pytest.mark.skipif(
    platform.machine() not in {"x86_64", "amd64"} or platform.system() != "Linux",
    reason="blanks the linux x86_64 digest",
)
def test_install_refuses_without_a_checksum_before_downloading(
    tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    env_file = tree / ".devcontainer/toolchain.env"
    env_file.write_text(
        re.sub(
            r"^AGG_SHA256_LINUX_X86_64=.*$",
            "AGG_SHA256_LINUX_X86_64=",
            env_file.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
    got = _run(tree, "install", "agg", home=tmp_path / "home")
    assert got.returncode == 1
    assert "no checksum for this platform" in got.stderr
    assert "bootstrap: downloading agg" not in got.stderr
