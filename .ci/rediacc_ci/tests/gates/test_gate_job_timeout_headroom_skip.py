"""`check_job_timeout_headroom.refresh()` skips a run whose jobs stay unreadable on a server fault (2026-11-11: run 36670172984 answered HTTP 502 on every attempt and blocked every lane-durations refresh), names it on stderr, and still fails on a 4xx or when too few runs remain.

`gh_retry.gh` is replaced by a fake that answers per run, so no network and no backoff sleep is involved; `gh_retry.is_transient` stays the real classifier.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import ghx

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT = paths.from_root(".ci/scripts/quality/check_job_timeout_headroom.py")
BAD = "36670172984"
JOBS = "Validate Promotion\t2026-09-01T00:00:00Z\t2026-09-01T00:%02d:00Z\n"
ERR_502 = "gh: Server Error (HTTP 502)"


def _load():
    hop = paths.on_sys_path(SCRIPT.parent)
    try:
        spec = importlib.util.spec_from_file_location("headroom_under_test", SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(hop)


def _baseline(tmp_path: Path) -> Path:
    path = tmp_path / "lane-durations.json"
    path.write_text(
        json.dumps(
            {
                "job_max_seconds": {
                    "refreshed_at": None,
                    "jobs": {"Validate Promotion": {"observed_max_seconds": 1, "samples": 1}},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _fake(monkeypatch, mod, run_ids, failures: dict[str, str]):
    """`failures` maps a run id to the stderr its jobs read answers with (exit 1)."""

    def fake_gh(args, **_kw):
        if args[:2] == ["run", "list"]:
            return ghx.GhResult(args, 0, "\n".join(run_ids) + "\n", "")
        run_id = args[1].split("/runs/")[1].split("/")[0]
        if run_id in failures:
            return ghx.GhResult(args, 1, "", failures[run_id])
        minutes = 10 + int(run_id[-1])
        return ghx.GhResult(args, 0, JOBS % minutes, "")

    monkeypatch.setattr(mod.gh_retry, "gh", fake_gh)


def test_a_502_run_is_skipped_named_and_the_rest_are_measured(tmp_path, monkeypatch, capsys):
    mod = _load()
    path = _baseline(tmp_path)
    _fake(monkeypatch, mod, ["111", BAD, "113"], {BAD: ERR_502})
    assert mod.refresh(path, 3) == 0
    err = capsys.readouterr().err
    assert "skipped run %s: jobs unreadable after 3 attempts: %s" % (BAD, ERR_502) in err
    rec = json.loads(path.read_text())["job_max_seconds"]["jobs"]["Validate Promotion"]
    assert rec["observed_max_seconds"] == 13 * 60  # the readable maximum, not the old 1
    assert rec["samples"] == 2


def test_control_a_401_still_fails_the_refresh(tmp_path, monkeypatch, capsys):
    mod = _load()
    path = _baseline(tmp_path)
    before = path.read_text()
    _fake(monkeypatch, mod, ["111", BAD, "113"], {BAD: "gh: Bad credentials (HTTP 401)"})
    assert mod.refresh(path, 3) == 1
    assert "refresh could not read the jobs of run %s" % BAD in capsys.readouterr().err
    assert path.read_text() == before


def test_control_every_run_unreadable_fails(tmp_path, monkeypatch, capsys):
    mod = _load()
    path = _baseline(tmp_path)
    before = path.read_text()
    _fake(monkeypatch, mod, ["111", BAD], {"111": ERR_502, BAD: ERR_502})
    assert mod.refresh(path, 2) == 1
    err = capsys.readouterr().err
    assert err.count("skipped run") == 2
    assert "read the jobs of only 0 of 2 run(s)" in err
    assert path.read_text() == before
