"""The five check scripts' GitHub reads go through `gh_retry` and a read that never answers fails loudly (PLAN-gh-retry G12)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.core import ghx

if TYPE_CHECKING:
    from pathlib import Path

QUALITY = paths.from_root(".ci/scripts/quality")


def _load(name: str):
    hop = paths.on_sys_path(QUALITY)
    try:
        spec = importlib.util.spec_from_file_location(name, QUALITY / f"{name}.py")
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(hop)


def _fake(monkeypatch, mod, results):
    """Replace the one-attempt gh call; `results` is consumed one per attempt."""
    calls: list[list[str]] = []
    queue = list(results)

    def runner(args, **_kw):
        calls.append(list(args))
        rc, out, err = queue.pop(0) if len(queue) > 1 else queue[0]
        return ghx.GhResult(["gh", *args], rc, out, err)

    monkeypatch.setattr(ghx, "gh", runner)
    monkeypatch.setattr(mod.gh_retry.time, "sleep", lambda _s: None)
    return calls


def test_actions_allowlist_refresh_retries_a_502_then_writes(monkeypatch, tmp_path: Path):
    mod = _load("check_actions_allowlist")
    live = {"github_owned_allowed": True, "verified_allowed": False, "patterns_allowed": ["a/b@*"]}
    calls = _fake(
        monkeypatch,
        mod,
        [(1, "", "gh: Server Error (HTTP 502)"), (0, json.dumps(live), "")],
    )
    record = tmp_path / "rec.json"
    record.write_text("{}", encoding="utf-8")
    assert mod.refresh(record) == 0
    assert len(calls) == 2
    assert json.loads(record.read_text())["patterns_allowed"] == ["a/b@*"]


def test_actions_allowlist_refresh_fails_at_once_on_a_404(monkeypatch, tmp_path: Path):
    mod = _load("check_actions_allowlist")
    calls = _fake(monkeypatch, mod, [(1, "", "gh: Not Found (HTTP 404)")])
    record = tmp_path / "rec.json"
    record.write_text("{}", encoding="utf-8")
    assert mod.refresh(record) == 1
    assert len(calls) == 1
    assert record.read_text() == "{}"


def test_session_archival_merged_at_cannot_run_after_retries(monkeypatch):
    mod = _load("check_agent_session_archival")
    calls = _fake(monkeypatch, mod, [(1, "", "gh: Bad Gateway (HTTP 502)")])
    with pytest.raises(mod.CannotRunError):
        mod._gh_merged_at("0101-1")
    assert len(calls) == 3


def test_session_archival_merged_at_reads_after_a_blip(monkeypatch):
    mod = _load("check_agent_session_archival")
    body = json.dumps([{"mergedAt": "2026-10-01T00:00:00Z"}])
    calls = _fake(monkeypatch, mod, [(1, "", "connection reset by peer"), (0, body, "")])
    assert mod._gh_merged_at("0101-1") is not None
    assert len(calls) == 2


def test_job_timeout_refresh_fails_loudly_and_leaves_the_file(monkeypatch, tmp_path: Path):
    mod = _load("check_job_timeout_headroom")
    _fake(monkeypatch, mod, [(1, "", "gh: Service Unavailable (HTTP 503)")])
    lane = tmp_path / "lane.json"
    lane.write_text("{}", encoding="utf-8")
    assert mod.refresh(lane, 5) == 1
    assert lane.read_text() == "{}"


def test_runner_advice_gh_json_raises_rather_than_reading_empty(monkeypatch):
    mod = _load("check_runner_advice")
    _fake(monkeypatch, mod, [(1, "", "gh: Server Error (HTTP 500)")])
    with pytest.raises(ghx.GhError):
        mod.gh_json(["api", "x"])


def test_runner_advice_gh_json_retries_then_splits_lines(monkeypatch):
    mod = _load("check_runner_advice")
    _fake(monkeypatch, mod, [(1, "", "HTTP 502"), (0, "1\n2\n", "")])
    assert mod.gh_json(["api", "x"]) == ["1", "2"]


def test_secret_reachability_refresh_does_not_read_a_failed_listing_as_empty(
    monkeypatch, tmp_path: Path
):
    # The refresh never parses YAML before the listing read; a runner without PyYAML gets an inert stand-in.
    if importlib.util.find_spec("yaml") is None:
        monkeypatch.setitem(sys.modules, "yaml", types.ModuleType("yaml"))
    mod = _load("check_secret_reachability")
    _fake(monkeypatch, mod, [(1, "", "gh: Server Error (HTTP 500)")])
    assert mod.refresh(tmp_path, tmp_path / "b.json") == 1
    assert not (tmp_path / "b.json").exists()
