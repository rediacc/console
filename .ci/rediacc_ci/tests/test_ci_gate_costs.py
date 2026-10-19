"""`rediacc_ci.ci.gate_costs` (PLAN-ci-quick-cpu-scheduling 2.5, P3): the per-gate CPU baseline built from the nightly `gate-costs-<sha>` captures.

FIXTURE-DRIVEN, NO NETWORK. Captures are run.ts `--json` reports built in-test; `collect_captures` is driven through its injectable `list_runs`/`list_artifacts`/`download`, and `refresh`/`check` through their `collect` seam, so nothing here calls `gh`.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import freshness as fr
from rediacc_ci.ci import gate_costs as gc
from rediacc_ci.quality import workflows

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


def twice(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """The same capture from two nights: the least evidence a drift verdict is given on (`MIN_DRIFT_CAPTURES`)."""
    return [cap] * gc.MIN_DRIFT_CAPTURES


def _drifted(
    cpu_factor: float, wall_factor: float = 1.0, cores: int = 4, nights: int = 2
) -> list[str]:
    committed = baseline_from([capture([gate("g", 10000, 10000)], cores=cores)])
    fresh = gc.aggregate(
        [capture([gate("g", 10000 * cpu_factor, 10000 * wall_factor)], cores=cores)] * nights
    )
    return gc.check_findings(committed, fresh, {"g"})


def test_drift_24_percent_passes():
    assert _drifted(1.24, 1.24) == []


def test_drift_26_percent_reds():
    findings = _drifted(1.26, 1.26)
    assert len(findings) == 1
    assert "cpu_s" in findings[0]


def test_one_capture_is_one_runner_and_judges_no_drift():
    """The window shrinks to one capture when a nightly capture fails or two age out. The same 26% and the same 30% width change that red on two captures are not judged on one."""
    assert _drifted(1.26, 1.26, nights=1) == []
    assert _drifted(1.0, 0.7, nights=1) == []
    # CONTROL: two captures that agree are a finding, in both figures.
    assert len(_drifted(1.26, 1.26, nights=2)) == 1
    assert len(_drifted(1.0, 0.7, nights=2)) == 1
    # CONTROL: a doubled gate is still not judged on one capture, and is named as unjudged.
    fresh = gc.aggregate([capture([gate("g", 20000, 20000)])])
    assert gc.thin_gates(fresh) == ["g"]
    assert gc.thin_gates(gc.aggregate(twice(capture([gate("g", 20000, 20000)])))) == []


# MEASURED 2026-10-13: the committed gate-costs.json (medians of captures 38129723990 and 38041991396) held against capture 38382535219 alone, cpu-seconds. Each was a drift finding on that one capture.
ONE_CAPTURE_REDS = {
    "check:ci-e2e-case-blind": (1.58, 1.15),
    "check:ci-env-manifest": (4.28, 3.2),
    "check:ci-python-control-plants": (2.77, 2.0),
}


def test_the_three_real_single_capture_reds_are_not_findings():
    committed = {
        "gates": {
            gid: {"cpu_s": was, "wall_s": was, "eff_cores": 1.0, "capped": False}
            for gid, (was, _now) in ONE_CAPTURE_REDS.items()
        },
        "unmeasured": {},
        "source": {"cores": 4},
    }
    newest = capture(
        [gate(g, now * 1000, now * 1000) for g, (_was, now) in ONE_CAPTURE_REDS.items()]
    )
    lock = set(ONE_CAPTURE_REDS)
    # Each move is past the 25% limit, which is all the retired rule asked of a gate of a cpu-second.
    for was, now in ONE_CAPTURE_REDS.values():
        assert abs(now - was) / was > gc.DRIFT_THRESHOLD
    assert gc.check_findings(committed, gc.aggregate([newest]), lock) == []
    # CONTROL: the same figures from two captures. The one move of a cpu-second is a finding; the two under it are not.
    findings = gc.check_findings(committed, gc.aggregate(twice(newest)), lock)
    assert _finding_keys(findings) == {"gate-costs:drift:cpu_s:check:ci-env-manifest"}


def test_a_refresh_keeps_the_figures_of_a_gate_one_capture_measured():
    prior = baseline_from(twice(capture([gate("kept", 10000, 10000), gate("moved", 10000, 10000)])))
    one = capture([gate("kept", 20000, 20000), gate("new", 3000, 3000)])
    two = [capture([gate("moved", 20000, 20000)]), capture([gate("moved", 20000, 20000)]), one]
    built = gc.build_baseline(two, [{"id": 2}], None, "2026-10-02T00:00:00Z", prior=prior)
    assert built["gates"]["kept"]["cpu_s"] == 10.0  # one capture: the committed figure stays
    assert built["gates"]["moved"]["cpu_s"] == 20.0  # CONTROL: two captures rewrite it
    assert (
        built["gates"]["new"]["cpu_s"] == 3.0
    )  # CONTROL: a gate new to the file is written at any count
    # And the check that follows that refresh on the same captures is green.
    assert gc.check_findings(built, gc.aggregate(two), {"kept", "moved", "new"}) == []


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
    fresh = gc.aggregate(twice(capture([gate("g", 20000, 14000)], cores=4)))
    assert any("eff_cores" in f for f in gc.check_findings(committed, fresh, {"g"}))


def test_sub_second_cpu_drift_is_not_judged():
    committed = baseline_from([capture([gate("g", 400, 1000)])])
    fresh = gc.aggregate(twice(capture([gate("g", 800, 1000)])))
    assert gc.check_findings(committed, fresh, {"g"}) == []


def test_gate_absent_from_the_manifest_is_reported():
    committed = baseline_from([capture([gate("gone", 2000, 2000), gate("kept", 2000, 2000)])])
    fresh = gc.aggregate([capture([gate("kept", 2000, 2000)])])
    findings = gc.check_findings(committed, fresh, {"kept"})
    assert len(findings) == 1
    assert "'gone'" in findings[0]
    assert "not in the manifest" in findings[0]


def test_a_refresh_keeps_only_the_manifest_gates_so_its_own_check_passes():
    """A capture from a run whose manifest still had a since-retired gate (2026-10-11: nine of them, read from main's runs) must not reach the refreshed file, or `--check` refuses the refresh's own output."""
    caps = [
        capture(
            [
                gate("kept", 2000, 2000),
                gate("retired", 2000, 2000),
                gate("gone-unmeasured", None, 5),
            ]
        )
    ]
    built = gc.build_baseline(
        caps, [{"id": 1}], None, "2026-10-01T00:00:00Z", prior={}, lock_ids={"kept"}, sampled=set()
    )
    assert set(built["gates"]) == {"kept"}
    assert "gone-unmeasured" not in built["unmeasured"]
    assert built["gates"]["kept"]["rank"] == 1
    assert gc.check_findings(built, gc.aggregate(caps), {"kept"}) == []


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
    under = _collect(twice(capture([gate("g", 12400, 12400)])))
    assert gc.check(target, "o/r", tmp_path, collect=under) == 0
    over = _collect(twice(capture([gate("g", 12600, 12600)])))
    assert gc.check(target, "o/r", tmp_path, collect=over) == 1


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


def test_sample_captures_fits_the_recorded_retention():
    """One nightly capture a day, and the repository keeps artifacts `days` days (.ci/config/actions-retention.json, the operator's 2026-10-07 "Keep 3 days"): a window larger than that names captures that cannot exist. Read from the record, so lowering the setting reds here until the window follows."""
    days, why = workflows.load_retention_days(paths.repo_root())
    assert days is not None, why
    assert 1 <= gc.SAMPLE_CAPTURES <= days


def test_collect_captures_defaults_to_sample_captures():
    """The default window stops at SAMPLE_CAPTURES even when more live captures are listed."""
    listed = [
        {"id": i, "head_sha": "s%d" % i, "created_at": "2026-10-0%d" % i}
        for i in range(1, gc.SAMPLE_CAPTURES + 3)
    ]
    blob = _zip("gate-costs.json", json.dumps(capture([gate("g", 1, 1)])))
    caps, sources, _warnings = gc.collect_captures(
        "o/r",
        list_runs=lambda _repo, _wf, event, *_a: listed if event == "schedule" else [],
        list_artifacts=lambda _repo, run_id: [{"id": run_id, "name": "gate-costs-x"}],
        download=lambda _repo, _aid: blob,
    )
    assert len(caps) == gc.SAMPLE_CAPTURES
    assert [s["id"] for s in sources] == list(range(gc.SAMPLE_CAPTURES + 2, 2, -1))


# --------------------------------------------------------------------------- the workflow's two entry points ---------------------------------------------------------------------------


def test_check_writes_no_report_and_reds_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """`rediacc_ci.ci.freshness --check --report-to` is the one writer of housekeeping's report (PLAN-ci-consolidation T8), so gate_costs has no `--report-to` and its failing verdict goes to stderr for freshness to capture."""
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))
    capsys.readouterr()
    doubled = _collect(twice(capture([gate("g", 20000, 20000)])))
    red = gc.check(target, "o/r", tmp_path, collect=doubled)
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
    fresh = gc.aggregate(twice(capture([gate("s", 20000, 20000)])))
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


