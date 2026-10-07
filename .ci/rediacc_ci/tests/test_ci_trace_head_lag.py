"""ci-trace --wait must not judge the PR's OLD head right after a push (2026-10-07: PR #599 returned run 37633980671's verdict on c6cca783 seconds after 515d1f901 was pushed, because GitHub had not yet moved headRefOid). It holds until the PR head equals origin's tip, bounded, and exits 2 rather than answer for an old head."""

import importlib.util

import pytest

from rediacc_ci import paths

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")
OLD, NEW = "c6cca783" + "0" * 32, "515d1f90" + "1" * 32


@pytest.fixture
def ct():
    spec = importlib.util.spec_from_file_location("ci_trace_head_lag_under_test", TRACE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(head, verdict="red"):
    return {
        "verdict": verdict,
        "detail": "x",
        "ref": "1007-1",
        "source": "pr",
        "pr": 599,
        "draft": False,
        "url": "",
        "owner": "o",
        "name": "n",
        "head": head,
        "live": [],
        "waiting": 0,
        "failing": [],
        "soft": [],
        "cancelled": [],
        "truncated": False,
        "foreign": 0,
        "cause": None,
        "progress": None,
        "ci_complete": "failure" if verdict == "red" else "success",
        "run": None,
    }


def _drive(ct, monkeypatch, heads, tip, argv=("--wait", "--until-final", "--ref", "1007-1")):
    """Run main() with the PR head following `heads` (last one repeats). Returns (rc, polls, sleeps)."""
    polls = [0]
    sleeps: list[float] = []
    clock = [1000.0]

    def snap(*_a, **_k):
        h = heads[min(polls[0], len(heads) - 1)]
        polls[0] += 1
        return (_payload(h, "red" if h == OLD else "green"), None)

    def sleep(sec):
        sleeps.append(sec)
        clock[0] += sec

    monkeypatch.setattr(ct, "_snapshot", snap)
    monkeypatch.setattr(ct, "_remote_tip", lambda *_a, **_k: tip)
    monkeypatch.setattr(ct, "_gh_tick", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_gh_transitions", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_attach_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_show_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_record_final", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_signals_tick", lambda *_a, **_k: None)
    monkeypatch.setattr(ct, "_local_unpushed_note", lambda *_a, **_k: "")
    monkeypatch.setattr(ct, "_branch", lambda *_a, **_k: "1007-1")
    monkeypatch.setattr(ct.time, "sleep", sleep)
    monkeypatch.setattr(ct.time, "time", lambda: clock[0])
    rc = ct.main(list(argv))
    return rc, polls[0], sleeps


def test_lagging_head_that_catches_up_gives_the_new_heads_verdict(ct, monkeypatch):
    rc, polls, _sleeps = _drive(ct, monkeypatch, [OLD, OLD, NEW], NEW)
    assert rc == ct.EXIT_GREEN, "the old head's red must never be returned"
    assert polls == 3


def test_head_that_never_catches_up_is_no_verdict(ct, monkeypatch, capsys):
    rc, _polls, sleeps = _drive(ct, monkeypatch, [OLD], NEW)
    assert rc == ct.EXIT_NO_VERDICT
    cap = capsys.readouterr()
    assert "head-lag" in cap.err
    assert "RED" not in cap.out, "no verdict for the old head on stdout"
    assert sum(sleeps) >= ct.HEAD_LAG_S


def test_matching_head_behaves_as_before(ct, monkeypatch):
    rc, polls, sleeps = _drive(ct, monkeypatch, [OLD], OLD)
    assert rc == ct.EXIT_RED
    assert polls == 1
    assert sleeps == []


def test_unreadable_tip_is_never_folded_into_fine(ct, monkeypatch, capsys):
    rc, _polls, _sleeps = _drive(ct, monkeypatch, [OLD], "")
    assert rc == ct.EXIT_NO_VERDICT
    assert "unreadable" in capsys.readouterr().err


def test_non_wait_read_does_not_consult_the_remote(ct, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("a one-shot read must not call ls-remote")

    monkeypatch.setattr(ct, "_remote_tip", boom)
    rc, _polls, _s = _drive(ct, monkeypatch, [OLD], "ignored", argv=("--ref", "1007-1"))
    monkeypatch.undo()
    assert rc == ct.EXIT_RED


def test_unpushed_local_commits_are_named(ct, monkeypatch):
    calls = []

    def fake(_root, *argv):
        calls.append(argv)
        if argv[0] == "rev-parse":
            return 0, "a" * 40
        return 0, "2"

    monkeypatch.setattr(ct, "_git_out", fake)
    note = ct._local_unpushed_note(".", NEW)
    assert "2 commit(s) ahead" in note
    assert "never pushed" in note
    assert ct._local_unpushed_note(".", "a" * 40) == ""
