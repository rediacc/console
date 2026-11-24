"""The landing reads' gh sidecars (agent/plans/PLAN-tooling-speed.md SP8).

A development tree whose landing PR had merged asked gh three times per stop for the merge commit and the release (wl_prscope.landing_released), and once more whether the landing branch's PR merged (wl_stack.gh_pr_merged): 3.6 s of a 9.7 s stop on 2026-11-24. The merge commit and a merged answer are kept for good, a release verdict for RELEASE_VERDICT_TTL_S; a failed read is never kept, and a caller's `gh` seam always asks.
"""

from __future__ import annotations

from typing import Any

import pytest

from rediacc_hooks.tests import wlfix

PS = wlfix.import_wl("wl_prscope")
WS = wlfix.import_wl("wl_stack")
GH = wlfix.import_wl("wl_gh")


def _merged(number=12):
    return [{"state": "MERGED", "number": number, "body": ""}]


@pytest.fixture
def counted(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    calls = {"sha": 0, "release": 0}
    answer = {"verdict": PS.CI_GREEN, "err": ""}

    def merged_sha(_top, _pr, _gh=None):
        calls["sha"] += 1
        return "abc123", ""

    def read_release(_top, _sha, _gh=None):
        calls["release"] += 1
        return answer["verdict"], "", answer["err"]

    monkeypatch.setattr(PS, "merged_sha", merged_sha)
    monkeypatch.setattr(PS, "read_release", read_release)
    monkeypatch.setattr(PS, "landing_pr", lambda _nodes: ("MERGED", 12, ""))
    return calls, answer


def test_a_fresh_verdict_is_served_without_gh(counted):
    calls, _answer = counted
    assert PS.landing_released("/top", _merged()) == 12
    assert PS.landing_released("/top", _merged()) == 12
    assert calls == {"sha": 1, "release": 1}


def test_a_stale_verdict_rereads_the_release_but_not_the_merge_commit(counted, monkeypatch):
    calls, answer = counted
    PS.landing_released("/top", _merged())
    monkeypatch.setattr(PS, "RELEASE_VERDICT_TTL_S", -1)
    answer["verdict"] = PS.CI_RED
    assert PS.landing_released("/top", _merged()) == 0
    assert calls == {"sha": 1, "release": 2}


def test_a_verdict_stamped_in_the_future_is_reread(counted, monkeypatch):
    """6fcda58e.2: a clock stepped back leaves a stamp ahead of now; the entry is not fresh. The unstepped clock is the control (test_a_fresh_verdict_is_served_without_gh)."""
    calls, _answer = counted
    PS.landing_released("/top", _merged())
    real = PS.time.time
    monkeypatch.setattr(PS.time, "time", lambda: real() - 3600)
    assert PS.landing_released("/top", _merged()) == 12
    assert calls == {"sha": 1, "release": 2}


def test_a_sidecar_owned_by_another_user_is_not_read(tmp_path, monkeypatch):
    """6fcda58e.3: the cache reads only its own user's file; the same file read as its owner is the control."""
    path = tmp_path / "side.json"
    path.write_text('{"k": true}', encoding="utf-8")
    assert GH.cache_load(path) == {"k": True}
    monkeypatch.setattr(GH.os, "getuid", lambda: GH.os.lstat(path).st_uid + 1)
    assert GH.cache_load(path) is None


def test_control_a_failed_release_read_is_not_kept(counted):
    calls, answer = counted
    answer["err"] = "fixture: HTTP 502"
    assert PS.landing_released("/top", _merged()) == PS.UNREADABLE_RELEASE
    answer["err"] = ""
    assert PS.landing_released("/top", _merged()) == 12
    assert calls["release"] == 2


def test_control_a_gh_seam_always_asks(counted):
    calls, _answer = counted
    PS.landing_released("/top", _merged(), gh=lambda *_a: (None, ""))
    PS.landing_released("/top", _merged(), gh=lambda *_a: (None, ""))
    assert calls["release"] == 2


def test_a_merged_answer_is_kept_and_a_no_is_not(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    seen = []
    answer: list[Any] = [[]]

    def call(argv, _cwd=None, **_k):
        seen.append(argv)
        return answer[0], ""

    monkeypatch.setattr(GH, "call", call)
    assert WS.gh_pr_merged("/root", "1104-1") is False
    assert WS.gh_pr_merged("/root", "1104-1") is False
    assert len(seen) == 2
    answer[0] = [{"number": 7}]
    assert WS.gh_pr_merged("/root", "1104-1") is True
    assert WS.gh_pr_merged("/root", "1104-1") is True
    assert len(seen) == 3
    # CONTROL: another branch still asks.
    answer[0] = []
    assert WS.gh_pr_merged("/root", "1105-1") is False
    assert len(seen) == 4
