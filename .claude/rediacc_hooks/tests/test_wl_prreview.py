"""wl_prreview: the PR-level review answer tool (agent/plans/PLAN-github-pr-review-restore.md, box GR7).

Every case drives the module through a fake `gh` runner that holds one PR's comments, review threads and check runs, and records every argv it is handed, so "nothing posted" is a read of the call log rather than an absence of errors. The git side is real: a temporary repository with commits on HEAD and one commit that is not an ancestor, because ancestry and citations go through wl_review's git
helpers and a faked git would prove nothing about them.

Controls run beside the refusals they make meaningful: each refused file differs from an accepted one in exactly the disposition under test, and the accepted one posts.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest
from rediacc_ci.quality import review_comments as RC

from rediacc_hooks.tests import wlfix
from rediacc_hooks.wellknown import GH_REPO

P = wlfix.import_wl("wl_prreview")

REPO = GH_REPO
PR = 7
HEAD = "c" * 40
BRANCH = "1004-1"
SUMMARY_ID = 5961212756
BOT = {"login": "github-actions[bot]"}
ME = {"login": "operator"}

FINDINGS = [
    {"path": "a.py", "line": 2, "severity": "high", "title": "guard the empty list", "body": "x"},
    {"path": "a.py", "line": 4, "severity": "low", "title": "rename the helper", "body": "y"},
    {"path": "b.py", "line": 9, "severity": "medium", "title": "outside the diff", "body": "z"},
]


def summary_body(findings: list) -> str:
    return (
        "**Claude finished the automated review of %s**\n\n---\n\n## Review verdict: findings\n\n"
        "```json:review-findings\n%s\n```\n" % (HEAD[:7], json.dumps(findings))
    )


def inline_root(cid: int, finding: dict) -> dict:
    return {
        "id": cid,
        "in_reply_to_id": None,
        "user": BOT,
        "path": finding["path"],
        "line": finding["line"],
        "body": "**[%s]** - %s\n\n%s"
        % (finding["severity"].upper(), finding["title"], finding["body"]),
        "created_at": "2026-10-03T10:00:0%dZ" % (cid % 10),
    }


class FakeGh:
    """One PR on GitHub. `fail` names argv substrings whose calls exit 1."""

    def __init__(self, findings: list | None = FINDINGS, inline: bool = True):
        self.calls: list[list[str]] = []
        self.fail: list[str] = []
        self.check_title: str | None = None
        self.issue: list[dict] = [
            {
                "id": 1,
                "user": BOT,
                "body": "<!-- claude-reviewed: %s -->" % HEAD,
                "created_at": "2026-10-03T09:00:00Z",
            }
        ]
        if findings is not None:
            self.issue.append(
                {
                    "id": SUMMARY_ID,
                    "user": BOT,
                    "body": summary_body(findings),
                    "created_at": "2026-10-03T10:00:00Z",
                }
            )
        self.inline: list[dict] = []
        self.threads: dict[int, list] = {}
        if inline and findings:
            for i, f in enumerate(findings[:2]):
                cid = 900 + i
                self.inline.append(inline_root(cid, f))
                self.threads[cid] = ["THREAD_%d" % cid, False]
        self.seq = 0

    def posts(self) -> list[list[str]]:
        return [c for c in self.calls if "POST" in c or any("mutation" in a for a in c)]

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        joined = " ".join(argv)
        if any(f in joined for f in self.fail):
            return 1, "", "HTTP 502: bad gateway"
        if argv[:2] == ["repo", "view"]:
            return 0, json.dumps({"nameWithOwner": REPO}), ""
        if argv[:2] == ["pr", "view"]:
            return 0, json.dumps({"number": PR, "headRefOid": HEAD, "headRefName": BRANCH}), ""
        if argv[0] == "api" and argv[1] == "graphql":
            query = next(a for a in argv if a.startswith("query="))
            if "mutation" in query:
                tid = next(a for a in argv if a.startswith("id=")).split("=", 1)[1]
                for t in self.threads.values():
                    if t[0] == tid:
                        t[1] = True
                return 0, json.dumps({"data": {"resolveReviewThread": {"thread": {}}}}), ""
            nodes = [
                {"id": t[0], "isResolved": t[1], "comments": {"nodes": [{"databaseId": cid}]}}
                for cid, t in self.threads.items()
            ]
            page = {"hasNextPage": False, "endCursor": None}
            data = {
                "repository": {"pullRequest": {"reviewThreads": {"nodes": nodes, "pageInfo": page}}}
            }
            return 0, json.dumps({"data": data}), ""
        if argv[0] == "api" and "POST" in argv:
            body = next(a for a in argv if a.startswith("body=")).split("=", 1)[1]
            self.seq += 1
            created = "2026-10-03T11:00:%02dZ" % self.seq
            path = argv[3]
            if path.endswith("/replies"):
                parent = int(path.split("/")[-2])
                c = {
                    "id": 2000 + self.seq,
                    "in_reply_to_id": parent,
                    "user": ME,
                    "body": body,
                    "created_at": created,
                }
                self.inline.append(c)
            else:
                c = {"id": 3000 + self.seq, "user": ME, "body": body, "created_at": created}
                self.issue.append(c)
            return 0, json.dumps(c), ""
        if argv[0] == "api" and "/issues/%d/comments" % PR in argv[1]:
            return 0, json.dumps([self.issue]), ""
        if argv[0] == "api" and "/pulls/%d/comments" % PR in argv[1]:
            return 0, json.dumps([self.inline]), ""
        if argv[0] == "api" and "/check-runs" in argv[1]:
            runs = []
            if self.check_title is not None:
                runs.append(
                    {
                        "name": "Review Complete",
                        "started_at": "2026-10-03T10:00:00Z",
                        "output": {"title": self.check_title},
                    }
                )
            return 0, json.dumps({"check_runs": runs}), ""
        return 1, "", "fake gh: unrouted %r" % argv


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> dict:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "a.py").write_text("".join("line %d\n" % i for i in range(1, 7)), encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "one")
    (root / "a.py").write_text("".join("line %d!\n" % i for i in range(1, 7)), encoding="utf-8")
    _git(root, "commit", "-q", "-am", "two")
    fix = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    stray = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree, "-m", "stray"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"root": root, "fix": fix, "stray": stray, "tmp": tmp_path}


ITEMS = {"abcdef12": (" ", "F2 of the PR review"), "deadbe00": ("x", "closed one")}


def good_lines(fix: str) -> list[str]:
    return [
        "# summary: %d" % SUMMARY_ID,
        "F1 fixed %s" % fix,
        "F2 not-a-bug | the helper name matches a.py:3 and the call sites",
        "F3 deferred #abcdef12",
    ]


def answer(repo: dict, gh: FakeGh, lines: list[str]) -> int:
    path = repo["tmp"] / "dispositions.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return P.cmd_answer(PR, path, gh, repo_root=repo["root"], items=lambda: ITEMS)


# ---- the selector is review_comments', by value ----


def test_selector_constants_equal_review_comments():
    assert P.FENCE_NEEDLE == RC.FENCE_NEEDLE
    assert P.VERDICT_HEADING.pattern == RC.VERDICT_HEADING.pattern
    assert P.VERDICT_HEADING.flags == RC.VERDICT_HEADING.flags
    assert P.FENCE_OPENER.pattern == RC.FENCE_OPENER.pattern
    assert P.FENCE_CLOSER.pattern == RC.FENCE_CLOSER.pattern
    assert P.LOW_EFFORT_PATTERNS == RC.LOW_EFFORT_PATTERNS
    assert P.INLINE_MIN_CHARS == RC.INLINE_MIN_CHARS
    assert P.SUMMARY_MIN_CHARS == RC.SUMMARY_MIN_CHARS
    assert P.SUMMARY_LONGFORM_CHARS == RC.SUMMARY_LONGFORM_CHARS
    assert P.TRAILING_PUNCT.pattern == RC.TRAILING_PUNCT.pattern


@pytest.mark.parametrize("findings", [FINDINGS, [], None])
def test_summary_verdict_agrees_with_review_comments(findings):
    gh = FakeGh(findings)
    ours = P.summary_verdict(gh.issue)
    theirs = RC.summary_verdict(gh.issue)
    assert ours[0] == theirs[0]
    assert (ours[1] or {}).get("id") == (theirs[1] or {}).get("id")


def test_module_reads_no_environment():
    src = pathlib.Path(P.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in src
    assert "getenv" not in src


# ---- --check and check_state ----


def test_check_no_summary_rc0():
    gh = FakeGh(None)
    assert P.cmd_check(None, gh) == 0
    assert gh.posts() == []


def test_check_empty_findings_rc0_nothing_posted(repo):
    gh = FakeGh([])
    assert P.cmd_check(None, gh) == 0
    assert P.check_state(None, gh)["verdict"] == "empty"
    assert answer(repo, gh, ["# summary: %d" % SUMMARY_ID]) == 0
    assert gh.posts() == []


def test_check_unanswered_rc1():
    gh = FakeGh()
    state = P.check_state(None, gh)
    assert state["rc"] == 1
    assert state["summary"] == str(SUMMARY_ID)
    assert state["head"] == HEAD
    assert "--draft" in state["reason"]
    assert P.cmd_check(None, gh) == 1


def test_check_unresolved_thread_with_answered_summary_rc1():
    gh = FakeGh()
    gh.issue.append(
        {
            "id": 4000,
            "user": ME,
            "body": "Answer to #issuecomment-%d: every finding is fixed in the follow-up commit."
            % SUMMARY_ID,
            "created_at": "2026-10-03T12:00:00Z",
        }
    )
    assert RC.summary_verdict(gh.issue)[0] == "answered"
    gh.threads[900][1] = True
    state = P.check_state(None, gh)
    assert state["rc"] == 1
    assert state["verdict"] == "answered"
    assert state["unresolved"] == [901]
    assert P.cmd_check(None, gh) == 1
    gh.threads[901][1] = True
    assert P.cmd_check(None, gh) == 0


def test_check_state_carries_review_token():
    gh = FakeGh()
    assert not P.check_state(None, gh)["review_token"]
    gh.check_title = "hygiene: 1 summary unanswered"
    state = P.check_state(None, gh)
    assert state["review_token"] in P.TITLE_TOKENS
    assert state["review_token"].startswith("hyg")


def test_check_unreadable_rc2():
    gh = FakeGh()
    gh.fail = ["/issues/"]
    assert P.cmd_check(None, gh) == 2
    assert P.check_state(None, gh)["verdict"] == "unreadable"


# ---- --status ----


def test_status_lists_findings_and_threads(capsys):
    gh = FakeGh()
    assert P.cmd_status(None, gh) == 0
    out = capsys.readouterr().out
    assert "summary #issuecomment-%d" % SUMMARY_ID in out
    assert "F1 [high] a.py:2" in out
    assert "inline 900 unanswered" in out
    assert "F3 [medium] b.py:9 outside the diff (no inline thread)" in out


def test_status_unreadable_rc2():
    gh = FakeGh()
    gh.fail = ["repo view"]
    assert P.cmd_status(None, gh) == 2


# ---- --wait ----


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


@pytest.mark.parametrize("token", ["current", "capped", "exhausted", "outage", "hygiene"])
def test_wait_reviewed_token_rc0(token):
    gh = FakeGh()
    gh.check_title = "%s: reviewed %s" % (token, HEAD[:7])
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 0
    assert clock.t == 0


def test_wait_failed_run_rc4_names_the_investigation(capsys):
    gh = FakeGh()
    gh.check_title = "failed-run: claude-code-action exited 1 at step Run review"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 4
    assert clock.t == 0
    err = capsys.readouterr().err
    assert "claude-code-action exited 1 at step Run review" in err
    assert "investigate the Claude Review run" in err
    assert "gh workflow run claude-review.yml -f pr_number=%d" % PR in err


@pytest.mark.parametrize("title", [None, "stale: head moved", "draft: not ready", "nonsense"])
def test_wait_times_out_rc3(title, capsys):
    gh = FakeGh()
    gh.check_title = title
    clock = Clock()
    assert P.cmd_wait(None, 100, gh, sleeper=clock.sleep, clock=clock) == 3
    assert clock.t >= 100
    err = capsys.readouterr().err
    assert "does not merge on a timeout" in err


def test_wait_tokens_cover_every_title_token():
    assert set(P.TITLE_TOKENS) == {
        "current",
        "capped",
        "exhausted",
        "outage",
        "draft",
        "stale",
        "failed-run",
        "hygiene",
    }
    expected = set(P.TITLE_TOKENS) - {"draft", "stale"}
    assert expected == P.TERMINAL_TOKENS


def test_wait_sees_a_review_that_lands_midway():
    gh = FakeGh()
    clock = Clock()

    def sleeper(s: float) -> None:
        clock.sleep(s)
        gh.check_title = "current: done"

    assert P.cmd_wait(None, 600, gh, sleeper=sleeper, clock=clock) == 0


# ---- --wait names the review-attempt class (agent/plans/PLAN-scheduled-red-detector.md, B3) ----


def attempt_comment(attempts: int, cls: str, sha: str = HEAD) -> dict:
    """The comment claude_review_gate.attempt_body writes, in the shape PR #594 carried."""
    return {
        "id": 77,
        "user": BOT,
        "body": "<!-- claude-review-attempt: %s -->\nattempts: %d\nclass: %s\n"
        "A review pass was attempted on `%s` and produced no report (`%s`)."
        % (sha, attempts, cls, sha[:7], cls),
        "created_at": "2026-10-03T10:30:00Z",
    }


