"""The lease `commit-msg` Plan-Box refusal (box T3 of agent/plans/PLAN-tick-tracking.md): `githooks.lease_plan_box_refusal`.

A fixture main checkout holds a lease tree at `.claude/worktrees/t`, a real linked tree of its store, so `commit_policy.lease_root` answers it the way it answers a real lease. `githooks.commit_msg` runs in process with the cwd in the lease (or in a plain repository), against a message file, exactly as git hands it to the hook.

THE CONTROL is the old hook: with the new branch stubbed out, the trailerless lease message is admitted.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
STRIP = ("COMMIT_POLICY_OK", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
PLAN_TEXT = """# PLAN: fx

Status: approved

## Tasks

- [ ] F1 the open box of the fixture plan
- [x] F2 the ticked box of the fixture plan
    (ticked) 2026-01-01 by x: commit:abc
"""
OPEN_SIG, DONE_SIG = "fd66592c", "074be283"
BODY = "feat(x): a subject\n\nA body paragraph.\n\n"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GH = _load("githooks_plan_box_under_test", HOOKS / "githooks.py")


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key in STRIP:
        monkeypatch.delenv(key, raising=False)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def repos(tmp_path):
    """(main checkout, lease tree inside it, a plain repository)."""
    main = (tmp_path / "main").resolve()
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "agent" / "plans").mkdir(parents=True)
    (main / "agent" / "plans" / "PLAN-fx.md").write_text(PLAN_TEXT, encoding="utf-8")
    (main / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "--no-gpg-sign", "-m", "init")
    lease = main / ".claude" / "worktrees" / "t"
    _git(main, "worktree", "add", "-q", "--detach", str(lease))
    plain = (tmp_path / "plain").resolve()
    plain.mkdir()
    _git(plain, "init", "-q", "-b", "0101-1")
    return main, lease, plain


def _run(monkeypatch, tmp_path, cwd, message):
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    monkeypatch.chdir(cwd)
    return GH.commit_msg([str(path)])


def test_lease_root_answers_the_fixture_lease(repos):
    main, lease, plain = repos
    assert GH.cp.lease_root(str(lease)) == str(lease)
    assert GH.cp.lease_root(str(plain)) == ""
    assert GH.cp.lease_root(str(main)) == ""


def test_plan_box_missing_in_a_lease_exits_1_with_the_grammar_line(
    repos, monkeypatch, tmp_path, capsys
):
    _main, lease, _plain = repos
    rc = _run(monkeypatch, tmp_path, lease, BODY + "PR-TASK: 1d805023\n")
    assert rc == 1
    err = capsys.readouterr().err
    assert "no Plan-Box trailer" in err
    assert "Plan-Box: <PLAN-file>.md#<sig8> clauses=<C1,C2,...|all>" in err


@pytest.mark.parametrize(
    "trailer",
    [
        "Plan-Box: PLAN-fx.md#%s clauses=all" % OPEN_SIG[:7],
        "Plan-Box: PLAN-fx.md#%s#x clauses=all" % OPEN_SIG,
        "Plan-Box: none -- short",
        "Plan-Box: PLAN-fx.md#%s" % OPEN_SIG,
    ],
)
def test_plan_box_malformed_in_a_lease_exits_1(repos, monkeypatch, tmp_path, capsys, trailer):
    _main, lease, _plain = repos
    rc = _run(monkeypatch, tmp_path, lease, BODY + "PR-TASK: 1d805023\n" + trailer + "\n")
    assert rc == 1
    assert "Plan-Box" in capsys.readouterr().err


@pytest.mark.parametrize(
    "trailer",
    [
        "Plan-Box: PLAN-fx.md#%s clauses=all" % OPEN_SIG,
        "Plan-Box: none -- a fixture commit that serves no box",
    ],
)
def test_plan_box_valid_in_a_lease_exits_0(repos, monkeypatch, tmp_path, trailer):
    _main, lease, _plain = repos
    assert _run(monkeypatch, tmp_path, lease, BODY + "PR-TASK: 1d805023\n" + trailer + "\n") == 0


@pytest.mark.parametrize(
    ("trailer", "why"),
    [
        ("Plan-Box: PLAN-fx.md#%s clauses=all" % DONE_SIG, "no open box"),
        ("Plan-Box: PLAN-fx.md#%s clauses=C1" % OPEN_SIG, "has no clause map"),
        ("Plan-Box: PLAN-gone.md#%s clauses=all" % OPEN_SIG, "no plan under agent/plans/"),
    ],
)
def test_plan_box_naming_a_box_land_would_refuse_exits_1(
    repos, monkeypatch, tmp_path, capsys, trailer, why
):
    _main, lease, _plain = repos
    rc = _run(monkeypatch, tmp_path, lease, BODY + "PR-TASK: 1d805023\n" + trailer + "\n")
    assert rc == 1
    assert why in capsys.readouterr().err


def test_plan_box_missing_outside_a_lease_exits_0(repos, monkeypatch, tmp_path):
    main, _lease, plain = repos
    assert _run(monkeypatch, tmp_path, plain, BODY + "PR-TASK: 1d805023\n") == 0
    _git(main, "switch", "-q", "-c", "0101-1")
    assert _run(monkeypatch, tmp_path, main, BODY + "PR-TASK: 1d805023\n") == 0


def test_plan_box_control_the_old_hook_admits_the_trailerless_lease_message(
    repos, monkeypatch, tmp_path
):
    _main, lease, _plain = repos
    message = BODY + "PR-TASK: 1d805023\n"
    assert _run(monkeypatch, tmp_path, lease, message) == 1
    monkeypatch.setattr(GH, "lease_plan_box_refusal", lambda _msg, _repo: 0)
    assert _run(monkeypatch, tmp_path, lease, message) == 0


def test_plan_box_hook_runs_under_a_real_git_commit(repos):
    """End to end: `core.hooksPath` at the real hooks, a real `git commit` in the lease."""
    _main, lease, _plain = repos
    (lease / "f.txt").write_text("f\n", encoding="utf-8")
    _git(lease, "add", "--", "f.txt")
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    base = ["git", "-c", "core.hooksPath=%s" % HOOKS, "commit", "-q", "--no-gpg-sign", "-m"]
    refused = subprocess.run(
        [*base, BODY + "PR-TASK: 1d805023\n"],
        cwd=str(lease),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "no Plan-Box trailer" in refused.stderr
    admitted = subprocess.run(
        [*base, BODY + "PR-TASK: 1d805023\nPlan-Box: PLAN-fx.md#%s clauses=all\n" % OPEN_SIG],
        cwd=str(lease),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert admitted.returncode == 0, admitted.stderr


# --------------------------------------------------------------------------- the PR-TASK epic check (#c9ca8d23) ---------------------------------------------------------------------------
# A lease writer's commit reached the tree carrying `PR-TASK: tracked finding #d31b4054`, a value naming no epic. `githooks.lease_pr_task_refusal` judges the trailer with `block_untagged_commit`'s own parser against the MAIN checkout's live branch: its `agent/pr/<branch>.md` united with the ledger.
EPIC, LEDGER_EPIC = "1d805023", "0f9e8d7c"
NONE_BOX = "Plan-Box: none -- a fixture commit that serves no box\n"


@pytest.fixture
def epics(repos):
    """The fixture main checkout on a `MMDD-N` branch that declares EPIC, with LEDGER_EPIC only in the ledger."""
    main, lease, plain = repos
    _git(main, "switch", "-q", "-c", "0101-1")
    (main / "agent" / "pr").mkdir(parents=True)
    (main / "agent" / "pr" / "0101-1.md").write_text(
        "### Port the guards\n\n`PR-TASK: %s`\n" % EPIC, encoding="utf-8"
    )
    (main / "agent" / "worklist").mkdir(parents=True)
    (main / "agent" / "worklist" / "epics.jsonl").write_text(
        '{"id": "%s", "title": "an older epic"}\n' % LEDGER_EPIC, encoding="utf-8"
    )
    return main, lease, plain


@pytest.mark.parametrize(
    ("trailer", "why"),
    [
        ("PR-TASK: tracked finding #d31b4054", "carries no PR-TASK trailer"),
        ("", "carries no PR-TASK trailer"),
        ("PR-TASK: f2757831", "PR-TASK id 'f2757831' names no epic"),
    ],
)
def test_pr_task_naming_no_declared_epic_in_a_lease_exits_1_with_the_epic_list(
    epics, monkeypatch, tmp_path, capsys, trailer, why
):
    _main, lease, _plain = epics
    rc = _run(monkeypatch, tmp_path, lease, BODY + trailer + "\n" + NONE_BOX)
    assert rc == 1
    err = capsys.readouterr().err
    assert why in err
    assert "Epics declared for this branch (agent/pr/0101-1.md):" in err
    assert "    %s  Port the guards" % EPIC in err


@pytest.mark.parametrize("epic", [EPIC, LEDGER_EPIC])
def test_pr_task_naming_a_declared_epic_in_a_lease_exits_0(epics, monkeypatch, tmp_path, epic):
    _main, lease, _plain = epics
    assert _run(monkeypatch, tmp_path, lease, BODY + "PR-TASK: %s\n" % epic + NONE_BOX) == 0


def test_pr_task_outside_a_lease_is_the_pre_bash_guards_business(epics, monkeypatch, tmp_path):
    main, _lease, _plain = epics
    assert _run(monkeypatch, tmp_path, main, BODY + "PR-TASK: tracked finding #d31b4054\n") == 0


def test_pr_task_control_the_old_hook_admits_the_malformed_lease_value(
    epics, monkeypatch, tmp_path
):
    _main, lease, _plain = epics
    for trailer in ("PR-TASK: tracked finding #d31b4054", "PR-TASK: f2757831"):
        message = BODY + trailer + "\n" + NONE_BOX
        assert _run(monkeypatch, tmp_path, lease, message) == 1
        with monkeypatch.context() as m:
            m.setattr(GH, "lease_pr_task_refusal", lambda _msg, _repo: 0)
            assert _run(monkeypatch, tmp_path, lease, message) == 0


def test_pr_task_hook_runs_under_a_real_git_commit(epics):
    _main, lease, _plain = epics
    (lease / "g.txt").write_text("g\n", encoding="utf-8")
    _git(lease, "add", "--", "g.txt")
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    base = ["git", "-c", "core.hooksPath=%s" % HOOKS, "commit", "-q", "--no-gpg-sign", "-m"]
    refused = subprocess.run(
        [*base, BODY + "PR-TASK: tracked finding #d31b4054\n" + NONE_BOX],
        cwd=str(lease),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "carries no PR-TASK trailer" in refused.stderr
    admitted = subprocess.run(
        [*base, BODY + "PR-TASK: %s\n" % EPIC + NONE_BOX],
        cwd=str(lease),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert admitted.returncode == 0, admitted.stderr
