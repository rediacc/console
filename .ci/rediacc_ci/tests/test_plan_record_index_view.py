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


# THE TWO MODES RENDER FROM THE SAME INPUTS (worklist #e01814e8). `--rendered-only --update`, the generator `.ci/config/generated-artifacts.json` names for the commit-time `plan-renders` check, read each plan from the index while the full gate's `--update` and the plan verbs read the working tree. A session's own unstaged plan edit, committed in the `git commit -- <paths>` form that takes working-tree bytes, was therefore refused after the named generator ran and passed only after the full `--update`.


def _plan(status: str, body: str) -> str:
    return "# PLAN: %s\n\nStatus: %s\n\n## Tasks\n\n- [ ] T1 %s\n" % (body, status, body)


@pytest.fixture
def corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    _git(tmp_path, "init", "-q")
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (plans / ("PLAN-%s.md" % name)).write_text(_plan("approved", name), encoding="utf-8")
    _git(tmp_path, "add", "--", "agent")
    _git(tmp_path, *IDENT, "commit", "-q", "-m", "base")
    return tmp_path


def _full_render(cpr, root: pathlib.Path) -> bytes:
    cpr.rendered_problems(root, update=True)
    return (root / "agent" / "INDEX.md").read_bytes()


def _fast_render(cpr, root: pathlib.Path, staged: bool = False) -> bytes:
    (root / "agent" / "INDEX.md").unlink(missing_ok=True)
    cpr.rendered_only(root, update=True, staged=staged)
    return (root / "agent" / "INDEX.md").read_bytes()


def _edit_unstaged_and_add_intent(root: pathlib.Path) -> None:
    plans = root / "agent" / "plans"
    with (plans / "PLAN-a.md").open("a", encoding="utf-8") as fh:
        fh.write("- [ ] T2 an unstaged box this commit carries\n")
    (plans / "PLAN-d.md").write_text(_plan("approved", "intent to add"), encoding="utf-8")
    _git(root, "add", "-N", "--", "agent/plans/PLAN-d.md")


def test_control_the_staged_render_differs_from_the_full_render(cpr, corpus):
    """CONTROL FIRST: with an unstaged edit and an intent-to-add plan, the index reading (`--staged`, the old default) and the full gate's reading differ, so the equality below is a statement about inputs and not two renders that cannot disagree."""
    _edit_unstaged_and_add_intent(corpus)
    full = _full_render(cpr, corpus)
    staged = _fast_render(cpr, corpus, staged=True)
    assert full != staged
    assert b"PLAN-d.md" in full
    assert b"PLAN-d.md" not in staged, "an intent-to-add plan has no bytes in the index"


def test_rendered_only_update_writes_the_full_update_bytes(cpr, corpus):
    _edit_unstaged_and_add_intent(corpus)
    full = _full_render(cpr, corpus)
    assert _fast_render(cpr, corpus) == full


def test_staged_without_rendered_only_is_refused(cpr, capsys):
    assert cpr.main(["--staged"]) == 2
    assert "--rendered-only" in capsys.readouterr().err


def test_a_disagreement_names_its_first_differing_line(cpr):
    got = "# INDEX\n| PLAN-a.md | 120 |\n| PLAN-b.md | 99 |\n"
    want = "# INDEX\n| PLAN-a.md | 123 |\n| PLAN-b.md | 99 |\n"
    said = cpr.first_difference(got, want)
    assert "line 2" in said
    assert "`| PLAN-a.md | 120 |`" in said
    assert "`| PLAN-a.md | 123 |`" in said
    assert "line 4: present ends" in cpr.first_difference(got, got + "| PLAN-c.md | 1 |\n")
