"""`rediacc_ci.ci.gate_costs` (PLAN-ci-quick-cpu-scheduling 2.5, P3): the per-gate CPU baseline built from the nightly `gate-costs-<sha>` captures.

FIXTURE-DRIVEN, NO NETWORK. Captures are run.ts `--json` reports built in-test; `collect_captures` is driven through its injectable `list_runs`/`list_artifacts`/`download`, and `refresh`/`check` through their `collect` seam, so nothing here calls `gh`.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.ci import gate_costs as gc

if TYPE_CHECKING:
    from pathlib import Path


def gate(
    gid: str, cpu_ms: float | None, ms: float, status: str = "ok", rss: float | None = None
) -> dict[str, Any]:
    g: dict[str, Any] = {"id": gid, "gate": True, "status": status, "ms": ms}
    if cpu_ms is not None:
        g["cpuMs"] = cpu_ms
    if rss is not None:
        g["rssMb"] = rss
    return g


def capture(gates: list[dict[str, Any]], cores: int | None = 4) -> dict[str, Any]:
    util = None if cores is None else {"cores": cores}
    return {"jobs": 1, "wallMs": 1, "utilisation": util, "gates": gates}


def write_lock(root: Path, ids: list[str]) -> None:
    lock = root / gc.GATES_LOCK_REL_PATH
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps([{"id": i, "run": "true", "gate": True} for i in ids]), encoding="utf-8"
    )


def baseline_from(captures: list[dict[str, Any]]) -> dict[str, Any]:
    return gc.build_baseline(captures, [{"id": 1}], None, "2026-10-01T00:00:00Z")


# --------------------------------------------------------------------------- aggregate ---------------------------------------------------------------------------


def test_medians_over_passing_measured_runs_only():
    caps = [
        capture([gate("a", 2000, 1000, rss=100)]),
        capture([gate("a", 4000, 2000, rss=300)]),
        capture([gate("a", 3000, 1500, rss=200)]),
        capture([gate("a", 99000, 99000, status="fail")]),
        capture([gate("a", None, 1000)]),
    ]
    rec = gc.aggregate(caps)["gates"]["a"]
    assert rec["cpu_s"] == 3.0
    assert rec["wall_s"] == 1.5
    assert rec["eff_cores"] == 2.0
    assert rec["peak_rss_mb"] == 200
    assert rec["capped"] is False


def test_rank_is_ordinal_of_cpu_s_largest_first():
    caps = [capture([gate("small", 500, 1000), gate("big", 9000, 3000), gate("mid", 2000, 2000)])]
    gates = gc.aggregate(caps)["gates"]
    assert [gates[g]["rank"] for g in ("big", "mid", "small")] == [1, 2, 3]


def test_capped_at_ninety_percent_of_runner_cores():
    caps = [capture([gate("wide", 3600, 1000), gate("narrow", 3500, 1000)], cores=4)]
    gates = gc.aggregate(caps)["gates"]
    assert gates["wide"]["capped"] is True
    assert gates["narrow"]["capped"] is False, "CONTROL: 3.5 of 4 cores is under the 0.9 line"


def test_capped_is_false_without_a_core_count():
    gates = gc.aggregate([capture([gate("wide", 8000, 1000)], cores=None)])["gates"]
    assert gates["wide"]["capped"] is False


def test_unmeasured_gates_are_named_with_their_newest_status():
    caps = [
        capture([gate("x", None, 10, status="blocked")]),
        capture([gate("x", None, 10, status="fail")]),
    ]
    agg = gc.aggregate(caps)
    assert agg["gates"] == {}
    assert agg["unmeasured"] == {"x": "blocked"}


def test_parse_capture_refuses_a_report_without_gates():
    with pytest.raises(TypeError, match="no `gates` list"):
        gc.parse_capture('{"partial": false}')
    assert gc.parse_capture(json.dumps(capture([])))["gates"] == []


# --------------------------------------------------------------------------- check_findings ---------------------------------------------------------------------------


def _drifted(cpu_factor: float, wall_factor: float = 1.0, cores: int = 4) -> list[str]:
    committed = baseline_from([capture([gate("g", 10000, 10000)], cores=cores)])
    fresh = gc.aggregate(
        [capture([gate("g", 10000 * cpu_factor, 10000 * wall_factor)], cores=cores)]
    )
    return gc.check_findings(committed, fresh, {"g"})


def test_drift_24_percent_passes():
    assert _drifted(1.24, 1.24) == []


def test_drift_26_percent_reds():
    findings = _drifted(1.26, 1.26)
    assert len(findings) == 1
    assert "cpu_s" in findings[0]


def test_uncapped_eff_cores_drift_reds():
    findings = _drifted(1.0, 0.7)
    assert len(findings) == 1
    assert "eff_cores" in findings[0]


def test_capped_eff_cores_drift_is_ignored():
    committed = baseline_from([capture([gate("g", 40000, 10000)], cores=4)])
    fresh = gc.aggregate([capture([gate("g", 40000, 14000)], cores=4)])
    assert committed["gates"]["g"]["capped"] is True
    assert gc.check_findings(committed, fresh, {"g"}) == []
    # CONTROL: the same wall change on an uncapped gate is a finding.
    committed = baseline_from([capture([gate("g", 20000, 10000)], cores=4)])
    fresh = gc.aggregate([capture([gate("g", 20000, 14000)], cores=4)])
    assert any("eff_cores" in f for f in gc.check_findings(committed, fresh, {"g"}))


def test_sub_second_cpu_drift_is_not_judged():
    committed = baseline_from([capture([gate("g", 400, 1000)])])
    fresh = gc.aggregate([capture([gate("g", 800, 1000)])])
    assert gc.check_findings(committed, fresh, {"g"}) == []


def test_gate_absent_from_the_manifest_is_reported():
    committed = baseline_from([capture([gate("gone", 2000, 2000), gate("kept", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("kept", 2000, 2000)])])
    findings = gc.check_findings(committed, fresh, {"kept"})
    assert len(findings) == 1
    assert "'gone'" in findings[0]
    assert "not in the manifest" in findings[0]


def test_new_gate_missing_from_the_file_is_reported():
    committed = baseline_from([capture([gate("old", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("old", 2000, 2000), gate("new", 2000, 2000)])])
    findings = gc.check_findings(committed, fresh, {"old", "new"})
    assert len(findings) == 1
    assert "'new'" in findings[0]
    assert "missing from" in findings[0]


def test_known_unmeasured_gate_is_not_new():
    committed = baseline_from(
        [capture([gate("old", 2000, 2000), gate("sub", None, 5, status="fail")])]
    )
    fresh = gc.aggregate([capture([gate("old", 2000, 2000), gate("sub", None, 5, status="fail")])])
    assert gc.check_findings(committed, fresh, {"old", "sub"}) == []


def test_baseline_gate_no_longer_measured_is_reported():
    committed = baseline_from([capture([gate("g", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("g", None, 5, status="fail")])])
    findings = gc.check_findings(committed, fresh, {"g"})
    assert len(findings) == 1
    assert "no capture measured it (fail" in findings[0]


def test_changed_runner_cores_is_reported():
    committed = baseline_from([capture([gate("g", 2000, 2000)], cores=4)])
    fresh = gc.aggregate([capture([gate("g", 2000, 2000)], cores=2)])
    assert any("runner cores changed" in f for f in gc.check_findings(committed, fresh, {"g"}))


# --------------------------------------------------------------------------- check / refresh ---------------------------------------------------------------------------


def _collect(caps: list[dict[str, Any]]):
    return lambda _repo: (caps, [{"id": 7, "sha": "abc", "created_at": "2026-10-01T03:00:00Z"}], [])


def test_missing_file_is_a_notice_not_a_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    def never(_repo: str):
        raise AssertionError("no baseline means nothing to compare, so no capture is read")

    rc = gc.check(tmp_path / "gate-costs.json", "o/r", tmp_path, collect=never)
    assert rc == gc.NO_BASELINE
    assert rc not in (0, 1)
    assert "NOT CHECKED" in capsys.readouterr().out


def test_check_green_then_red_end_to_end(tmp_path: Path):
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    assert gc.refresh(target, "o/r", collect=_collect([capture([gate("g", 10000, 10000)])])) == 0
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["source"] == {
        "runner": "ubuntu-latest",
        "cores": 4,
        "runs": [{"id": 7, "sha": "abc", "created_at": "2026-10-01T03:00:00Z"}],
    }
    assert written["$comment"] == gc.DEFAULT_COMMENT
    assert (
        gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 12400, 12400)])]))
        == 0
    )
    assert (
        gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 12600, 12600)])]))
        == 1
    )


def test_check_reds_on_zero_captures(tmp_path: Path):
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    target.write_text(
        json.dumps(baseline_from([capture([gate("g", 2000, 2000)])])), encoding="utf-8"
    )
    assert gc.check(target, "o/r", tmp_path, collect=_collect([])) == 1


def test_refresh_preserves_comment_and_refuses_without_captures(tmp_path: Path):
    target = tmp_path / "gate-costs.json"
    target.write_text(json.dumps({"$comment": ["kept"]}), encoding="utf-8")
    assert gc.refresh(target, "o/r", collect=_collect([])) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"$comment": ["kept"]}
    assert gc.refresh(target, "o/r", collect=_collect([capture([gate("g", 1, 1)])])) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["$comment"] == ["kept"]


# --------------------------------------------------------------------------- collect_captures ---------------------------------------------------------------------------


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


def test_collect_captures_takes_newest_live_artifacts_up_to_limit():
    runs = {
        "schedule": [
            {"id": 3, "head_sha": "c", "created_at": "2026-10-03"},
            {"id": 1, "head_sha": "a", "created_at": "2026-10-01"},
        ],
        "workflow_dispatch": [{"id": 2, "head_sha": "b", "created_at": "2026-10-02"}],
    }
    artifacts = {
        3: [{"id": 30, "name": "gate-costs-c", "expired": True}],
        2: [{"id": 20, "name": "other"}, {"id": 21, "name": "gate-costs-b"}],
        1: [{"id": 10, "name": "gate-costs-a"}],
    }
    blobs = {21: _zip("gate-costs.json", json.dumps(capture([gate("b", 1, 1)]))), 10: b"not a zip"}
    caps, sources, warnings = gc.collect_captures(
        "o/r",
        limit=5,
        list_runs=lambda _repo, wf, event, *_a: runs[event] if wf == gc.CAPTURE_WORKFLOW else [],
        list_artifacts=lambda _repo, run_id: artifacts[run_id],
        download=lambda _repo, aid: blobs[aid],
    )
    assert [s["id"] for s in sources] == [2]
    assert caps[0]["gates"][0]["id"] == "b"
    assert len(warnings) == 1
    assert "run 1" in warnings[0]


# --------------------------------------------------------------------------- the workflow's two entry points ---------------------------------------------------------------------------


def test_check_report_to_appends_only_a_failing_verdict(tmp_path: Path):
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    summary = tmp_path / "budget-check.txt"
    summary.write_text("budget: green\n", encoding="utf-8")
    gc.refresh(target, "o/r", collect=_collect([capture([gate("g", 10000, 10000)])]))
    ok = gc.check(
        target,
        "o/r",
        tmp_path,
        collect=_collect([capture([gate("g", 10000, 10000)])]),
        report_to=summary,
    )
    assert ok == 0
    assert summary.read_text(encoding="utf-8") == "budget: green\n"
    red = gc.check(
        target,
        "o/r",
        tmp_path,
        collect=_collect([capture([gate("g", 20000, 20000)])]),
        report_to=summary,
    )
    assert red == 1
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("budget: green\n")
    assert "gate_costs --check" in text
    assert "'g' cpu_s" in text


def test_validate_capture(tmp_path: Path):
    report = tmp_path / "gate-costs.json"
    report.write_text(
        json.dumps(capture([gate("a", 1000, 1000), gate("b", None, 5, "fail")])), encoding="utf-8"
    )
    assert gc.validate_capture(report) == 0
    report.write_text(json.dumps(capture([gate("b", None, 5, "fail")])), encoding="utf-8")
    assert gc.validate_capture(report) == 1, "a capture that measured nothing is refused"
    report.write_text("", encoding="utf-8")
    assert gc.validate_capture(report) == 1, "an empty report (run.ts refused a flag) is refused"
    assert gc.validate_capture(tmp_path / "absent.json") == 1
