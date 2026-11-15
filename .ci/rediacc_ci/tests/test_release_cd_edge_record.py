"""The oracle for `rediacc_ci.release.cd_edge_record`: a CD edge release writes `release-records/v<V>/edge.json` with the local release's schema, only for a whole release, once, and the ring runner reads it as bench having taken the version. Nothing reaches R2: the bucket is a dict behind the module's read/write seams."""

from __future__ import annotations

import datetime
import json
import pathlib
from typing import Any

import pytest

from rediacc_ci import paths, workflows
from rediacc_ci.deploy import deploy_record
from rediacc_ci.release import cd_edge_record, local, rings_run

V = "3.0.2"
SHA = "a" * 40
TREE = "b" * 40
WORKFLOW = paths.repo_root() / ".github" / "workflows" / "cd-release-edge.yml"


def _needs(**override: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        job: {"result": "success", "outputs": {}} for job in cd_edge_record.REQUIRED
    }
    out["init"]["outputs"] = {"workers_only": "false", "next_version": V}
    for job, result in override.items():
        out[job]["result"] = result
    return out


def _jobs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for minute, (name, _section) in enumerate(cd_edge_record.DISPLAY.values()):
        rows.append(
            {
                "name": name,
                "conclusion": "success",
                "run_attempt": 1,
                "started_at": "2026-11-15T10:%02d:00Z" % minute,
                "completed_at": "2026-11-15T10:%02d:30Z" % minute,
            }
        )
    return rows


class Bucket:
    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.puts: list[str] = []

    def read(self, key: str) -> dict[str, Any] | None:
        text = self.keys.get(key)
        return None if text is None else json.loads(text)

    def write(self, record: dict[str, Any], key: str) -> None:
        if key in self.keys:
            raise deploy_record.RecordError(
                "%s already exists: a deploy record is written once" % key
            )
        self.puts.append(key)
        self.keys[key] = json.dumps(record, sort_keys=True)


def _run(
    tmp_path: pathlib.Path,
    bucket: Bucket,
    needs: dict[str, Any],
    write: cd_edge_record.Writer | None = None,
) -> int:
    needs_file = tmp_path / "needs.json"
    needs_file.write_text(json.dumps(needs), encoding="utf-8")
    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text("\n".join(json.dumps(j) for j in _jobs()) + "\n", encoding="utf-8")
    return cd_edge_record.main(
        [
            "--version",
            V,
            "--sha",
            SHA,
            "--run-id",
            "123",
            "--needs",
            str(needs_file),
            "--jobs",
            str(jobs_file),
        ],
        root=paths.repo_root(),
        read=bucket.read,
        write=write or bucket.write,
        tree_of=lambda _root, _sha: TREE,
    )


def _local_record(tmp_path: pathlib.Path) -> dict[str, Any]:
    ctx = local.Context(
        version=V,
        sha=SHA,
        tree=TREE,
        run_id="t",
        regions=["eu"],
        smoke_rc="0",
        workers_only="",
        branch_release="",
        build_meta="",
    )
    return local.release_record(local.Run(tmp_path, ctx))


def test_a_whole_cd_release_writes_edge_json_with_the_local_schema(
    tmp_path: pathlib.Path,
) -> None:
    bucket = Bucket()
    assert _run(tmp_path, bucket, _needs()) == 0
    key = "release-records/v%s/edge.json" % V
    assert bucket.puts == [key]
    assert key == local.edge_record_key(V)
    record = bucket.read(key)
    assert record is not None
    assert set(record) == set(_local_record(tmp_path))
    assert record["schema"] == 1
    assert record["kind"] == "release-cd"
    assert record["version"] == V
    assert record["channel"] == "edge"
    assert record["sha"] == record["head_sha"] == SHA
    assert record["tree"] == TREE
    assert record["run_id"] == "gh-123"
    assert record["failed_step"] is None
    assert record["smoke_rc"] == 0
    assert record["workers_only"] is False
    assert record["branch_release"] is False
    assert record["regions"] == list(local.read_regions(paths.repo_root()))
    assert [s["id"] for s in record["steps"]] == list(cd_edge_record.REQUIRED)
    assert all(s["rc"] == 0 and s["seconds"] == 30.0 for s in record["steps"])
    assert record["total_seconds"] == 30.0 * len(cd_edge_record.REQUIRED)


@pytest.mark.parametrize(
    "job", ["deploy-account-edge", "deploy-marketing-edge", "smoke-test", "tag-and-release"]
)
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_a_failed_or_partial_release_writes_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], job: str, result: str
) -> None:
    bucket = Bucket()
    assert _run(tmp_path, bucket, _needs(**{job: result})) == 1
    assert bucket.keys == {}
    assert "job %s is %s" % (job, result) in capsys.readouterr().err


def test_a_workers_only_deploy_writes_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bucket = Bucket()
    needs = _needs()
    needs["init"]["outputs"]["workers_only"] = "true"
    assert _run(tmp_path, bucket, needs) == 1
    assert bucket.keys == {}
    assert "workers-only" in capsys.readouterr().err


