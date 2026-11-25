"""wl_ci hands the red's category to the long-red ledger: it reaches the row, a classifier failure is named, and a round whose category is not read yet is not recorded.

Each case is paired with a control on the normal path.
"""

from __future__ import annotations

import types
from typing import Any

import pytest
import wl_ci
import wl_longred as L

TIP = "a" * 40
CLASSIFIED = ("infra-likely", "github-api-5xx")
INFO = {"pr": 5, "contexts": [{"name": "E2E", "conclusion": "FAILURE"}]}


@pytest.fixture(autouse=True)
def _private_tmp(monkeypatch, tmp_path):
    """wl_longred's flock sidecar lives under $TMPDIR; keep it out of the shared one."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))


class Fetch:
    def json(self, _path):
        return {"status": "completed"}, ""


def _diag(classify):
    return types.SimpleNamespace(
        DOWNSTREAM_JOBS=(),
        job_log=lambda _f, _k, **_kw: ("log", ""),
        failing_step_slice=lambda _log, _job: ("step", "slice"),
        classify=classify,
    )


def _split(monkeypatch, classify, lookups=None, carried=({"g": ["k"]}, "")):
    monkeypatch.setattr(wl_ci, "carried_at", lambda _r, _t: carried)
    monkeypatch.setattr(
        wl_ci, "judge_job_carry", lambda *_a: {"verdict": "real", "why": "x", "keys": []}
    )
    if lookups is not None:
        monkeypatch.setattr(wl_ci, "CI_CARRY_LOOKUPS", lookups)
    cache: dict[str, Any] = {}
    real, _carried = wl_ci.ci_carry_split(
        "/nowhere",
        {},
        TIP,
        [{"name": "E2E", "job": "11"}],
        cache,
        diag=_diag(classify),
        fetch=Fetch(),
    )
    return real, cache


def _boom(_text):
    raise RuntimeError("classifier-boom")


# ---- the category reaches the row and the ledger ----


def test_the_category_reaches_the_red_row_and_the_ledger(monkeypatch, tmp_path):
    real, cache = _split(monkeypatch, lambda _t: CLASSIFIED)
    assert (real[0]["category"], real[0]["signature"]) == CLASSIFIED
    assert cache["_cat"]["11"] == list(CLASSIFIED)
    wl_ci.ci_longred(tmp_path, dict(INFO), TIP, real)
    reds = L.read_rows(tmp_path, 5)[-1]["reds"]
    assert reds == [{"check": "E2E", "category": "infra-likely", "signature": "github-api-5xx"}]


def test_a_classifier_failure_is_named_in_the_row_signature(monkeypatch):
    real, cache = _split(monkeypatch, _boom)
    assert real[0]["category"] == "unknown"
    assert "classify-failed: RuntimeError: classifier-boom" in real[0]["signature"]
    assert "11" not in cache.get("_cat", {})


def test_control_a_classifier_that_works_names_no_failure(monkeypatch):
    real, _cache = _split(monkeypatch, lambda _t: CLASSIFIED)
    assert "classify-failed" not in real[0]["signature"]


# ---- a round whose category is unread is held back ----


def test_a_spent_carry_budget_holds_the_round_back(monkeypatch, tmp_path):
    real, _cache = _split(monkeypatch, lambda _t: CLASSIFIED, lookups=0)
    assert real[0]["category_pending"] is True
    wl_ci.ci_longred(tmp_path, dict(INFO), TIP, real)
    assert L.read_rows(tmp_path, 5) == []


def test_an_unreadable_carry_file_names_the_unread_category(monkeypatch, tmp_path):
    real, _cache = _split(monkeypatch, lambda _t: CLASSIFIED, carried=(None, "no file"))
    assert real[0]["signature"] == "category-unread: no file"
    assert "category" not in real[0]
    wl_ci.ci_longred(tmp_path, dict(INFO), TIP, real)
    red = L.read_rows(tmp_path, 5)[-1]["reds"][0]
    assert (red["category"], red["signature"]) == ("unknown", "category-unread: no file")


def test_control_a_read_category_is_never_pending(monkeypatch, tmp_path):
    real, _cache = _split(monkeypatch, lambda _t: CLASSIFIED)
    assert not real[0].get("category_pending")
    wl_ci.ci_longred(tmp_path, dict(INFO), TIP, real)
    assert len(L.read_rows(tmp_path, 5)) == 1
