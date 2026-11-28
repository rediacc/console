"""`differential.write_recorded` stamps the golden header's `source` truthfully (review finding 8422dd2f.1)."""

from __future__ import annotations

import os
import sys

import pytest

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import regolden

TWIN = "scripts/x/fake.sh"
STEM = "fake"


@pytest.fixture
def golden(tmp_path, monkeypatch):
    path = tmp_path / "fake.jsonl"
    monkeypatch.setattr(diff, "golden_file", lambda _twin: path)
    monkeypatch.setattr(diff, "RECORDED", {STEM: {}})
    monkeypatch.setattr(diff, "RECORDED_TWINS", {STEM: TWIN})
    diff.goldenio.write_golden(
        path,
        {
            "bash_version": "b",
            "case_count": 2,
            "source": "bash",
            "twin": TWIN,
            "twin_blob": "a" * 40,
        },
        set(),
        {"one": {"rc": 0, "out": "x", "err": ""}, "two": {"rc": 0, "out": "y", "err": ""}},
    )
    return path


def _header(path):
    return diff.goldenio.read_golden(path)[0]


def test_a_selective_port_rerecord_over_bash_cases_is_mixed(golden, monkeypatch):
    monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", "")}})
    diff.write_recorded("port", "fix", keep_unseen=True)
    assert _header(golden)["source"] == "mixed"


def test_a_full_port_rerecord_is_port(golden, monkeypatch):
    monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", ""), "two": (0, "y", "")}})
    diff.write_recorded("port", "fix")
    assert _header(golden)["source"] == "port"


def test_a_selective_rerecord_from_the_same_source_keeps_it(golden, monkeypatch):
    monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", "")}})
    monkeypatch.setattr(diff, "blob_sha", lambda _twin: "b" * 40)
    diff.write_recorded("bash", "fix", keep_unseen=True)
    assert _header(golden)["source"] == "bash"


def test_a_full_rerecord_that_loses_a_case_is_refused_and_writes_nothing(golden, monkeypatch):
    before = golden.read_bytes()
    monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", "")}})
    with pytest.raises(diff.ShrinkRefusedError, match="two"):
        diff.write_recorded("port", "fix")
    assert golden.read_bytes() == before


@pytest.mark.usefixtures("golden")
def test_allow_shrink_drops_the_lost_case_and_counts_it(monkeypatch):
    monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", "")}})
    (line,) = diff.write_recorded("port", "fix", allow_shrink=True)
    assert "1 case(s)" in line
    assert "1 dropped" in line


@pytest.mark.usefixtures("golden")
def test_regolden_exits_non_zero_naming_the_lost_ids(monkeypatch, capsys):
    class _Pytest:
        @staticmethod
        def main(_args):
            monkeypatch.setattr(diff, "RECORDED", {STEM: {"one": (0, "x2", "")}})
            return 0

    monkeypatch.setitem(sys.modules, "pytest", _Pytest)
    monkeypatch.setattr(regolden, "modules_naming", lambda _twin: ["m"])
    monkeypatch.setattr(regolden.os, "chdir", lambda _p: None)
    monkeypatch.setattr(diff, "golden_stem", lambda _twin: STEM)
    # regolden.main sets REDIACC_CI_REGOLDEN process-wide; setenv first so the monkeypatch undo removes it again (39f2a137.2).
    monkeypatch.setenv("REDIACC_CI_REGOLDEN", "")
    argv = [TWIN, "--source", "port", "--reason", "r"]
    assert regolden.main(argv) == 1
    err = capsys.readouterr().err
    assert "two" in err
    assert "--allow-shrink" in err
    assert regolden.main([*argv, "--allow-shrink"]) == 0
    assert os.environ["REDIACC_CI_REGOLDEN"] == "port"