def test_committed_baseline_header_is_what_the_generator_writes() -> None:
    """A header that differs from DEFAULT_COMMENT would be rewritten by the next --refresh."""
    committed = json.loads((paths.repo_root() / ".ci/config/gate-costs.json").read_text("utf-8"))
    assert committed["$comment"] == gc.DEFAULT_COMMENT


# --------------------------------------------------------------------------- finding keys (review d21f5510.1) ---------------------------------------------------------------------------


def _keys(text: str) -> list[str]:
    return [
        line[len("::finding::") :] for line in text.splitlines() if line.startswith("::finding::")
    ]


def _finding_keys(findings: list[str]) -> set[str]:
    """Each finding's key; a finding that is not `Keyed` fails here, by name."""
    for f in findings:
        assert isinstance(f, fr.Keyed), "unkeyed finding: %r" % f
    return {f.key for f in findings if isinstance(f, fr.Keyed)}


def test_every_gate_cost_finding_class_carries_its_key():
    """`check_findings`' six classes, each a `Keyed` string named `gate-costs:<class>:<gate id>`."""
    committed = baseline_from(
        [
            capture(
                [
                    gate("drifts", 10000, 10000),
                    gate("old", 10000, 10000),
                    gate("quiet", 10000, 10000),
                ]
            )
        ]
    )
    fresh = gc.aggregate(
        twice(
            capture(
                [
                    gate("drifts", 30000, 5000),
                    gate("new", 10000, 10000),
                    gate("quiet", None, 10, status="fail"),
                ],
                cores=8,
            )
        )
    )
    findings = gc.check_findings(committed, fresh, {"drifts", "new", "quiet"})
    keys = _finding_keys(findings)
    assert keys >= {
        "gate-costs:not-in-manifest:old",
        "gate-costs:missing-from-baseline:new",
        "gate-costs:unmeasured:quiet",
        "gate-costs:cores-changed",
        "gate-costs:drift:cpu_s:drifts",
    }, keys
    assert all(isinstance(f, fr.Keyed) for f in findings)


