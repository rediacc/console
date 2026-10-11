"""With `CLAUDE_PROJECT_DIR` unset, a hook still judges the PROJECT, not the directory its process stands in (worklist #f32d3604).

THE DEFECT. `hookio.Event.project_dir` ported the bash `${CLAUDE_PROJECT_DIR:-.}`, and `.` is the hook process's directory. From `.claude/` with the variable unset, block_git_force_push allowed `git push --prune origin` (rc 0 against rc 2 from the root, 2026-10-11) and test_hooks_static failed those two cases. Two hooks outside the guard package read the event's `cwd` ahead of their own checkout and failed the same way: why-on-edit let a near-duplicate plan through, and
ctx_budget named `.claude/agent/<session>/STATE.md` as the state file. Each test below runs from a SUBDIRECTORY of the checkout with the variable absent, in-process through `dispatch.run_one(env=...)` and in a real process, and was red before the fix.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks import dispatch, hookio

ROOT = pathlib.Path(__file__).resolve().parents[3]
CLAUDE = ROOT / ".claude"
SUBDIRS = (CLAUDE, CLAUDE / "rediacc_hooks")
PRUNE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --prune origin"}})


def _env():
    """The process environment without the variable, as a hand run or a CI step has it."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}


@pytest.mark.parametrize("where", SUBDIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_project_dir_is_the_checkout_from_a_subdirectory(where, monkeypatch):
    monkeypatch.chdir(where)
    assert pathlib.Path(hookio.Event("{}", env=_env()).project_dir).resolve() == ROOT


def test_project_dir_follows_the_payload_cwd_before_the_process(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"cwd": str(CLAUDE)})
    assert pathlib.Path(hookio.Event(payload, env=_env()).project_dir).resolve() == ROOT


def test_project_dir_outside_any_checkout_is_that_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert hookio.Event("{}", env=_env()).project_dir == str(tmp_path)


def test_a_set_or_empty_variable_keeps_its_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(CLAUDE)
    assert hookio.Event(
        "{}", env={**_env(), "CLAUDE_PROJECT_DIR": str(tmp_path)}
    ).project_dir == str(tmp_path)
    # EMPTY takes the fallback too, as `:-` did: a harness exporting "" must not make "" the root.
    assert (
        pathlib.Path(
            hookio.Event("{}", env={**_env(), "CLAUDE_PROJECT_DIR": ""}).project_dir
        ).resolve()
        == ROOT
    )


@pytest.mark.parametrize("where", SUBDIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_force_push_prune_is_refused_in_process_from_a_subdirectory(where, monkeypatch):
    monkeypatch.chdir(where)
    rc, _out, err = dispatch.run_one("block_git_force_push", PRUNE, env=_env())
    assert rc == 2, err


@pytest.mark.parametrize("where", SUBDIRS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_force_push_prune_is_refused_by_the_real_process_from_a_subdirectory(where):
    done = subprocess.run(
        [sys.executable, str(CLAUDE / "rediacc_hooks" / "dispatch.py"), "block_git_force_push"],
        input=PRUNE,
        capture_output=True,
        text=True,
        cwd=where,
        env=_env(),
        timeout=120,
        check=False,
    )
    assert done.returncode == 2, done.stderr


def test_why_on_edit_refuses_a_duplicate_plan_from_a_subdirectory():
    """A near-duplicate of an existing plan is refused from `.claude/` exactly as from the root."""
    existing = sorted((ROOT / "agent" / "plans").glob("**/PLAN-*-*.md"))
    assert existing, (
        "the checkout has no multi-word plan to duplicate; this test would prove nothing"
    )
    slug = existing[0].stem[len("PLAN-") :]
    twin = ROOT / "agent" / ("PLAN-%s-again.md" % slug)
    assert not twin.exists()
    for where in (ROOT, CLAUDE):
        doc = {
            "tool_name": "Write",
            "cwd": str(where),
            "tool_input": {"file_path": str(twin), "content": "x"},
        }
        done = subprocess.run(
            [sys.executable, str(CLAUDE / "hooks" / "why-on-edit.py")],
            input=json.dumps(doc),
            capture_output=True,
            text=True,
            cwd=where,
            env=_env(),
            timeout=120,
            check=False,
        )
        assert done.returncode == 2, (where, done.stderr)


def test_the_context_hooks_name_the_state_file_at_the_root(monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    spec = importlib.util.spec_from_file_location(
        "ctx_budget_probe", CLAUDE / "hooks" / "context" / "ctx_budget.py"
    )
    assert spec is not None
    assert spec.loader is not None
    budget = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(budget)
    # The stdlib twin and the guard package's resolver give ONE answer, inside the checkout and outside any.
    for start in (CLAUDE, CLAUDE / "rediacc_hooks", ROOT, pathlib.Path("/")):
        assert budget.project_of(str(start)) == hookio.project_root(str(start))
    project = budget.project_dir({"cwd": str(CLAUDE)})
    assert pathlib.Path(project).resolve() == ROOT
    assert (
        budget.state_md_path(project, "abcd1234-x").parent.parent == pathlib.Path(project) / "agent"
    )
