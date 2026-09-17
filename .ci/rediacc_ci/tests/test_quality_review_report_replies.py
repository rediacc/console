"""`rediacc_ci.quality.review_report_replies` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-review-report-replies.sh` over a specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-review-report-replies.observations.jsonl`.

THE FOUR REPLY CLAUSES ARE EACH A CASE, and clause (a) is the one that decides whether this gate can fire at all: the pipeline posts several comments in a row under one identity, and on PR #551 the reviewed-SHA marker landed FOUR SECONDS after the report and is long enough to clear every substance test. Without the different-author rule the review answers itself on every PR.

THE 2026-08-05 SHAPE IS A CASE TOO. A report whose body is a bare wrap-up ("Posted the review. Summary of what I did:") carries neither the findings fence nor a `### Review` heading, and the twin used to AND those in. It found no report and exited 0 while an 8141-char verdict sat unanswered. Keyed on the producer constant alone, it fires.

THE PER-EPIC FAN-OUT IS ALSO HERE, driven from a snapshot at `agent/pr/<branch>.md`. It is a BOUNDED SELF-INVOCATION on both sides -- the twin re-executes `"$0"` with `REVIEW_EPIC_PREFIX` set, the port re-enters `main()` with the same variable -- so the case proves the recursion terminates and that one unanswered epic out of two fails the whole run while the answered one prints its
OK line.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import review_comments as sibling
from rediacc_ci.quality import review_report_replies as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-review-report-replies.sh"
MODULE = "review_report_replies"

ENV_PREFIX = 'PR_NUMBER=42 GH_TOKEN=t GITHUB_REPOSITORY=rediacc/console PATH="$PWD/fxbin:$PATH"'

# DISPATCHES ON $2, the endpoint. `gh_json` calls `gh api <endpoint> --paginate`, so a stub keyed on $3 fails every call and makes both sides agree about nothing.
GH_STUB = """#!/bin/bash
D="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fxdata"
if [ "$1" = "api" ] && [ "$2" != "graphql" ]; then
  cat "$D/comments.json" 2>/dev/null || exit 1
  exit 0
