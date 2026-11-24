"""Named read failures in `wl_core` and `wl_store` (SF4 of agent/plans/PLAN-silent-failure-sweep.md).

THE CLASS: a reader that cannot answer used to hand back the same value as "nothing there". Here each one still answers what its callers route on, and the failure is said: in the evidence string it already returns (session_liveness, the compaction's kept rows), or as the `problem` half of `wl_core.read_landing_record`, which the stop's landing-stack advisory names once.

Every red case has a silent twin: a clean read adds no text and no row, so the naming cannot turn into noise.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess

import pytest
import wl_core as C
import wl_stack
import wl_store as S

DEV, PR = "1120-1", "1120-2"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


@pytest.fixture(autouse=True)
def _fresh_memo():
    C._LANDING_READS.clear()
    yield
    C._LANDING_READS.clear()


def _git(directory, *args) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_ENV)
    proc = subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, env=env
    )
    return proc.stdout.decode().strip()


@pytest.fixture
def world(tmp_path):
    """`(dev, landing, record_file)`: a main tree on DEV, a linked tree on PR, no record yet."""
    dev = tmp_path / "console"
    dev.mkdir()
    _git(dev, "init", "-q", "-b", "main")
    (dev / "f").write_text("x\n", encoding="utf-8")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "branch", DEV)
    _git(dev, "branch", PR)
    _git(dev, "symbolic-ref", "HEAD", "refs/heads/" + DEV)
    landing = tmp_path / "console-landing"
    _git(dev, "worktree", "add", "-q", str(landing), PR)
    dev, landing = pathlib.Path(os.path.realpath(dev)), pathlib.Path(os.path.realpath(landing))
    return dev, landing, dev / ".git" / C.LANDING_RECORD_NAME


# ---- wl_core.landing_record ----------------------------------------------------


def test_a_missing_record_stays_silent(world):
    dev, landing, _rec = world
    assert C.read_landing_record(dev) == (None, "")
    assert C.landing_record(landing) is None
    assert wl_stack.stack_report(dev, fetch=False) == ""


def test_a_malformed_record_binds_nothing_and_its_problem_reaches_the_caller(world):
    dev, landing, rec = world
    rec.write_text("{not json", encoding="utf-8")
    record, problem = C.read_landing_record(dev)
    assert record is None
    assert "is unreadable" in problem
    assert C.LANDING_RECORD_NAME in problem
    # The routing callers keep their record-less answer...
    assert C.landing_record(dev) is None
    assert C.landing_main(landing) is None


def test_a_malformed_record_is_named_once_in_the_stop_text(world):
    """The caller that speaks is the stop's landing-stack read: its advisory carries the same validator's problem."""
    dev, _landing, rec = world
    rec.write_text("{not json", encoding="utf-8")
    _record, problem = C.read_landing_record(dev)
    text = wl_stack.stack_report(dev, fetch=False)
    assert "LANDING STACK UNREAD" in text
    assert problem in text
    assert text.count(C.LANDING_RECORD_NAME) == 1


def test_a_record_off_the_validator_is_refused_with_its_defect(world):
    """The one validator is commit_policy's: a branch off the MMDD-N shape binds nothing here either (the old local reader accepted it), and the reason is commit_policy's own text."""
    _dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": "feature"}), encoding="utf-8")
    record, problem = C.read_landing_record(landing)
    assert record is None
    assert "is not an MMDD-N name" in problem
    assert C.landing_main(landing) is None


def test_a_valid_record_binds(world):
    dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": PR}), encoding="utf-8")
    assert C.read_landing_record(dev) == ({"path": str(landing), "branch": PR}, "")
    assert C.landing_main(landing) == dev


def test_one_record_version_is_validated_once(world, monkeypatch):
    """project_root is a hot path: commit_policy (which asks git) runs once per record version, and a rewrite is read afresh."""
    _dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": PR}), encoding="utf-8")
    policy = C._commit_policy()
    calls = []
    real = policy.read_landing_record

    def counted(root):
        calls.append(root)
        return real(root)

    monkeypatch.setattr(policy, "read_landing_record", counted)
    for _ in range(5):
        C.landing_record(landing)
    assert len(calls) == 1
    rec.write_text("{}", encoding="utf-8")
    assert C.read_landing_record(landing)[0] is None
    assert len(calls) == 2


def test_an_unloadable_validator_is_named_not_read_as_no_record(world, monkeypatch):
    dev, landing, rec = world
    rec.write_text(json.dumps({"path": str(landing), "branch": PR}), encoding="utf-8")

    def broken():
        raise ImportError("sf4-injected")

    monkeypatch.setattr(C, "_commit_policy", broken)
    record, problem = C.read_landing_record(dev)
    assert record is None
    assert "sf4-injected" in problem


# ---- wl_store.session_liveness -------------------------------------------------


def _stamp(minutes_ago: float) -> str:
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def liveness(tmp_path):
    """A worklist path with no sidecar, no brief, no transcript, and one old event by `abcd1234` from this host."""
    wl = tmp_path / "worklist.md"
    wl.write_text("", encoding="utf-8")
    events = [{"by": "abcd1234", "at": _stamp(600), "h": S.host_hash()}]
    return wl, events


def test_a_clean_liveness_read_adds_no_unread_note(liveness, tmp_path):
    wl, events = liveness
    verdict, why = S.session_liveness(wl, "abcd1234", str(tmp_path / "projects"), events)
    assert verdict == "idle"
    assert "unread" not in why


def test_a_failed_brief_read_is_named_in_the_evidence(liveness, monkeypatch, tmp_path):
    wl, events = liveness

    def boom(_wl):
        raise OSError("sf4-brief")

    monkeypatch.setattr(S, "read_briefs", boom)
    verdict, why = S.session_liveness(wl, "abcd1234", str(tmp_path / "projects"), events)
    assert verdict == "idle"
    assert "unread: the session brief (OSError: sf4-brief)" in why


def test_a_failed_transcript_stat_is_named_in_the_evidence(liveness, monkeypatch, tmp_path):
    wl, events = liveness

    def boom(_p, _d):
        raise OSError("sf4-transcript")

    monkeypatch.setattr(S, "owner_age_hours", boom)
    verdict, why = S.session_liveness(wl, "abcd1234", str(tmp_path / "projects"), events)
    assert verdict == "idle"
    assert "its transcript (OSError: sf4-transcript)" in why


def test_an_unparseable_event_stamp_is_named_in_the_evidence(liveness, tmp_path):
    wl, _events = liveness
    events = [{"by": "abcd1234", "at": "2026-13-99Tgarbage", "h": S.host_hash()}]
    verdict, why = S.session_liveness(wl, "abcd1234", str(tmp_path / "projects"), events)
    assert verdict == "idle"
    assert "its newest event stamp `2026-13-99Tgarbage` does not parse" in why


def test_a_live_verdict_still_names_an_earlier_unread_source(liveness, monkeypatch, tmp_path):
    wl, _events = liveness
    monkeypatch.setattr(S, "read_briefs", lambda _wl: (_ for _ in ()).throw(OSError("sf4-brief")))
    events = [{"by": "abcd1234", "at": _stamp(1), "h": S.host_hash()}]
    verdict, why = S.session_liveness(wl, "abcd1234", str(tmp_path / "projects"), events)
    assert verdict == "live"
    assert "sf4-brief" in why


# ---- wl_store._branch_of -------------------------------------------------------


def test_branch_of_lets_an_unexpected_failure_raise(monkeypatch, tmp_path):
    """git_branch already answers "" for a detached HEAD or a git that cannot run; anything else used to be cached as "" for the whole process."""
    S._BRANCH_CACHE.clear()

    def boom(_root):
        raise RuntimeError("sf4-branch")

    monkeypatch.setattr(C, "git_branch", boom)
    with pytest.raises(RuntimeError, match="sf4-branch"):
        S._branch_of(tmp_path)
    assert str(S.own_tree(tmp_path)) not in S._BRANCH_CACHE


def test_branch_of_caches_the_answer(monkeypatch, tmp_path):
    S._BRANCH_CACHE.clear()
    calls = []

    def branch(root):
        calls.append(root)
        return "1121-1"

    monkeypatch.setattr(C, "git_branch", branch)
    assert S._branch_of(tmp_path) == "1121-1"
    assert S._branch_of(tmp_path) == "1121-1"
    assert len(calls) == 1
    S._BRANCH_CACHE.clear()


# ---- wl_store.compact_store: a kept sidecar says why ---------------------------


def _compact(tmp_path, monkeypatch, peer_at):
    store = tmp_path / "store"
    store.mkdir()
    (store / "peer0001.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(store))
    wl = tmp_path / "worklist.md"
    wl.write_text("", encoding="utf-8")
    fold = type("Fold", (), {"items": [], "md_hash": ""})()
    monkeypatch.setattr(S, "load", lambda *_a, **_k: fold)
    monkeypatch.setattr(S, "_read_events", lambda *_a, **_k: [{"by": "peer0001", "at": peer_at}])
    monkeypatch.setattr(S, "session_liveness", lambda *_a, **_k: ("idle", "no artifact here"))
    monkeypatch.setattr(S, "snapshot_events", lambda *_a, **_k: [])
    S.compact_store(wl, root=tmp_path, me="me000001", projects_dir=str(tmp_path / "projects"))
    return store


def test_an_unparseable_peer_stamp_keeps_its_file_and_says_why(tmp_path, monkeypatch, capsys):
    store = _compact(tmp_path, monkeypatch, "not-a-stamp")
    out = capsys.readouterr().out
    assert (store / "peer0001.jsonl").exists()
    assert "kept peer0001.jsonl: writer is idle" in out
    assert "its newest event stamp `not-a-stamp` does not parse" in out


def test_an_old_peer_is_cleared_without_comment(tmp_path, monkeypatch, capsys):
    store = _compact(tmp_path, monkeypatch, _stamp(60 * 48))
    out = capsys.readouterr().out
    assert not (store / "peer0001.jsonl").exists()
    assert "kept" not in out
    assert "does not parse" not in out
