"""`rediacc_ci.ci.freshness` (agent/plans/PLAN-ci-consolidation.md Part B, T8 and T9).

FIXTURE-DRIVEN, NO NETWORK. Every check here is a `python -c` argv run under a `REDIACC_CI_ROOT` fixture tree, so the real subprocess path (cwd, PYTHONPATH, merged streams, exit codes) is exercised without reading GitHub. The real registry and the real wiring (housekeeping.yml's budget-check job, package.json's `check:ci-budget-freshness`) are read, never run.
"""

from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci import paths, workflows
from rediacc_ci.ci import freshness as fr

if TYPE_CHECKING:
    from pathlib import Path

REAL_ROOT = paths.repo_root()
PY = sys.executable


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def entry(
    artifact: str,
    check: list[str],
    *,
    cadence: list[str] | None = None,
    producers: list[list[str]] | None = None,
    network: bool = False,
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "producers": producers or [py("pass")],
        "check": check,
        "network": network,
        "cadence": cadence or ["pr", "nightly"],
    }


def make_root(
    tmp_path: Path, entries: list[dict[str, Any]], *, extra: dict[str, Any] | None = None
) -> Path:
    root = tmp_path / "root"
    (root / ".ci" / "config").mkdir(parents=True)
    doc: dict[str, Any] = {"$comment": ["fixture"], "artifacts": entries}
    doc.update(extra or {})
    (root / fr.REGISTRY_REL_PATH).write_text(json.dumps(doc), encoding="utf-8")
    for e in entries:
        art = root / e["artifact"]
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text("{}\n", encoding="utf-8")
    return root


def run_main(monkeypatch: pytest.MonkeyPatch, root: Path, argv: list[str]) -> int:
    monkeypatch.setenv(paths.ROOT_ENV, str(root))
    return fr.main(argv)


# --------------------------------------------------------------------------- --check ---------------------------------------------------------------------------


def test_all_checks_pass_and_the_report_has_one_section_per_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(
        tmp_path,
        [
            entry("a/one.json", py("print('one is fresh')")),
            entry("b/two.json", py("print('two is fresh')")),
        ],
    )
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)]) == 0
    )
    text = report.read_text(encoding="utf-8")
    assert "=== a/one.json: PASS (rc 0) ===" in text
    assert "one is fresh" in text
    assert "=== b/two.json: PASS (rc 0) ===" in text
    assert "2 artifact(s) fresh, 0 skipped" in text
    assert "2 artifact(s) fresh" in capsys.readouterr().out


def test_one_failing_check_is_rc_1_and_names_its_artifact_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(
        tmp_path,
        [
            entry("a/ok.json", py("print('ok')")),
            entry(
                "b/stale.json", py("import sys; sys.stderr.write('drifted 40%\\n'); sys.exit(1)")
            ),
        ],
    )
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "nightly", "--report-to", str(report)])
        == 1
    )
    text = report.read_text(encoding="utf-8")
    assert "=== b/stale.json: FAIL (rc 1) ===" in text
    assert "drifted 40%" in text, "the failing check's stderr reaches the report"
    assert "=== a/ok.json: PASS (rc 0) ===" in text, "the green artifact's section is kept"
    assert "1 of 2 artifact(s) FAILED (exit codes sum 1): b/stale.json (rc 1)" in text
    assert "b/stale.json (rc 1)" in capsys.readouterr().err


def test_exit_codes_are_summed_in_the_verdict_but_the_process_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(
        tmp_path,
        [
            entry("a.json", py("import sys; sys.exit(1)")),
            entry("b.json", py("import sys; sys.exit(3)")),
        ],
    )
    assert run_main(monkeypatch, root, ["--check", "--cadence", "pr"]) == 1
    assert "2 of 2 artifact(s) FAILED (exit codes sum 4)" in capsys.readouterr().err


def test_nightly_skips_a_pr_only_entry_and_never_runs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "pr-only-ran"
    root = make_root(
        tmp_path,
        [
            entry("nightly.json", py("print('n')"), cadence=["nightly"]),
            entry(
                "pr-only.json",
                py(
                    "import pathlib, sys; pathlib.Path(%r).write_text('x'); sys.exit(1)"
                    % str(marker)
                ),
                cadence=["pr"],
            ),
        ],
    )
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "nightly", "--report-to", str(report)])
        == 0
    )
    assert not marker.exists(), "a pr-only check ran at the nightly cadence"
    text = report.read_text(encoding="utf-8")
    assert "=== pr-only.json: skipped (cadence pr only) ===" in text
    assert "1 artifact(s) fresh, 1 skipped" in text
    # CONTROL: at its own cadence the same entry does run, and reds.
    assert run_main(monkeypatch, root, ["--check", "--cadence", "pr"]) == 1
    assert marker.exists()


