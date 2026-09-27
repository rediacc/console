"""`rediacc_ci.ci.budget_report`'s T3.2/T3.3 additions (PLAN-ci-time-budget, operator spec W): the lane/unit duration schema `.ci/config/lane-durations.json` gets written into, the parsers for the five T1.6 unit-duration artifact formats, and the `--refresh`/`--check` commands built on top of them.

FIXTURE-DRIVEN, NO NETWORK. Every test here drives a pure function directly, or a network-touching one (`compute_lane_durations`, `collect_unit_durations`) through its injectable `compute`/`list_artifacts`/`download` parameters -- the same seam the module's own docstring names as the reason those parameters exist: T1.6 has not landed, so there is no live artifact to record a fixture FROM, only the contract this module's own docstring defines. `refresh_lane_durations`/`check_lane_durations` are driven the same way, through their own `compute` parameter, so neither test calls `gh` or the real Actions API.

T1.1's `build_report`/`collect_class`/`fetch_runs`/`fetch_jobs` machinery already exists and is unchanged by this box; it is not retested here.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from rediacc_ci.ci import budget_report as br

# --------------------------------------------------------------------------- parse_workflow_jobs: has_matrix ---------------------------------------------------------------------------


def test_parse_workflow_jobs_captures_has_matrix():
    text = """jobs:
  quality-code:
    name: Code
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - run: echo hi
  quality-content:
    name: Content
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
    jobs = br.parse_workflow_jobs(text)
    assert jobs["quality-code"]["has_matrix"] is True
    assert jobs["quality-content"]["has_matrix"] is False


# --------------------------------------------------------------------------- _display_name_pattern ---------------------------------------------------------------------------


def test_display_name_pattern_template_segments_become_wildcards():
    pattern = br._display_name_pattern(
        "Tests + Infra / E2E Workers (${{ matrix.os-image }}, ${{ matrix.shard }}/8)", False
    )
    assert pattern.match("Tests + Infra / E2E Workers (ubuntu-24.04, 3/8)")
    assert not pattern.match("Tests + Infra / E2E Workers")


def test_display_name_pattern_matrix_without_template_gets_optional_suffix():
    pattern = br._display_name_pattern("Quality / Code", True)
    assert pattern.match("Quality / Code")
    assert pattern.match("Quality / Code (1)")
    assert not pattern.match("Quality / Content")


def test_display_name_pattern_plain_name_matches_verbatim_only():
    pattern = br._display_name_pattern("Quality / Content", False)
    assert pattern.match("Quality / Content")
    # CONTROL: an unsharded lane's exact name must not accidentally accept a sharded-looking suffix -- that would let a same-prefixed sharded lane's legs satisfy an unsharded lane's own pattern.
    assert not pattern.match("Quality / Content (1)")


# --------------------------------------------------------------------------- lane_display_patterns ---------------------------------------------------------------------------

_FIXTURE_CI_YML = """jobs:
  quality:
    name: Quality
    uses: ./.github/workflows/ci-quality.yml
  tests:
    name: Tests + Infra
    uses: ./.github/workflows/ct-tests.yml
"""

_FIXTURE_QUALITY_YML = """jobs:
  quality-code:
    name: Code
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
  quality-content:
    name: Content
"""

_FIXTURE_CT_TESTS_YML = """jobs:
  test-e2e-workers:
    name: E2E Workers (${{ matrix.os-image }}, ${{ matrix.shard }}/8)
"""


