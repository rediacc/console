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


def lock_entries(
    ids: list[str], slow: tuple[str, ...] = (), needs: dict[str, list[str]] | None = None
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for i in ids:
        e: dict[str, Any] = {"id": i, "run": "true", "gate": True}
        if i in slow:
            e["slow"] = True
        if needs and i in needs:
            e["needs"] = needs[i]
        entries.append(e)
    return entries


def write_lock(
    root: Path,
    ids: list[str],
    slow: tuple[str, ...] = (),
    needs: dict[str, list[str]] | None = None,
) -> None:
    lock = root / gc.GATES_LOCK_REL_PATH
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps(lock_entries(ids, slow, needs)), encoding="utf-8")


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
    assert (
        gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))
        == 0
    )
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
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    target.write_text(json.dumps({"$comment": ["kept"]}), encoding="utf-8")
    assert gc.refresh(target, "o/r", tmp_path, collect=_collect([])) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"$comment": ["kept"]}
    assert gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 1, 1)])])) == 0
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


def test_check_writes_no_report_and_reds_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """`rediacc_ci.ci.freshness --check --report-to` is the one writer of housekeeping's report (PLAN-ci-consolidation T8), so gate_costs has no `--report-to` and its failing verdict goes to stderr for freshness to capture."""
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))
    capsys.readouterr()
    red = gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 20000, 20000)])]))
    assert red == 1
    err = capsys.readouterr().err
    assert "Gate cost baseline check found 1 issue(s)" in err
    assert "'g' cpu_s" in err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["gate-costs.json", "scripts"], (
        "check wrote a file beside the baseline"
    )
    with pytest.raises(SystemExit) as exc:
        gc.main(["--check", "--report-to", str(tmp_path / "budget-check.txt")])
    assert exc.value.code == 2, "--report-to must be refused by argparse: freshness owns the report"
    assert not (tmp_path / "budget-check.txt").exists()


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


# --------------------------------------------------------------------------- diff-sampled (slow) gates ---------------------------------------------------------------------------
#
# FIRES-if-unfixed, MEASURED 2026-10-07. The capture is `run.ts --quick`, which runs every fast gate and ONLY the slow gates the captured commit's diff touches (run.ts quickDiffAdmit; capture 37294996911 reads "--quick (286 fast gate(s) + 3 diff-selected slow; 66 deferred)"). check:ci-format-scope (slow) entered the baseline from capture 37192382851, whose diff touched it, and every PR went red with "has a baseline but no capture measured it (absent in the newest)" once that capture left the window. 365933af3 was the same red for check:ci-proxy-rdc-update.


def test_sampled_gates_are_the_slow_fixpoint_over_needs():
    entries = lock_entries(
        ["fast", "slow", "dep", "depdep"],
        slow=("slow",),
        needs={"dep": ["slow"], "depdep": ["dep"]},
    )
    assert gc.sampled_gate_ids(entries) == {"slow", "dep", "depdep"}
    assert gc.sampled_gate_ids(lock_entries(["fast"])) == set(), (
        "CONTROL: no slow gate, nothing sampled"
    )


def test_slow_gate_no_capture_ran_is_not_a_finding():
    committed = baseline_from([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("q", 2000, 2000)])])
    assert gc.check_findings(committed, fresh, {"q", "s"}, sampled={"s"}) == []
    # CONTROL: the same absence on a gate every capture runs is still red.
    findings = gc.check_findings(committed, fresh, {"q", "s"}, sampled=set())
    assert len(findings) == 1
    assert "'s'" in findings[0]
    assert "no capture measured it" in findings[0]


def test_slow_gate_a_capture_ran_but_could_not_measure_still_reds():
    committed = baseline_from([capture([gate("s", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("s", None, 5, status="fail")])])
    findings = gc.check_findings(committed, fresh, {"s"}, sampled={"s"})
    assert len(findings) == 1
    assert "no capture measured it (fail" in findings[0]


def test_slow_gate_removed_from_the_manifest_still_reds():
    committed = baseline_from([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("q", 2000, 2000)])])
    findings = gc.check_findings(committed, fresh, {"q"}, sampled=set())
    assert len(findings) == 1
    assert "not in the manifest" in findings[0]


def test_slow_gate_newly_seen_is_not_new_but_a_fast_one_is():
    committed = baseline_from([capture([gate("q", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])
    assert gc.check_findings(committed, fresh, {"q", "s"}, sampled={"s"}) == []
    findings = gc.check_findings(committed, fresh, {"q", "s"}, sampled=set())
    assert len(findings) == 1, "CONTROL: a fast gate the captures ran is registered-after-refresh"
    assert "missing from" in findings[0]


def test_slow_gate_drift_is_still_judged_when_sampled():
    committed = baseline_from([capture([gate("s", 10000, 10000)])])
    fresh = gc.aggregate([capture([gate("s", 20000, 20000)])])
    findings = gc.check_findings(committed, fresh, {"s"}, sampled={"s"})
    assert len(findings) == 1
    assert "'s' cpu_s" in findings[0]


def test_sampling_notes_name_every_unsampled_and_pending_gate():
    committed = baseline_from([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("q", 2000, 2000), gate("t", 2000, 2000)])])
    notes = gc.sampling_notes(committed, fresh, {"q", "s", "t"}, {"s", "t"})
    assert notes["not_sampled"] == ["s"]
    assert notes["pending"] == ["t"]


def test_check_end_to_end_slow_gate_absent_is_green_and_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    write_lock(tmp_path, ["q", "s"], slow=("s",))
    target = tmp_path / "gate-costs.json"
    target.write_text(
        json.dumps(baseline_from([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])),
        encoding="utf-8",
    )
    assert (
        gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("q", 2000, 2000)])])) == 0
    )
    out = capsys.readouterr().out
    assert "1 diff-sampled gate(s) not in this window: s" in out
    # CONTROL: the same tree with s registered as a fast gate is red.
    write_lock(tmp_path, ["q", "s"])
    assert (
        gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("q", 2000, 2000)])])) == 1
    )


