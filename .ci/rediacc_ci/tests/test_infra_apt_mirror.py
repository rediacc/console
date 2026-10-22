"""`rediacc_ci.infra.apt_mirror`: the Azure -> archive.ubuntu.com rewrite, against fixture apt trees."""

from __future__ import annotations

import typing

import pytest

from rediacc_ci.infra import apt_mirror

if typing.TYPE_CHECKING:
    import pathlib

HOSTED = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}

MIRRORS_BARE = "http://azure.archive.ubuntu.com/ubuntu/ priority:1\nhttp://archive.ubuntu.com/ubuntu/ priority:1\nhttp://security.ubuntu.com/ubuntu/ priority:3\n"
DEB822 = "Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\nSuites: noble noble-updates\nComponents: main\n"


def make_tree(root: pathlib.Path) -> pathlib.Path:
    apt = root / "apt"
    (apt / "sources.list.d").mkdir(parents=True)
    (apt / "apt-mirrors.txt").write_text(MIRRORS_BARE, encoding="utf-8")
    (apt / "sources.list.d" / "ubuntu.sources").write_text(DEB822, encoding="utf-8")
    return apt


def test_rewrites_azure_to_archive_on_hosted(tmp_path: pathlib.Path) -> None:
    apt = make_tree(tmp_path)
    changed = apt_mirror.apply(apt, HOSTED)
    assert {p.name for p in changed} == {"apt-mirrors.txt", "ubuntu.sources"}
    assert "azure" not in (apt / "apt-mirrors.txt").read_text()
    # The rewrite makes the first line a duplicate of the second; one survives.
    assert (
        (apt / "apt-mirrors.txt").read_text()
        == "http://archive.ubuntu.com/ubuntu/ priority:1\nhttp://security.ubuntu.com/ubuntu/ priority:3\n"
    )
    assert (
        "URIs: http://archive.ubuntu.com/ubuntu/\n"
        in (apt / "sources.list.d" / "ubuntu.sources").read_text()
    )


def test_deb_lines_are_not_deduplicated() -> None:
    text = "deb http://azure.archive.ubuntu.com/ubuntu/ noble main\ndeb http://archive.ubuntu.com/ubuntu/ noble main\n"
    assert (
        apt_mirror.rewrite_text(text).count("deb http://archive.ubuntu.com/ubuntu/ noble main") == 2
    )


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"GITHUB_ACTIONS": "true"},
        {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
        {"RUNNER_ENVIRONMENT": "github-hosted"},
    ],
)
def test_noop_off_github_hosted(tmp_path: pathlib.Path, env: dict[str, str]) -> None:
    apt = make_tree(tmp_path)
    assert apt_mirror.apply(apt, env) == []
    assert (apt / "apt-mirrors.txt").read_text() == MIRRORS_BARE
    assert (apt / "sources.list.d" / "ubuntu.sources").read_text() == DEB822


def test_idempotent(tmp_path: pathlib.Path) -> None:
    apt = make_tree(tmp_path)
    apt_mirror.apply(apt, HOSTED)
    snapshot = {p.name: p.read_text() for p in apt.rglob("*") if p.is_file()}
    assert apt_mirror.apply(apt, HOSTED) == []
    assert {p.name: p.read_text() for p in apt.rglob("*") if p.is_file()} == snapshot


def test_missing_files_are_skipped(tmp_path: pathlib.Path) -> None:
    assert apt_mirror.apply(tmp_path, HOSTED) == []
