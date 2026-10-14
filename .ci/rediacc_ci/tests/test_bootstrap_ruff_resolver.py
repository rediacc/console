"""bootstrap.sh resolves ruff only AT THE PIN, an explicit RUFF_BIN included.

Driven through the real `doctor` arm: its ruff row prints the resolved binary beside the pinned version, so a RUFF_BIN reporting another version must not appear there as the pinned one.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
BOOTSTRAP = ROOT / ".ci" / "bootstrap.sh"
TOOLCHAIN_ENV = ROOT / ".devcontainer" / "toolchain.env"


def _pin() -> str:
    text = TOOLCHAIN_ENV.read_text(encoding="utf-8")
    match = re.search(r'^RUFF_VERSION="?([0-9.]+)"?\s*$', text, re.MULTILINE)
    assert match, "RUFF_VERSION left toolchain.env"
    return match.group(1)


def _ruff_row(tmp_path: pathlib.Path, version: str) -> str:
    fake = tmp_path / "ruff"
    fake.write_text("#!/bin/sh\necho 'ruff %s'\n" % version, encoding="utf-8")
    fake.chmod(0o755)
    env = dict(os.environ, RUFF_BIN=str(fake), NO_COLOR="1")
    proc = subprocess.run(
        ["bash", str(BOOTSTRAP), "doctor"],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    rows = [line for line in proc.stdout.splitlines() if line.split()[:1] == ["ruff"]]
    assert len(rows) == 1, proc.stdout + proc.stderr
    return rows[0]


def test_an_explicit_ruff_at_another_version_is_not_reported_as_the_pin(tmp_path):
    row = _ruff_row(tmp_path, "0.0.1")
    assert str(tmp_path) not in row, row


def test_an_explicit_ruff_at_the_pin_is_the_resolved_binary(tmp_path):
    row = _ruff_row(tmp_path, _pin())
    assert str(tmp_path / "ruff") in row, row
