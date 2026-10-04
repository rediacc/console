"""wl_prsignals: the copied marker constants equal their sources, and a real attempt comment round-trips to its action (agent/plans/PLAN-scheduled-red-detector.md, B1).

The hook module cannot import `rediacc_ci`, so every marker it keys on is a copy. A copy that drifts makes a real review-attempt comment read as an unknown bot comment, and the re-run command it carries disappears from every watch again, which is the PR #594 blindness this module ended. Each pin below compares the copy with the live source, so the drift fails here first.

The round trips use the gate's own writer, `claude_review_gate.attempt_body`, beside the verbatim PR #594 comment: a hand-written fixture would pass against a format the gate no longer writes.
"""

import pathlib
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.core import review_budget
from rediacc_ci.review import claude_review_gate, pr_labels, review_status, review_table

paths.on_sys_path(paths.hooks_stop_dir())
import wl_prreview  # noqa: E402
import wl_prsignals as S  # noqa: E402

HEAD = "4d3b950c524781f7854ae64e8f9b186c2e334737"
OTHER = "a0f482ca8" + "0" * 31
BRANCH = "1004-1"
PR = 594
BOT = {"login": "github-actions[bot]", "type": "Bot"}

# The comment as GitHub served it on PR #594 (issuecomment-5976442241), body verbatim.
PR594_BODY = (
    "<!-- claude-review-attempt: 4d3b950c524781f7854ae64e8f9b186c2e334737 -->\n"
    "attempts: 1\n"
    "class: error_max_turns\n"
    "A review pass was attempted on `4d3b950` and produced no report (`error_max_turns`).\n"
    "That is an INFRASTRUCTURE-class failure, not a verdict on the code, so it does not\n"
    "close this head's budget yet: attempt 1 of 3.\n"
    "Re-run it on the same head, no push required:\n"
    "`gh workflow run claude-review.yml --ref <this PR's branch> -f pr_number=594`"
)


def comment(body, cid=1, created="2026-10-04T04:09:58Z", user=BOT):
    return {"id": cid, "user": user, "body": body, "created_at": created, "updated_at": created}


def label_guide_marker() -> str:
    src = paths.from_root(".ci", "scripts", "ci", "label-guide-comment.cjs").read_text(
        encoding="utf-8"
    )
    m = re.search(r"^const MARKER = '([^']+)';", src, re.MULTILINE)
    assert m, "label-guide-comment.cjs no longer declares `const MARKER = '...'`"
    return m.group(1)


# ---- the pins ----


def test_markers_equal_their_sources():
    assert S.MARKER_PREFIX == claude_review_gate.MARKER_PREFIX
    assert S.ATTEMPT_PREFIX == claude_review_gate.ATTEMPT_PREFIX
    assert S.TABLE_PREFIX == review_table.MARKER_PREFIX
    assert S.LEDGER_PREFIX == pr_labels.LEDGER_PREFIX
    assert label_guide_marker() == S.LABEL_GUIDE_MARKER


def test_report_head_equals_wl_prreview_and_matches_the_gate_header():
    assert S.REPORT_HEAD.pattern == wl_prreview.REPORT_HEAD.pattern
    assert S.REPORT_HEAD.flags == wl_prreview.REPORT_HEAD.flags
    header = "%s the automated review of %s**" % (claude_review_gate.REPORT_HEADER, HEAD[:7])
    found = S.REPORT_HEAD.search(header)
    assert found is not None
    assert found.group(1) == HEAD[:7]


def test_budget_and_outage_classes_equal_their_sources():
    assert S.INFRA_CLASSES == review_budget.INFRA_CLASSES
    assert S.REVIEW_FREE_REATTEMPTS_PER_HEAD == review_budget.REVIEW_FREE_REATTEMPTS_PER_HEAD
    assert S.REVIEW_MAX_ATTEMPTS_PER_HEAD == review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD
    assert S.OUTAGE_CLASSES == review_status.OUTAGE_CLASSES


def test_the_pins_can_fail(monkeypatch):
    """CONTROL: a drifted copy is caught, so the equality above is not vacuous."""
    monkeypatch.setattr(S, "ATTEMPT_PREFIX", "<!-- claude-review-try:")
    with pytest.raises(AssertionError):
        test_markers_equal_their_sources()


# ---- the attempt round trips ----


