"""`rediacc_ci.quality.pr_description`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-pr-description.sh` over a specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-pr-description.observations.jsonl`, which licensed the port at K=5; the twin was retired in
W7 P5 and the stubbed cases were retired with it.

WHAT THOSE CASES SAID THAT THE LEDGER DOES NOT, recorded rather than dropped without trace. A fresh description and a two-commit PR both exit 0 printing only chatter, so the comparator scores them VACUOUS_BOTH_EMPTY and refuses to record them; they were still the negative half of this gate. And the twin died silently when `gh api graphql` failed, because pipefail plus `set -e`
killed it at the assignment and the "Could not get PR description edit time" handler three lines below was unreachable. The port reproduces that rather than repairing it, and its own `--selftest` is what drives both halves now.

THE 100-COMMIT REGRESSION GUARD BELOW IS NOT A DIFFERENTIAL and stays: it reads the port's source for a call that must never come back.
"""

import pathlib

from rediacc_ci.quality import pr_description as gate
from rediacc_ci.tests import differential as diff

MODULE = "pr_description"


def test_the_advice_block_still_protects_the_generated_sections():
    """The 2026-09-03 correction, asserted in both directions.

    Nothing in the exit code protects this sentence, and the wording it replaced told the reader to overwrite the entire PR body, which deletes both machine-written marker blocks.
    """
    text = "\n".join(gate.stale_block("rediacc/console", "553", 6, 90))
    assert "WITHOUT dropping its generated sections" in text
    assert "<!-- worklist-epics -->" in text
    assert "<!-- pushed-head -->" in text
    assert "sync-epic-block.sh 553" in text
    assert '--body "new body"' not in text
    assert "pr edit --body" not in text


def test_the_gate_does_not_read_the_commit_list_through_gh_pr_view():
    """The regression guard for the 100-commit cap.

    `gh pr view --json commits` stops at 100 and says nothing about it. Measured 2026-09-15 on rediacc/console#589 (254 commits): the "latest commit" it reported was 2026-09-07, eight days stale, so the age came out NEGATIVE and the gate printed "within 30m - OK" forever. No stubbed case can see that, because a stub serves whatever shape the test author chose -- only the call
    itself distinguishes a gate that can fail from one that cannot.

    `gh pr view ... --json body` in the ADVICE text is fine and is why this asserts the `commits` field specifically rather than the command.
    """
    root = pathlib.Path(diff.repo())
    port = (root / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)).read_text(
        encoding="utf-8"
    )

    # COMMENTS ARE STRIPPED FIRST. The file EXPLAINS the retired call by name, and a check that could not tell an explanation from a call would force the next reader to delete the record of why the call was retired.
    code = "\n".join(line for line in port.split("\n") if not line.lstrip().startswith("#"))

    assert "--json commits" not in code, "the port reads the capped commit list again"
    assert "sort_by(.committedDate)" not in code, "the port sorts a list it may not have whole"
    assert "pulls/" in code, "the port no longer reads the PR object"
    assert "/commits/" in code, "the port no longer reads the head commit's date"


def test_the_thresholds_are_carried_from_the_twin():
    assert gate.MIN_COMMITS == 3
    assert gate.STALE_THRESHOLD_MINUTES == 30
    assert gate.REQUIRED_VARS == ("PR_NUMBER", "GH_TOKEN", "GITHUB_REPOSITORY")


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 14
