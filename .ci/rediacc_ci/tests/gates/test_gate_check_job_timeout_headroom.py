"""`.ci/scripts/quality/check_job_timeout_headroom.py` after D-W2/T3.4 (PLAN-ci-time-budget): its baseline moved from its own `job-timeout-baseline.json` into `.ci/config/lane-durations.json`'s `job_max_seconds` section, which carries its OWN `refreshed_at` independent of that file's top-level one.

WHY A REAL COPY OF THE SCRIPT AND NOT AN IMPORT. `main()` resolves its root as `pathlib.Path(__file__).resolve().parents[3]`, so a test that imports the module in-process cannot hand it a fake tree: the path is derived from where the FILE lives on disk, not from an argument or the cwd. `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`'s own `run_against_empty_tree` solves the identical problem by copying the real trees into a temp directory at the same relative depth and running the copy; `_tree()` below does the same, scoped to exactly the two things this script reads (its own file, one workflow file, and `.ci/config/lane-durations.json`).

`gh` IS FAKED ON PATH, never called for real: `refresh()` shells out to `gh run list` then `gh api .../jobs?...`, and the fake below routes on argv[0:2] rather than reimplementing `--jq` -- it returns exactly what `gh ... --jq EXPR` would have printed for the fixture data, not a real jq evaluation.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT_REL = ".ci/scripts/quality/check_job_timeout_headroom.py"
WORKFLOW_REL = ".github/workflows/ci.yml"
LANE_DURATIONS_REL = ".ci/config/lane-durations.json"
REAL_SCRIPT = paths.from_root(SCRIPT_REL)

# D-W2: a job ci.yml (or a workflow it calls) reaches is the lane budget's, not this gate's. The two baseline jobs therefore live in a workflow ci.yml does NOT call, so the tests below exercise the 1.5x rule this gate keeps for non-budgeted jobs; the D-W2 tests move them into the ci.yml graph.
FIXTURE_WORKFLOW = """name: Fake CI

jobs:
  lint:
    name: Lint
    timeout-minutes: 10
"""

RELEASE_REL = ".github/workflows/cd-release.yml"
RELEASE_WORKFLOW = """name: Fake release

jobs:
  validate-promotion:
    name: Validate Promotion
    timeout-minutes: 30
  stage-artifacts:
    name: Stage Artifacts
    timeout-minutes: 15
"""

FAKE_GH = r"""#!/bin/bash
# Minimal routing fake: `gh run list ...` serves $RUN_LIST_FIXTURE, `gh api
# .../runs/<id>/jobs?...` serves $JOBS_FIXTURE_DIR/<id>.tsv (or nothing for an
# id with no fixture, matching a real run whose jobs the --jq filter dropped).
set -uo pipefail
if [ "${1:-}" = "run" ] && [ "${2:-}" = "list" ]; then
    cat "$RUN_LIST_FIXTURE"
    exit 0
fi
if [ "${1:-}" = "api" ]; then
    path="${2:-}"
    run_id=$(printf '%s' "$path" | sed -E 's#.*/runs/([0-9]+)/jobs.*#\1#')
    fixture="$JOBS_FIXTURE_DIR/${run_id}.tsv"
    if [ -f "$fixture" ]; then cat "$fixture"; fi
    exit 0
fi
exit 0
"""


def _copy_imports(tmp: Path) -> None:
    """What the script imports: the `.ci` hop, the package marker, the registry reader and the registry."""
    for rel in (
        ".ci/scripts/quality/_cipath.py",
        ".ci/rediacc_ci/__init__.py",
        ".ci/rediacc_ci/well_known.py",
        ".ci/config/well-known.env",
    ):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths.from_root(rel), dst)


def _tree(
    tmp: Path,
    lane_durations: dict,
    workflow_text: str = FIXTURE_WORKFLOW,
    extra_workflows: dict[str, str] | None = None,
) -> Path:
    """A minimal tree at the SAME relative depth the script's own `parents[3]` expects: `<tmp>/.ci/scripts/quality/check_job_timeout_headroom.py`, `<tmp>/.github/workflows/ci.yml` (plus `extra_workflows`, by default the uncalled release workflow holding the baseline jobs), `<tmp>/.ci/config/lane-durations.json`."""
    script_dst = tmp / SCRIPT_REL
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_SCRIPT, script_dst)
    _copy_imports(tmp)
    workflow_dst = tmp / WORKFLOW_REL
    workflow_dst.parent.mkdir(parents=True, exist_ok=True)
    workflow_dst.write_text(workflow_text, encoding="utf-8")
    for rel, text in (
        {RELEASE_REL: RELEASE_WORKFLOW} if extra_workflows is None else extra_workflows
    ).items():
        (tmp / rel).write_text(text, encoding="utf-8")
    lane_dst = tmp / LANE_DURATIONS_REL
    lane_dst.parent.mkdir(parents=True, exist_ok=True)
    lane_dst.write_text(json.dumps(lane_durations, indent=2) + "\n", encoding="utf-8")
    return tmp