def test_wait_failed_run_names_the_attempt_class_and_the_rerun(capsys):
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(1, "error_max_turns"))
    gh.check_title = "failed-run: no report"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 4
    err = capsys.readouterr().err
    assert "review attempt (class error_max_turns)" in err
    assert "gh workflow run claude-review.yml --ref %s -f pr_number=%d" % (BRANCH, PR) in err
    # The generic investigation text stays beside it.
    assert "investigate the Claude Review run" in err


def test_wait_failed_run_without_an_attempt_comment_keeps_the_fallback(capsys):
    gh = FakeGh(None)
    gh.check_title = "failed-run: no report"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 4
    err = capsys.readouterr().err
    assert "review attempt" not in err
    assert "investigate the Claude Review run" in err


def test_wait_ignores_an_attempt_for_another_head(capsys):
    """MUTATION CONTROL: the class is shown only for the PR head's own attempt."""
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(1, "error_max_turns", sha="d" * 40))
    gh.check_title = "failed-run: no report"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 4
    assert "review attempt" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("token", "attempts", "cls", "needle"),
    [
        ("exhausted", 3, "error_max_turns", "push a change"),
        ("outage", 1, "api_error_529", "excused"),
    ],
)
def test_wait_reviewed_with_a_warning_names_the_attempt(capsys, token, attempts, cls, needle):
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(attempts, cls))
    gh.check_title = "%s: passing with a warning" % token
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 0
    out = capsys.readouterr().out
    assert "review attempt (class %s)" % cls in out
    assert needle in out