def test_a_cadence_no_entry_runs_at_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(tmp_path, [entry("a.json", py("pass"), cadence=["pr"])])
    report = tmp_path / "report.txt"
    rc = run_main(
        monkeypatch, root, ["--check", "--cadence", "nightly", "--report-to", str(report)]
    )
    assert rc == fr.REFUSED
    assert "selects nothing verifies nothing" in capsys.readouterr().err
    assert "REFUSED" in report.read_text(encoding="utf-8")


def test_checks_run_from_the_root_with_pythonpath_ci(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = make_root(
        tmp_path,
        [
            entry(
                "a.json",
                py(
                    "import os; print('CWD=' + os.getcwd()); print('PP=' + os.environ['PYTHONPATH'])"
                ),
            )
        ],
    )
    monkeypatch.setenv("PYTHONPATH", "/somewhere/else")
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)]) == 0
    )
    text = report.read_text(encoding="utf-8")
    assert "CWD=%s" % root.resolve() in text
    assert "PP=%s" % (root.resolve() / ".ci") in text


def test_a_missing_artifact_is_a_failure_naming_its_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "check-ran"
    root = make_root(
        tmp_path,
        [entry("gone.json", py("import pathlib; pathlib.Path(%r).write_text('x')" % str(marker)))],
    )
    (root / "gone.json").unlink()
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)]) == 1
    )
    text = report.read_text(encoding="utf-8")
    assert "=== gone.json: FAIL (rc 1) ===" in text
    assert "--refresh gone.json" in text
    assert not marker.exists(), "the check ran against an artifact that is not there"


def test_a_check_that_cannot_start_is_unchecked_not_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = make_root(tmp_path, [entry("a.json", ["/nonexistent/freshness-probe-binary"])])
    report = tmp_path / "report.txt"
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)]) == 1
    )
    assert "UNCHECKED: the check could not be started" in report.read_text(encoding="utf-8")


def test_the_budget_is_shared_a_slow_check_is_stopped_and_the_next_never_starts(tmp_path: Path):
    marker = tmp_path / "second-ran"
    root = make_root(
        tmp_path,
        [
            entry("slow.json", py("import time; time.sleep(30)")),
            entry(
                "next.json", py("import pathlib; pathlib.Path(%r).write_text('x')" % str(marker))
            ),
        ],
    )
    report = tmp_path / "report.txt"
    entries = fr.load_registry(root)
    assert fr.check(entries, "pr", root, report_to=report, budget_s=1.0) == 1
    text = report.read_text(encoding="utf-8")
    assert "=== slow.json: FAIL (rc 124) ===" in text
    assert "UNCHECKED: the check ran past the 1s left of the run's budget" in text
    assert "=== next.json: FAIL (rc 124) ===" in text
    assert "budget was spent before this check started" in text
    assert not marker.exists(), "a check started after the shared deadline"
    # CONTROL: with room in the budget the same second check runs and passes.
    assert fr.check(entries[1:], "pr", root, report_to=report, budget_s=60) == 0
    assert marker.exists()


def test_the_report_is_overwritten_not_appended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """One writer: a stale report from an earlier run must not survive into the posted summary."""
    root = make_root(tmp_path, [entry("a.json", py("print('fresh')"))])
    report = tmp_path / "report.txt"
    report.write_text("LEFT OVER FROM A PREVIOUS RUN\n", encoding="utf-8")
    assert (
        run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)]) == 0
    )
    assert "LEFT OVER" not in report.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- registry refusals ---------------------------------------------------------------------------


