"""`rediacc_ci.quality.resolved_threads`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-resolved-threads.sh` over a specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-resolved-threads.observations.jsonl`, which recorded that comparison over six distinct
trees. The twin has now been deleted and every case that executed it compares against `goldens/resolved-threads/`, which holds the twin's OWN recorded output, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

THE STUB DISPATCHES ON THE ENDPOINT ARGUMENT, and that detail is here because getting it wrong is invisible. `gh_json` calls `gh api <endpoint> --paginate`, so the endpoint is `$2`; a sibling fixture keyed on `$3` (which is `--paginate`) and therefore failed EVERY call. Both implementations then failed identically, byte for byte, and the differential scored EQUIVALENT over six
trees. Only the comparator's distinct-fingerprint rule refused it. A stub that answers nothing is the both-empty trap wearing a costume. Freezing does not retire that hazard: a recording of an error message is still an error message, so the control proving the clean case reached the SUCCESS path is kept and now reads the golden as well as the port.

BOTH DIRECTIONS. The corpus carries a fully resolved PR (must be silent), an unresolved thread, an OUTDATED unresolved thread (must be silent, because it points at a line that no longer exists), a standing CHANGES_REQUESTED, a block that a later approval supersedes (must be silent), and a GraphQL error response, which is valid JSON and exits 0 and therefore has to be caught per
page rather than by an exit code.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import resolved_threads as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "resolved-threads"
MODULE = "resolved_threads"

ENV_PREFIX = 'PR_NUMBER=42 GH_TOKEN=t GITHUB_REPOSITORY=rediacc/console PATH="$PWD/fxbin:$PATH"'

GH_STUB = """#!/bin/bash
D="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fxdata"
if [ "$1" = "api" ] && [ "$2" = "graphql" ]; then
  cat "$D/threads.json" 2>/dev/null || exit 1
  exit 0
fi
if [ "$1" = "api" ]; then cat "$D/reviews.json" 2>/dev/null || exit 1; exit 0; fi
exit 1
"""


def thread(
    ident: str, *, resolved: bool, outdated: bool, path: str, line: int, body: str, author: str
) -> dict:
    return {
        "id": ident,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": path,
        "line": line,
        "comments": {"nodes": [{"body": body, "author": {"login": author}}]},
    }


def graphql(nodes: list[dict]) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": nodes,
                        }
                    }
                }
            }
        }
    )


def build(tmp_path: pathlib.Path, threads: str, reviews: str) -> pathlib.Path:
    """The fixture tree the twin was recorded over, minus the twin itself."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (".ci/rediacc_ci/quality", "fxbin", "fxdata"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    (root / "fxbin" / "gh").write_text(GH_STUB, encoding="utf-8")
    (root / "fxbin" / "gh").chmod(0o755)
    (root / "fxdata" / "threads.json").write_text(threads, encoding="utf-8")
    (root / "fxdata" / "reviews.json").write_text(reviews, encoding="utf-8")
    return root


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    return diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(root: pathlib.Path, name: str) -> tuple[int, str, str]:
    """Byte equality on BOTH streams against the twin's recorded bytes."""
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr = run_port(root)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert stdout == want_out, "%s: stdout diverged from the twin's recorded bytes" % name
    assert stderr == want_err, "%s: stderr diverged from the twin's recorded bytes" % name
    return returncode, stdout, stderr


OPEN_THREAD = thread(
    "t1", resolved=False, outdated=False, path="src/a.ts", line=12, body="rename", author="alice"
)
DONE_THREAD = thread(
    "t2", resolved=True, outdated=False, path="src/b.ts", line=3, body="ok", author="bob"
)
STALE_THREAD = thread(
    "t3", resolved=False, outdated=True, path="src/gone.ts", line=9, body="stale", author="alice"
)

CASES = [
    # THE NEGATIVE HALF, first: everything resolved and nobody blocking.
    ("a-fully-resolved-pr-is-silent", graphql([DONE_THREAD]), "[]", 0),
    ("an-unresolved-thread-blocks", graphql([OPEN_THREAD]), "[]", 1),
    # AN OUTDATED THREAD IS EXCLUDED, which is the other direction of the same rule.
    ("an-outdated-unresolved-thread-does-not-block", graphql([STALE_THREAD]), "[]", 0),
    (
        "a-standing-changes-requested-blocks",
        graphql([DONE_THREAD]),
        json.dumps(
            [
                {
                    "user": {"login": "amy"},
                    "state": "CHANGES_REQUESTED",
                    "submitted_at": "2026-09-01T00:00:00Z",
                }
            ]
        ),
        1,
    ),
    (
        # SUPERSEDED. Reviewers can change their review, and the LATEST per reviewer is what counts; without this the gate could never be cleared.
        "a-later-approval-supersedes-the-block",
        graphql([DONE_THREAD]),
        json.dumps(
            [
                {
                    "user": {"login": "amy"},
                    "state": "CHANGES_REQUESTED",
                    "submitted_at": "2026-09-01T00:00:00Z",
                },
                {
                    "user": {"login": "amy"},
                    "state": "APPROVED",
                    "submitted_at": "2026-09-02T00:00:00Z",
                },
            ]
        ),
        0,
    ),
    (
        # A GRAPHQL ERROR IS VALID JSON AND EXITS 0, so an exit-code check alone would read it as a PR with no threads.
        "a-graphql-error-fails-closed",
        json.dumps({"errors": [{"message": "Could not resolve to a Repository"}]}),
        "[]",
        1,
    ),
]