def test_a_rerun_leaves_the_record_unchanged(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bucket = Bucket()
    assert _run(tmp_path, bucket, _needs()) == 0
    first = dict(bucket.keys)
    assert _run(tmp_path, bucket, _needs()) == 0
    assert bucket.keys == first
    assert bucket.puts == [local.edge_record_key(V)]
    assert "unchanged" in capsys.readouterr().out


def test_a_record_of_another_version_at_the_key_refuses_and_is_not_overwritten(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bucket = Bucket()
    key = local.edge_record_key(V)
    bucket.keys[key] = json.dumps({"version": "9.9.9"})
    assert _run(tmp_path, bucket, _needs()) == 1
    assert bucket.keys[key] == json.dumps({"version": "9.9.9"})
    assert bucket.puts == []
    assert "not %s" % V in capsys.readouterr().err


def test_a_lost_race_on_the_conditional_put_refuses(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def racing_write(_record: dict[str, Any], key: str) -> None:
        raise deploy_record.RecordError("%s already exists: a deploy record is written once" % key)

    assert _run(tmp_path, Bucket(), _needs(), write=racing_write) == 1
    assert "written once" in capsys.readouterr().err


def test_steps_take_the_latest_successful_attempt_and_every_reusable_row() -> None:
    jobs = [j for j in _jobs() if j["name"] != "Deploy edge Account (all regions)"]
    jobs += [
        {
            "name": "Deploy edge Account (all regions) / Deploy edge eu",
            "conclusion": "failure",
            "run_attempt": 1,
            "started_at": "2026-11-15T09:00:00Z",
            "completed_at": "2026-11-15T09:01:00Z",
        },
        {
            "name": "Deploy edge Account (all regions) / Deploy edge eu",
            "conclusion": "success",
            "run_attempt": 2,
            "started_at": "2026-11-15T11:00:00Z",
            "completed_at": "2026-11-15T11:02:00Z",
        },
        {
            "name": "Deploy edge Account (all regions) / Read regions",
            "conclusion": "success",
            "run_attempt": 2,
            "started_at": "2026-11-15T10:59:00Z",
            "completed_at": "2026-11-15T10:59:30Z",
        },
        # A different job whose name only shares a prefix is not this job.
        {"name": "Deploy edge Account (all regions)X", "conclusion": "success", "run_attempt": 3},
    ]
    rows = {r.id: r for r in cd_edge_record.step_rows(jobs)}
    account = rows["deploy-account-edge"]
    assert account.attempts == 2
    assert account.started_at == "2026-11-15T10:59:00Z"
    assert account.seconds == 180.0
    assert account.section == "deploy"


def test_a_required_job_with_no_successful_row_refuses() -> None:
    jobs = [j for j in _jobs() if j["name"] != "Smoke Test"]
    with pytest.raises(cd_edge_record.RefusedError, match="smoke-test"):
        cd_edge_record.step_rows(jobs)


def test_the_display_names_and_needs_match_the_workflow() -> None:
    doc = workflows.load(WORKFLOW)
    jobs = doc["jobs"]
    for job, (name, section) in cd_edge_record.DISPLAY.items():
        assert jobs[job]["name"] == name
        assert section in local.SECTIONS
    record_job = jobs["edge-record"]
    assert list(record_job["needs"]) == list(cd_edge_record.REQUIRED)
    assert "success()" in record_job["if"]
    assert "workers_only != 'true'" in record_job["if"]
    runs = " ".join(str(s.get("run", "")) for s in record_job["steps"])
    assert "rediacc_ci.release.cd_edge_record" in runs


def _no_target(_row: rings_run.CompanyRow) -> Any:
    pytest.fail("no company is targeted")


def _world(record: Any) -> rings_run.World:
    return rings_run.World(
        query=lambda _db, _sql, _params: [],
        release_record=record,
        runner=lambda *_a: (0, ""),
        now=lambda: datetime.datetime(2026, 11, 20, tzinfo=datetime.UTC),
        root=pathlib.Path("/nonexistent"),
        out=pathlib.Path("/nonexistent"),
        target=_no_target,
    )


def test_rings_read_a_cd_written_record_as_bench_done(tmp_path: pathlib.Path) -> None:
    bucket = Bucket()
    assert _run(tmp_path, bucket, _needs()) == 0

    def from_bucket(version: str) -> dict[str, Any] | None:
        return bucket.read(local.edge_record_key(version))

    read = rings_run.read_world(_world(from_bucket), V, bench=False, sample=False)
    assert read.state.bench_done is True
    written = bucket.read(local.edge_record_key(V))
    assert written is not None
    assert read.state.fast_at == datetime.datetime.fromisoformat(written["recorded_at"])
    # Control: the same version with nothing written has not been taken by bench.
    empty = rings_run.read_world(_world(lambda _v: None), V, bench=False, sample=False)
    assert empty.state.bench_done is False
