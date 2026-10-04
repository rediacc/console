"""ci-trace.py prints a PR SIGNALS block on every verdict and during --wait, and the block never moves an exit code (agent/plans/PLAN-scheduled-red-detector.md, B2).

On PR #594 the review workflow's attempt comment (`class: error_max_turns`, attempt 1 of 3, a re-run command) never reached the session watching CI. Each case drives the REAL `main` with the rollup read (`_snapshot`) and the comment fetcher (`_fetcher`) stubbed, so the PR #594 body travels through the real `_pr_signals` and `wl_prsignals.classify`. The exit code of every verdict is
asserted three ways, signals readable, unreadable and raising, which is the mutation control for the invariance.
"""

import importlib.util
import json

import pytest

from rediacc_ci import paths

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")
HEAD = "4d3b950c524781f7854ae64e8f9b186c2e334737"
PR = 594
BRANCH = "1004-1"
ATTEMPT = {
    "id": 5976442241,
    "user": {"login": "github-actions[bot]", "type": "Bot"},
    "created_at": "2026-10-04T04:09:58Z",
    "updated_at": "2026-10-04T04:09:58Z",
    "body": (
        "<!-- claude-review-attempt: %s -->\nattempts: 1\nclass: error_max_turns\n"
        "A review pass was attempted on `4d3b950` and produced no report (`error_max_turns`).\n"
        "`gh workflow run claude-review.yml --ref <this PR's branch> -f pr_number=594`" % HEAD
    ),
}
RERUN = "gh workflow run claude-review.yml --ref 1004-1 -f pr_number=594"


