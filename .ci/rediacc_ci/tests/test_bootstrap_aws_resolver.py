"""`.ci/bootstrap.sh`'s aws rungs (`resolve_aws`, `which aws [--pin]`, the doctor row), against `rediacc_ci.core.awscli`'s.

Each case runs the real bootstrap from a scratch copy of the three files it reads (the script, `.ci/scripts/lib/toolchain.sh`, `.devcontainer/toolchain.env`), so its cache rung is the scratch tree's and the repo's own `.ci/cache` install never answers. `aws` is masked out of PATH with `pathmask`, and every aws planted is a fake that prints a version line.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import awscli
from rediacc_ci.tests import pathmask

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
COPIED = (".ci/bootstrap.sh", ".ci/scripts/lib/toolchain.sh", ".devcontainer/toolchain.env")
PIN = awscli.pin()
FAKE = "#!/bin/sh\necho 'aws-cli/{version} Python/3.13.7 Linux/6.8.0 exe/x86_64.ubuntu.24'\n"
BASH = shutil.which("bash") or "/bin/bash"


def _fake(path: pathlib.Path, version: str = PIN) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE.format(version=version), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "root"
    for rel in COPIED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, root / rel)
    return root


def _cache(root: pathlib.Path) -> pathlib.Path:
    return root / ".ci" / "cache" / "toolchain" / "aws-cli" / PIN / "bin" / "aws"


def _run(root: pathlib.Path, tmp_path: pathlib.Path, *args: str, extra_path: str = "", **env: str):
    path = pathmask.path_without("aws", tmp_path / "mask")
    pathmask.assert_absent("aws", path)
    full = {
        "PATH": (extra_path + os.pathsep + path) if extra_path else path,
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "NO_COLOR": "1",
        **env,
    }
    return subprocess.run(
        [BASH, str(root / ".ci" / "bootstrap.sh"), *args],
        capture_output=True,
        text=True,
        check=False,
        env=full,
        timeout=120,
    )


def test_nothing_resolves(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    proc = _run(tree, tmp_path, "which", "aws")
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_aws_bin_is_the_first_rung(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    explicit = _fake(tmp_path / "explicit" / "aws")
    on_path = _fake(tmp_path / "onpath" / "aws")
    _fake(_cache(tree))
    proc = _run(
        tree, tmp_path, "which", "aws", extra_path=str(on_path.parent), AWS_BIN=str(explicit)
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(explicit)


def test_an_aws_bin_that_does_not_exist_refuses(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    on_path = _fake(tmp_path / "onpath" / "aws")
    proc = _run(
        tree,
        tmp_path,
        "which",
        "aws",
        extra_path=str(on_path.parent),
        AWS_BIN=str(tmp_path / "absent"),
    )
    assert proc.returncode == 1
    assert "AWS_BIN" in proc.stderr


def test_path_is_taken_as_found(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    on_path = _fake(tmp_path / "onpath" / "aws", version="1.0.0")
    _fake(_cache(tree))
    proc = _run(tree, tmp_path, "which", "aws", extra_path=str(on_path.parent))
    assert proc.stdout.strip() == str(on_path)


def test_the_cache_answers_only_at_the_pin(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    cached = _fake(_cache(tree), version="2.0.0")
    assert _run(tree, tmp_path, "which", "aws").returncode == 1
    _fake(cached)
    proc = _run(tree, tmp_path, "which", "aws")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(cached)


def test_which_pin_ignores_a_path_aws(tree: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """The CI export: a runner's own aws on PATH is not the pin."""
    on_path = _fake(tmp_path / "onpath" / "aws")
    assert (
        _run(tree, tmp_path, "which", "aws", "--pin", extra_path=str(on_path.parent)).returncode
        == 1
    )
    cached = _fake(_cache(tree))
    proc = _run(tree, tmp_path, "which", "aws", "--pin", extra_path=str(on_path.parent))
    assert proc.stdout.strip() == str(cached)


def test_install_aws_is_idempotent_by_the_cache_rung(
    tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """With the pin already cached, `install aws` downloads nothing and names the cached binary."""
    cached = _fake(_cache(tree))
    proc = _run(tree, tmp_path, "install", "aws")
    assert proc.returncode == 0, proc.stderr
    assert "aws %s already at %s" % (PIN, cached) in proc.stdout


def test_the_doctor_row_is_optional_and_shows_drift(
    tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    absent = _run(tree, tmp_path, "doctor")
    row = [line for line in absent.stdout.splitlines() if line.split()[:1] == ["aws"]]
    assert len(row) == 1, absent.stdout
    assert PIN in row[0]
    assert "ABSENT" in row[0]
    assert "optional" in row[0]
    on_path = _fake(tmp_path / "onpath" / "aws", version="1.0.0")
    drift = _run(tree, tmp_path, "doctor", extra_path=str(on_path.parent))
    row = [line for line in drift.stdout.splitlines() if line.split()[:1] == ["aws"]]
    assert "reports 1.0.0" in row[0], drift.stdout


def test_the_python_and_bash_rungs_agree(
    tree: pathlib.Path, tmp_path: pathlib.Path, monkeypatch
) -> None:
    """One plant per rung, asked of both resolvers."""
    explicit = _fake(tmp_path / "explicit" / "aws")
    on_path = _fake(tmp_path / "onpath" / "aws")
    cached = _fake(_cache(tree))
    monkeypatch.setattr(awscli, "cache_binary", lambda _version=None, _root=None: cached)
    awscli._PROBED.clear()
    masked = pathmask.path_without("aws", tmp_path / "mask")
    cases: tuple[tuple[dict[str, str], str], ...] = (
        ({"AWS_BIN": str(explicit)}, str(on_path.parent)),
        ({}, str(on_path.parent)),
        ({}, ""),
    )
    for env, extra in cases:
        bash = _run(tree, tmp_path, "which", "aws", extra_path=extra, **env).stdout.strip()
        python = awscli.resolve({**env, "PATH": (extra + os.pathsep + masked) if extra else masked})
        assert bash == python, (env, extra)
