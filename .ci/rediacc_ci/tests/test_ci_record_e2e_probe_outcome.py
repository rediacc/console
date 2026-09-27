"""Unit tests for `rediacc_ci.ci.record_e2e_probe_outcome`.

No differential: this module's bash twin (`.ci/scripts/test/record-e2e-probe-outcome.sh`) was added and deleted inside the same task -- ruling 7 refuses new bash under `.ci` -- so there is no recorded corpus and no ledger. These tests drive the module directly against a tmp `$RUNNER_TEMP`.
"""

from __future__ import annotations

import pathlib

import pytest

from rediacc_ci.ci import record_e2e_probe_outcome as subject


def test_outcome_for_success_is_pass() -> None:
    assert subject.outcome_for("success") == "pass"


@pytest.mark.parametrize("status", ["failure", "cancelled", "", "SUCCESS", "skipped"])
def test_outcome_for_anything_else_is_fail(status: str) -> None:
    assert subject.outcome_for(status) == "fail"


def test_result_dir_uses_runner_temp_when_set() -> None:
    assert subject.result_dir({"RUNNER_TEMP": "/x"}) == pathlib.Path("/x/e2e-probe")


def test_result_dir_falls_back_to_tmp_when_runner_temp_is_unset() -> None:
    assert subject.result_dir({}) == pathlib.Path("/tmp/e2e-probe")


def test_result_dir_falls_back_to_tmp_when_runner_temp_is_empty() -> None:
    assert subject.result_dir({"RUNNER_TEMP": ""}) == pathlib.Path("/tmp/e2e-probe")


def test_main_writes_the_result_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert subject.main(["tests/13-postgres-fork-isolation.test.ts", "success"]) == 0
    result = tmp_path / "e2e-probe" / "result.json"
    assert result.read_text(encoding="utf-8") == (
        '{"file":"tests/13-postgres-fork-isolation.test.ts","outcome":"pass"}\n'
    )


def test_main_records_a_fail_for_a_non_success_status(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert subject.main(["a.test.ts", "failure"]) == 0
    result = tmp_path / "e2e-probe" / "result.json"
    assert result.read_text(encoding="utf-8") == '{"file":"a.test.ts","outcome":"fail"}\n'


def test_main_creates_the_output_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "not-yet-created"
    monkeypatch.setenv("RUNNER_TEMP", str(nested))
    assert not nested.exists()
    assert subject.main(["a.test.ts", "success"]) == 0
    assert (nested / "e2e-probe" / "result.json").exists()


def test_main_refuses_with_too_few_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    assert subject.main(["only-one"]) == 1
    assert "usage" in capsys.readouterr().err

    assert subject.main([]) == 1
    assert "usage" in capsys.readouterr().err


def test_main_ignores_extra_arguments(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    assert subject.main(["a.test.ts", "success", "extra", "args"]) == 0
    result = tmp_path / "e2e-probe" / "result.json"
    assert result.read_text(encoding="utf-8") == '{"file":"a.test.ts","outcome":"pass"}\n'
