"""`differential.write_recorded` stamps the golden header's `source` truthfully (review finding 8422dd2f.1)."""

from __future__ import annotations

import pytest

from rediacc_ci.tests import differential as diff

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
