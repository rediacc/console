"""`rediacc_ci.quality.submodule_branches` against the shell and jq it replaces.

WHAT THIS FILE COVERS AND WHAT IT CANNOT. The gh call sites cannot be exercised
locally, so the parts that DECIDE a merge -- the low-effort-reply normaliser, the
PR-link matcher, and the two jq oracles -- are exercised as pure functions
against the shapes the GitHub API actually returns. The branch/pointer logic is
covered end to end by `.ci/shadow/w7p2-submodule-branches.observations.jsonl`
over five distinct trees.
"""

import json
import pathlib
import subprocess

import pytest

from rediacc_ci.quality import submodule_branches as mod
from rediacc_ci.tests import differential as diff

# Every shape the twin's four-stage normaliser has to survive.
REPLIES = [
    "ok",
    "Done",
    "  fixed.  ",
    "THANKS!!",
    "will do",
    "hm, sure",
    "agreed.",
    "  ok  \n",
    "Fixed by moving the guard above the fetch, see line 42.",
    "done, and here is why that was the wrong shape",
    "",
    "a",
    "no?!",
    "See Above",
]


@pytest.mark.parametrize("reply", REPLIES)
def test_low_effort_normalisation_matches_the_shell(tmp_path: pathlib.Path, reply: str) -> None:
    """The port's normaliser and the twin's `tr | sed | sed` agree."""
    (tmp_path / "reply.txt").write_text(reply, encoding="utf-8")
    script = (
        'reply="$(cat reply.txt)"; '
        "printf '%s' \"$(echo \"$reply\" | tr '[:upper:]' '[:lower:]' | "
        "sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')\""
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    expected_low = out in mod.LOW_EFFORT_PATTERNS or len(out) < mod.MIN_SUBSTANTIVE_LENGTH
    assert mod.is_low_effort_reply(reply) is expected_low


LINK_CASES = [
    ("see https://github.com/rediacc/renet/pull/123", True),
    ("depends on rediacc/renet#123", True),
    ("rediacc/renet/pull/123", True),
    ("no mention here", False),
    ("rediacc/renet#124", False),
    ("rediacc/account#123", False),  # right number, wrong repo
    ("", False),
]


@pytest.mark.parametrize(("body", "linked"), LINK_CASES)
def test_pr_is_linked(body: str, linked: bool) -> None:
    url = "https://github.com/rediacc/renet/pull/123"
    assert mod.pr_is_linked(url, body) is linked


def _issue(body: str, at: str, login: str) -> dict:
    return {"body": body, "created_at": at, "user": {"login": login}}


REPORT_CASES = [
    ([_issue("hello", "2026-09-01T00:00:00Z", "human")], "none"),
    ([_issue("**Claude finished", "2026-09-01T00:00:00Z", "bot")], "unanswered"),
    (
        [
            _issue("**Claude finished", "2026-09-01T00:00:00Z", "bot"),
            _issue("thanks", "2026-09-01T01:00:00Z", "human"),
        ],
        "answered",
    ),
    (
        [
            _issue("**Claude finished", "2026-09-01T00:00:00Z", "bot"),
            _issue("still working", "2026-09-01T01:00:00Z", "bot"),
        ],
        "unanswered",
    ),
    (
        [
            _issue("**Claude finished one", "2026-09-01T00:00:00Z", "bot"),
            _issue("replied", "2026-09-01T01:00:00Z", "human"),
            _issue("**Claude finished two", "2026-09-01T02:00:00Z", "bot"),
        ],
        "unanswered",
    ),
    ([], "none"),
]


@pytest.mark.parametrize(("comments", "verdict"), REPORT_CASES)
def test_report_oracle_matches_jq(comments: list[dict], verdict: str) -> None:
    """The port's oracle and the twin's jq expression agree.

    The jq is lifted from the twin unchanged, so a divergence here is a
    divergence in the port and not in a paraphrase of it.
    """
    program = (
        '([.[] | select(.body | startswith("**Claude finished"))] '
        "| sort_by(.created_at) | last) as $r "
        '| if $r == null then "none" '
        "elif ([.[] | select(.created_at > $r.created_at "
        "and .user.login != $r.user.login)] | length) > 0 "
        'then "answered" else "unanswered" end'
    )
    proc = subprocess.run(
        ["jq", "-r", program],
        input=json.dumps(comments),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == verdict
    assert mod.judge_report(comments) == verdict


def _review(cid: int, reply_to, body: str) -> dict:
    return {"id": cid, "in_reply_to_id": reply_to, "body": body}


UNREPLIED_CASES = [
    ([_review(1, None, "why?"), _review(2, 1, "because the guard moved up")], 0),
    ([_review(1, None, "why?"), _review(2, 1, "done")], 1),
    ([_review(1, None, "why?")], 1),
    ([_review(1, None, "a"), _review(2, None, "b"), _review(3, 2, "a real answer here")], 1),
    ([], 0),
]


@pytest.mark.parametrize(("comments", "count"), UNREPLIED_CASES)
def test_unreplied_oracle(comments: list[dict], count: int) -> None:
    assert mod.count_unreplied(comments) == count


def test_detached_head_never_reads_as_a_branch(tmp_path: pathlib.Path) -> None:
    """`rev-parse --abbrev-ref HEAD` SUCCEEDS on a detached checkout.

    It prints the literal "HEAD", so a `|| echo main` fallback never fires. Two
    coincidentally-detached checkouts would then compare EQUAL and report a
    branch match that is not real.
    """
    subprocess.run(["git", "init", "-q", "-b", "feature-x"], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.invalid"], cwd=str(tmp_path), check=True
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    (tmp_path / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=str(tmp_path), check=True)
    assert mod.current_branch(tmp_path, env={}) == "feature-x"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", head], cwd=str(tmp_path), check=True)
    assert mod.current_branch(tmp_path, env={}) == "main"
    assert mod.submodule_branch(tmp_path, ".") == "detached"