def test_an_empty_registry_is_refused_and_says_so_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(tmp_path, [])
    report = tmp_path / "report.txt"
    rc = run_main(monkeypatch, root, ["--check", "--cadence", "pr", "--report-to", str(report)])
    assert rc == fr.REFUSED
    assert "ZERO artifacts" in capsys.readouterr().err
    assert "ZERO artifacts" in report.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda d: d["artifacts"][0].update({"owner": "x"}), "unknown key(s): owner"),
        (lambda d: d.update({"version": 2}), "unknown top-level key(s): version"),
        (lambda d: d["artifacts"][0].pop("network"), "missing key(s): network"),
        (lambda d: d["artifacts"][0].update({"cadence": ["weekly"]}), "cadence must be"),
        (lambda d: d["artifacts"][0].update({"cadence": []}), "cadence must be"),
        (lambda d: d["artifacts"][0].update({"producers": []}), "has no producers"),
        (
            lambda d: d["artifacts"][0].update({"check": "python3 -m x"}),
            "check must be a non-empty list",
        ),
        (lambda d: d["artifacts"][0].update({"network": "yes"}), "network must be true or false"),
        (lambda d: d["artifacts"][0].update({"artifact": "/abs/path.json"}), "repo-relative"),
        (lambda d: d["artifacts"].append(dict(d["artifacts"][0])), "a second time"),
        (lambda d: d.pop("artifacts"), "ZERO artifacts"),
    ],
)
def test_a_malformed_registry_is_refused(mutate: Any, needle: str):
    doc: dict[str, Any] = {"$comment": [], "artifacts": [entry("a.json", py("pass"))]}
    fr.parse_registry(doc, "fixture")  # CONTROL: the unmutated document is accepted.
    mutate(doc)
    with pytest.raises(fr.RegistryError, match=None) as exc:
        fr.parse_registry(doc, "fixture")
    assert needle in str(exc.value)


def test_a_missing_or_unparseable_registry_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "bare"
    root.mkdir()
    assert run_main(monkeypatch, root, ["--list"]) == fr.REFUSED
    (root / ".ci" / "config").mkdir(parents=True)
    (root / fr.REGISTRY_REL_PATH).write_text("{not json", encoding="utf-8")
    assert run_main(monkeypatch, root, ["--list"]) == fr.REFUSED


def test_check_needs_a_cadence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = make_root(tmp_path, [entry("a.json", py("pass"))])
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, root, ["--check"])
    assert exc.value.code == 2


# --------------------------------------------------------------------------- --list / --refresh ---------------------------------------------------------------------------


def test_list_prints_every_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(
        tmp_path,
        [
            entry("a.json", py("pass"), cadence=["nightly"], network=True),
            entry("b.json", py("pass")),
        ],
    )
    assert run_main(monkeypatch, root, ["--list"]) == 0
    out = capsys.readouterr().out
    assert "a.json\n  cadence: nightly\n  network: yes" in out
    assert "2 artifact(s) registered" in out


def test_refresh_runs_producers_in_order_and_stops_at_the_first_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    log = tmp_path / "log.txt"
    append = "import pathlib; p = pathlib.Path(%r); p.write_text(p.read_text() + %r if p.exists() else %r)"
    good = make_root(
        tmp_path,
        [
            entry(
                "a.json",
                py("pass"),
                producers=[py(append % (str(log), "1", "1")), py(append % (str(log), "2", "2"))],
            )
        ],
    )
    assert run_main(monkeypatch, good, ["--refresh", "a.json"]) == 0
    assert log.read_text() == "12"

    log.unlink()
    bad = make_root(
        tmp_path / "bad",
        [
            entry(
                "a.json",
                py("pass"),
                producers=[py("import sys; sys.exit(5)"), py(append % (str(log), "2", "2"))],
            )
        ],
    )
    assert run_main(monkeypatch, bad, ["--refresh", "a.json"]) == 1
    assert "exited 5; later producers were not run" in capsys.readouterr().err
    assert not log.exists()


def test_refresh_refuses_an_unregistered_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = make_root(tmp_path, [entry("a.json", py("pass"))])
    assert run_main(monkeypatch, root, ["--refresh", "zzz.json"]) == fr.REFUSED
    assert "registered: a.json" in capsys.readouterr().err


def test_refresh_reds_when_producers_leave_no_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = make_root(tmp_path, [entry("a.json", py("pass"))])
    (root / "a.json").unlink()
    assert run_main(monkeypatch, root, ["--refresh", "a.json"]) == 1


# --------------------------------------------------------------------------- the real registry ---------------------------------------------------------------------------


def _module_file(argv: tuple[str, ...]) -> Path | None:
    if len(argv) >= 3 and argv[1] == "-m":
        return REAL_ROOT / ".ci" / (argv[2].replace(".", "/") + ".py")
    if len(argv) >= 2 and argv[1].endswith(".py"):
        return REAL_ROOT / argv[1]
    return None