def test_the_eff_cores_drift_is_keyed():
    committed = baseline_from([capture([gate("g", 10000, 10000)], cores=8)])
    fresh = gc.aggregate(twice(capture([gate("g", 10000, 5000)], cores=8)))
    assert _finding_keys(gc.check_findings(committed, fresh, {"g"})) == {
        "gate-costs:drift:eff_cores:g"
    }


def test_a_red_gate_cost_check_prints_one_key_per_finding(tmp_path: Path, capsys):
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    assert (
        gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))
        == 0
    )
    capsys.readouterr()
    over = _collect(twice(capture([gate("g", 12600, 12600)])))
    assert gc.check(target, "o/r", tmp_path, collect=over) == 1
    first = _keys(capsys.readouterr().err)
    more = _collect(twice(capture([gate("g", 19000, 19000)])))
    assert gc.check(target, "o/r", tmp_path, collect=more) == 1
    assert first == _keys(capsys.readouterr().err) == ["gate-costs:drift:cpu_s:g"], (
        "the key does not move with the drift"
    )
    assert (
        gc.check(target, "o/r", tmp_path, collect=lambda _repo: ([], [], ["run 9: bad zip"])) == 1
    )
    assert _keys(capsys.readouterr().err) == [
        "gate-costs:capture-unreadable",
        "gate-costs:no-capture",
    ]
    target.write_text("{not json", encoding="utf-8")
    assert gc.check(target, "o/r", tmp_path, collect=_collect([])) == 1
    assert _keys(capsys.readouterr().err) == ["gate-costs:unreadable"]