def _run(
    tree: Path, args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    full_env = {"PATH": "/usr/bin:/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(tree / SCRIPT_REL), *args],
        capture_output=True,
        text=True,
        cwd=str(tree),
        env=full_env,
        check=False,
        timeout=30,
    )


def _iso(days_ago: float) -> str:
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


FRESH_HEADROOM_BASELINE = {
    "refreshed_at": None,
    "concurrency": 20,
    "jobs": {"quality-code": 999},
    "units": {},
    "job_max_seconds": {
        "refreshed_at": None,
        "jobs": {
            "Validate Promotion": {"observed_max_seconds": 600, "samples": 3},
            "Stage Artifacts": {"observed_max_seconds": 300, "samples": 3},
        },
    },
}


def test_reads_job_max_seconds_and_ignores_the_top_level_jobs_map(tmp_path):
    """The gate's baseline is `job_max_seconds.jobs`, not the top-level `jobs` map T3.2's `--refresh` owns. `jobs: {"quality-code": 999}` is a bare int, not a `{"observed_max_seconds": ...}` record -- reading it as the baseline would crash on `rec["observed_max_seconds"]`, not merely disagree, so a wrong read is loud rather than a quiet false pass."""
    data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
    data["job_max_seconds"]["refreshed_at"] = _iso(1)
    tree = _tree(tmp_path, data)
    result = _run(tree, [])
    assert result.returncode == 0, result.stderr
    assert "2 job(s) keep at least 1.50x headroom" in result.stdout, result.stdout
    assert "0 superseded" in result.stdout, result.stdout


def test_stale_job_max_seconds_fires_even_with_a_fresh_top_level_refreshed_at():
    """The two `refreshed_at` fields are INDEPENDENT: a fresh top-level one (T3.2's own) must never mask a stale `job_max_seconds` one."""
    with harness.temp_dir() as tmp_path:
        data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
        data["refreshed_at"] = _iso(1)  # fresh top-level
        data["job_max_seconds"]["refreshed_at"] = _iso(20)  # stale (> 14 days)
        tree = _tree(tmp_path, data)
        result = _run(tree, [])
        assert result.returncode == 1
        assert "stale" in result.stderr, result.stderr
        assert "20.0 day" in result.stderr or "20 day" in result.stderr, result.stderr


def test_fresh_job_max_seconds_passes_even_with_a_stale_or_missing_top_level_refreshed_at():
    """The inverse: a stale (or absent) top-level `refreshed_at` must never fail THIS gate on its own -- that is `scripts/gates/check-lane-budget.ts` check 5's job, not this one's."""
    with harness.temp_dir() as tmp_path:
        data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
        data["refreshed_at"] = None  # missing entirely
        data["job_max_seconds"]["refreshed_at"] = _iso(1)  # fresh
        tree = _tree(tmp_path, data)
        result = _run(tree, [])
        assert result.returncode == 0, result.stderr
        assert "stale" not in result.stdout


def test_15_days_fires_13_days_does_not_control_and_inverse():
    """D-W2 tightened MAX_BASELINE_AGE_DAYS from 45 to 14. Right at the boundary."""
    with harness.temp_dir() as tmp_path:
        data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
        data["job_max_seconds"]["refreshed_at"] = _iso(15)
        tree = _tree(tmp_path, data)
        stale_result = _run(tree, [])
    assert stale_result.returncode == 1
    assert "stale" in stale_result.stderr

    with harness.temp_dir() as tmp_path2:
        data2 = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
        data2["job_max_seconds"]["refreshed_at"] = _iso(13)
        tree2 = _tree(tmp_path2, data2)
        fresh_result = _run(tree2, [])
    assert fresh_result.returncode == 0, fresh_result.stderr


def test_vacuous_without_lane_durations_json():
    """No `.ci/config/lane-durations.json` at all (the file this gate now reads) is VACUOUS INPUT, the same refusal it gave for a missing `job-timeout-baseline.json` before the retirement -- `test_gate_gate_anti_vacuity.py`'s own empty-tree case covers the full anti-vacuity registry; this pins the specific message this script gives."""
    with harness.temp_dir() as tmp_path:
        script_dst = tmp_path / SCRIPT_REL
        script_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_SCRIPT, script_dst)
        _copy_imports(tmp_path)
        workflow_dst = tmp_path / WORKFLOW_REL
        workflow_dst.parent.mkdir(parents=True, exist_ok=True)
        workflow_dst.write_text(FIXTURE_WORKFLOW, encoding="utf-8")
        result = _run(tmp_path, [])
        assert result.returncode == 1
        assert "VACUOUS INPUT" in result.stderr, result.stderr