def test_the_real_registry_names_exactly_the_two_live_artifacts():
    entries = fr.load_registry(REAL_ROOT)
    assert [e.artifact for e in entries] == [
        ".ci/config/lane-durations.json",
        ".ci/config/gate-costs.json",
    ]
    for e in entries:
        assert (REAL_ROOT / e.artifact).is_file(), e.artifact
        assert set(e.cadence) == {"pr", "nightly"}, "both are bound per PR since 7c845cf3b"
        for argv in (e.check, *e.producers):
            target = _module_file(argv)
            assert target is not None, "%s: %s names no module or script" % (e.artifact, argv)
            assert target.is_file(), "%s: %s resolves to no file" % (e.artifact, argv)
    lane = entries[0]
    assert (
        "python3",
        ".ci/scripts/quality/check_job_timeout_headroom.py",
        "--refresh",
    ) in lane.producers, (
        "job_max_seconds has its own producer (check_job_timeout_headroom.py RETIRED INTO)"
    )


# --------------------------------------------------------------------------- T9: the wiring pins ---------------------------------------------------------------------------

HOUSEKEEPING = REAL_ROOT / ".github" / "workflows" / "housekeeping.yml"
OLD_CALLS = ("rediacc_ci.ci.budget_report", "rediacc_ci.ci.gate_costs")


def budget_job_findings(doc: dict[str, Any]) -> list[str]:
    """What is wrong with housekeeping's budget-check job, as parsed YAML. Pure, so the test can plant the old wiring into a copy."""
    job = (doc.get("jobs") or {}).get("budget-check")
    if not isinstance(job, dict):
        return ["housekeeping.yml has no budget-check job"]
    steps = [s for s in job.get("steps") or [] if isinstance(s, dict)]
    out: list[str] = []
    callers = [s for s in steps if "rediacc_ci.ci.freshness" in str(s.get("run", ""))]
    if len(callers) != 1:
        out.append(
            "expected exactly one step calling rediacc_ci.ci.freshness, found %d" % len(callers)
        )
    for s in steps:
        run = str(s.get("run", ""))
        out.extend(
            "step %r calls %s directly; it belongs in .ci/config/freshness.json"
            % (s.get("name"), old)
            for old in OLD_CALLS
            if old in run
        )
    if len(callers) == 1:
        run = str(callers[0].get("run", ""))
        out.extend(
            "the freshness step does not pass %s" % needle
            for needle in ("--check", "--cadence nightly", "--report-to /tmp/budget-check.txt")
            if needle not in run
        )
        sid = callers[0].get("id")
        for s in steps:
            cond = str(s.get("if", ""))
            keys = set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", cond))
            if keys - {sid}:
                out.append(
                    "step %r keys on %s, not only on the freshness step %r"
                    % (s.get("name"), ", ".join(sorted(keys - {sid})), sid)
                )
        keyed = [s for s in steps if ("steps.%s.outputs.rc" % sid) in str(s.get("if", ""))]
        if len(keyed) != 2:
            out.append(
                "expected the report and fail steps to key on %s, found %d" % (sid, len(keyed))
            )
    return out


def test_housekeeping_budget_check_calls_freshness_only():
    assert budget_job_findings(workflows.load(HOUSEKEEPING)) == []


def test_control_the_old_two_step_wiring_reds():
    doc = workflows.load(HOUSEKEEPING)
    steps = doc["jobs"]["budget-check"]["steps"]
    at = next(i for i, s in enumerate(steps) if "rediacc_ci.ci.freshness" in str(s.get("run", "")))
    steps.insert(
        at + 1,
        {
            "name": "Gate cost baseline check",
            "id": "gate-costs-check",
            "run": "PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --check\n",
        },
    )
    for s in steps:
        if "outputs.rc" in str(s.get("if", "")):
            s["if"] = str(s["if"]) + " || steps.gate-costs-check.outputs.rc != '0'"
    findings = budget_job_findings(doc)
    assert any("calls rediacc_ci.ci.gate_costs directly" in f for f in findings), findings
    assert any("not only on the freshness step" in f for f in findings), findings
    steps[at]["run"] = "PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --check\n"
    findings = budget_job_findings(doc)
    assert any(
        "exactly one step calling rediacc_ci.ci.freshness, found 0" in f for f in findings
    ), findings


def test_package_json_budget_freshness_runs_the_registry_at_pr_cadence():
    scripts = json.loads((REAL_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    cmd = scripts["check:ci-budget-freshness"]
    assert "rediacc_ci.ci.freshness --check --cadence pr" in cmd, cmd
    for old in OLD_CALLS:
        assert old not in cmd, "check:ci-budget-freshness calls %s directly: %s" % (old, cmd)