def test_control_an_unkeyed_gate_cost_finding_class_is_refused(tmp_path: Path, monkeypatch):
    write_lock(tmp_path, ["g"])
    target = tmp_path / "gate-costs.json"
    assert (
        gc.refresh(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))
        == 0
    )
    monkeypatch.setattr(
        gc, "check_findings", lambda *_a, **_k: ["a new finding class nobody keyed"]
    )
    with pytest.raises(TypeError, match="unkeyed finding"):
        gc.check(target, "o/r", tmp_path, collect=_collect([capture([gate("g", 10000, 10000)])]))


def test_collect_captures_reads_a_capture_dispatched_on_the_pr_head(monkeypatch):
    """Main has no capture; the PR head branch has a dispatched one: it is read (2026-10-19, the capture fix sat on the PR this check kept red). Without GITHUB_HEAD_REF the head branch is not listed at all."""
    calls: list[tuple[str, str]] = []

    def list_runs(_repo, wf, event, branch, *_a):
        calls.append((event, branch))
        if wf == gc.CAPTURE_WORKFLOW and branch == "1008-1" and event == "workflow_dispatch":
            return [{"id": 7, "head_sha": "h", "created_at": "2026-10-19"}]
        return []

    blob = _zip("gate-costs.json", json.dumps(capture([gate("h", 1, 1)])))
    kwargs = {
        "list_runs": list_runs,
        "list_artifacts": lambda _repo, _rid: [{"id": 70, "name": "gate-costs-h"}],
        "download": lambda _repo, _aid: blob,
    }
    monkeypatch.setenv("GITHUB_HEAD_REF", "1008-1")
    caps, sources, _w = gc.collect_captures("o/r", limit=3, **kwargs)
    assert [s["id"] for s in sources] == [7]
    assert caps[0]["gates"][0]["id"] == "h"
    assert ("workflow_dispatch", "1008-1") in calls
    assert ("schedule", "1008-1") not in calls
    calls.clear()
    monkeypatch.delenv("GITHUB_HEAD_REF")
    caps, sources, _w = gc.collect_captures("o/r", limit=3, **kwargs)
    assert sources == []
    assert all(branch != "1008-1" for _e, branch in calls)
    for head in ("", "  ", "main"):
        calls.clear()
        monkeypatch.setenv("GITHUB_HEAD_REF", head)
        caps, sources, _w = gc.collect_captures("o/r", limit=3, **kwargs)
        assert caps == []
        assert sources == []
        assert ("workflow_dispatch", "main") in calls
        assert len(calls) == len(gc.CAPTURE_EVENTS)