def _write_fixture_workflows(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(_FIXTURE_CI_YML, encoding="utf-8")
    (workflows / "ci-quality.yml").write_text(_FIXTURE_QUALITY_YML, encoding="utf-8")
    (workflows / "ct-tests.yml").write_text(_FIXTURE_CT_TESTS_YML, encoding="utf-8")
    return tmp_path


def test_lane_display_patterns_aliases_caller_and_callee_names(tmp_path):
    root = _write_fixture_workflows(tmp_path)
    patterns = br.lane_display_patterns(root, "ci.yml")
    assert patterns["quality-code"].match("Quality / Code (1)")
    assert patterns["quality-content"].match("Quality / Content")
    assert not patterns["quality-content"].match("Quality / Content (1)")
    assert patterns["test-e2e-workers"].match("Tests + Infra / E2E Workers (ubuntu-24.04, 3/8)")


def test_lane_display_patterns_has_no_entry_for_a_lane_not_split_out_yet(tmp_path):
    """A lane absent from the workflow entirely (T2.12/T2.14/T2.16 not yet landed for it) is simply not a key here -- never a crash, never a guessed pattern."""
    root = _write_fixture_workflows(tmp_path)
    patterns = br.lane_display_patterns(root, "ci.yml")
    assert "ops-tutorials" not in patterns


# --------------------------------------------------------------------------- job_fixed_cost_minutes ---------------------------------------------------------------------------


def test_job_fixed_cost_minutes_measures_up_to_the_runner_step():
    job = {
        "started_at": "2026-09-27T00:00:00Z",
        "steps": [
            {"name": "Checkout", "started_at": "2026-09-27T00:00:05Z"},
            {"name": "Setup workspace", "started_at": "2026-09-27T00:01:00Z"},
            {"name": "Run E2E Tests (Workers)", "started_at": "2026-09-27T00:05:00Z"},
            {"name": "Upload logs", "started_at": "2026-09-27T00:40:00Z"},
        ],
    }
    minutes = br.job_fixed_cost_minutes(job, br.RUNNER_STEP_PATTERNS["test-e2e-workers"])
    assert minutes == pytest.approx(5.0)


def test_job_fixed_cost_minutes_is_none_when_no_step_matches():
    """Never a guessed 0, never the whole job -- an absent runner step means an absent estimate."""
    job = {
        "started_at": "2026-09-27T00:00:00Z",
        "steps": [{"name": "Checkout", "started_at": "2026-09-27T00:00:05Z"}],
    }
    assert br.job_fixed_cost_minutes(job, br.RUNNER_STEP_PATTERNS["test-e2e-workers"]) is None


# --------------------------------------------------------------------------- the five T1.6 unit-duration parsers ---------------------------------------------------------------------------


def test_parse_playwright_unit_ms_sums_every_test_and_attempt_per_file():
    text = json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "file": "a.spec.ts",
                            "tests": [{"results": [{"duration": 1000}, {"duration": 500}]}],
                        }
                    ],
                    "suites": [
                        {
                            "specs": [
                                {"file": "b.spec.ts", "tests": [{"results": [{"duration": 2000}]}]}
                            ]
                        }
                    ],
                }
            ]
        }
    )
    out = br.parse_playwright_unit_ms(text, "test-e2e-workers")
    assert out == {"e2e-workers:a.spec.ts": 1500.0, "e2e-workers:b.spec.ts": 2000.0}


def test_parse_playwright_unit_ms_prefixes_by_lane():
    text = json.dumps(
        {"suites": [{"specs": [{"file": "x.spec.ts", "tests": [{"results": [{"duration": 1}]}]}]}]}
    )
    out = br.parse_playwright_unit_ms(text, "test-account-e2e")
    assert list(out.keys()) == ["account-e2e:x.spec.ts"]


def test_parse_playwright_unit_ms_raises_on_malformed_json():
    with pytest.raises(ValueError, match="not JSON"):
        br.parse_playwright_unit_ms("not json", "test-e2e-workers")


def test_parse_pytest_junit_unit_ms_by_file_for_quality_pytest():
    text = (
        "<testsuites><testsuite>"
        '<testcase classname="tests.foo" name="test_x" file="tests/foo.py" time="1.5"/>'
        '<testcase classname="tests.foo" name="test_y" file="tests/foo.py" time="0.5"/>'
        "</testsuite></testsuites>"
    )
    out = br.parse_pytest_junit_unit_ms(text, "quality-pytest")
    assert out == {"pytest:tests/foo.py": pytest.approx(2000.0)}


def test_parse_pytest_junit_unit_ms_by_basename_for_renet_integration():
    text = '<testsuites><testsuite><testcase classname="x" file="tests/integration/test_a.py" time="3"/></testsuite></testsuites>'
    out = br.parse_pytest_junit_unit_ms(text, "test-renet-integration")
    assert out == {"renet-integration:test_a.py": pytest.approx(3000.0)}


