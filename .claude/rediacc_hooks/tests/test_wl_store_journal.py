"""The checkout journal: a branch switch cannot hide or lose worklist events (worklist #8e513af2).

THE 2026-10-20 SEQUENCE, replayed in a disposable git repo. The store under agent/worklist/ is tracked, so `git switch main` swapped in main's stale committed copy and the Stop hook listed an item as open that had been ticked hours earlier on the live branch. Each case drives wl_store (and wl_epic) in-process against a temp repo with the store at its default location,
because the journal is deliberately off under $WORKLIST_STORE_DIR; one control proves the journal is what carries the result, by deleting it and watching the stale read come back.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import wl_core as C
import wl_epic as E
import wl_store as S

if TYPE_CHECKING:
    import pathlib

ME = "aaaabbbb"


def git(repo: pathlib.Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit_store(repo: pathlib.Path, msg: str) -> None:
    git(repo, "add", "-A", "agent")
    git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README").write_text("x\n")
    git(root, "add", "README")
    git(root, "commit", "-q", "-m", "init")
    for name in ("WORKLIST_STORE_DIR", "WORKLIST_AGENT_BRANCH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("WORKLIST_SESSION_ID", ME + "-0000-0000-0000-000000000000")
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(root)
    S._BRANCH_CACHE.clear()
    S._GITDIR_CACHE.clear()
    return root


def worklist() -> pathlib.Path:
    return C.worklist_for(C.project_start())


def state_of(item_id: str) -> str:
    rec = S.load(worklist(), sync=False).by_id.get(item_id)
    return rec["state"] if rec else "<absent>"


def tick_on_branch_then_switch_back(repo: pathlib.Path) -> str:
    """main holds the item OPEN; branch live ticks it and commits; switch to main. Returns the item id."""
    rid = S.add_item(worklist(), ME, "(%s) ship the thing" % ME)
    commit_store(repo, "store: item open")
    git(repo, "switch", "-q", "-c", "live")
    S.set_state(worklist(), ME, rid, "x", note="done, rc=0")
    commit_store(repo, "store: item ticked")
    git(repo, "switch", "-q", "main")
    return rid


def test_a_tick_on_the_live_branch_survives_a_switch_to_a_stale_branch(repo):
    rid = tick_on_branch_then_switch_back(repo)
    tracked = (repo / "agent" / "worklist" / ("%s.jsonl" % ME)).read_text()
    assert '"ev":"state"' not in tracked, "fixture is wrong: main's copy should predate the tick"
    assert state_of(rid) == "x"


def test_control_without_the_journal_the_stale_copy_wins(repo):
    """The control: the same sequence with the journal removed reads the item OPEN, which is the 2026-10-20 defect. Proves the case above is carried by the journal and not by the fixture."""
    rid = tick_on_branch_then_switch_back(repo)
    jd = S.journal_dir()
    assert jd is not None
    assert jd.is_dir()
    assert str(jd).startswith(str(repo / ".git")), (
        "the journal must live under the checkout's git dir"
    )
    shutil.rmtree(jd)
    assert state_of(rid) == " "


def test_an_event_appended_on_the_stale_branch_is_not_lost_switching_back(repo):
    rid = tick_on_branch_then_switch_back(repo)
    other = S.add_item(worklist(), ME, "(%s) found while on main" % ME)
    commit_store(repo, "store: item added on main")
    git(repo, "switch", "-q", "live")
    tracked = (repo / "agent" / "worklist" / ("%s.jsonl" % ME)).read_text()
    assert other not in tracked, "fixture is wrong: live's copy should lack main's event"
    assert state_of(other) == " "
    assert state_of(rid) == "x"


def test_union_never_doubles_an_event(repo):
    """Tracked and journal hold the same bytes for every event on the current branch: the union must carry each once."""
    tick_on_branch_then_switch_back(repo)
    S.add_item(worklist(), ME, "(%s) third" % ME)
    commit_store(repo, "store: third")
    git(repo, "switch", "-q", "live")
    events = S._read_events(worklist())
    keys = [(e.get("ev"), e.get("id"), e.get("ns")) for e in events]
    assert len(keys) == len(set(keys)) == 3


def test_phase_and_epics_survive_the_switch(repo):
    S.phase_event(worklist(), ME, ME, "merge", branch="live")
    E.record_epic(ME, "e1e1e1e1", "the epic", ["abc"])
    commit_store(repo, "store: phase and epic")
    git(repo, "switch", "-q", "-c", "older", "HEAD~1")
    assert not (repo / "agent" / "worklist" / "epics.jsonl").exists()
    assert "e1e1e1e1" in E.load_epics()
    assert S.phase_fold(worklist()).phase.get(ME, {}).get("mode") == "merge"


def test_store_override_disables_the_journal(repo, tmp_path, monkeypatch):
    """$WORKLIST_STORE_DIR points the store at a fixture or another tree; this checkout's journal must neither receive nor contribute events."""
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(tmp_path / "fixture-store"))
    assert S.journal_dir() is None
    S.add_item(worklist(), ME, "(%s) fixture item" % ME)
    assert not (repo / ".git" / S.JOURNAL_DIR_NAME).exists()
    assert (tmp_path / "fixture-store" / ("%s.jsonl" % ME)).is_file()


def test_a_linked_checkout_journal_is_its_own(repo, tmp_path):
    """Per checkout: a linked checkout's `.git` is a `gitdir:` FILE, and its journal lives in the git dir that file names, not in the main checkout's."""
    linked = tmp_path / "linked"
    linked.mkdir()
    private = repo / ".git" / "checkouts" / "linked"
    private.mkdir(parents=True)
    (linked / ".git").write_text("gitdir: %s\n" % private)
    S._GITDIR_CACHE.clear()
    jd = S.journal_dir(linked)
    assert jd == private.resolve() / S.JOURNAL_DIR_NAME
    assert S.journal_dir(repo) == repo / ".git" / S.JOURNAL_DIR_NAME
