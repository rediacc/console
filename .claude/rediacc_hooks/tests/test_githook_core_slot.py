"""The commit hook's heavy work holds one core of the machine-wide pool, and its cheap path holds none (PR-TASK 79b7e92e).

`githooks._core_slot` wraps `rediacc_ci.core.host_slots.host_slot(1)`; `artifacts_pre_commit` takes it only when the artifact selection picks a checker, so a commit staging no enrolled input never waits on a busy machine. The end-to-end refusals and allows of both checks stay in test_githook_gen_docs.py and test_githook_generated_artifacts.py, which drive real commits through this file.
"""

from __future__ import annotations

import contextlib
import importlib.util
import pathlib
import types

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1] / "git" / "githooks.py"


def _load():
    spec = importlib.util.spec_from_file_location("githooks_core_slot_under_test", HOOKS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GH = _load()


def _recording_slots(taken):
    @contextlib.contextmanager
    def host_slot(weight, *, label=""):
        taken.append((weight, label))
        yield types.SimpleNamespace(env={"CI_CORE_LEASE_HELD": "1"})

    return types.SimpleNamespace(host_slot=host_slot)


def test_core_slot_takes_one_token_and_hands_its_env_to_the_child(monkeypatch):
    taken: list[tuple[int, str]] = []
    monkeypatch.setattr(GH.sp, "import_from_ci", lambda _name: _recording_slots(taken))
    with GH._core_slot("gen-docs verify") as env:
        assert env == {"CI_CORE_LEASE_HELD": "1"}
    assert taken == [(1, "commit hook gen-docs verify")]


def test_an_unimportable_pool_runs_unthrottled_and_says_so(monkeypatch, capsys):
    def boom(_name):
        raise ImportError("no pool here")

    monkeypatch.setattr(GH.sp, "import_from_ci", boom)
    with GH._core_slot("artifact check") as env:
        assert env == {}
    assert "no pool here" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [SyntaxError("half-edited module"), OSError(13, "permission denied")],
    ids=["syntax-error", "oserror"],
)
def test_a_pool_module_that_fails_to_load_for_any_reason_runs_unthrottled(
    monkeypatch, capsys, error
):
    """Review S75 (githooks.py `_core_slot` caught only ImportError): a module a writer is mid-edit on raises SyntaxError, an unreadable one OSError, and a throttle must never refuse the commit over either."""

    def boom(_name):
        raise error

    monkeypatch.setattr(GH.sp, "import_from_ci", boom)
    with GH._core_slot("artifact check") as env:
        assert env == {}
    err = capsys.readouterr().err
    assert "artifact check runs unthrottled" in err
    assert str(error) in err


def test_control_an_unrelated_error_from_the_import_is_not_folded_into_unthrottled(monkeypatch):
    def boom(_name):
        raise ValueError("a real bug")

    monkeypatch.setattr(GH.sp, "import_from_ci", boom)
    with pytest.raises(ValueError, match="a real bug"), GH._core_slot("artifact check"):
        pytest.fail("the block must not run when the loader raises an unrelated error")


def test_control_an_error_from_the_commit_check_itself_is_not_taken_for_a_pool_failure(
    monkeypatch,
):
    taken: list[tuple[int, str]] = []
    monkeypatch.setattr(GH.sp, "import_from_ci", lambda _name: _recording_slots(taken))
    with pytest.raises(OSError, match="check failed"), GH._core_slot("gen-docs verify"):
        raise OSError("check failed")
    assert taken == [(1, "commit hook gen-docs verify")]


def _artifacts_world(monkeypatch, selected):
    taken: list[tuple[int, str]] = []
    monkeypatch.setattr(GH, "_repo", lambda: "/repo")
    monkeypatch.setattr(GH, "_git", lambda _args: "/repo/.git")
    monkeypatch.setattr(GH, "_gen_env", lambda _repo, _scratch: {})
    monkeypatch.setattr(GH.ga, "registry_text", lambda _repo, _env: "{}")
    monkeypatch.setattr(GH.ga, "parse", lambda _text: (["art"], []))
    monkeypatch.setattr(GH.ga, "changed_paths", lambda _repo, _env: ["a.ts"])
    monkeypatch.setattr(GH.ga, "select", lambda _arts, _changed: list(selected))
    seen_env = []

    def judge(_repo, _git_dir, env, _tree):
        seen_env.append(env)
        return [], 1, 1

    monkeypatch.setattr(GH.ga, "judge", judge)
    monkeypatch.setattr(GH.sp, "import_from_ci", lambda _name: _recording_slots(taken))
    return taken, seen_env


def test_control_a_commit_that_selects_no_artifact_takes_no_slot(monkeypatch):
    taken, seen_env = _artifacts_world(monkeypatch, selected=[])
    assert GH.artifacts_pre_commit() == 0
    assert taken == []
    assert seen_env == [{}]


def test_a_commit_that_selects_an_artifact_runs_its_check_under_one_slot(monkeypatch):
    taken, seen_env = _artifacts_world(monkeypatch, selected=[("art", ("a.ts",))])
    assert GH.artifacts_pre_commit() == 0
    assert taken == [(1, "commit hook artifact check")]
    assert seen_env == [{"CI_CORE_LEASE_HELD": "1"}]


def test_an_unreadable_selection_still_takes_the_slot(monkeypatch):
    taken, _seen = _artifacts_world(monkeypatch, selected=[])

    def broken(_repo, _env):
        raise OSError("diff failed")

    monkeypatch.setattr(GH.ga, "changed_paths", broken)
    assert GH.artifacts_pre_commit() == 0
    assert taken == [(1, "commit hook artifact check")]
