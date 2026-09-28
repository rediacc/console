"""`rediacc_ci.ci.budget_report`'s T3.2/T3.3 additions (PLAN-ci-time-budget, operator spec W): the lane/unit duration schema `.ci/config/lane-durations.json` gets written into, the parsers for the five T1.6 unit-duration artifact formats, and the `--refresh`/`--check` commands built on top of them.

FIXTURE-DRIVEN, NO NETWORK. Every test here drives a pure function directly, or a network-touching one (`compute_lane_durations`, `collect_unit_durations`) through its injectable `compute`/`list_artifacts`/`download` parameters -- the same seam the module's own docstring names as the reason those parameters exist: T1.6 has not landed, so there is no live artifact to record a fixture FROM, only the contract this module's own docstring defines. `refresh_lane_durations`/`check_lane_durations` are driven the same way, through their own `compute` parameter, so neither test calls `gh` or the real Actions API.

T1.1's `build_report`/`collect_class` machinery is retested only for its sample selection (the per-class branch scope and the sampled-run record, P2's 2026-09-28 fix). `fetch_runs`/`fetch_jobs`/`fetch_artifacts` ARE part of T3.1's own fix set (pagination, explicit sort, staleness) and are retested below, against `br.ghx.api_json` monkeypatched -- still no real `gh` call.

T3.1 ALSO CLOSES `scripts/gates/check-lane-budget.ts`'s own BLOCKER, so several tests below drive the real parser against classnames and describe titles MEASURED live from a real downloaded artifact (cited by run id in each test's own docstring) and check the produced ids against the ACTUALLY COMMITTED shard manifest (`.ci/config/shards/*.json`, read via `rediacc_ci.paths.repo_root()`) rather than a copy of it -- the same "prove it against the real committed file" shape `check-lane-budget.ts`'s own selftest uses for `quality-code`'s manifest.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from rediacc_ci import paths
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


def test_parse_gotestsum_junit_unit_ms_records_a_package_with_no_tests_at_its_suite_time():
    text = (
        "<testsuites>"
        '<testsuite tests="0" time="0.763" name="github.com/rediacc/renet/pkg/notests"></testsuite>'
        '<testsuite tests="1" time="9.0" name="github.com/rediacc/renet/pkg/foo">'
        '<testcase classname="github.com/rediacc/renet/pkg/foo" name="TestA" time="1.5"/>'
        "</testsuite></testsuites>"
    )
    out = br.parse_gotestsum_junit_unit_ms(text)
    # the no-test package gets its measured compile-and-run time; the tested one keeps the testcase sum, not the suite's 9.0 s
    assert out == {
        "github.com/rediacc/renet/pkg/notests": pytest.approx(763.0),
        "github.com/rediacc/renet/pkg/foo": pytest.approx(1500.0),
    }


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
        "job_p90_minutes": {},
        "gate_step_p90_seconds": {},
        "missing_artifact_lanes": [],
    }
    base.update(overrides)

    def compute(_repo, _workflow, _branch, _limit):
        return base

    return compute


def test_refresh_lane_durations_refuses_a_stale_sample_and_leaves_the_file_alone(tmp_path):
    path = tmp_path / "lane-durations.json"
    original = json.dumps({"refreshed_at": "2026-01-01T00:00:00Z", "concurrency": 20, "jobs": {}})
    path.write_text(original)
    compute = _fake_compute(
        jobs={"quality-code": 1.0},
        stale_sample=[
            "run 1 (created 2026-08-30T23:24:50Z) is 28.2 day(s) old, over the 14-day sample limit."
        ],
    )
    assert br.refresh_lane_durations(path, limit=10, compute=compute) == 1
    assert path.read_text() == original


def test_check_lane_durations_reports_a_stale_sample(tmp_path, capsys):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"jobs": {}, "units": {}}))
    compute = _fake_compute(stale_sample=["run 1 is 28.2 day(s) old"])
    assert br.check_lane_durations(path, limit=10, compute=compute) == 1
    assert "stale sample" in capsys.readouterr().err


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
                "unitParallelism": {"quality-pytest": 4},
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
    assert data["unitParallelism"] == {"quality-pytest": 4}
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


# --------------------------------------------------------------------------- T3.1: fetch_jobs/fetch_artifacts pagination ---------------------------------------------------------------------------


def test_fetch_jobs_paginates_beyond_the_first_page(monkeypatch):
    """FIRES-if-unfixed: MEASURED live, run 36358238015 -- 158 jobs across two Actions API pages; a single `per_page=100` call used to silently drop the last 58."""
    page1 = [{"id": i} for i in range(100)]
    page2 = [{"id": i} for i in range(100, 158)]

    def fake_api_json(path, **_kw):
        assert "per_page=100" in path
        if path.endswith("&page=1"):
            return {"total_count": 158, "jobs": page1}
        if path.endswith("&page=2"):
            return {"total_count": 158, "jobs": page2}
        raise AssertionError("unexpected page in %r" % path)

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    jobs = br.fetch_jobs("o/r", 1)
    assert [j["id"] for j in jobs] == list(range(158))


def test_fetch_jobs_stops_at_a_short_page_even_with_no_total_count(monkeypatch):
    """CONTROL: a page shorter than per_page ends the walk even when `total_count` is absent, rather than looping forever."""
    calls = []

    def fake_api_json(path, **_kw):
        calls.append(path)
        return {"jobs": [{"id": 1}, {"id": 2}]}

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    assert br.fetch_jobs("o/r", 1) == [{"id": 1}, {"id": 2}]
    assert len(calls) == 1


def test_fetch_jobs_stops_once_total_count_is_reached(monkeypatch):
    """CONTROL: a full page whose `total_count` is already satisfied does not fetch a third page it does not need."""
    calls = []

    def fake_api_json(path, **_kw):
        calls.append(path)
        page = int(path.rsplit("page=", 1)[1])
        if page == 1:
            return {"total_count": 100, "jobs": [{"id": i} for i in range(100)]}
        raise AssertionError("should not fetch a second page once total_count is met")

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    jobs = br.fetch_jobs("o/r", 1)
    assert len(jobs) == 100
    assert len(calls) == 1


def test_fetch_artifacts_paginates_beyond_the_first_page(monkeypatch):
    """Same pagination fix as `fetch_jobs`, over `.../artifacts` (also `per_page=100` before this box)."""
    page1 = [{"id": i, "name": "a-%d" % i} for i in range(100)]
    page2 = [{"id": i, "name": "a-%d" % i} for i in range(100, 130)]

    def fake_api_json(path, **_kw):
        if path.endswith("&page=1"):
            return {"total_count": 130, "artifacts": page1}
        if path.endswith("&page=2"):
            return {"total_count": 130, "artifacts": page2}
        raise AssertionError("unexpected page in %r" % path)

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    artifacts = br.fetch_artifacts("o/r", 1)
    assert len(artifacts) == 130


def test_fetch_artifacts_stops_at_a_short_page(monkeypatch):
    def fake_api_json(_path, **_kw):
        return {"artifacts": [{"id": 1}]}

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    assert br.fetch_artifacts("o/r", 1) == [{"id": 1}]


# --------------------------------------------------------------------------- T3.1: fetch_runs sorting and sample staleness ---------------------------------------------------------------------------


def test_fetch_runs_sorts_by_created_at_descending_explicitly(monkeypatch):
    """FIRES-if-unfixed: MEASURED live, 2026-09-27 -- the identical query returned an out-of-order page (an August-dated run after September-dated ones), so slicing on the API's own order silently picked stale runs."""
    runs = [
        {"id": 1, "created_at": "2026-08-01T00:00:00Z"},
        {"id": 2, "created_at": "2026-09-20T00:00:00Z"},
        {"id": 3, "created_at": "2026-09-10T00:00:00Z"},
    ]
    monkeypatch.setattr(br.ghx, "api_json", lambda *_a, **_k: {"workflow_runs": runs})
    result = br.fetch_runs("o/r", "ci.yml", "pull_request", None, "completed", 2)
    assert [r["id"] for r in result] == [2, 3]


