"""`rediacc_ci.quality.pr_description` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-pr-description.sh` over a
specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and
its bytes are compared against the port's. Same recipe as the committed ledger,
`.ci/shadow/w7p2-pr-description.observations.jsonl`.

THE `gh` STUB FAILS ON ANYTHING IT DOES NOT RECOGNISE, deliberately. A stub that
answered every call with an empty success would make both sides take the
"skipping check" branch and agree perfectly about nothing, which is the both-empty
trap `scripts/lib/shadow-gate.ts` names as rule 2. Failing loudly on an
unrecognised shape means a change to the twin's call arguments turns these cases
red rather than quietly vacuous.

TWO CASES HERE ARE NOT IN THE LEDGER, AND THAT IS THE POINT OF HAVING BOTH. A
fresh description and a two-commit PR both exit 0 printing only chatter, so the
comparator would score them VACUOUS_BOTH_EMPTY and refuse to record them. They are
still the negative half of this gate: without them a port that reported EVERY PR
stale would pass every ledger row. Byte equality is a stronger claim than the
comparator's finding-set equality, so it can rule on them where the ledger cannot.

THE UNGUARDED-PIPELINE DEFECT IS ASSERTED HERE. The twin dies silently when
`gh api graphql` fails, because pipefail plus `set -e` kill it at the assignment
and the "Could not get PR description edit time" handler three lines below is
unreachable. That is reproduced rather than repaired (invariant 5), and it is
pinned by a case so that a future "fix" to either side shows up as a
disagreement rather than as a silent improvement in one of them.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import pr_description as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-pr-description.sh"
MODULE = "pr_description"

# ROUTED BY URL, because the gate no longer makes the same call twice with a different --jq. It reads the REST PR object for the count and the head SHA, then that head commit for its date. A stub that still answered `pr view` would make both sides fail identically and this file would agree about nothing.
GH_STUB = """#!/bin/bash
D="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fxdata"
if [ "$1" = "api" ]; then
  case "$2" in
    graphql)      cat "$D/graphql.json" 2>/dev/null || exit 1; exit 0 ;;
    */pulls/*)    cat "$D/pr-view.json" 2>/dev/null || exit 1; exit 0 ;;
    */commits/*)  cat "$D/latest-commit.txt" 2>/dev/null || exit 1; exit 0 ;;
  esac
fi
exit 1
"""

# The fixture is the POST-`--jq` shape, as it was before: these files stand in
# for what `gh` writes to stdout, not for the raw API body.
HEAD_SHA = "dead0beef0dead0beef0dead0beef0dead0beef0"


def pr_view(commits: int) -> str:
    """`gh api repos/{R}/pulls/{n} --jq '{commits, head, body, title}'`.

    `commits` is an INTEGER here, which is the whole point of the change: it is
    the PR's true commit count from the REST object rather than the length of a
    `gh pr view` array that silently stops at 100.
    """
    return json.dumps({"commits": commits, "head": HEAD_SHA, "body": "b", "title": "t"})


def graphql(last_edited: str | None, created: str = "2026-09-06T09:00:00Z") -> str:
    return json.dumps(
        {
            "data": {
                "repository": {"pullRequest": {"lastEditedAt": last_edited, "createdAt": created}}
            }
        }
    )


def build(tmp_path: pathlib.Path, data: dict[str, str]) -> pathlib.Path:
    """A specimen holding BOTH implementations, a `gh` stub, and `data` under fxdata."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    (root / "fxbin").mkdir()
    (root / "fxdata").mkdir()
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
    for name, text in data.items():
        (root / "fxdata" / name).write_text(text, encoding="utf-8")
    return root


ENV_PREFIX = 'PR_NUMBER=42 GH_TOKEN=t GITHUB_REPOSITORY=rediacc/console PATH="$PWD/fxbin:$PATH"'


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (ENV_PREFIX, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )
    return old, new


STALE = {
    "pr-view.json": pr_view(5),
    "latest-commit.txt": "2026-09-06T12:00:00Z\n",
    "graphql.json": graphql("2026-09-06T10:30:00Z"),
}
FRESH = {
    "pr-view.json": pr_view(5),
    "latest-commit.txt": "2026-09-06T12:00:00Z\n",
    "graphql.json": graphql("2026-09-06T11:50:00Z"),
}

CASES = [
    ("a 90-minute-old description on a 5-commit PR is stale", STALE, 1),
    # THE NEGATIVE HALF, and it cannot live in the ledger: it exits 0 printing only chatter, which the comparator refuses to score.
    ("a description edited 10 minutes before the last commit is fresh", FRESH, 0),
    (
        "a description edited AFTER the last commit is always OK",
        {
            "pr-view.json": pr_view(5),
            "latest-commit.txt": "2026-09-06T10:00:00Z\n",
            "graphql.json": graphql("2026-09-06T12:00:00Z"),
        },
        0,
    ),
    (
        # THE COMMIT FLOOR, also invisible to the ledger.
        "a two-commit PR is not judged at all",
        {
            "pr-view.json": pr_view(2),
            "latest-commit.txt": "2026-09-06T12:00:00Z\n",
            "graphql.json": graphql("2026-09-06T08:00:00Z"),
        },
        0,
    ),
    (
        "a never-edited description falls back to createdAt",
        {
            "pr-view.json": pr_view(4),
            "latest-commit.txt": "2026-09-06T14:00:00Z\n",
            "graphql.json": graphql(None, "2026-09-06T08:00:00Z"),
        },
        1,
    ),
    ("an unfetchable PR is a failure, not a skip", {}, 1),
    (
        "an empty commit-time read is a failure, not a skip",
        {
            "pr-view.json": pr_view(6),
            "latest-commit.txt": "",
            "graphql.json": graphql("2026-09-06T10:00:00Z"),
        },
        1,
    ),
    (
        "an unfetchable commit-time read is a failure, not a skip",
        {
            "pr-view.json": pr_view(6),
            "graphql.json": graphql("2026-09-06T10:00:00Z"),
        },
        1,
    ),
    (
        "an unparseable timestamp skips rather than comparing zero",
        {
            "pr-view.json": pr_view(5),
            "latest-commit.txt": "not-a-timestamp\n",
            "graphql.json": graphql("2026-09-06T10:00:00Z"),
        },
        0,
    ),
]


@pytest.mark.parametrize(
    ("data", "want_exit"),
    [(c[1], c[2]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, data, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, data)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_a_failing_graphql_read_kills_both_sides_silently(tmp_path):
    """The unguarded pipeline, pinned so a one-sided "fix" is a disagreement.

    `gh api graphql` failing means pipefail fails the pipeline, the pipeline is the
    right-hand side of an assignment, and `set -e` ends the script there. The
    "Could not get PR description edit time - skipping check" branch below it is
    unreachable. Reproduced rather than repaired: invariant 5 says the twin is not
    edited in the change that ports it.
    """
    root = build(
        tmp_path,
        {"pr-view.json": pr_view(5), "latest-commit.txt": "2026-09-06T12:00:00Z\n"},
    )
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == 1
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err
    assert "Could not get PR description edit time" not in (old_out + old_err), (
        "the handler became reachable in the twin; the port must be updated with it"
    )


def test_the_advice_block_still_protects_the_generated_sections():
    """The 2026-09-03 correction, asserted in both directions.

    Nothing in the exit code protects this sentence, and the wording it replaced
    told the reader to overwrite the entire PR body, which deletes both
    machine-written marker blocks.
    """
    text = "\n".join(gate.stale_block("rediacc/console", "553", 6, 90))
    assert "WITHOUT dropping its generated sections" in text
    assert "<!-- worklist-epics -->" in text
    assert "<!-- pushed-head -->" in text
    assert "sync-epic-block.sh 553" in text
    assert '--body "new body"' not in text
    assert "pr edit --body" not in text


def test_neither_side_reads_the_commit_list_through_gh_pr_view():
    """The regression guard for the 100-commit cap, asserted on BOTH sources.

    `gh pr view --json commits` stops at 100 and says nothing about it. Measured
    2026-09-15 on rediacc/console#589 (254 commits): the "latest commit" it
    reported was 2026-09-07, eight days stale, so the age came out NEGATIVE and
    the gate printed "within 30m - OK" forever. Nothing in the cases above can
    see that, because a stub serves whatever shape the test author chose -- only
    the call itself distinguishes a gate that can fail from one that cannot.

    `gh pr view ... --json body` in the ADVICE text is fine and is why this
    asserts the `commits` field specifically rather than the command.
    """
    root = pathlib.Path(diff.repo())
    twin = (root / TWIN).read_text(encoding="utf-8")
    port = (root / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)).read_text(
        encoding="utf-8"
    )

    # COMMENTS ARE STRIPPED FIRST. Both files EXPLAIN the retired call by name, and a check that could not tell an explanation from a call would force the next reader to delete the record of why the call was retired.
    def code_only(text: str) -> str:
        return "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))

    for name, text in (("twin", code_only(twin)), ("port", code_only(port))):
        assert "--json commits" not in text, "%s reads the capped commit list again" % name
        assert "sort_by(.committedDate)" not in text, "%s sorts a list it may not have whole" % name
        assert "pulls/" in text, "%s no longer reads the PR object" % name
        assert "/commits/" in text, "%s no longer reads the head commit's date" % name


def test_the_thresholds_are_the_twins():
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


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
