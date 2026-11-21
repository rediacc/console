"""`check_plan_record.index_view`: the `--rendered-only` render reads each plan as the git index holds it (worklist #d28a11d7).

An uncommitted edit of a plan another session is writing changed that plan's byte size in the rendered `agent/INDEX.md` row, and the commit-policy `plan-renders` check (run against the commit's own tree) then refused an unrelated commit. The view holds the staged bytes of every tracked plan, links every other tracked file under agent/ to the working tree, and leaves untracked files out.
"""

import importlib.util
import pathlib
import subprocess

import pytest

from rediacc_ci import paths

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_record.py")
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


@pytest.fixture(scope="module")
def cpr():
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("PLAN_RECORD_ROOT", raising=False)
        paths.on_sys_path(GATE.parent)
        spec = importlib.util.spec_from_file_location("check_plan_record_index_view", GATE)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    _git(tmp_path, "init", "-q")
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    (plans / "PLAN-a.md").write_text("Status: draft\nA committed\n", encoding="utf-8")
    (plans / "PLAN-b.md").write_text("Status: draft\nB committed\n", encoding="utf-8")
    (plans / "QUEUE.md").write_text("queue committed\n", encoding="utf-8")
    _git(tmp_path, "add", "--", "agent")
    _git(tmp_path, *IDENT, "commit", "-q", "-m", "base")
    return tmp_path


def test_a_staged_plan_and_an_unstaged_plan_are_both_read_from_the_index(cpr, repo):
    plans = repo / "agent" / "plans"
    (plans / "PLAN-a.md").write_text("Status: draft\nA staged, longer\n", encoding="utf-8")
    _git(repo, "add", "--", "agent/plans/PLAN-a.md")
    (plans / "PLAN-b.md").write_text("Status: draft\nB edited by a live writer\n" * 40, "utf-8")
    (plans / "PLAN-c.md").write_text("Status: draft\nuntracked draft\n", encoding="utf-8")
    with cpr.index_view(repo) as (view, indexed):
        assert indexed is True
        got = view / "agent" / "plans"
        assert (got / "PLAN-a.md").read_text(
            encoding="utf-8"
        ) == "Status: draft\nA staged, longer\n"
        assert (got / "PLAN-b.md").read_text(encoding="utf-8") == "Status: draft\nB committed\n"
        assert (got / "PLAN-b.md").stat().st_size == len(b"Status: draft\nB committed\n")
        assert not (got / "PLAN-c.md").exists(), "an untracked plan is not rendered"


def test_a_non_plan_file_is_the_working_tree_file_and_a_write_lands_in_place(cpr, repo):
    queue = repo / "agent" / "plans" / "QUEUE.md"
    queue.write_text("queue edited, not staged\n", encoding="utf-8")
    with cpr.index_view(repo) as (view, _indexed):
        link = view / "agent" / "plans" / "QUEUE.md"
        assert link.read_text(encoding="utf-8") == "queue edited, not staged\n"
        link.write_text("queue rendered\n", encoding="utf-8")
    assert queue.read_text(encoding="utf-8") == "queue rendered\n"


def test_a_replaced_generated_file_is_carried_back(cpr, repo):
    with cpr.index_view(repo) as (view, _indexed):
        made = view / "agent" / "plans" / "QUEUE.md"
        made.unlink()
        made.write_text("replaced by the renderer\n", encoding="utf-8")
    assert (repo / "agent" / "plans" / "QUEUE.md").read_text(
        encoding="utf-8"
    ) == "replaced by the renderer\n"


def test_a_directory_that_is_no_git_checkout_is_read_in_place(cpr, tmp_path):
    (tmp_path / "agent").mkdir()
    with cpr.index_view(tmp_path) as (view, indexed):
        assert (view, indexed) == (tmp_path, False)
