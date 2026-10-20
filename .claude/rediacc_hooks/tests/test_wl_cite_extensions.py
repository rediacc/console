"""Every tracked text format can be cited as `<path>:<line>` (worklist #6522a5ba).

CITE_RE's extension alternation was found one format short seven times, each by a refused tick. This pins the full set the 2026-10-20 sweep of tracked extensions produced, plus a binary that must stay uncitable."""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

C = wlfix.import_wl("wl_checks")

TEXT_FORMATS = [
    "private/account/drizzle/0059_backup_manifest_index.sql",
    "pkg/x/testdata/case.golden",
    "debian/pkgs.list",
    "logs/run.log",
    "biome-plugins/rule.grit",
    "etc/nginx.conf",
    "systemd/rediacc.service",
    "web/index.html",
    "res/strings.xml",
    "tpl/unit.template",
    "go.sum",
    "go.mod",
    "src/__snapshots__/a.snap",
    "scripts/setup.ps1",
    "patches/fix.patch",
    "native/probe.c",
]


@pytest.mark.parametrize("rel", TEXT_FORMATS)
def test_a_tracked_text_format_is_citable(tmp_path, rel):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    ok, detail = C.citation_state(tmp_path, "see %s:2 for it" % rel)
    assert ok, detail


def test_control_a_binary_stays_uncitable(tmp_path):
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n")
    ok, detail = C.citation_state(tmp_path, "see img.png:1")
    assert not ok
    assert "citation" in detail


def test_control_a_bare_word_in_prose_is_not_a_citation(tmp_path):
    ok, _ = C.citation_state(tmp_path, "rerun at 10:30 with mode:3")
    assert not ok


# Binary formats a line number cannot point into, and the empty `.gitkeep` placeholder (it has no lines). Root and nested dotfiles are covered by their own CITE_RE branch, by name.
UNCITABLE = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "ico",
    "pdf",
    "woff",
    "woff2",
    "ttf",
    "otf",
    "eot",
    "avif",
    "gz",
    "zip",
    "mp4",
    "webm",
    "mp3",
    "wav",
    "o",
    "native",
    "gitkeep",
}


REPOS = ("", "private/renet", "private/account", "private/elite")
ROOT = pathlib.Path(__file__).resolve().parents[3]


def _tracked_extensions(rel_repo: str) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT / rel_repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    exts = set()
    for rel in out.splitlines():
        name = rel.rsplit("/", 1)[-1]
        if "." in name.lstrip("."):
            # Case kept: CITE_RE is case-sensitive, so NOTES.TXT must be checked as TXT.
            exts.add(name.rsplit(".", 1)[1])
    return exts


@pytest.mark.parametrize("rel_repo", REPOS, ids=lambda r: r or "console")
def test_every_tracked_text_extension_is_citable(tmp_path, rel_repo):
    """The completeness claim in wl_checks.CITE_RE's comment, checked against the live tree instead of trusted: a new text format anywhere in the console or its submodules fails here until it is citable or named uncitable above. A submodule that is not checked out is a visible skip locally and a failure on CI, never a silent pass."""
    if not (ROOT / rel_repo / ".git").exists():
        # CI's pytest lane checks out with `submodules: true` (.github/workflows/ci-quality.yml, quality-pytest), so a missing submodule there is a broken checkout and fails; only a local tree without submodules skips, and says which.
        if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
            pytest.fail(
                "%s is not checked out on CI, so its extensions cannot be checked" % rel_repo
            )
        pytest.skip("%s is not checked out here, so its extensions were not checked" % rel_repo)
    missing = []
    # UNCITABLE is matched case-insensitively (LOGO.PNG is a binary too); the probe keeps the case, since CITE_RE does.
    for ext in sorted(e for e in _tracked_extensions(rel_repo) if e.lower() not in UNCITABLE):
        rel = "probe/file.%s" % ext
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a\nb\n", encoding="utf-8")
        ok, _ = C.citation_state(tmp_path, "see %s:1" % rel)
        if not ok:
            missing.append(ext)
    assert missing == [], "tracked extensions in %s that cannot be cited: %s" % (
        rel_repo or "console",
        missing,
    )