def test_stale_sample_findings_fires_past_14_days():
    now = br._iso_to_epoch("2026-09-28T00:00:00Z")
    runs = [{"id": 9, "created_at": "2026-09-10T00:00:00Z"}]
    findings = br.stale_sample_findings(runs, now=now)
    assert findings
    assert "18.0 day" in findings[0]
    assert "14-day" in findings[0]


def test_stale_sample_findings_silent_within_the_limit():
    now = br._iso_to_epoch("2026-09-28T00:00:00Z")
    runs = [{"id": 9, "created_at": "2026-09-20T00:00:00Z"}]
    assert br.stale_sample_findings(runs, now=now) == []


def test_stale_sample_findings_ignores_a_run_with_no_created_at():
    assert br.stale_sample_findings([{"id": 1}], now=0.0) == []


def test_fetch_runs_warns_loudly_on_a_stale_sample(monkeypatch, capsys):
    old_run = {"id": 9, "created_at": "2026-01-01T00:00:00Z"}
    monkeypatch.setattr(br.ghx, "api_json", lambda *_a, **_k: {"workflow_runs": [old_run]})
    br.fetch_runs("o/r", "ci.yml", "pull_request", None, "completed", 1)
    err = capsys.readouterr().err
    assert "over the 14-day sample limit" in err


def test_fetch_runs_silent_on_a_fresh_sample(monkeypatch, capsys):
    fresh_run = {"id": 9, "created_at": "2026-09-27T00:00:00Z"}
    monkeypatch.setattr(br.ghx, "api_json", lambda *_a, **_k: {"workflow_runs": [fresh_run]})
    br.fetch_runs("o/r", "ci.yml", "pull_request", None, "completed", 1)
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------- P2 sample: the date window, per-class branch scope, and the sampled-run record ---------------------------------------------------------------------------


def test_sample_window_param_bounds_the_query_to_the_age_limit():
    now = br._iso_to_epoch("2026-09-28T12:00:00Z")
    assert br.sample_window_param(now) == "created=%3E%3D2026-09-14"


def test_fetch_runs_puts_the_date_window_into_the_request(monkeypatch):
    """FIRES-if-unfixed: MEASURED 2026-09-28 -- `event=pull_request&status=completed` with no `created` bound answered ten August runs while that morning's PR runs existed; the same query with `created=>=` answered today's. Sorting a page that holds no fresh run cannot fix it, so the bound must be in the request."""
    seen: list[str] = []

    def fake_api_json(path, **_kw):
        seen.append(path)
        return {"workflow_runs": []}

    monkeypatch.setattr(br.ghx, "api_json", fake_api_json)
    now = br._iso_to_epoch("2026-09-28T12:00:00Z")
    br.fetch_runs("o/r", "ci.yml", "pull_request", "0923-1", "completed", 10, now=now)
    assert len(seen) == 1
    assert "created=%3E%3D2026-09-14" in seen[0]
    assert "branch=0923-1" in seen[0]
    assert "status=completed" in seen[0]