def test_wait_current_does_not_read_the_comments():
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(1, "error_max_turns"))
    gh.check_title = "current: reviewed"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 0
    assert not any("/issues/" in " ".join(c) for c in gh.calls)


def test_wait_stale_timeout_names_the_attempt(capsys):
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(2, "error_during_execution"))
    gh.check_title = "stale: the current head has not been reviewed"
    clock = Clock()
    assert P.cmd_wait(None, 100, gh, sleeper=clock.sleep, clock=clock) == 3
    err = capsys.readouterr().err
    assert "does not merge on a timeout" in err
    assert "review attempt (class error_during_execution)" in err
    assert "--ref %s" % BRANCH in err


def test_wait_an_unreadable_comment_list_keeps_the_fallback(capsys):
    gh = FakeGh(None)
    gh.issue.append(attempt_comment(1, "error_max_turns"))
    gh.fail = ["/issues/"]
    gh.check_title = "failed-run: no report"
    clock = Clock()
    assert P.cmd_wait(None, 60, gh, sleeper=clock.sleep, clock=clock) == 4
    err = capsys.readouterr().err
    assert "review attempt" not in err
    assert "investigate the Claude Review run" in err


# ---- --draft ----


def test_draft_one_line_per_finding(capsys):
    gh = FakeGh()
    assert P.cmd_draft(None, gh) == 0
    out = capsys.readouterr().out
    assert "# summary: %d" % SUMMARY_ID in out
    lines = [ln for ln in out.splitlines() if ln and not ln.startswith("#")]
    assert lines == ["F1 TODO", "F2 TODO", "F3 TODO"]
    summary, disp, errors = P.parse_dispositions(out)
    assert summary == str(SUMMARY_ID)
    assert sorted(disp) == [1, 2, 3]
    assert errors == []


