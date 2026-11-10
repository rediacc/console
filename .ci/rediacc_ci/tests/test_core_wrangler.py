"""`rediacc_ci.core.wrangler`: the one argv prefix that never lets npx download wrangler, and the named refusal."""

from __future__ import annotations

import pathlib
import stat

import pytest

from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import control_db


def _bin(base: pathlib.Path) -> pathlib.Path:
    binary = base / "node_modules" / ".bin" / "wrangler"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_argv_forbids_the_registry_download() -> None:
    assert wrangler.ARGV == ["npx", "--no-install", "wrangler"]


def test_a_local_install_in_the_directory_is_accepted(tmp_path: pathlib.Path) -> None:
    tool = _bin(tmp_path)
    assert wrangler.require(tmp_path, {"PATH": ""}) == [str(tool)]


def test_a_local_install_in_an_ancestor_is_accepted(tmp_path: pathlib.Path) -> None:
    tool = _bin(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert wrangler.require(nested, {"PATH": ""}) == [str(tool)]


def test_a_wrangler_on_path_is_accepted(tmp_path: pathlib.Path) -> None:
    on_path = tmp_path / "bin"
    on_path.mkdir()
    exe = on_path / "wrangler"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    # npx reads no PATH, so the prefix is the verified binary itself, never `ARGV`.
    assert wrangler.require(work, {"PATH": str(on_path)}) == [str(exe)]


def test_binary_is_absolute_for_a_relative_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    tool = _bin(tmp_path / "w")
    monkeypatch.chdir(tmp_path)
    got = wrangler.binary(pathlib.Path("w"), {"PATH": ""})
    assert got.is_absolute()
    assert got == tool


def test_binary_is_absolute_for_a_relative_path_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    exe = tmp_path / "bin" / "wrangler"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(tmp_path)
    got = wrangler.binary(work, {"PATH": "bin"})
    assert got.is_absolute()
    assert got == exe


def test_an_absolute_cwd_and_path_are_unchanged(tmp_path: pathlib.Path) -> None:
    """THE SILENT CONTROL: already-absolute inputs come back as they were."""
    tool = _bin(tmp_path)
    assert wrangler.binary(tmp_path, {"PATH": ""}) == tool


def test_no_install_anywhere_is_a_named_refusal(tmp_path: pathlib.Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(wrangler.WranglerNotInstalledError) as err:
        wrangler.require(work, {"PATH": str(tmp_path / "empty")})
    assert str(work) in str(err.value)
    assert "npm ci" in str(err.value)


def test_resolve_swaps_the_npx_prefix_for_the_local_binary(tmp_path: pathlib.Path) -> None:
    binary = _bin(tmp_path)
    got = wrangler.resolve([*wrangler.ARGV, "d1", "list"], tmp_path, {"PATH": ""})
    assert got == [str(binary), "d1", "list"]


def test_resolve_finds_a_path_binary_from_a_directory_with_no_install(
    tmp_path: pathlib.Path,
) -> None:
    """THE CASE npx GETS WRONG: npm 11.21.0's `npx --no-install` ignores PATH, so a call from a neutral directory with the pinned `.bin` on PATH must run that binary by its path."""
    on_path = _bin(tmp_path / "workers" / "signer")
    neutral = tmp_path / "neutral"
    neutral.mkdir()
    got = wrangler.resolve([*wrangler.ARGV, "d1", "list"], neutral, {"PATH": str(on_path.parent)})
    assert got == [str(on_path), "d1", "list"]


def test_resolve_leaves_any_other_argv_alone(tmp_path: pathlib.Path) -> None:
    """THE SILENT CONTROL: an argv that does not start with `ARGV` is not rewritten and needs no install."""
    assert wrangler.resolve(["wrangler", "--version"], tmp_path, {"PATH": ""}) == [
        "wrangler",
        "--version",
    ]


def test_resolve_refuses_by_name_when_nothing_is_installed(tmp_path: pathlib.Path) -> None:
    with pytest.raises(wrangler.WranglerNotInstalledError):
        wrangler.resolve([*wrangler.ARGV, "d1", "list"], tmp_path, {"PATH": str(tmp_path / "no")})


def test_control_db_runs_the_pinned_binary_from_its_neutral_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Defect 2 of finding fc8ad2fd: `control_db ensure` ran `npx --no-install wrangler d1 list` from a temporary directory and npx, ignoring the `.bin` that `wrangler_env` put on PATH, exited 1. No npx is on PATH here, so only a run by the binary's own path can answer."""
    tool = _bin(tmp_path / "workers" / "signer")
    tool.write_text('#!/bin/sh\necho pinned "$@"\n', encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    done = control_db.run_wrangler([*wrangler.ARGV, "d1", "list", "--json"], root=tmp_path)
    assert (done.rc, done.stdout.strip()) == (0, "pinned d1 list --json")