def test_class_branch_filter_scopes_pr_full_to_a_pr_branch():
    """FIRES-if-unfixed: `--branch 0923-1` used to filter only `main-push`, so `pr-full` sampled every branch's runs and its table carried no E2E job of 0923-1."""
    assert br.class_branch_filter("pr-full", "0923-1") == "0923-1"
    assert br.class_branch_filter("main-push", "0923-1") == "0923-1"
    assert br.class_branch_filter("schedule", "0923-1") is None


def test_class_branch_filter_keeps_pr_full_repo_wide_on_the_default_branch():
    assert br.class_branch_filter("pr-full", br.DEFAULT_BRANCH) is None
    assert br.class_branch_filter("main-push", br.DEFAULT_BRANCH) == br.DEFAULT_BRANCH


def test_build_report_samples_pr_full_on_the_requested_branch(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    def fake_fetch_runs(_repo, _wf, event, branch, _status, _limit, **_kw):
        calls.append((event, branch))
        return []

    monkeypatch.setattr(br, "fetch_runs", fake_fetch_runs)
    monkeypatch.setattr(br, "build_display_graph", lambda *_a: {})
    br.build_report("o/r", "ci.yml", "0923-1", 10, "completed")
    assert ("pull_request", "0923-1") in calls
    assert ("push", "0923-1") in calls
    assert ("schedule", None) in calls


def test_collect_class_records_which_runs_it_sampled(monkeypatch):
    """FIRES-if-unfixed: the JSON carried only a `runs_sampled` COUNT, so a report drawn from the wrong runs could not be told apart from a right one."""
    runs = [
        {
            "id": 36427771349,
            "created_at": "2026-09-28T13:19:13Z",
            "head_branch": "0923-1",
            "event": "pull_request",
            "conclusion": "failure",
            "run_attempt": 1,
            "other": "dropped",
        }
    ]
    job = {
        "name": "Tests + Infra / E2E Ceph",
        "conclusion": "success",
        "created_at": "2026-09-28T13:30:00Z",
        "started_at": "2026-09-28T13:34:44Z",
        "completed_at": "2026-09-28T13:46:17Z",
    }
    monkeypatch.setattr(br, "fetch_runs", lambda *_a, **_k: runs)
    monkeypatch.setattr(br, "fetch_jobs", lambda *_a: [job])
    data = br.collect_class("o/r", "ci.yml", "pull_request", "0923-1", "completed", 10)
    assert data["runs_sampled"] == 1
    assert data["branch_filter"] == "0923-1"
    assert data["runs"] == [{k: v for k, v in runs[0].items() if k != "other"}]
    assert data["jobs"]["Tests + Infra / E2E Ceph"]["max"] == 11.6


# --------------------------------------------------------------------------- T3.1: pytest/renet-integration classname keying (BLOCKER item 2) ---------------------------------------------------------------------------


def test_classname_to_module_relpath_keeps_the_leading_dot_of_a_dot_prefixed_testpath():
    """FIRES-if-unfixed: MEASURED live (run 36358238015) -- a blind `classname.replace(".", "/")` turns ".ci.rediacc_ci.tests.test_x" into "/ci/rediacc_ci/tests/test_x.py" (a leading SLASH), not the manifest's ".ci/rediacc_ci/tests/test_x.py" (a leading DOT)."""
    assert (
        br._classname_to_module_relpath(".ci.rediacc_ci.tests.test_housekeeping_cleanup_versions")
        == ".ci/rediacc_ci/tests/test_housekeeping_cleanup_versions.py"
    )


def test_classname_to_module_relpath_keeps_the_leading_dot_under_dot_claude_too():
    assert (
        br._classname_to_module_relpath(".claude.rediacc_hooks.tests.test_hooks_fixtures")
        == ".claude/rediacc_hooks/tests/test_hooks_fixtures.py"
    )


def test_classname_to_module_relpath_drops_a_trailing_pascalcase_class_segment():
    """FIRES-if-unfixed: MEASURED live (run 36332059919) -- every `private/renet/tests/integration` file wraps its tests in a `class TestXxx:`, so a blind replace produced "TestPortAutoSync.py" instead of the file the class lives in."""
    assert (
        br._classname_to_module_relpath("tests.integration.test_config_autosync.TestPortAutoSync")
        == "tests/integration/test_config_autosync.py"
    )


def test_classname_to_module_relpath_unchanged_with_no_class_segment():
    assert (
        br._classname_to_module_relpath("tests.integration.test_daemon_lifecycle")
        == "tests/integration/test_daemon_lifecycle.py"
    )


def test_parse_pytest_junit_unit_ms_falls_back_correctly_for_quality_pytest_real_shape():
    """The exact junit shape MEASURED live (run 36358238015, quality-pytest shard 3): no `file` attribute at all."""
    text = (
        "<testsuites><testsuite>"
        '<testcase classname=".ci.rediacc_ci.tests.test_housekeeping_cleanup_versions" '
        'name="test_both_subjects_exist@housekeeping-cleanup-versions" time="0.025" />'
        "</testsuite></testsuites>"
    )
    out = br.parse_pytest_junit_unit_ms(text, "quality-pytest")
    assert out == {
        "pytest:.ci/rediacc_ci/tests/test_housekeeping_cleanup_versions.py": pytest.approx(25.0)
    }


def test_parse_pytest_junit_unit_ms_falls_back_correctly_for_renet_integration_real_shape():
    """The exact junit shape MEASURED live (run 36332059919, test-renet-integration shard 1): a class-wrapped test, no `file` attribute."""
    text = (
        "<testsuites><testsuite>"
        '<testcase classname="tests.integration.test_config_autosync.TestPortAutoSync" '
        'name="test_default_port_when_no_env_file" time="120.131" />'
        "</testsuite></testsuites>"
    )
    out = br.parse_pytest_junit_unit_ms(text, "test-renet-integration")
    assert out == {"renet-integration:test_config_autosync.py": pytest.approx(120131.0)}


# --------------------------------------------------------------------------- CONTROL: real classname shapes land in the committed manifests ---------------------------------------------------------------------------


def test_quality_pytest_classname_ids_land_in_the_committed_manifest():
    """The BLOCKER this box closes, in its own words: "quality-pytest ... unit p90s are keyed by junit classname ... and match no committed manifest id". Drives the real parser over classnames MEASURED from a live artifact (run 36358238015) and checks the produced ids against the ACTUALLY COMMITTED shard manifest, not a copy of it."""
    root = paths.repo_root()
    manifest = json.loads((root / ".ci/config/shards/quality-pytest.json").read_text())
    manifest_ids = {i for leg in manifest["legs"] for i in leg["ids"]}
    real_classnames = [
        ".ci.rediacc_ci.tests.test_housekeeping_cleanup_versions",
        ".ci.rediacc_ci.tests.test_release_assert_artifact_version",
        ".claude.rediacc_hooks.tests.test_hooks_fixtures",
        ".claude.rediacc_hooks.tests.test_guards_differential",
    ]
    text = (
        "<testsuites><testsuite>"
        + "".join('<testcase classname="%s" name="t" time="1.0" />' % c for c in real_classnames)
        + "</testsuite></testsuites>"
    )
    ids = br.parse_pytest_junit_unit_ms(text, "quality-pytest")
    assert len(ids) == len(real_classnames)
    for unit_id in ids:
        assert unit_id in manifest_ids, "%s not in the committed manifest" % unit_id


def test_renet_integration_classname_ids_land_in_the_committed_manifest():
    """Same control, other lane: classnames MEASURED from run 36332059919's test-renet-integration shard 1."""
    root = paths.repo_root()
    manifest = json.loads((root / ".ci/config/shards/test-renet-integration.json").read_text())
    manifest_ids = {i for leg in manifest["legs"] for i in leg["ids"]}
    real_classnames = [
        "tests.integration.test_config_autosync.TestPortAutoSync",
        "tests.integration.test_config_autosync.TestDomainAutoSync",
        "tests.integration.test_daemon_proxy_sync.TestDaemonProxyCoordination",
    ]
    text = (
        "<testsuites><testsuite>"
        + "".join('<testcase classname="%s" name="t" time="1.0" />' % c for c in real_classnames)
        + "</testsuite></testsuites>"
    )
    ids = br.parse_pytest_junit_unit_ms(text, "test-renet-integration")
    # TestPortAutoSync/TestDomainAutoSync share test_config_autosync.py; TestDaemonProxyCoordination is a second file.
    assert len(ids) == 2
    for unit_id in ids:
        assert unit_id in manifest_ids, "%s not in the committed manifest" % unit_id


# --------------------------------------------------------------------------- T3.1: e2e-workers describe-block buckets (BLOCKER item 5, #partN) ---------------------------------------------------------------------------

_FIXTURE_RUN_E2E_SH = """
declare -A E2E_SHARD_GREP_BUCKETS=(
    ["part1"]="PostgreSQL Data Persistence @bridge @integration|Repository Fork Data Inheritance @bridge @integration"
    ["part2"]="Multiple Fork Independence @bridge @integration|Fork Data Integrity @bridge @integration"
    ["part3"]="Large Data Volume Fork @bridge @integration|Service Restart Persistence @bridge @integration"
)
"""


def _write_fixture_run_e2e_sh(tmp_path):
    script_dir = tmp_path / ".ci" / "scripts" / "test"
    script_dir.mkdir(parents=True)
    (script_dir / "run-e2e.sh").write_text(_FIXTURE_RUN_E2E_SH, encoding="utf-8")
    return tmp_path


def test_e2e_shard_bucket_titles_reads_the_bash_array(tmp_path):
    root = _write_fixture_run_e2e_sh(tmp_path)
    titles = br._e2e_shard_bucket_titles(root)
    assert titles["PostgreSQL Data Persistence @bridge @integration"] == "part1"
    assert titles["Repository Fork Data Inheritance @bridge @integration"] == "part1"
    assert titles["Large Data Volume Fork @bridge @integration"] == "part3"


def test_e2e_shard_bucket_titles_missing_script_is_an_empty_map_not_a_crash(tmp_path):
    assert br._e2e_shard_bucket_titles(tmp_path) == {}


def _pw_describe_suite(file, describe_title, duration):
    return {
        "title": describe_title,
        "specs": [{"file": file, "tests": [{"results": [{"duration": duration}]}]}],
    }


def test_parse_playwright_unit_ms_buckets_a_describe_block_into_its_partn_id():
    """FIRES-if-unfixed: the shard manifest's own three `13-postgres-fork-isolation.test.ts#partN` units have no sample at all. MEASURED live shape (run 36358238015): the Playwright JSON nests one suite per describe directly under the file-level suite."""
    bucket_titles = {"PostgreSQL Data Persistence @bridge @integration": "part1"}
    file = "13-postgres-fork-isolation.test.ts"
    text = json.dumps(
        {
            "suites": [
                {
                    "title": file,
                    "file": file,
                    "suites": [
                        _pw_describe_suite(
                            file, "PostgreSQL Data Persistence @bridge @integration", 5000
                        )
                    ],
                }
            ]
        }
    )
    out = br.parse_playwright_unit_ms(text, "test-e2e-workers", bucket_titles=bucket_titles)
    assert out == {"e2e-workers:13-postgres-fork-isolation.test.ts#part1": 5000.0}


def test_parse_playwright_unit_ms_sums_two_describes_sharing_one_bucket():
    bucket_titles = {
        "PostgreSQL Data Persistence @bridge @integration": "part1",
        "Repository Fork Data Inheritance @bridge @integration": "part1",
    }
    file = "13-postgres-fork-isolation.test.ts"
    text = json.dumps(
        {
            "suites": [
                {
                    "title": file,
                    "file": file,
                    "suites": [
                        _pw_describe_suite(
                            file, "PostgreSQL Data Persistence @bridge @integration", 1000
                        ),
                        _pw_describe_suite(
                            file, "Repository Fork Data Inheritance @bridge @integration", 2000
                        ),
                    ],
                }
            ]
        }
    )
    out = br.parse_playwright_unit_ms(text, "test-e2e-workers", bucket_titles=bucket_titles)
    assert out == {"e2e-workers:13-postgres-fork-isolation.test.ts#part1": 3000.0}


def test_parse_playwright_unit_ms_leaves_an_unbucketed_file_whole():
    """CONTROL: a file whose describe titles are not in bucket_titles keeps the pre-existing whole-file grouping."""
    bucket_titles = {"PostgreSQL Data Persistence @bridge @integration": "part1"}
    file = "01-system-checks.test.ts"
    text = json.dumps(
        {
            "suites": [
                {
                    "title": file,
                    "file": file,
                    "suites": [_pw_describe_suite(file, "System Functions @bridge @smoke", 743)],
                }
            ]
        }
    )
    out = br.parse_playwright_unit_ms(text, "test-e2e-workers", bucket_titles=bucket_titles)
    assert out == {"e2e-workers:01-system-checks.test.ts": 743.0}


def test_parse_playwright_unit_ms_with_no_bucket_titles_is_unchanged():
    """INVERSE control: the default (no bucket_titles) behaves exactly as before this box -- whole-file grouping, no '#'."""
    text = json.dumps(
        {
            "suites": [
                {"specs": [{"file": "a.spec.ts", "tests": [{"results": [{"duration": 1000}]}]}]}
            ]
        }
    )
    assert br.parse_playwright_unit_ms(text, "test-e2e-workers") == {
        "e2e-workers:a.spec.ts": 1000.0
    }


def test_e2e_workers_bucket_ids_land_in_the_committed_manifest():
    """The BLOCKER's other named gap: the three `#partN` units have no sample. Reads the REAL `run-e2e.sh` bucket table and the REAL committed `test-e2e-workers.json` manifest (both via `paths.repo_root()`, no fixture copy) and checks the produced ids against it."""
    root = paths.repo_root()
    bucket_titles = br._e2e_shard_bucket_titles(root)
    assert bucket_titles, "run-e2e.sh's E2E_SHARD_GREP_BUCKETS did not parse"
    manifest = json.loads((root / ".ci/config/shards/test-e2e-workers.json").read_text())
    manifest_ids = {i for leg in manifest["legs"] for i in leg["ids"]}
    file = "13-postgres-fork-isolation.test.ts"
    text = json.dumps(
        {
            "suites": [
                {
                    "title": file,
                    "file": file,
                    "suites": [_pw_describe_suite(file, title, 1000) for title in bucket_titles],
                }
            ]
        }
    )
    ids = br.parse_playwright_unit_ms(text, "test-e2e-workers", bucket_titles=bucket_titles)
    bucketed = {i for i in ids if "#" in i}
    assert bucketed == {
        "e2e-workers:13-postgres-fork-isolation.test.ts#part1",
        "e2e-workers:13-postgres-fork-isolation.test.ts#part2",
        "e2e-workers:13-postgres-fork-isolation.test.ts#part3",
    }
    for unit_id in bucketed:
        assert unit_id in manifest_ids, "%s not in the committed manifest" % unit_id


# --------------------------------------------------------------------------- T3.1: job_p90_minutes (check 2's whole-job p90, BLOCKER item 3) ---------------------------------------------------------------------------


def test_compute_lane_durations_reports_job_p90_minutes_by_display_name(tmp_path, monkeypatch):
    """FIRES-if-unfixed: `check-lane-budget.ts`'s own BLOCKER -- "no whole-job p90 exists for check 2 over the 63 non-lane jobs"."""
    root = _write_fixture_workflows(tmp_path)

    def fake_fetch_runs(_repo, _workflow, event, _branch, _status, _limit):
        return [{"id": 1, "created_at": "2026-09-27T00:00:00Z"}] if event == "pull_request" else []

    def fake_fetch_jobs(_repo, _run_id):
        return [
            {
                "name": "Tests + Infra / E2E K8s Ceph",
                "conclusion": "success",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:14:00Z",
            }
        ]

    monkeypatch.setattr(br, "fetch_runs", fake_fetch_runs)
    monkeypatch.setattr(br, "fetch_jobs", fake_fetch_jobs)
    computed = br.compute_lane_durations(
        root=root, list_artifacts=lambda *_a: [], download=lambda *_a: b""
    )
    assert computed["job_p90_minutes"] == {"Tests + Infra / E2E K8s Ceph": pytest.approx(14.0)}


def test_compute_lane_durations_job_p90_minutes_is_success_only(tmp_path, monkeypatch):
    root = _write_fixture_workflows(tmp_path)

    def fake_fetch_runs(_repo, _workflow, event, _branch, _status, _limit):
        return [{"id": 1, "created_at": "2026-09-27T00:00:00Z"}] if event == "pull_request" else []

    def fake_fetch_jobs(_repo, _run_id):
        return [
            {
                "name": "flaky job",
                "conclusion": "failure",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:30:00Z",
            }
        ]

    monkeypatch.setattr(br, "fetch_runs", fake_fetch_runs)
    monkeypatch.setattr(br, "fetch_jobs", fake_fetch_jobs)
    computed = br.compute_lane_durations(
        root=root, list_artifacts=lambda *_a: [], download=lambda *_a: b""
    )
    assert computed["job_p90_minutes"] == {}


def test_refresh_lane_durations_writes_job_p90_minutes(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    compute = _fake_compute(job_p90_minutes={"Tests + Infra / E2E K8s Ceph": 14.0})
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    data = json.loads(path.read_text())
    assert data["job_p90_minutes"] == {"Tests + Infra / E2E K8s Ceph": 14.0}


def test_refresh_lane_durations_merges_job_p90_minutes_with_existing(tmp_path):
    path = tmp_path / "lane-durations.json"
    path.write_text(
        json.dumps(
            {
                "refreshed_at": "2026-01-01T00:00:00Z",
                "concurrency": 20,
                "jobs": {},
                "units": {},
                "job_p90_minutes": {"Quality / Content": 3.0},
            }
        )
    )
    compute = _fake_compute(job_p90_minutes={"Tests + Infra / E2E K8s Ceph": 14.0})
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    data = json.loads(path.read_text())
    assert data["job_p90_minutes"] == {
        "Quality / Content": 3.0,
        "Tests + Infra / E2E K8s Ceph": 14.0,
    }


def test_refresh_lane_durations_still_refuses_when_only_job_p90_minutes_would_be_empty(tmp_path):
    """CONTROL: `job_p90_minutes` joins the "nothing measured" refusal set -- an empty result across all four sections still refuses to stamp `refreshed_at`."""
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    rc = br.refresh_lane_durations(path, limit=10, compute=_fake_compute())
    assert rc == 1
    assert json.loads(path.read_text())["refreshed_at"] is None


def test_prune_units_to_manifests_drops_ids_no_manifest_names(tmp_path):
    """A merged-in id its lane's manifest no longer names is dropped; a named one, and one from a lane with no manifest, are kept."""
    shards = tmp_path / ".ci" / "config" / "shards"
    shards.mkdir(parents=True)
    (shards / "quality-pytest.json").write_text(
        json.dumps(
            {"lane": "quality-pytest", "of": 1, "legs": [{"index": 1, "ids": ["pytest:.ci/a.py"]}]}
        )
    )
    (shards / "test-renet-go.json").write_text(
        json.dumps(
            {"lane": "test-renet-go", "of": 1, "legs": [{"index": 1, "ids": ["example.com/p"]}]}
        )
    )
    units = {
        "pytest:.ci/a.py": 1,
        "pytest:/ci/a.py": 2,
        "example.com/p": 3,
        "example.com/gone": 4,
        "battery:x": 5,
    }
    assert br.prune_units_to_manifests(units, tmp_path) == {
        "pytest:.ci/a.py": 1,
        "example.com/p": 3,
        "battery:x": 5,
    }


def test_prune_units_to_manifests_keeps_everything_without_manifests(tmp_path):
    """Inverse control: with no manifests on disk nothing can be judged stale, so nothing is dropped."""
    units = {"pytest:/ci/a.py": 2, "example.com/gone": 4}
    assert br.prune_units_to_manifests(units, tmp_path) == units


# --------------------------------------------------------------------------- gate_step_p90_seconds (CI-representative tier timing) ---------------------------------------------------------------------------


def _write_gates_lock(root, gates):
    lock_dir = root / "scripts" / "ci-runner"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "gates.lock.json").write_text(json.dumps(gates), encoding="utf-8")
    return root


def test_load_gate_ci_steps_reads_only_kind_step_gates(tmp_path):
    _write_gates_lock(
        tmp_path,
        [
            {
                "id": "check:a",
                "ci": {"kind": "step", "job": "quality-code", "step": "Lint"},
            },
            {"id": "check:b", "ci": {"kind": "local-only"}},
            {"id": "check:c", "ci": {"kind": "test"}},
            {"id": "check:d"},
        ],
    )
    assert br.load_gate_ci_steps(tmp_path) == {"check:a": ("quality-code", "Lint")}


def test_load_gate_ci_steps_missing_or_malformed_lock_is_empty(tmp_path):
    assert br.load_gate_ci_steps(tmp_path) == {}
    (tmp_path / "scripts" / "ci-runner").mkdir(parents=True)
    (tmp_path / "scripts" / "ci-runner" / "gates.lock.json").write_text("not json")
    assert br.load_gate_ci_steps(tmp_path) == {}


def test_exclusive_ci_steps_drops_a_pair_shared_by_two_gates(tmp_path):
    """FIRES-if-unfixed: MEASURED 2026-09-28, `ci-quality.yml`'s `i18n` step chains 27 gates into one `npm run check:i18n` and measured 36.1s in CI while five of those ids' own standalone local costs were 2-9s each -- attributing the whole step to each id would wrongly tell every fast one to mark `slow: true`."""
    _write_gates_lock(
        tmp_path,
        [
            {"id": "check:shared-a", "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"}},
            {"id": "check:shared-b", "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"}},
            {"id": "check:solo", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}},
        ],
    )
    assert br._exclusive_ci_steps(tmp_path) == {"check:solo": ("quality-code", "Lint")}