def test_refresh_touches_only_job_max_seconds_leaving_everything_else_byte_identical():
    """`--refresh` rewrites `job_max_seconds.jobs`/`job_max_seconds.refreshed_at` and nothing else -- T3.2's `jobs`/`units`/`concurrency`/`$comment`/`defaultUnitMs` are budget_report.py's own to write, never this script's."""
    with harness.temp_dir() as tmp_path:
        data = {
            "$comment": ["untouched marker"],
            "refreshed_at": "2026-01-01T00:00:00Z",
            "concurrency": 20,
            "jobs": {"quality-code": 3.5},
            "units": {"pytest:tests/test_x.py": 1234.0},
            "defaultUnitMs": {"quality-pytest": 5000},
            "job_max_seconds": {
                "refreshed_at": "2026-01-01T00:00:00Z",
                "jobs": {
                    "Validate Promotion": {"observed_max_seconds": 999999, "samples": 1},
                    "Stage Artifacts": {"observed_max_seconds": 999999, "samples": 1},
                },
            },
        }
        tree = _tree(tmp_path, data)

        run_list_fixture = tmp_path / "run-list.txt"
        run_list_fixture.write_text("111\n", encoding="utf-8")
        jobs_dir = tmp_path / "jobs-fixtures"
        jobs_dir.mkdir()
        (jobs_dir / "111.tsv").write_text(
            "Validate Promotion\t2026-09-01T00:00:00Z\t2026-09-01T00:20:00Z\n"
            "Stage Artifacts\t2026-09-01T00:00:00Z\t2026-09-01T00:10:00Z\n",
            encoding="utf-8",
        )
        with harness.temp_dir() as bindir:
            harness._write_exec(bindir / "gh", FAKE_GH)
            result = _run(
                tree,
                ["--refresh", "--runs", "5"],
                env={
                    "PATH": "%s:/usr/bin:/bin" % bindir,
                    "RUN_LIST_FIXTURE": str(run_list_fixture),
                    "JOBS_FIXTURE_DIR": str(jobs_dir),
                },
            )
        assert result.returncode == 0, result.stderr + result.stdout

        after = json.loads((tree / LANE_DURATIONS_REL).read_text())
        assert after["$comment"] == ["untouched marker"]
        assert after["refreshed_at"] == "2026-01-01T00:00:00Z"  # TOP-LEVEL untouched
        assert after["concurrency"] == 20
        assert after["jobs"] == {"quality-code": 3.5}
        assert after["units"] == {"pytest:tests/test_x.py": 1234.0}
        assert after["defaultUnitMs"] == {"quality-pytest": 5000}

        section = after["job_max_seconds"]
        assert section["refreshed_at"] != "2026-01-01T00:00:00Z"  # its OWN stamp moved
        assert section["jobs"]["Validate Promotion"]["observed_max_seconds"] == 1200
        assert section["jobs"]["Validate Promotion"]["samples"] == 1
        assert section["jobs"]["Stage Artifacts"]["observed_max_seconds"] == 600