def test_parse_pytest_junit_unit_ms_falls_back_to_classname_without_a_file_attribute():
    text = '<testsuites><testsuite><testcase classname="tests.foo" name="test_x" time="1"/></testsuite></testsuites>'
    out = br.parse_pytest_junit_unit_ms(text, "quality-pytest")
    assert out == {"pytest:tests/foo.py": pytest.approx(1000.0)}


def test_parse_pytest_junit_unit_ms_raises_on_malformed_xml():
    with pytest.raises(ValueError, match="not XML"):
        br.parse_pytest_junit_unit_ms("<not-xml", "quality-pytest")


def test_parse_gotestsum_junit_unit_ms_keys_by_bare_package_path():
    text = (
        "<testsuites><testsuite>"
        '<testcase classname="github.com/rediacc/renet/pkg/foo" name="TestA" time="1.0"/>'
        '<testcase classname="github.com/rediacc/renet/pkg/foo" name="TestB" time="1.25"/>'
        "</testsuite></testsuites>"
    )
    out = br.parse_gotestsum_junit_unit_ms(text)
    assert out == {"github.com/rediacc/renet/pkg/foo": pytest.approx(2250.0)}


def test_parse_battery_summary_unit_ms():
    text = json.dumps({"drivers": [{"name": "W-writer1", "duration_ms": 4200}]})
    assert br.parse_battery_summary_unit_ms(text) == {"battery:W-writer1": 4200.0}


def test_parse_battery_summary_unit_ms_raises_without_the_drivers_array():
    with pytest.raises(TypeError, match="drivers"):
        br.parse_battery_summary_unit_ms(json.dumps({"nope": []}))


def test_parse_tutorial_summary_unit_ms():
    text = json.dumps({"tutorials": [{"slug": "quickstart", "duration_ms": 90000}]})
    assert br.parse_tutorial_summary_unit_ms(text) == {"tutorial:quickstart": 90000.0}


# --------------------------------------------------------------------------- parse_unit_duration_artifact (the zip layer) ---------------------------------------------------------------------------


def _zip_with(member_name: str, content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(member_name, content)
    return buf.getvalue()


def _zip_with_many(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for member_name, content in members.items():
            archive.writestr(member_name, content)
    return buf.getvalue()


def test_parse_unit_duration_artifact_dispatches_by_lane_format():
    blob = _zip_with(
        "results.json",
        json.dumps(
            {
                "suites": [
                    {"specs": [{"file": "a.spec.ts", "tests": [{"results": [{"duration": 2000}]}]}]}
                ]
            }
        ),
    )
    assert br.parse_unit_duration_artifact("test-e2e-workers", blob) == {
        "e2e-workers:a.spec.ts": 2000.0
    }


def test_parse_unit_duration_artifact_raises_when_no_member_matches_the_expected_suffix():
    blob = _zip_with("readme.txt", "nothing useful")
    with pytest.raises(ValueError, match="carries no"):
        br.parse_unit_duration_artifact("test-e2e-workers", blob)


def test_parse_unit_duration_artifact_raises_for_an_undeclared_lane():
    blob = _zip_with("results.json", "{}")
    with pytest.raises(ValueError, match="no unit-duration artifact format"):
        br.parse_unit_duration_artifact("not-a-real-lane", blob)


def _playwright_json(file_name: str, duration_ms: int) -> str:
    return json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {"file": file_name, "tests": [{"results": [{"duration": duration_ms}]}]}
                    ]
                }
            ]
        }
    )


def test_parse_unit_duration_artifact_sums_several_members_of_the_same_format():
    """CONTROL: a sharded E2E leg's own run-e2e.sh can invoke Playwright more than once, writing one `unit-durations*.json` per invocation into the SAME artifact. Two members naming the same spec file must sum to that file's total duration, not have one silently discarded by `next(...)`."""
    blob = _zip_with_many(
        {
            "unit-durations-1.json": _playwright_json("a.spec.ts", 2000),
            "unit-durations-2.json": _playwright_json("a.spec.ts", 500),
        }
    )
    assert br.parse_unit_duration_artifact("test-e2e-workers", blob) == {
        "e2e-workers:a.spec.ts": 2500.0
    }