def test_exclusive_ci_steps_control_a_pair_occupied_by_one_gate_is_kept(tmp_path):
    _write_gates_lock(
        tmp_path,
        [{"id": "check:solo", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    assert br._exclusive_ci_steps(tmp_path) == {"check:solo": ("quality-code", "Lint")}


def _step_job(name, steps):
    return {"name": name, "conclusion": "success", "steps": steps}


def test_gate_step_seconds_measures_success_only_step_wall_time(tmp_path):
    _write_gates_lock(
        tmp_path,
        [{"id": "check:a", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    patterns = {"quality-code": br._display_name_pattern("Quality / Code", False)}
    jobs_by_run = [
        [
            _step_job(
                "Quality / Code",
                [
                    {
                        "name": "Lint",
                        "conclusion": "success",
                        "started_at": "2026-09-27T00:00:00Z",
                        "completed_at": "2026-09-27T00:00:10Z",
                    }
                ],
            )
        ]
    ]
    assert br.gate_step_seconds(tmp_path, patterns, jobs_by_run) == {"check:a": pytest.approx(10.0)}


def test_gate_step_seconds_skips_a_job_with_no_display_pattern(tmp_path):
    """A gate whose ci.job names a lane with no pattern yet (not split out of its reusable workflow) contributes no entry, never a guess."""
    _write_gates_lock(
        tmp_path,
        [{"id": "check:a", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    jobs_by_run = [
        [
            _step_job(
                "Quality / Code",
                [
                    {
                        "name": "Lint",
                        "conclusion": "success",
                        "started_at": "2026-09-27T00:00:00Z",
                        "completed_at": "2026-09-27T00:00:10Z",
                    }
                ],
            )
        ]
    ]
    assert br.gate_step_seconds(tmp_path, {}, jobs_by_run) == {}


def test_gate_step_seconds_skips_a_non_success_step_and_a_non_success_job(tmp_path):
    _write_gates_lock(
        tmp_path,
        [{"id": "check:a", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    patterns = {"quality-code": br._display_name_pattern("Quality / Code", False)}
    step_failed_job = _step_job(
        "Quality / Code",
        [
            {
                "name": "Lint",
                "conclusion": "failure",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:00:10Z",
            }
        ],
    )
    job_failed = {
        "name": "Quality / Code",
        "conclusion": "failure",
        "steps": [
            {
                "name": "Lint",
                "conclusion": "success",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:00:10Z",
            }
        ],
    }
    assert br.gate_step_seconds(tmp_path, patterns, [[step_failed_job]]) == {}
    assert br.gate_step_seconds(tmp_path, patterns, [[job_failed]]) == {}


def test_gate_step_seconds_never_attributes_a_shared_step_to_either_gate_sharing_it(tmp_path):
    """The end-to-end shape of the composite-step bug: two gates declared against the SAME (job, step) both get excluded, even though the step ran and would otherwise measure cleanly."""
    _write_gates_lock(
        tmp_path,
        [
            {"id": "check:shared-a", "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"}},
            {"id": "check:shared-b", "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"}},
        ],
    )
    patterns = {"quality-i18n": br._display_name_pattern("Quality / i18n", False)}
    jobs_by_run = [
        [
            _step_job(
                "Quality / i18n",
                [
                    {
                        "name": "i18n",
                        "conclusion": "success",
                        "started_at": "2026-09-27T00:00:00Z",
                        "completed_at": "2026-09-27T00:00:36Z",
                    }
                ],
            )
        ]
    ]
    assert br.gate_step_seconds(tmp_path, patterns, jobs_by_run) == {}


def test_prune_gate_steps_to_lock_drops_ids_no_longer_in_the_lock(tmp_path):
    _write_gates_lock(
        tmp_path,
        [{"id": "check:kept", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    gate_steps = {"check:kept": 5.0, "check:retired": 9.0}
    assert br.prune_gate_steps_to_lock(gate_steps, tmp_path) == {"check:kept": 5.0}


def test_prune_gate_steps_to_lock_drops_an_id_whose_step_became_shared(tmp_path):
    """A stale entry for an id whose (job, step) now has a second occupant is pruned too -- not just an id the lock dropped outright -- so a composite-step mis-attribution from a stale write does not linger forever."""
    _write_gates_lock(
        tmp_path,
        [
            {
                "id": "check:now-shared",
                "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"},
            },
            {
                "id": "check:new-sibling",
                "ci": {"kind": "step", "job": "quality-i18n", "step": "i18n"},
            },
        ],
    )
    assert br.prune_gate_steps_to_lock({"check:now-shared": 36.1}, tmp_path) == {}


def test_prune_gate_steps_to_lock_drops_an_id_whose_gate_kind_changed(tmp_path):
    """A gate still in the lock but no longer `kind: step` (moved local-only or test) is dropped too -- not just an id removed outright."""
    _write_gates_lock(
        tmp_path,
        [{"id": "check:moved", "ci": {"kind": "local-only"}}],
    )
    assert br.prune_gate_steps_to_lock({"check:moved": 5.0}, tmp_path) == {}


def _lane_durations_path(root):
    """`refresh_lane_durations` derives the repo root for pruning as `path.parent.parent.parent`, matching the real `.ci/config/lane-durations.json` -> repo-root nesting; a fixture that wants pruning against a real `root` must nest its lane-durations.json the same three levels down."""
    config_dir = root / ".ci" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "lane-durations.json"


def test_refresh_lane_durations_writes_gate_step_p90_seconds(tmp_path):
    path = _lane_durations_path(tmp_path)
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    _write_gates_lock(
        tmp_path,
        [
            {
                "id": "check:ci-embed-asset-versions",
                "ci": {
                    "kind": "step",
                    "job": "quality-go",
                    "step": "Check embedded asset versions match their pins",
                },
            }
        ],
    )
    compute = _fake_compute(gate_step_p90_seconds={"check:ci-embed-asset-versions": 1.2})
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    data = json.loads(path.read_text())
    assert data["gate_step_p90_seconds"] == {"check:ci-embed-asset-versions": 1.2}


def test_refresh_lane_durations_merges_and_prunes_gate_step_p90_seconds(tmp_path):
    """A previously-committed id the lock no longer names as a step gate is dropped on refresh, the same ADD-and-PRUNE shape `units` already gets from `prune_units_to_manifests`."""
    path = _lane_durations_path(tmp_path)
    path.write_text(
        json.dumps(
            {
                "refreshed_at": "2026-01-01T00:00:00Z",
                "concurrency": 20,
                "jobs": {},
                "units": {},
                "gate_step_p90_seconds": {"check:kept": 3.0, "check:retired": 99.0},
            }
        )
    )
    _write_gates_lock(
        tmp_path,
        [{"id": "check:kept", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )
    compute = _fake_compute(gate_step_p90_seconds={"check:kept": 4.0})
    rc = br.refresh_lane_durations(path, limit=10, compute=compute)
    assert rc == 0
    data = json.loads(path.read_text())
    assert data["gate_step_p90_seconds"] == {"check:kept": 4.0}


def test_refresh_lane_durations_still_refuses_when_only_gate_step_p90_seconds_would_be_empty(
    tmp_path,
):
    """CONTROL: `gate_step_p90_seconds` joins the "nothing measured" refusal set."""
    path = tmp_path / "lane-durations.json"
    path.write_text(json.dumps({"refreshed_at": None, "concurrency": 20, "jobs": {}, "units": {}}))
    rc = br.refresh_lane_durations(path, limit=10, compute=_fake_compute())
    assert rc == 1
    assert json.loads(path.read_text())["refreshed_at"] is None


def test_compute_lane_durations_reports_gate_step_p90_seconds(tmp_path, monkeypatch):
    """Integration: a fixture ci.yml/ci-quality.yml plus a fixture gates.lock.json produce a gate's own step p90 from the same PR-full job sample job_p90_minutes already walks -- no extra network call."""
    root = _write_fixture_workflows(tmp_path)
    _write_gates_lock(
        root,
        [{"id": "check:lint", "ci": {"kind": "step", "job": "quality-code", "step": "Lint"}}],
    )

    def fake_fetch_runs(_repo, _workflow, event, _branch, _status, _limit):
        return [{"id": 1, "created_at": "2026-09-27T00:00:00Z"}] if event == "pull_request" else []

    def fake_fetch_jobs(_repo, _run_id):
        return [
            {
                "name": "Quality / Code (1)",
                "conclusion": "success",
                "started_at": "2026-09-27T00:00:00Z",
                "completed_at": "2026-09-27T00:14:00Z",
                "steps": [
                    {
                        "name": "Lint",
                        "conclusion": "success",
                        "started_at": "2026-09-27T00:00:00Z",
                        "completed_at": "2026-09-27T00:00:30Z",
                    }
                ],
            }
        ]

    monkeypatch.setattr(br, "fetch_runs", fake_fetch_runs)
    monkeypatch.setattr(br, "fetch_jobs", fake_fetch_jobs)
    computed = br.compute_lane_durations(
        root=root, list_artifacts=lambda *_a: [], download=lambda *_a: b""
    )
    assert computed["gate_step_p90_seconds"] == {"check:lint": pytest.approx(30.0)}