# ---- --answer refusals, each beside the accepted control ----


def test_answer_control_posts(repo):
    gh = FakeGh()
    assert answer(repo, gh, good_lines(repo["fix"])) == 0
    assert gh.posts() != []


def test_answer_refuses_non_ancestor_fixed_sha(repo, capsys):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    lines[1] = "F1 fixed %s" % repo["stray"]
    assert answer(repo, gh, lines) == 1
    assert "not an ancestor of HEAD" in capsys.readouterr().err
    assert gh.posts() == []


def test_answer_refuses_evidence_without_citation(repo, capsys):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    lines[2] = "F2 not-a-bug | the helper name is fine and matches the call sites"
    assert answer(repo, gh, lines) == 1
    assert "must cite a path:line" in capsys.readouterr().err
    assert gh.posts() == []


def test_answer_refuses_missing_disposition(repo, capsys):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    del lines[3]
    assert answer(repo, gh, lines) == 1
    assert "F3: no disposition" in capsys.readouterr().err
    assert gh.posts() == []


def test_answer_refuses_todo_left_in(repo, capsys):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    lines[3] = "F3 TODO"
    assert answer(repo, gh, lines) == 1
    assert "F3: no disposition" in capsys.readouterr().err
    assert gh.posts() == []


@pytest.mark.parametrize(
    ("item", "needle"), [("0badc0de", "does not exist"), ("deadbe00", "is not open")]
)
def test_answer_refuses_bad_deferral(repo, capsys, item, needle):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    lines[3] = "F3 deferred #%s" % item
    assert answer(repo, gh, lines) == 1
    assert needle in capsys.readouterr().err
    assert gh.posts() == []