def test_parse_unit_duration_artifact_single_member_is_unchanged():
    """INVERSE of the control above: with exactly one matching member, summing across "every matching member" degenerates to the original single-member behavior."""
    blob = _zip_with("unit-durations-1.json", _playwright_json("a.spec.ts", 2000))
    assert br.parse_unit_duration_artifact("test-e2e-workers", blob) == {
        "e2e-workers:a.spec.ts": 2000.0
    }


# --------------------------------------------------------------------------- collect_unit_durations: the missing-lane report ---------------------------------------------------------------------------


def test_collect_unit_durations_reports_a_lane_with_zero_artifacts_rather_than_skipping_it():
    """T3.2's own instruction: "Missing artifacts for a lane must be reported per lane, never silently skipped." A lane the fake never serves an artifact for must appear in `missing`, not simply be absent from the result with no trace."""
    blob = _zip_with(
        "results.json",
        json.dumps(
            {
                "suites": [
                    {"specs": [{"file": "a.spec.ts", "tests": [{"results": [{"duration": 500}]}]}]}
                ]
            }
        ),
    )

    def fake_list(_repo, _run_id):
        return [{"id": "art-1", "name": "unit-durations-test-e2e-workers-ubuntu-abc123"}]

    def fake_download(_repo, _artifact_id):
        return blob

    per_lane, missing = br.collect_unit_durations(
        "rediacc/console",
        [1],
        ["test-e2e-workers", "test-account-e2e"],
        list_artifacts=fake_list,
        download=fake_download,
    )
    assert per_lane["test-e2e-workers"] == {"e2e-workers:a.spec.ts": [500.0]}
    assert per_lane["test-account-e2e"] == {}
    assert missing == ["test-account-e2e"]


def test_collect_unit_durations_no_lane_missing_when_every_lane_gets_an_artifact():
    def fake_list(_repo, _run_id):
        return [{"id": "1", "name": "unit-durations-test-e2e-workers-x-sha"}]

    def fake_download(_repo, _artifact_id):
        return _zip_with("results.json", '{"suites": []}')

    _, missing = br.collect_unit_durations(
        "rediacc/console",
        [1],
        ["test-e2e-workers"],
        list_artifacts=fake_list,
        download=fake_download,
    )
    assert missing == []


def test_collect_unit_durations_survives_a_download_failure_and_still_reports_missing():
    def fake_list(_repo, _run_id):
        return [{"id": "1", "name": "unit-durations-test-e2e-workers-x-sha"}]

    def failing_download(_repo, _artifact_id):
        raise OSError("network hiccup")

    per_lane, missing = br.collect_unit_durations(
        "rediacc/console",
        [1],
        ["test-e2e-workers"],
        list_artifacts=fake_list,
        download=failing_download,
    )
    assert per_lane["test-e2e-workers"] == {}
    assert missing == ["test-e2e-workers"]


# --------------------------------------------------------------------------- T3.3: leg_over_budget_finding / drift_finding ---------------------------------------------------------------------------


def test_leg_over_budget_finding_fires_at_12_1_not_at_11_9():
    assert br.leg_over_budget_finding("lane-a", 12.1) is not None
    assert br.leg_over_budget_finding("lane-a", 11.9) is None
    assert br.leg_over_budget_finding("lane-a", 12.0) is None  # exactly at budget: not over


def test_drift_finding_fires_at_26_percent_not_at_24_percent():
    assert br.drift_finding("job", 10.0, 12.6) is not None
    assert br.drift_finding("job", 10.0, 12.4) is None


def test_drift_finding_is_none_when_either_side_is_unmeasured():
    assert br.drift_finding("job", None, 12.6) is None
    assert br.drift_finding("job", 10.0, None) is None


def test_drift_finding_zero_committed_zero_measured_is_not_drifted():
    assert br.drift_finding("job", 0.0, 0.0) is None


def test_drift_finding_zero_committed_nonzero_measured_is_drifted():
    assert br.drift_finding("job", 0.0, 5.0) is not None


# --------------------------------------------------------------------------- refresh_lane_durations ---------------------------------------------------------------------------


