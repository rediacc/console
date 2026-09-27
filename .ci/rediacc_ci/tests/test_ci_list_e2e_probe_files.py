"""Unit tests for `rediacc_ci.ci.list_e2e_probe_files`.

No differential: this module's bash twin (`.ci/scripts/test/list-e2e-probe-files.sh`) was added and deleted inside the same task -- ruling 7 refuses new bash under `.ci` -- so there is no recorded corpus to compare against and no ledger to hold. These tests drive the module directly: a real shard-manifest-shaped JSON fixture on disk, and `$GITHUB_OUTPUT`/stdout as a tmp file or captured output.
"""

from __future__ import annotations

import json
import typing

import pytest

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


def test_probe_files_strips_the_prefix_and_the_part_suffix(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        [
            "e2e-workers:13-postgres-fork-isolation.test.ts#part1",
            "e2e-workers:13-postgres-fork-isolation.test.ts#part2",
            "e2e-workers:01-system-checks.test.ts",
        ],
    )
    assert subject.probe_files(manifest) == [
        "01-system-checks.test.ts",
        "13-postgres-fork-isolation.test.ts",
    ]


def test_probe_files_reads_every_leg(tmp_path: pathlib.Path) -> None:
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
    assert subject.probe_files(manifest) == ["a.test.ts", "b.test.ts"]


def test_probe_files_refuses_a_vacuous_manifest(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"legs": []}), encoding="utf-8")
    with pytest.raises(subject.Vacuous, match="VACUOUS"):
        subject.probe_files(manifest)


def test_main_writes_files_line_to_github_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / ".ci" / "config" / "shards" / "test-e2e-workers.json"
    manifest.parent.mkdir(parents=True)
    write_manifest(manifest, ["e2e-workers:z.test.ts", "e2e-workers:a.test.ts#part1"])

    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    github_output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))

    assert subject.main([]) == 0
    assert github_output.read_text(encoding="utf-8") == 'files=["a.test.ts","z.test.ts"]\n'


def test_main_prints_to_stdout_without_github_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / ".ci" / "config" / "shards" / "test-e2e-workers.json"
    manifest.parent.mkdir(parents=True)
    write_manifest(manifest, ["e2e-workers:only.test.ts"])

    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert subject.main([]) == 0
    assert capsys.readouterr().out == 'files=["only.test.ts"]\n'


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
