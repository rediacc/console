"""The session pytest wrapper draws its lease module from the checkout it is launched in.

`.ci/cache/toolchain` is shared with scratch clones by symlink, so a wrapper that baked the installing checkout's `core_lease.py` ran the LIVE tree's lease code under a clone's tests. The wrapper text is taken from the real `pytest_wrapper_text` in `bootstrap.sh` and run with a stand-in interpreter that prints the lease path it was handed.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

BOOTSTRAP = paths.repo_root() / ".ci" / "bootstrap.sh"


def _wrapper(tmp_path: pathlib.Path, baked_lease: pathlib.Path) -> pathlib.Path:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(r"^pytest_wrapper_text\(\) \{\n.*?^\}\n", source, re.MULTILINE | re.DOTALL)
    assert match, "pytest_wrapper_text left bootstrap.sh"
    real = tmp_path / "real-pytest"
    real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    real.chmod(0o755)
    python = tmp_path / "python"
    python.write_text('#!/bin/sh\necho "LEASE=$1"\n', encoding="utf-8")
    python.chmod(0o755)
    script = (
        'WRAPPER_MARK="# rediacc core-lease pytest wrapper"\n'
        'REAL_PYTEST="$1" REAL_PYTHON="$2" LEASE_PY="$3"\n'
        + match.group(0)
        + "pytest_wrapper_text\n"
    )
    done = subprocess.run(
        ["bash", "-c", script, "bash", str(real), str(python), str(baked_lease)],
        capture_output=True,
        text=True,
        check=True,
    )
    wrapper = tmp_path / "pytest"
    wrapper.write_text(done.stdout, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def _run(wrapper: pathlib.Path, cwd: pathlib.Path) -> str:
    env = {k: v for k, v in os.environ.items() if k != "CI_CORE_LEASE_HELD"}
    done = subprocess.run(
        [str(wrapper), "-q"], capture_output=True, text=True, cwd=cwd, env=env, check=True
    )
    return done.stdout.strip()


def test_the_lease_comes_from_the_invoking_checkout(tmp_path):
    baked = tmp_path / "installed" / "core_lease.py"
    wrapper = _wrapper(tmp_path, baked)
    clone = tmp_path / "clone"
    (clone / ".ci" / "rediacc_ci").mkdir(parents=True)
    (clone / ".ci" / "rediacc_ci" / "core_lease.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    sub = clone / "deep"
    sub.mkdir()
    for cwd in (clone, sub):
        got = _run(wrapper, cwd)
        assert got == "LEASE=%s" % (clone.resolve() / ".ci/rediacc_ci/core_lease.py"), got


def test_outside_a_checkout_the_installed_lease_is_the_fallback(tmp_path):
    baked = tmp_path / "installed" / "core_lease.py"
    wrapper = _wrapper(tmp_path, baked)
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _run(wrapper, bare) == "LEASE=%s" % baked