def _fake_compute(**overrides):
    base: dict[str, object] = {
        "jobs": {},
        "units": {},
        "job_max_seconds": {},
        "missing_artifact_lanes": [],
    }
    base.update(overrides)

    def compute(_repo, _workflow, _branch, _limit):
        return base

    return compute


def test_refresh_lane_durations_merges_and_preserves_untouched_fields(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(
        json.dumps(
            {
                "$comment": ["hello"],
                "refreshed_at": "2026-01-01T00:00:00Z",
                "concurrency": 20,
                "jobs": {"quality-code": 3.0},
                "units": {"pytest:x.py": 111.0},
                "defaultUnitMs": {"quality-pytest": 5000},
            }
        )
    )
    compute = _fake_compute(
        jobs={"test-e2e-workers": 5.5},
        units={"e2e-workers:a.spec.ts": 2000.0},
        job_max_seconds={"Validate Promotion": {"observed_max_seconds": 300, "samples": 3}},
    )
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    data = json.loads(path.read_text())
    assert data["$comment"] == ["hello"]
    assert data["concurrency"] == 20
    assert data["jobs"] == {"quality-code": 3.0, "test-e2e-workers": 5.5}
    assert data["units"] == {"pytest:x.py": 111.0, "e2e-workers:a.spec.ts": 2000.0}
    assert data["defaultUnitMs"] == {"quality-pytest": 5000}
    assert data["refreshed_at"] != "2026-01-01T00:00:00Z"
    assert data["job_max_seconds"]["jobs"]["Validate Promotion"]["observed_max_seconds"] == 300


def test_refresh_lane_durations_dry_run_never_writes(tmp_path):
    path = tmp_path / "lane-durations.json"
    original = json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}})
    path.write_text(original)
    compute = _fake_compute(jobs={"test-e2e-workers": 5.5})
    rc = br.refresh_lane_durations(path, limit=10, dry_run=True, compute=compute)
    assert rc == 0
    assert path.read_text() == original


def test_refresh_lane_durations_refuses_to_stamp_when_nothing_was_measured(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    compute = _fake_compute()  # everything empty
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 1
    assert json.loads(path.read_text())["refreshed_at"] is None


def test_refresh_lane_durations_warns_per_missing_lane_never_silently(tmp_path, capsys):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    compute = _fake_compute(
        jobs={"test-e2e-workers": 5.0}, missing_artifact_lanes=["ops-tutorials"]
    )
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    assert "ops-tutorials" in capsys.readouterr().err


# --------------------------------------------------------------------------- check_lane_durations ---------------------------------------------------------------------------


def _committed(**overrides):
    base = {"refreshed_at": "2026-01-01T00:00:00Z", "concurrency": 20, "jobs": {}, "units": {}}
    base.update(overrides)
    return base


def test_check_lane_durations_passes_when_nothing_drifted_and_nothing_is_over_budget(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps(_committed(jobs={"test-e2e-workers": 5.5})))
    compute = _fake_compute(jobs={"test-e2e-workers": 5.5})
    assert br.check_lane_durations(path, limit=10, compute=compute) == 0


def test_check_lane_durations_fails_on_a_leg_over_12_minutes(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps(_committed(jobs={"test-e2e-workers": 12.1})))
    compute = _fake_compute(jobs={"test-e2e-workers": 12.1})
    assert br.check_lane_durations(path, limit=10, compute=compute) == 1


def test_check_lane_durations_fails_on_26_percent_drift_not_24_percent(tmp_path):
    """Committed 8.0m against a measured 10.08m (26%, over) / 9.92m (24%, under) -- both measurements stay under the 12-minute per-leg budget on their own, so only `drift_finding` is at play here, not `leg_over_budget_finding`."""
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps(_committed(jobs={"test-e2e-workers": 8.0})))

    over = br.check_lane_durations(
        path, limit=10, compute=_fake_compute(jobs={"test-e2e-workers": 8.0 * 1.26})
    )
    assert over == 1

    under = br.check_lane_durations(
        path, limit=10, compute=_fake_compute(jobs={"test-e2e-workers": 8.0 * 1.24})
    )
    assert under == 0


