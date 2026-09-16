"""`rediacc_ci.quality.resolved_threads` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-resolved-threads.sh` over a
specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and
its bytes are compared against the port's. Same recipe as the committed ledger,
`.ci/shadow/w7p2-resolved-threads.observations.jsonl`.

THE STUB DISPATCHES ON THE ENDPOINT ARGUMENT, and that detail is here because
getting it wrong is invisible. `gh_json` calls `gh api <endpoint> --paginate`, so
the endpoint is `$2`; a sibling fixture keyed on `$3` (which is `--paginate`) and
therefore failed EVERY call. Both implementations then failed identically, byte for
byte, and the differential scored EQUIVALENT over six trees. Only the comparator's
distinct-fingerprint rule -- six trees, one finding set -- refused it. A stub that
answers nothing is the both-empty trap wearing a costume.

BOTH DIRECTIONS. The corpus carries a fully resolved PR (must be silent), an
unresolved thread, an OUTDATED unresolved thread (must be silent, because it points
at a line that no longer exists), a standing CHANGES_REQUESTED, a block that a
later approval supersedes (must be silent), and a GraphQL error response, which is
valid JSON and exits 0 and therefore has to be caught per page rather than by an
exit code.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import resolved_threads as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-resolved-threads.sh"
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
    (root / "fxdata" / "threads.json").write_text(threads, encoding="utf-8")
    (root / "fxdata" / "reviews.json").write_text(reviews, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (ENV_PREFIX, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )
    return old, new


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
    ("a fully resolved PR with no blocking review is silent", graphql([DONE_THREAD]), "[]", 0),
    ("an unresolved thread blocks", graphql([OPEN_THREAD]), "[]", 1),
    # AN OUTDATED THREAD IS EXCLUDED, which is the other direction of the same rule.
    ("an unresolved but OUTDATED thread does not block", graphql([STALE_THREAD]), "[]", 0),
    (
        "a standing CHANGES_REQUESTED blocks even with every thread resolved",
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
        # SUPERSEDED. Reviewers can change their review, and the LATEST per
        # reviewer is what counts; without this the gate could never be cleared.
        "a later approval from the same reviewer supersedes the block",
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
        # A GRAPHQL ERROR IS VALID JSON AND EXITS 0, so an exit-code check alone
        # would read it as a PR with no threads.
        "a GraphQL error response fails closed",
        json.dumps({"errors": [{"message": "Could not resolve to a Repository"}]}),
        "[]",
        1,
    ),
]


@pytest.mark.parametrize(
    ("threads", "reviews", "want_exit"),
    [(c[1], c[2], c[3]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, threads, reviews, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, threads, reviews)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_the_stub_actually_answers(tmp_path):
    """The control on the control, and it is not paranoia.

    A `gh` stub that fails every call makes both implementations fail identically,
    which is byte-equal and proves nothing. This asserts the clean case reaches the
    SUCCESS path, so a stub that stopped answering reds this test rather than
    silently turning every case above into a comparison of two error messages.
    """
    root = build(tmp_path, graphql([DONE_THREAD]), "[]")
    (old_rc, _old_out, old_err), _new = run_both(root)
    assert old_rc == 0
    assert "gh failed after 3 attempts" not in old_err
    assert "Review status: OK" in old_err


def test_reviewers_are_named_in_login_order():
    """jq's `group_by` SORTS by key, so the failure block is login-ordered.

    A port using insertion order would name the same reviewers differently and the
    differential would only catch it on a PR with two blocking reviewers, which is
    rare enough to ship.
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

    Driven with a nonexistent binary and an injected sleeper, so the control needs
    neither `gh` nor nine seconds.
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


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
    assert subprocess.run(["bash", "-c", "true"], check=False).returncode == 0
