"""`rediacc_ci.core.review_budget`: the review cap tiers and the attempt ledger, pinned as numbers.

The gate (`claude_review_gate`) and the reporter (`review_status`) both import these rules, so a changed number here changes both at once; these cases are what makes such a change a visible decision. The network half is driven through a fake `ghx.gh`: a failed read must raise, never answer 0.
"""

import pytest

from rediacc_ci.core import ghx
from rediacc_ci.core import review_budget as rb

SHA_A = "a" * 40
SHA_B = "b" * 40


# --------------------------------------------------------------------------- the cap tiers ---------------------------------------------------------------------------


def test_the_cap_tiers_are_pinned():
    assert rb.CAP_TIERS == ((10000, 3), (50000, 5), (None, 7))
    assert rb.CAP_FALLBACK == 3


@pytest.mark.parametrize(
    ("lines", "cap"),
    [
        (0, 3),
        (1, 3),
        (10000, 3),
        (10001, 5),
        (50000, 5),
        (50001, 7),
        (100000, 7),
        (10**9, 7),
        ("10001", 5),
    ],
)
def test_cap_for_is_inclusive_at_each_upper_bound(lines, cap):
    assert rb.cap_for(lines) == cap


@pytest.mark.parametrize("junk", ["", "abc", "-5", "1e3", " 20000", None])
def test_a_non_numeric_line_count_lands_in_the_smallest_tier(junk):
    assert rb.cap_for(junk) == 3


# --------------------------------------------------------------------------- attempt constants and classes ---------------------------------------------------------------------------


def test_the_attempt_constants_are_pinned():
    assert rb.REVIEW_FREE_REATTEMPTS_PER_HEAD == 2
    assert rb.REVIEW_MAX_ATTEMPTS_PER_HEAD == 3
    assert rb.INFRA_CLASSES == ("error_max_turns", "error_during_execution")
    assert all(" " not in cls for cls in rb.INFRA_CLASSES)
    assert rb.REPORT_NEEDLE == "**Claude finished"
    assert rb.ATTEMPT_EOF == "---REVIEW-ATTEMPT-EOF---"
    assert rb.DIFF_LOC_FAILS_TO_ZERO == 0


@pytest.mark.parametrize(
    ("cls", "infra"),
    [
        ("error_max_turns", True),
        ("error_during_execution", True),
        ("", False),
        ("review step did not succeed", False),
        ("error_max_turns ", False),
    ],
)
def test_class_is_infra(cls, infra):
    assert rb.class_is_infra(cls) is infra


# --------------------------------------------------------------------------- parse_attempt_states ---------------------------------------------------------------------------


def body(sha, attempts=None, cls=None):
    lines = ["<!-- claude-review-attempt: %s -->" % sha]
    if attempts is not None:
        lines.append("attempts: %s" % attempts)
    if cls is not None:
        lines.append("class: %s" % cls)
    lines.append("A review pass was attempted.")
    return "\n".join(lines)


def test_parse_reads_each_record_between_sentinels():
    raw = "\n".join(
        [body(SHA_A, 2, "error_max_turns"), rb.ATTEMPT_EOF, body(SHA_B, 1, "x"), rb.ATTEMPT_EOF]
    )
    assert rb.parse_attempt_states(raw) == [
        rb.AttemptState(SHA_A, 2, "error_max_turns"),
        rb.AttemptState(SHA_B, 1, "x"),
    ]


def test_parse_keeps_a_trailing_record_with_no_sentinel():
    assert rb.parse_attempt_states(body(SHA_A, 3, "c")) == [rb.AttemptState(SHA_A, 3, "c")]


def test_a_legacy_marker_reads_as_one_attempt_of_unknown_class():
    assert rb.parse_attempt_states(body(SHA_A)) == [rb.AttemptState(SHA_A, 1, "")]


def test_a_non_numeric_count_reads_as_the_default_one():
    assert rb.parse_attempt_states(body(SHA_A, "zz", "c")) == [rb.AttemptState(SHA_A, 1, "c")]


def test_a_record_with_no_sha_yields_nothing_and_empty_input_yields_nothing():
    assert rb.parse_attempt_states("attempts: 3\nclass: c\n" + rb.ATTEMPT_EOF) == []
    assert rb.parse_attempt_states("") == []


def test_the_first_key_in_a_record_names_its_sha():
    raw = body(SHA_A, 1, "c") + "\nquoted: claude-review-attempt: %s" % SHA_B
    assert rb.parse_attempt_states(raw)[0].sha == SHA_A


# --------------------------------------------------------------------------- charging and exhaustion ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("states", "charged"),
    [
        ([], 0),
        ([rb.AttemptState(SHA_A, 1, "error_max_turns")], 0),
        ([rb.AttemptState(SHA_A, 2, "error_max_turns")], 0),
        ([rb.AttemptState(SHA_A, 3, "error_max_turns")], 1),
        ([rb.AttemptState(SHA_A, 1, "")], 1),
        ([rb.AttemptState(SHA_A, 3, "other")], 3),
        ([rb.AttemptState(SHA_A, 1, "error_during_execution"), rb.AttemptState(SHA_B, 5, "")], 5),
    ],
)
def test_chargeable_attempts(states, charged):
    assert rb.chargeable_attempts(states) == charged