def test_check_lane_durations_reports_a_missing_artifact_lane_as_a_finding(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps(_committed()))
    compute = _fake_compute(missing_artifact_lanes=["ops-tutorials"])
    assert br.check_lane_durations(path, limit=10, compute=compute) == 1


def test_check_lane_durations_checks_the_headroom_jobs_too(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(
        json.dumps(
            _committed(
                job_max_seconds={
                    "refreshed_at": "2026-01-01T00:00:00Z",
                    "jobs": {"Validate Promotion": {"observed_max_seconds": 300, "samples": 3}},
                }
            )
        )
    )
    over_budget = _fake_compute(
        job_max_seconds={"Validate Promotion": {"observed_max_seconds": 800, "samples": 3}}
    )
    assert br.check_lane_durations(path, limit=10, compute=over_budget) == 1


def test_check_lane_durations_never_writes_the_file(tmp_path):
    path = tmp_path / "lane-durations.json"
    original = json.dumps(_committed(jobs={"test-e2e-workers": 5.0}))
    path.write_text(original)
    br.check_lane_durations(path, limit=10, compute=_fake_compute(jobs={"test-e2e-workers": 5.0}))
    assert path.read_text() == original


def test_the_refresh_samples_completed_pr_runs_not_successful_ones(monkeypatch, tmp_path) -> None:
    """CONTROL (#32e66d3b): a run-level `success` filter found no PR run at all while check:ci-plan-implementation reds every run until spec W closes, so W could never close its own budget boxes. The PR sample is COMPLETED runs; jobs stay success-only."""
    seen: list[tuple[str, str]] = []

    def fake_fetch_runs(*args):
        # fetch_runs(repo, workflow, event, branch, status, limit)
        seen.append((args[2], args[4]))
        return []

    monkeypatch.setattr(br, "fetch_runs", fake_fetch_runs)
    monkeypatch.setattr(br, "lane_display_patterns", lambda *_a: {})
    monkeypatch.setattr(br, "collect_unit_durations", lambda *_a, **_k: ({}, []))
    br.compute_lane_durations(
        root=tmp_path, list_artifacts=lambda *_a: [], download=lambda *_a: b""
    )
    assert ("pull_request", "completed") in seen


def test_inverse_a_failed_job_in_a_completed_run_is_still_not_sampled() -> None:
    assert (
        br.job_wall_minutes(
            {
                "conclusion": "failure",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:05:00Z",
            }
        )
        is None
    )


def test_every_read_asks_ghx_for_the_retrying_attempt_count(monkeypatch):
    """A single transient failure (2026-09-27: `stream error ... CANCEL` on one run's jobs) aborted a whole refresh; every read now asks ghx for GH_ATTEMPTS."""
    seen = []

    def fake_api_json(_path, **kw):
        seen.append(kw.get("attempts"))
        return {"workflow_runs": [], "jobs": [], "artifacts": []}

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    br.fetch_runs("o/r", "ci.yml", "pull_request", None, "completed", 1)
    br.fetch_jobs("o/r", 1)
    br.fetch_artifacts("o/r", 1)
    assert br.GH_ATTEMPTS > 1
    assert seen == [br.GH_ATTEMPTS] * 3


class _Proc:
    def __init__(self, rc, out=b""):
        self.returncode, self.stdout, self.stderr = rc, out, b"stream error"


def test_artifact_download_retries_a_transient_failure(monkeypatch):
    calls = iter([_Proc(1), _Proc(0, b"ZIP")])
    monkeypatch.setattr(br.subprocess, "run", lambda *_a, **_k: next(calls))
    monkeypatch.setattr(br.time, "sleep", lambda _s: None)
    assert br.download_artifact_zip("o/r", 7) == b"ZIP"


def test_artifact_download_still_raises_after_the_last_attempt(monkeypatch):
    """Inverse control: the retry is bounded, and a persistent failure still surfaces as an error, never as empty bytes."""
    n = []

    def run(*_a, **_k):
        n.append(1)
        return _Proc(1)

    monkeypatch.setattr(br.subprocess, "run", run)
    monkeypatch.setattr(br.time, "sleep", lambda _s: None)
    with pytest.raises(br.ghx.GhBadOutputError):
        br.download_artifact_zip("o/r", 7)
    assert len(n) == br.GH_ATTEMPTS