def test_refresh_carries_a_slow_gate_the_window_missed(tmp_path: Path):
    write_lock(tmp_path, ["q", "s", "f", "gone"], slow=("s",))
    target = tmp_path / "gate-costs.json"
    prior = gc.build_baseline(
        [
            capture(
                [
                    gate("q", 2000, 2000),
                    gate("s", 9000, 3000),
                    gate("f", 1500, 1500),
                    gate("gone", 1, 1),
                ]
            )
        ],
        [{"id": 1}],
        None,
        "2026-10-01T00:00:00Z",
    )
    target.write_text(json.dumps(prior), encoding="utf-8")
    write_lock(tmp_path, ["q", "s", "f"], slow=("s",))
    assert (
        gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("q", 4000, 2000)])]))
        == 0
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["gates"]["s"] == {**prior["gates"]["s"], "rank": 1}, (
        "the slow gate's figures are carried"
    )
    assert written["carried"] == {"s": "2026-10-01T00:00:00Z"}
    assert "f" not in written["gates"], (
        "CONTROL: a fast gate the captures stopped measuring is dropped"
    )
    assert "gone" not in written["gates"], "CONTROL: a gate the manifest dropped is not carried"
    assert written["gates"]["q"]["rank"] == 2
    # Carried again, the stamp keeps naming when the figure was measured, not the refresh that carried it.
    assert (
        gc.refresh(
            target,
            "o/r",
            tmp_path,
            collect=_collect([capture([gate("q", 4000, 2000)])]),
            now=lambda: "2026-10-09T00:00:00Z",
        )
        == 0
    )
    assert json.loads(target.read_text(encoding="utf-8"))["carried"] == {
        "s": "2026-10-01T00:00:00Z"
    }
    # Sampled again, it is measured, not carried.
    assert (
        gc.refresh(
            target,
            "o/r",
            tmp_path,
            collect=_collect([capture([gate("q", 4000, 2000), gate("s", 3000, 3000)])]),
        )
        == 0
    )
    again = json.loads(target.read_text(encoding="utf-8"))
    assert again["gates"]["s"]["cpu_s"] == 3.0
    assert again["carried"] == {}


def _gh404(*_a: Any) -> Any:
    raise gc.ghx.GhError(["gh", "api", "x"], 1, "gh: Not Found (HTTP 404)", gc.ghx.FAILURE_FAILED)


def test_collect_captures_passes_over_a_listed_run_github_answers_404_for(
    capsys: pytest.CaptureFixture[str],
):
    """FIRES-if-unfixed, MEASURED 2026-10-07: run 37192382851 (a source of the committed file) answers `Not Found (HTTP 404)` on its artifact list, and that GhError made the whole --check exit 1."""
    runs = [
        {"id": 2, "head_sha": "b", "created_at": "2026-10-02"},
        {"id": 1, "head_sha": "a", "created_at": "2026-10-01"},
    ]
    blob = _zip("gate-costs.json", json.dumps(capture([gate("a", 1, 1)])))

    def artifacts(_repo: str, run_id: int) -> list[dict[str, Any]]:
        if run_id == 2:
            _gh404()
        return [{"id": 10, "name": "gate-costs-a"}]

    caps, sources, warnings = gc.collect_captures(
        "o/r",
        list_runs=lambda _repo, _wf, event, *_a: runs if event == "schedule" else [],
        list_artifacts=artifacts,
        download=lambda _repo, _aid: blob,
    )
    assert [s["id"] for s in sources] == [1]
    assert warnings == []
    assert "run 2 is listed but GitHub answers 404" in capsys.readouterr().err
    # A deleted artifact is passed over the same way.
    caps, sources, _w = gc.collect_captures(
        "o/r",
        list_runs=lambda _repo, _wf, event, *_a: runs[1:] if event == "schedule" else [],
        list_artifacts=lambda _repo, _rid: [{"id": 10, "name": "gate-costs-a"}],
        download=_gh404,
    )
    assert caps == []


def test_collect_captures_still_raises_on_a_failure_that_is_not_404():
    def denied(*_a: Any) -> Any:
        raise gc.ghx.GhError(["gh"], 1, "HTTP 401: Bad credentials", gc.ghx.FAILURE_UNAUTHENTICATED)

    with pytest.raises(gc.ghx.GhError):
        gc.collect_captures(
            "o/r",
            list_runs=lambda _repo, _wf, event, *_a: (
                [{"id": 1, "created_at": "x"}] if event == "schedule" else []
            ),
            list_artifacts=denied,
            download=lambda *_a: b"",
        )


def test_a_single_capture_window_still_reds_a_fast_gate_it_could_not_measure(tmp_path: Path):
    """The window can collapse to one capture (2026-10-07: only 37294996911 is live). One capture is still evidence for every fast gate, since every capture runs every fast gate, so a fast gate that one capture failed is still red."""
    write_lock(tmp_path, ["q", "s"], slow=("s",))
    target = tmp_path / "gate-costs.json"
    target.write_text(
        json.dumps(baseline_from([capture([gate("q", 2000, 2000), gate("s", 2000, 2000)])])),
        encoding="utf-8",
    )
    one = [capture([gate("q", None, 5, status="fail")])]
    assert gc.check(target, "o/r", tmp_path, collect=_collect(one)) == 1