fi
exit 1
"""

BOT = {"login": "github-actions[bot]"}
HUMAN = {"login": "muhammed"}
LONG = "y" * 250
REPORT = {
    "id": 100,
    "user": BOT,
    "created_at": "2026-08-05T10:00:00Z",
    "body": "**Claude finished** reviewing.",
}


def build(
    tmp_path: pathlib.Path, comments: list[dict], snapshot: str | None = None
) -> pathlib.Path:
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (".ci/scripts/quality", ".ci/rediacc_ci/quality", "fxbin", "fxdata"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    (root / "fxbin" / "gh").write_text(GH_STUB, encoding="utf-8")
    (root / "fxbin" / "gh").chmod(0o755)
    (root / "fxdata" / "comments.json").write_text(json.dumps(comments), encoding="utf-8")
    if snapshot is not None:
        (root / "agent" / "pr").mkdir(parents=True)
        (root / "agent" / "pr" / "main.md").write_text(snapshot, encoding="utf-8")
    # A REAL GIT REPOSITORY ON `main`, because the fan-out asks git for the branch name and `review_epic_ids` looks for `agent/pr/<branch>.md`. Without it the branch is empty, no epics are found, and the fan-out case silently takes the FLAT path -- which happens to exit 1 as well, so the case would have passed
    # while testing the wrong code. Caught by asserting on the output rather than
    # only on the status.
    for args in (
        ["init", "-q", "-b", "main", "."],
        ["config", "user.email", "gate@example.invalid"],
        ["config", "user.name", "test"],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "specimen"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (ENV_PREFIX, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )
    return old, new


CASES = [
    # THE NEGATIVE HALF, first: an answered report must be silent, or the gate is a permanent block and gets switched off.
    (
        "a long-form answer from another author clears the gate",
        [REPORT, {"id": 101, "user": HUMAN, "created_at": "2026-08-05T11:00:00Z", "body": LONG}],
        None,
        0,
    ),
    ("an unanswered report blocks", [REPORT], None, 1),
    # CLAUSE (a). The pipeline must not answer itself.
    (
        "the pipeline's own later comment is not an answer",
        [REPORT, {"id": 101, "user": BOT, "created_at": "2026-08-05T10:00:04Z", "body": LONG}],
        None,
        1,
    ),
    # CLAUSE (c).
    (
        "a stock acknowledgement is not an answer",
        [
            REPORT,
            {
                "id": 101,
                "user": HUMAN,
                "created_at": "2026-08-05T11:00:00Z",
                "body": "Acknowledged",
            },
        ],
        None,
        1,
    ),
    # CLAUSE (d).
    (
        "a substantive but unrelated comment is not an answer",
        [
            REPORT,
            {
                "id": 101,
                "user": HUMAN,
                "created_at": "2026-08-05T11:00:00Z",
                "body": "preview looks good, merging tomorrow when CI is green",
            },
        ],
        None,
        1,
    ),
    (
        # NEWEST WINS. The older report is answered; the newer one is not, and it is the newer one that is gated.
        "a newer report supersedes an answered older one",
        [
            dict(
                REPORT, id=100, created_at="2026-08-04T10:00:00Z", body="**Claude finished** one."
            ),
            {"id": 101, "user": HUMAN, "created_at": "2026-08-04T11:00:00Z", "body": LONG},
            dict(
                REPORT, id=102, created_at="2026-08-06T10:00:00Z", body="**Claude finished** two."
            ),
        ],
        None,
        1,
    ),
    (
        # THE 2026-08-05 SHAPE: no fence, no heading, still a report.
        "a bare wrap-up with no fence and no heading is still a report",
        [dict(REPORT, body="**Claude finished** Posted the review. Summary of what I did:")],
        None,
        1,
    ),
    (
        "a PR with no report at all is silent",
        [{"id": 1, "user": HUMAN, "created_at": "2026-08-05T10:00:00Z", "body": "just chatter"}],
        None,
        0,
    ),
    (
        # THE PER-EPIC FAN-OUT: one epic answered, one not, and the run fails.
        "one unanswered epic out of two fails the whole run",
        [
            dict(REPORT, id=200, body="**Claude finished (epic ab12cd34) reviewing."),
            {"id": 201, "user": HUMAN, "created_at": "2026-08-05T11:00:00Z", "body": LONG},
            dict(
                REPORT,
                id=202,
                created_at="2026-08-05T12:00:00Z",
                body="**Claude finished (epic ef56ab78) reviewing.",
            ),
        ],
        "`PR-TASK: ab12cd34`\n`PR-TASK: ef56ab78`\n",
        1,
    ),
]


@pytest.mark.parametrize(
    ("comments", "snapshot", "want_exit"),
    [(c[1], c[2], c[3]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, comments, snapshot, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, comments, snapshot)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_the_fan_out_runs_every_epic_and_names_the_unanswered_ones(tmp_path):
    """The summary block only exists in the fan-out path, so it needs its own case.

    Gating only the newest report across all epics "would enforce the LAST epic's reply and silently excuse every other, which is worse than not gating: the unanswered ones look cleared."
    """
    root = build(
        tmp_path,
        [
            dict(REPORT, id=200, body="**Claude finished (epic ab12cd34) reviewing."),
            {"id": 201, "user": HUMAN, "created_at": "2026-08-05T11:00:00Z", "body": LONG},
            dict(
                REPORT,
                id=202,
                created_at="2026-08-05T12:00:00Z",
                body="**Claude finished (epic ef56ab78) reviewing.",
            ),
        ],
        "`PR-TASK: ab12cd34`\n`PR-TASK: ef56ab78`\n",
    )
    (old_rc, old_out, _err), (new_rc, new_out, _) = run_both(root)
    assert old_rc == 1
    assert new_out == old_out
    assert "Per-epic review reports: 2 epic(s) declared for main" in old_out
    assert "--- epic ab12cd34 ---" in old_out
    assert "--- epic ef56ab78 ---" in old_out
    assert "1 of 2 epic report(s) unanswered:" in old_out
    assert new_rc == old_rc


def test_the_two_shared_constants_match_the_sibling_gate():
    """One reply must clear BOTH gates, so these cannot drift.

    `test-review-status.sh` parses both bash files and fails if they disagree; this asserts the same thing across the two ports, which is the half that gate cannot see.
    """
    assert gate.SUMMARY_MIN_CHARS == sibling.SUMMARY_MIN_CHARS == 30
    assert gate.SUMMARY_LONGFORM_CHARS == sibling.SUMMARY_LONGFORM_CHARS == 200


def test_the_low_effort_default_differs_from_the_siblings():
    """Same function name, different default, on purpose.

    30 here (a reply to a whole report), 10 there (a reply to one inline thread). A port that unified them would silently tighten one gate or loosen the other.
    """
    assert gate.is_low_effort_reply("x" * 15) is True
    assert sibling.is_low_effort_reply("x" * 15) is False


def test_the_matcher_ands_nothing_onto_the_producer_constant():
    """Every extra clause is another chance to describe the report wrongly."""
    assert gate.newest_report([REPORT], gate.REPORT_PREFIX)["id"] == 100
    assert (
        gate.newest_report([dict(REPORT, body="**Claude is working**")], gate.REPORT_PREFIX) is None
    )
    assert gate.newest_report([dict(REPORT, user=HUMAN)], gate.REPORT_PREFIX) is None
    # The GraphQL fallback spells the bot without `[bot]`; `contains()` covers both.
    assert (
        gate.newest_report([dict(REPORT, user={"login": "github-actions"})], gate.REPORT_PREFIX)[
            "id"
        ]
        == 100
    )


def test_epic_ids_are_read_from_the_repo_root(tmp_path):
    """A bare relative path made this silently take the flat path from a subdirectory."""
    (tmp_path / "agent" / "pr").mkdir(parents=True)
    (tmp_path / "agent" / "pr" / "feat-x.md").write_text(
        "`PR-TASK: ab12cd34`\nPR-TASK: ef56ab78\nnot a task line\n", encoding="utf-8"
    )
    assert gate.review_epic_ids("feat/x", str(tmp_path)) == ["ab12cd34", "ef56ab78"]
    assert gate.review_epic_ids("other", str(tmp_path)) == []
    assert gate.review_epic_ids("", str(tmp_path)) == []


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 20


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