def test_an_unreadable_worklist_refuses_every_deferral_as_unreadable(repo):
    calls = []

    def broken() -> dict:
        calls.append(1)
        raise OSError("store locked")

    errors = P.validate({1: "deferred #0badc0de", 2: "deferred #deadbe00"}, 2, repo["root"], broken)
    assert errors == [
        "F1: the worklist cannot be read (store locked)",
        "F2: the worklist cannot be read (store locked)",
    ]
    assert calls == [1]


def test_answer_refuses_stale_summary_id(repo, capsys):
    gh = FakeGh()
    lines = good_lines(repo["fix"])
    lines[0] = "# summary: 123"
    assert answer(repo, gh, lines) == 1
    assert "run --draft again" in capsys.readouterr().err
    assert gh.posts() == []


# ---- --answer posts the shape the gate accepts ----


def test_answer_reply_cites_summary_and_clears_review_comments(repo):
    gh = FakeGh()
    assert RC.summary_verdict(gh.issue)[0] == "unanswered"
    assert answer(repo, gh, good_lines(repo["fix"])) == 0
    top = [c for c in gh.posts() if c[3] == "repos/%s/issues/%d/comments" % (REPO, PR)]
    assert len(top) == 1
    body = next(a for a in top[0] if a.startswith("body=")).split("=", 1)[1]
    assert "#issuecomment-%d" % SUMMARY_ID in body
    assert "| F1 | high | `a.py:2` | guard the empty list | fixed in %s |" % repo["fix"] in body
    assert "deferred to worklist item #abcdef12" in body
    summary = RC.newest_summary(gh.issue)
    assert summary is not None
    assert summary["id"] == SUMMARY_ID
    reply = RC.summary_reply(gh.issue, summary)
    assert reply is not None
    assert reply["body"] == body
    assert RC.summary_verdict(gh.issue)[0] == "answered"
    assert P.cmd_check(None, gh) == 0


def test_answer_replies_in_each_inline_thread_and_resolves_it(repo):
    gh = FakeGh()
    assert answer(repo, gh, good_lines(repo["fix"])) == 0
    replies = [c for c in gh.posts() if c[3].endswith("/replies")]
    assert sorted(c[3] for c in replies) == [
        "repos/%s/pulls/%d/comments/900/replies" % (REPO, PR),
        "repos/%s/pulls/%d/comments/901/replies" % (REPO, PR),
    ]
    resolves = [c for c in gh.calls if any("resolveReviewThread" in a for a in c)]
    assert sorted(next(a for a in c if a.startswith("id=")) for c in resolves) == [
        "id=THREAD_900",
        "id=THREAD_901",
    ]
    assert all(t[1] for t in gh.threads.values())
    unreplied, low_effort, _n = RC.inline_findings(gh.inline)
    assert unreplied == []
    assert low_effort == []


def test_answer_partial_api_failure_is_rc2(repo):
    gh = FakeGh()
    gh.fail = ["/replies"]
    assert answer(repo, gh, good_lines(repo["fix"])) == 2


def test_help_rc0(capsys):
    with pytest.raises(SystemExit) as exc:
        P.main(["--help"])
    assert exc.value.code == 0
    assert "--answer" in capsys.readouterr().out
