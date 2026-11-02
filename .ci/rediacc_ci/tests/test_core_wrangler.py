"""`rediacc_ci.core.wrangler`: the one argv prefix that never lets npx download wrangler, and the named refusal."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.core import wrangler

if TYPE_CHECKING:
    import pathlib


def _bin(base: pathlib.Path) -> pathlib.Path:
    binary = base / "node_modules" / ".bin" / "wrangler"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_argv_forbids_the_registry_download() -> None:
    assert wrangler.ARGV == ["npx", "--no-install", "wrangler"]


def test_a_local_install_in_the_directory_is_accepted(tmp_path: pathlib.Path) -> None:
    _bin(tmp_path)
    assert wrangler.require(tmp_path, {"PATH": ""}) == wrangler.ARGV


def test_a_local_install_in_an_ancestor_is_accepted(tmp_path: pathlib.Path) -> None:
    _bin(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert wrangler.require(nested, {"PATH": ""}) == wrangler.ARGV


def test_a_wrangler_on_path_is_accepted(tmp_path: pathlib.Path) -> None:
    on_path = tmp_path / "bin"
    on_path.mkdir()
    exe = on_path / "wrangler"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    assert wrangler.require(work, {"PATH": str(on_path)}) == wrangler.ARGV


def test_no_install_anywhere_is_a_named_refusal(tmp_path: pathlib.Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(wrangler.WranglerNotInstalledError) as err:
        wrangler.require(work, {"PATH": str(tmp_path / "empty")})
    assert str(work) in str(err.value)
    assert "npm ci" in str(err.value)