def test_pr594_comment_gives_the_rerun_with_the_branch_filled_in():
    sigs = S.classify([comment(PR594_BODY)], HEAD, PR, BRANCH)
    assert len(sigs) == 1
    sig = sigs[0]
    assert (sig["kind"], sig["cls"], sig["attempts"]) == ("attempt", "error_max_turns", 1)
    assert sig["action"] == "gh workflow run claude-review.yml --ref 1004-1 -f pr_number=594"
    block = S.render(sigs, PR, HEAD)
    assert block.splitlines()[0] == "PR SIGNALS (#594 @ 4d3b950c)"
    assert "error_max_turns" in block
    assert "--ref 1004-1" in block


@pytest.mark.parametrize(
    ("attempts", "cls", "disposition", "needle"),
    [
        (1, "error_max_turns", S.RERUN_FREE, "gh workflow run claude-review.yml --ref 1004-1"),
        (2, "error_during_execution", S.RERUN_FREE, "-f pr_number=594"),
        (3, "error_max_turns", S.PUSH, "push a change"),
        (1, "api_error_529", S.EXCUSED, "excused"),
        (1, "", S.PUSH, "push a change"),
    ],
)
def test_gate_written_attempts_round_trip(attempts, cls, disposition, needle):
    body = claude_review_gate.attempt_body(HEAD, attempts, cls, str(PR))
    sig = S.newest_attempt(S.classify([comment(body)], HEAD, PR, BRANCH))
    assert sig is not None
    assert sig["disposition"] == disposition
    assert needle in sig["action"]
    # The gate's own prose and the module agree on whether a re-run is free.
    assert ("Re-run it on the same head" in body) == (disposition == S.RERUN_FREE)


def test_the_disposition_is_what_decides_the_action(monkeypatch):
    """MUTATION CONTROL: with the free-reattempt allowance at 0, the PR #594 comment must no longer offer a re-run."""
    monkeypatch.setattr(S, "REVIEW_FREE_REATTEMPTS_PER_HEAD", 0)
    sig = S.classify([comment(PR594_BODY)], HEAD, PR, BRANCH)[0]
    assert sig["disposition"] == S.PUSH
    assert "gh workflow run" not in sig["action"]


def test_an_attempt_for_another_sha_is_ignored():
    assert S.classify([comment(PR594_BODY)], OTHER, PR, BRANCH) == []


def test_without_a_branch_the_placeholder_stays():
    sig = S.classify([comment(PR594_BODY)], HEAD, PR, "")[0]
    assert "--ref <this PR's branch>" in sig["action"]


# ---- the other signal kinds ----


def test_summary_reviewed_table_ledger_and_unknown_bot():
    summary = (
        "**Claude finished the automated review of %s**\n\n## Review verdict\n\n"
        '```json:review-findings\n[{"path": "a.py", "line": 1, "title": "t"}]\n```\n' % HEAD[:7]
    )
    comments = [
        comment("<!-- claude-reviewed: %s -->\nAutomated Claude review completed." % HEAD, 1),
        comment(summary, 2),
        comment("<!-- per-commit-reviews: %s -->\n| table |" % HEAD, 3),
        comment("<!-- claude-labels: %s -->\napplied" % OTHER, 4),
        comment("Deploy preview ready at https://example.invalid", 5, "2026-10-04T05:00:00Z"),
        comment("a human remark", 6, user={"login": "operator", "type": "User"}),
        comment(S.LABEL_GUIDE_MARKER + "\n### Label guide", 7, "2026-10-04T01:00:00Z"),
    ]
    sigs = S.classify(comments, HEAD, PR, BRANCH, head_date="2026-10-04T04:00:00Z")
    kinds = [s["kind"] for s in sigs]
    assert kinds == ["reviewed", "summary", "table", "bot"]
    assert "--status" in sigs[0]["action"]
    assert sigs[1]["findings"] == 1
    assert "--draft" in sigs[1]["action"]
    assert sigs[2]["action"] == ""
    assert sigs[3]["text"].startswith("github-actions[bot]: Deploy preview ready")


def test_a_shaless_comment_is_dropped_without_a_head_date():
    sigs = S.classify([comment("Deploy preview ready", 5)], HEAD, PR, BRANCH)
    assert sigs == []


def test_empty_render_says_so():
    assert S.render([], PR, HEAD) == "PR SIGNALS (#594 @ 4d3b950c): no bot comment for this head"


def test_module_reads_no_environment_and_makes_no_call():
    src = pathlib.Path(S.__file__).read_text(encoding="utf-8")
    for needle in ("os.environ", "getenv", "subprocess", "urllib"):
        assert needle not in src