def test_refresh_leaves_an_unmatched_job_unchanged_and_warns():
    """A baseline job the sampled runs never mention keeps its OLD number rather than being zeroed -- the same "unchanged and may be stale" rule the pre-retirement version already had."""
    with harness.temp_dir() as tmp_path:
        data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
        data["job_max_seconds"]["jobs"]["Stage Artifacts"]["observed_max_seconds"] = 111
        tree = _tree(tmp_path, data)

        run_list_fixture = tmp_path / "run-list.txt"
        run_list_fixture.write_text("222\n", encoding="utf-8")
        jobs_dir = tmp_path / "jobs-fixtures"
        jobs_dir.mkdir()
        # Only Validate Promotion appears in the sampled run's jobs.
        (jobs_dir / "222.tsv").write_text(
            "Validate Promotion\t2026-09-01T00:00:00Z\t2026-09-01T00:10:00Z\n",
            encoding="utf-8",
        )
        with harness.temp_dir() as bindir:
            harness._write_exec(bindir / "gh", FAKE_GH)
            result = _run(
                tree,
                ["--refresh", "--runs", "5"],
                env={
                    "PATH": "%s:/usr/bin:/bin" % bindir,
                    "RUN_LIST_FIXTURE": str(run_list_fixture),
                    "JOBS_FIXTURE_DIR": str(jobs_dir),
                },
            )
        assert result.returncode == 0, result.stderr
        assert "Stage Artifacts" in result.stderr
        assert "UNCHANGED" in result.stderr
        after = json.loads((tree / LANE_DURATIONS_REL).read_text())
        assert after["job_max_seconds"]["jobs"]["Stage Artifacts"]["observed_max_seconds"] == 111


# --- D-W2: the lane budget supersedes the 1.5x rule for budgeted jobs -----------------

TIGHT_CI = """name: Fake CI

jobs:
  validate-promotion:
    name: Validate Promotion
    timeout-minutes: 10
  stage:
    uses: ./.github/workflows/cd-stage.yml
"""

CALLED_STAGE = """name: Stage

on:
  workflow_call:

jobs:
  stage:
    name: Stage Artifacts
    timeout-minutes: 10
"""


def _tight_baseline() -> dict:
    """Both jobs observed at 600 s: under a 10-minute timeout that is 1.00x, far below the 1.5x floor."""
    data = json.loads(json.dumps(FRESH_HEADROOM_BASELINE))
    data["job_max_seconds"]["refreshed_at"] = _iso(1)
    for rec in data["job_max_seconds"]["jobs"].values():
        rec["observed_max_seconds"] = 600
    return data


def test_budgeted_jobs_are_superseded_directly_and_through_a_called_workflow():
    """MATCH: a job in ci.yml and a job in a workflow ci.yml calls are the lane budget's (check-lane-budget.ts checks 2 and 7), so 1.00x headroom is not a finding here; each is named as superseded."""
    with harness.temp_dir() as tmp_path:
        tree = _tree(
            tmp_path,
            _tight_baseline(),
            workflow_text=TIGHT_CI,
            extra_workflows={".github/workflows/cd-stage.yml": CALLED_STAGE},
        )
        result = _run(tree, [])
    assert result.returncode == 0, result.stderr
    assert "0 job(s) keep" in result.stdout, result.stdout
    assert "2 superseded" in result.stdout, result.stdout
    assert "Stage Artifacts: superseded by check:ci-lane-budget (D-W2)" in result.stdout
    assert "Validate Promotion: superseded by check:ci-lane-budget (D-W2)" in result.stdout


def test_the_same_tight_jobs_outside_the_ci_graph_still_fire():
    """CONTROL for the test above: the identical 1.00x numbers in a workflow ci.yml does NOT call are still judged at 1.5x, so the skip is D-W2's partition and not a detector that went quiet."""
    with harness.temp_dir() as tmp_path:
        uncalled = TIGHT_CI.replace(
            "  stage:\n    uses: ./.github/workflows/cd-stage.yml\n",
            "  stage:\n    name: Stage Artifacts\n    timeout-minutes: 10\n",
        )
        tree = _tree(
            tmp_path,
            _tight_baseline(),
            extra_workflows={RELEASE_REL: uncalled},
        )
        result = _run(tree, [])
    assert result.returncode == 1, result.stdout
    assert "Validate Promotion: timeout-minutes=10" in result.stderr, result.stderr
    assert "Stage Artifacts: timeout-minutes=10" in result.stderr, result.stderr


def test_a_ci_yml_with_no_jobs_is_refused_rather_than_superseding_nothing():
    """An unreadable ci.yml would make the budgeted set empty and silently hand every job back to this gate; it is refused instead."""
    with harness.temp_dir() as tmp_path:
        tree = _tree(tmp_path, _tight_baseline(), workflow_text="name: Fake CI\n")
        result = _run(tree, [])
    assert result.returncode == 1
    assert "parsed to zero jobs" in result.stderr, result.stderr
