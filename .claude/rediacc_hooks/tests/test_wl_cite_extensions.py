"""Every tracked text format can be cited as `<path>:<line>` (worklist #6522a5ba).

CITE_RE's extension alternation was found one format short seven times, each by a refused tick. This pins the full set the 2026-10-20 sweep of tracked extensions produced, plus a binary that must stay uncitable."""

from __future__ import annotations

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