def test_head_attempt_state_takes_the_last_row_and_defaults_to_zero():
    states = [rb.AttemptState(SHA_A, 1, "x"), rb.AttemptState(SHA_A, 2, "y")]
    assert rb.head_attempt_state(states, SHA_A) == (2, "y")
    assert rb.head_attempt_state(states, SHA_B) == (0, "")


@pytest.mark.parametrize(
    ("attempts", "cls", "exhausted"),
    [
        (2, "error_max_turns", False),
        (3, "error_max_turns", True),
        (4, "error_during_execution", True),
        (9, "", False),
        (9, "other", False),
    ],
)
def test_only_an_infra_head_at_the_ceiling_is_exhausted(attempts, cls, exhausted):
    assert rb.head_is_exhausted([rb.AttemptState(SHA_A, attempts, cls)], SHA_A) is exhausted


def test_an_unrecorded_head_is_never_exhausted():
    assert rb.head_is_exhausted([], SHA_A) is False


@pytest.mark.parametrize(
    ("posted", "spent", "total"),
    [(0, 0, 0), (2, 1, 3), ("  2\n", " 1", 3), ("", 4, 4), ("", "", 0)],
)
def test_spend_total(posted, spent, total):
    assert rb.spend_total(posted, spent) == total


# --------------------------------------------------------------------------- the network half ---------------------------------------------------------------------------


class FakeGh:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return ghx.GhResult(["gh", *args], self.rc, self.stdout, self.stderr)


COMMENTS = (
    '[{"user": {"login": "github-actions[bot]"}, "body": "**Claude finished the automated review of aaaaaaa**"},'
    ' {"user": {"login": "someone"}, "body": "**Claude finished fake"},'
    ' {"user": {"login": "github-actions[bot]"}, "body": "<!-- claude-review-attempt: %s -->\\nattempts: 2\\nclass: error_max_turns"},'
    ' {"user": {"login": "github-actions[bot]"}, "body": "<!-- claude-review-attempt: %s -->\\nattempts: 2"}]'
    % (SHA_A, SHA_B)
)


def test_report_count_counts_github_actions_reports_only(monkeypatch):
    fake = FakeGh(stdout=COMMENTS)
    monkeypatch.setattr(rb.ghx, "gh", fake)
    assert rb.report_count(42, repo="o/r") == 1
    args, kwargs = fake.calls[0]
    assert args == ["api", "repos/o/r/issues/42/comments", "--paginate"]
    # core.gh_retry owns the retry (5xx and connection faults only) and calls ghx once per attempt.
    assert kwargs["attempts"] == 1


def test_attempt_states_and_spent_count(monkeypatch):
    monkeypatch.setattr(rb.ghx, "gh", FakeGh(stdout=COMMENTS))
    prefix = "<!-- claude-review-attempt:"
    assert rb.attempt_states(42, prefix, repo="o/r") == [
        rb.AttemptState(SHA_A, 2, "error_max_turns"),
        rb.AttemptState(SHA_B, 2, ""),
    ]
    assert rb.spent_attempt_count(42, prefix, repo="o/r") == 2


@pytest.mark.parametrize(
    "call",
    [
        lambda: rb.report_count(42, repo="o/r"),
        lambda: rb.attempt_states(42, "<!-- claude-review-attempt:", repo="o/r"),
        lambda: rb.spent_attempt_count(42, "<!-- claude-review-attempt:", repo="o/r"),
        lambda: rb.diff_loc(42, repo="o/r"),
    ],
)
def test_a_failed_read_raises_rather_than_answering_zero(monkeypatch, call):
    monkeypatch.setattr(rb.ghx, "gh", FakeGh(rc=1, stderr="HTTP 403: API rate limit exceeded"))
    with pytest.raises(ghx.GhError):
        call()


def test_diff_loc_falls_to_zero_only_when_asked(monkeypatch):
    monkeypatch.setattr(rb.ghx, "gh", FakeGh(rc=1, stderr="boom"))
    assert rb.diff_loc(42, repo="o/r", on_error=rb.DIFF_LOC_FAILS_TO_ZERO) == 0
    monkeypatch.setattr(rb.ghx, "gh", FakeGh(stdout="null\n"))
    with pytest.raises(ValueError, match="unparseable diff size"):
        rb.diff_loc(42, repo="o/r")
    assert rb.diff_loc(42, repo="o/r", on_error=0) == 0
    monkeypatch.setattr(rb.ghx, "gh", FakeGh(stdout="12345\n"))
    assert rb.diff_loc(42, repo="o/r") == 12345


def test_no_repo_anywhere_is_a_named_error(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY"):
        rb.report_count(42)
    assert rb._repo_slug(None, {"GITHUB_REPOSITORY": "x/y"}) == "x/y"