@pytest.fixture(scope="module")
def ct():
    spec = importlib.util.spec_from_file_location("ci_trace_signals_under_test", TRACE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeFetch:
    def __init__(self, comments=None, fail=""):
        self.comments = [ATTEMPT] if comments is None else comments
        self.fail = fail
        self.paths = []

    def json(self, path):
        self.paths.append(path)
        if self.fail:
            return None, self.fail
        if "issues/%d/comments" % PR in path:
            return list(self.comments), ""
        if path.startswith("commits/"):
            return {"commit": {"committer": {"date": "2026-10-04T03:00:00Z"}}}, ""
        return None, "unrouted %s" % path


def payload(verdict, pr=PR, draft=False):
    return {
        "verdict": verdict,
        "detail": "d",
        "ref": BRANCH,
        "source": "pr" if pr else "branch",
        "pr": pr,
        "draft": draft,
        "url": "u",
        "owner": "rediacc",
        "name": "console",
        "head": HEAD,
        "live": ["x"] if verdict == "running" else [],
        "waiting": 1 if verdict == "running" else 0,
        "failing": [{"conclusion": "failure", "name": "Quality / Code"}]
        if verdict == "red"
        else [],
        "soft": [],
        "cancelled": [],
        "truncated": False,
        "foreign": 0,
        "cause": None,
        "ci_complete": "success",
        "run": 1,
    }


@pytest.fixture
def drive(ct, monkeypatch):
    def _drive(payloads, fetch, argv=()):
        seq = list(payloads)
        monkeypatch.setattr(
            ct, "_snapshot", lambda *_a, **_k: (seq.pop(0) if len(seq) > 1 else seq[0], None)
        )
        monkeypatch.setattr(ct, "_fetcher", lambda _root: fetch)
        monkeypatch.setattr(ct, "_record_final", lambda *_a, **_k: None)
        monkeypatch.setattr(ct.time, "sleep", lambda _s: None)
        return ct.main(["--ref", BRANCH, *argv])

    return _drive


VERDICTS = [("red", 1), ("green", 0), ("no-ci", 4), ("running", 2)]


@pytest.mark.parametrize(("verdict", "rc"), VERDICTS)
def test_block_on_every_verdict(drive, capsys, verdict, rc):
    assert drive([payload(verdict)], FakeFetch()) == rc
    out = capsys.readouterr().out
    assert "PR SIGNALS (#594 @ 4d3b950c)" in out
    assert "error_max_turns" in out
    assert "next: %s" % RERUN in out


@pytest.mark.parametrize(("verdict", "rc"), VERDICTS)
def test_unreadable_signals_keep_the_exit_code(drive, capsys, verdict, rc):
    assert drive([payload(verdict)], FakeFetch(fail="HTTP 502: bad gateway")) == rc
    out = capsys.readouterr().out
    assert "PR SIGNALS: unreadable (HTTP 502: bad gateway)" in out


@pytest.mark.parametrize(("verdict", "rc"), VERDICTS)
def test_a_raising_classifier_keeps_the_exit_code(ct, drive, capsys, monkeypatch, verdict, rc):
    """MUTATION CONTROL: a bug inside the signals path is reported as unreadable, never as a changed exit code."""
    # Importable through the sys.path hop the `ct` fixture's load of ci-trace made; the same module object ci-trace imports.
    assert ct.REPO_ROOT
    wl_prsignals = importlib.import_module("wl_prsignals")

    def boom(*_a, **_k):
        raise ValueError("classifier bug")

    monkeypatch.setattr(wl_prsignals, "classify", boom)
    assert drive([payload(verdict)], FakeFetch()) == rc
    assert "PR SIGNALS: unreadable (ValueError: classifier bug)" in capsys.readouterr().out


def test_a_branch_read_has_no_pr_and_makes_no_comment_read(drive, capsys):
    fetch = FakeFetch()
    assert drive([payload("green", pr=None)], fetch) == 0
    assert "PR SIGNALS" not in capsys.readouterr().out
    assert fetch.paths == []


def test_the_wait_loop_prints_a_signal_once(ct, drive, capsys, monkeypatch):
    monkeypatch.setattr(ct, "SIGNALS_POLL_S", 0)
    fetch = FakeFetch()
    running = payload("running")
    assert drive([running, running, running, running, payload("green")], fetch, ["--wait"]) == 0
    out = capsys.readouterr().out
    before_verdict = out.split("GREEN  PR #594")[0]
    # Read on every poll (throttle 0), printed on the first only.
    assert sum("issues/594/comments" in p for p in fetch.paths) >= 4
    assert before_verdict.count("error_max_turns") == 1
    # The verdict block still carries it, so the turn the watch ends starts with the action in hand.
    assert out.split("GREEN  PR #594")[1].count("error_max_turns") == 1


def test_the_wait_loop_is_throttled(ct, drive, monkeypatch):
    monkeypatch.setattr(ct, "SIGNALS_POLL_S", 3600)
    fetch = FakeFetch()
    running = payload("running")
    assert drive([running, running, running, payload("green")], fetch, ["--wait"]) == 0
    # One in-wait read on the first poll, one at the verdict; the hour-long throttle stops the rest.
    assert sum("issues/594/comments" in p for p in fetch.paths) == 2


def test_a_new_signal_mid_wait_is_printed_when_it_lands(ct, drive, capsys, monkeypatch):
    monkeypatch.setattr(ct, "SIGNALS_POLL_S", 0)
    fetch = FakeFetch(comments=[])
    running = payload("running")
    polls = {"n": 0}
    real_json = fetch.json

    def json_hook(path):
        if "issues/" in path:
            polls["n"] += 1
            if polls["n"] == 2:
                fetch.comments = [ATTEMPT]
        return real_json(path)

    fetch.json = json_hook
    assert drive([running, running, running, payload("green")], fetch, ["--wait"]) == 0
    out = capsys.readouterr().out.split("GREEN  PR #594")[0]
    assert out.count("error_max_turns") == 1


def test_json_carries_pr_signals_and_prints_one_document(drive, capsys):
    assert drive([payload("running"), payload("green")], FakeFetch(), ["--wait", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["pr_signals"]["state"] == "ok"
    assert data["pr_signals"]["signals"][0]["cls"] == "error_max_turns"
    assert data["pr_signals"]["signals"][0]["action"] == RERUN


def test_green_on_a_ready_pr_points_to_the_review_wait(drive, capsys):
    assert drive([payload("green")], FakeFetch(comments=[])) == 0
    out = capsys.readouterr().out
    assert "python3 .claude/hooks/stop/wl_prreview.py --wait" in out


def test_green_on_a_draft_keeps_the_ready_flip_text(drive, capsys):
    assert drive([payload("green", draft=True)], FakeFetch(comments=[])) == 0
    out = capsys.readouterr().out
    assert "still a DRAFT" in out
    assert "wl_prreview.py --wait" not in out