@pytest.mark.parametrize(
    ("name", "threads", "reviews", "want_exit"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_port_matches_the_twins_recorded_output(tmp_path, name, threads, reviews, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, threads, reviews)
    returncode, _stdout, _stderr = compare(root, name)
    assert returncode == want_exit, "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _t, _r, _e in CASES})


def test_the_stub_actually_answered(tmp_path):
    """The control on the control, and it is not paranoia.

    A `gh` stub that fails every call makes both implementations fail identically, which is byte-equal and proves nothing. The twin's RECORDED clean case is asserted to have reached the SUCCESS path, and the port is asserted to reach it today, so a stub that stopped answering reds this test rather than silently turning every case above into a comparison of two error messages.
    """
    _rc, _out, recorded_err = split_golden(frozen.read(SLUG, "a-fully-resolved-pr-is-silent"))
    assert "gh failed after 3 attempts" not in recorded_err
    assert "Review status: OK" in recorded_err
    root = build(tmp_path, graphql([DONE_THREAD]), "[]")
    code, _out, err = run_port(root)
    assert code == 0
    assert "Review status: OK" in err


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing."""
    green = split_golden(frozen.read(SLUG, "a-fully-resolved-pr-is-silent"))[2]
    red = split_golden(frozen.read(SLUG, "an-unresolved-thread-blocks"))[1]
    assert green != red
    assert "All 1 review thread(s) are resolved" in green
    assert "Found 1 unresolved review thread(s)" in red


def test_planted_defect_is_caught_by_the_goldens(tmp_path):
    """THE CONTROL ON THE GOLDENS. Let an OUTDATED thread through as unresolved.

    Dropping the `isOutdated` half of the filter is exactly the simplification a reader would make on sight, and it turns the silent `an-outdated-unresolved-thread-does-not-block` tree into a blocking one. The mutation is applied to the module COPY inside the throwaway fixture; the tracked port is never touched.
    """
    tracked = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    before = tracked.read_text(encoding="utf-8")
    anchor = 'if node.get("isResolved") is False and node.get("isOutdated") is False'
    assert before.count(anchor) == 1, "the plant's anchor moved"

    root = build(tmp_path, graphql([STALE_THREAD]), "[]")
    copy = root / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    copy.write_text(
        copy.read_text(encoding="utf-8").replace(anchor, 'if node.get("isResolved") is False'),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        compare(root, "an-outdated-unresolved-thread-does-not-block")

    # And the real, unmutated module still agrees against the same fixture.
    clean = build(tmp_path / "clean", graphql([STALE_THREAD]), "[]")
    compare(clean, "an-outdated-unresolved-thread-does-not-block")
    assert tracked.read_text(encoding="utf-8") == before


def test_reviewers_are_named_in_login_order():
    """jq's `group_by` SORTS by key, so the failure block is login-ordered.

    A port using insertion order would name the same reviewers differently and the differential would only have caught it on a PR with two blocking reviewers, which is rare enough to ship.
    """
    reviews = [
        {"user": {"login": "zoe"}, "state": "CHANGES_REQUESTED", "submitted_at": "t"},
        {"user": {"login": "amy"}, "state": "CHANGES_REQUESTED", "submitted_at": "t"},
    ]
    assert [r["user"]["login"] for r in gate.changes_requested(reviews)] == ["amy", "zoe"]


def test_the_thread_renderer_defaults_and_cuts():
    """`.line // "N/A"`, `.login // "unknown"`, first line only, 80 characters."""
    rendered = gate.thread_lines(
        [
            {
                "path": "x.ts",
                "line": None,
                "comments": {"nodes": [{"body": "first\nsecond", "author": None}]},
            }
        ]
    )
    assert rendered[0] == "  x.ts:N/A"
    assert rendered[1] == "    Author: @unknown"
    assert rendered[2] == "    Comment: first..."
    long_body = "y" * 200
    cut = gate.thread_lines(
        [
            {
                "path": "x",
                "line": 1,
                "comments": {"nodes": [{"body": long_body, "author": {"login": "a"}}]},
            }
        ]
    )
    assert cut[2] == "    Comment: %s..." % ("y" * 80)


def test_a_failed_read_returns_none_and_never_an_empty_list():
    """`|| echo "[]"` is what this replaces, and it was a silent green.

    Driven with a nonexistent binary and an injected sleeper, so the control needs neither `gh` nor nine seconds.
    """
    waits: list[float] = []
    assert gate.gh_json("t", ["x"], sleeper=waits.append, binary="gh-does-not-exist-zzz") is None
    assert waits == [3, 6], "the retry ladder stopped waiting, so it stopped retrying"


def test_the_pagination_ceiling_is_fifty():
    """5000 threads. Hitting it means the cursor stopped advancing; fail closed."""
    assert gate.MAX_PAGES == 50


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 15
