"""Unit tests for `rediacc_ci.ci.list_e2e_probe_files`.

No differential: this module's bash twin (`.ci/scripts/test/list-e2e-probe-files.sh`) was added and deleted inside the same task -- ruling 7 refuses new bash under `.ci` -- so there is no recorded corpus to compare against and no ledger to hold. Almost every test drives the module directly: a real shard-manifest-shaped JSON fixture on disk, and `$GITHUB_OUTPUT`/stdout as a tmp file or captured output; the two that start a subprocess say so in their own docstrings.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import list_e2e_probe_files as subject

if typing.TYPE_CHECKING:
    import pathlib


def write_manifest(path: pathlib.Path, ids: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "lane": "e2e",
                "of": 1,
                "generatedAt": "2026-09-01",
                "legs": [{"index": 1, "ids": ids}],
            }
        ),
        encoding="utf-8",
    )


def test_probe_units_keep_each_part_as_its_own_leg_with_its_bucket_grep(
    tmp_path: pathlib.Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        [
            "e2e-workers:13-postgres-fork-isolation.test.ts#part2",
            "e2e-workers:13-postgres-fork-isolation.test.ts#part1",
            "e2e-workers:01-system-checks.test.ts",
        ],
    )
    assert subject.probe_units(manifest) == [
        {
            "unit": "01-system-checks.test.ts",
            "test": "01-system-checks.test.ts",
            "grep": "",
            "slug": "01-system-checks.test.ts",
        },
        {
            "unit": "13-postgres-fork-isolation.test.ts#part1",
            "test": "13-postgres-fork-isolation.test.ts",
            "grep": subject.SHARD_GREP_BUCKETS["part1"],
            "slug": "13-postgres-fork-isolation.test.ts-part1",
        },
        {
            "unit": "13-postgres-fork-isolation.test.ts#part2",
            "test": "13-postgres-fork-isolation.test.ts",
            "grep": subject.SHARD_GREP_BUCKETS["part2"],
            "slug": "13-postgres-fork-isolation.test.ts-part2",
        },
    ]


def test_probe_units_refuse_a_bucket_the_runner_cannot_select(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, ["e2e-workers:a.test.ts", "e2e-workers:13-x.test.ts#part9"])
    with pytest.raises(subject.UnknownBucketError, match="part9"):
        subject.probe_units(manifest)


def test_probe_units_refuse_an_empty_bucket_after_the_separator(tmp_path: pathlib.Path) -> None:
    """Review 729e29cc.1: `a.test.ts#` named a bucket of nothing, which became a whole-file unit with `#` in its id."""
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, ["e2e-workers:a.test.ts", "e2e-workers:b.test.ts#"])
    with pytest.raises(subject.UnknownBucketError, match=r"b\.test\.ts"):
        subject.probe_units(manifest)


def test_the_module_imports_with_the_standard_library_only() -> None:
    """Review 729e29cc.2: the `list-files` job installs nothing, so the module and everything it imports must load without site-packages."""
    proc = subprocess.run(
        [sys.executable, "-S", "-c", "import rediacc_ci.ci.list_e2e_probe_files"],
        cwd=paths.repo_root(),
        env={**os.environ, "PYTHONPATH": os.fspath(paths.from_root(".ci"))},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_probe_units_deduplicate_a_unit_two_legs_name(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, ["e2e-workers:a.test.ts", "e2e-workers:a.test.ts"])
    assert [u["unit"] for u in subject.probe_units(manifest)] == ["a.test.ts"]


def test_probe_units_read_every_leg(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "legs": [
                    {"index": 1, "ids": ["e2e-workers:a.test.ts"]},
                    {"index": 2, "ids": ["e2e-workers:b.test.ts"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert [u["unit"] for u in subject.probe_units(manifest)] == ["a.test.ts", "b.test.ts"]


def test_probe_units_refuse_a_vacuous_manifest(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"legs": []}), encoding="utf-8")
    with pytest.raises(subject.VacuousError, match="VACUOUS"):
        subject.probe_units(manifest)


def test_main_writes_units_line_to_github_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / ".ci" / "config" / "shards" / "test-e2e-workers.json"
    manifest.parent.mkdir(parents=True)
    write_manifest(manifest, ["e2e-workers:z.test.ts", "e2e-workers:a.test.ts#part1"])

    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    github_output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))

    assert subject.main([]) == 0
    line = github_output.read_text(encoding="utf-8")
    assert line.startswith("units=")
    assert line.endswith("\n")
    assert [u["unit"] for u in json.loads(line.removeprefix("units="))] == [
        "a.test.ts#part1",
        "z.test.ts",
    ]


def test_main_prints_to_stdout_without_github_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / ".ci" / "config" / "shards" / "test-e2e-workers.json"
    manifest.parent.mkdir(parents=True)
    write_manifest(manifest, ["e2e-workers:only.test.ts"])

    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert subject.main([]) == 0
    captured = capsys.readouterr()
    assert (
        captured.out
        == 'units=[{"unit":"only.test.ts","test":"only.test.ts","grep":"","slug":"only.test.ts"}]\n'
    )
    assert "1 unit(s)" in captured.err


def test_main_returns_1_and_reports_a_vacuous_manifest(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / ".ci" / "config" / "shards" / "test-e2e-workers.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"legs": []}), encoding="utf-8")

    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert subject.main([]) == 1
    assert "VACUOUS" in capsys.readouterr().err


def test_main_returns_1_when_the_manifest_is_missing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert subject.main([]) == 1
    assert capsys.readouterr().err != ""


def test_the_probe_edges_selftest_runs_and_passes() -> None:
    """Worklist #d168ab86: `scripts/ci-runner/e2e-probe-edges.ts --selftest` carries the probe's edge-proposal controls (control, inverse, no-predecessor, consecutive, buckets, vacuous), and nothing ran it, so a broken proposer stayed green. A missing tsx is a failure, never a skip."""
    tsx = paths.from_root("node_modules", ".bin", "tsx")
    script = paths.from_root("scripts", "ci-runner", "e2e-probe-edges.ts")
    assert os.access(tsx, os.X_OK), (
        "tsx not installed at %s; run npm install && npm run install:natives" % tsx
    )
    proc = subprocess.run(
        [os.fspath(tsx), os.fspath(script), "--selftest"],
        cwd=paths.repo_root(),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # The script writes its OK line to stderr (e2e-probe-edges.ts), so that channel is the one checked.
    assert "OK: e2e-probe-edges selftest passed" in proc.stderr
