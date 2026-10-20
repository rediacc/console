"""Every tracked text format can be cited as `<path>:<line>` (worklist #6522a5ba).

CITE_RE's extension alternation was found one format short seven times, each by a refused tick. This pins the full set the 2026-10-20 sweep of tracked extensions produced, plus a binary that must stay uncitable."""

from __future__ import annotations

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


# Formats a line number cannot point into, plus root/nested dotfiles (their own CITE_RE branch covers them by name, not by extension).
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
    "map",
    "o",
    "native",
    "lock",
    "gitkeep",
}


def _tracked_extensions():
    root = pathlib.Path(__file__).resolve().parents[3]
    repos = [root] + [root / s for s in ("private/renet", "private/account", "private/elite")]
    exts = set()
    for repo in repos:
        if not (repo / ".git").exists():
            continue
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
        ).stdout
        for rel in out.splitlines():
            name = rel.rsplit("/", 1)[-1]
            if "." in name.lstrip("."):
                exts.add(name.rsplit(".", 1)[1].lower())
    return exts


def test_every_tracked_text_extension_is_citable(tmp_path):
    """The completeness claim in wl_checks.CITE_RE's comment, checked against the live tree instead of trusted: a new text format anywhere in the console or its submodules fails here until it is citable or named uncitable above."""
    missing = []
    for ext in sorted(_tracked_extensions() - UNCITABLE):
        rel = "probe/file.%s" % ext
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a\nb\n", encoding="utf-8")
        ok, _ = C.citation_state(tmp_path, "see %s:1" % rel)
        if not ok:
            missing.append(ext)
    assert missing == [], "tracked extensions that cannot be cited: %s" % missing
