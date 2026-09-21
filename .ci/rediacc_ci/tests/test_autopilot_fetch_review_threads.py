"""`rediacc_ci.autopilot.fetch_review_threads`, driven against the bytes and the requests its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/fetch-review-threads.sh` and the port over the same fixture and compared five things: exit code, stdout, stderr, the `gh` CALL LOG and the content of `--out`. The K=5 ledger `.ci/shadow/w7p6-fetch-review-threads.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been
deleted and every case that executed it compares against `goldens/fetch-review-threads/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

A RECORDING FAKE `gh` ON A STUB PATH, and here the fake is not a convenience: it is the only thing standing between a test run and a real GraphQL query against whatever repository a fixture names. The fake answers from a SCRIPT of per-call responses handed to it in the environment, so a case can make page two fail, or return a GraphQL error object, or hand back a cursor that
never advances, without any of it leaving the process tree. `test_the_fake_gh_is_the_gh` resolves `gh` through the stub PATH and fails if anything else wins. Every other case rests on that.

THE CALL LOG AND THE OUT FILE ARE THE ARTIFACT. This script's entire effect on the world is which GraphQL requests it makes and what array it leaves behind, and a port that fetched the right threads from the wrong repository, or dropped the `repo`/`pr` tags that let a reply be routed back, would print an identical summary line. The recorded call log therefore carries the
full argv INCLUDING the query text, so a reflowed query is a failure here rather than a surprise in production.

THE OUT FILE IS RECORDED FOR ABSENCE, not for emptiness. "No threads" and "could not ask" must not share an output; an empty file is a value a reader could act on, absence is not, so the two are different markers in the recording.

THE STALENESS ALARM THAT READ THE TWIN'S `QUERY='...'` IS GONE, and the recording replaces it. It existed so the port's copy of the query could not drift away from the text the twin sent. A deleted file does not drift; the port's copy still can, so `test_the_query_is_the_recorded_query` parses it back out of the recorded request rather than out of a source file.

ONE CASE COSTS EIGHTEEN SECONDS. `_gh_probe` sleeps 3 then 6 between its three attempts, and it is the only way to prove the retry loop, the final `gh failed after 3 attempts` line and the exit code agree. It is named `test_slow_...` so it can be deselected by name, and it is not skipped by default, because a retry loop nobody drives is a retry loop nobody has seen.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import fetch_review_threads as frt
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "fetch_review_threads.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "fetch-review-threads"

CALLS_MARKER = "--- gh calls ---\n"
OUT_MARKER = "--- out file ---\n"
NO_OUT = "<no file written>"

# A recording fake `gh`. It answers from FAKE_GH_SCRIPT, a JSON list consumed in call order, and it RECORDS EVERY ARGV before deciding anything -- so a case that produced no call log fails loudly rather than passing quietly.
FAKE_GH = """#!/usr/bin/python3
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
with open(log, "a") as fh:
    fh.write(json.dumps(argv) + "\\n")

index = sum(1 for _ in open(log)) - 1
script = json.loads(os.environ.get("FAKE_GH_SCRIPT", "[]"))
if index >= len(script):
    sys.stderr.write("fake gh: no scripted response for call %d: %r\\n" % (index, argv))
    sys.exit(97)
step = script[index]
sys.stdout.write(step.get("out", ""))
sys.stderr.write(step.get("err", ""))
sys.exit(int(step.get("rc", 0)))
"""


def page(nodes: list[dict], *, has_next: bool = False, cursor: str | None = None) -> str:
    """One well-formed GraphQL page body."""
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                            "nodes": nodes,
                        }
                    }
                }
            }
        }
    )


def thread(tid: str, *, resolved: bool = False, path: str = "a.ts") -> dict:
    return {
        "id": tid,
        "isResolved": resolved,
        "isOutdated": False,
        "path": path,
        "line": 12,
        "comments": {"nodes": [{"databaseId": 1, "body": "finding", "author": {"login": "bot"}}]},
    }


def ok(body: str) -> dict:
    return {"rc": 0, "out": body + "\n"}


def graphql_error(message: str | None = None) -> str:
    return json.dumps({"errors": [{} if message is None else {"message": message}]})


BASE_ARGV = ["--pr", "31", "--repo", "acme/console", "--out", "threads.json"]

LINKED_BODY = """Some description.

- renet: rediacc/renet#7
"""

# The page whose `nodes` is not an array. Reaching the preserved accumulator hazard needs one, and `gh_json` passes it through because it IS valid JSON.
BROKEN_PAGE = json.dumps(
    {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": "not-an-array",
                    }
                }
            }
        }
    }
)

PAGE_LIMIT_SCRIPT = [
    ok(page([thread("T_%d" % i)], has_next=True, cursor="CUR%d" % i)) for i in range(50)
]

# name -> (argv, how the run is wired)
CASE_KW: dict[str, tuple[list[str], dict[str, typing.Any]]] = {
    "no-flags-at-all": ([], {}),
    "only-the-pr": (["--pr", "31"], {}),
    "no-out": (["--pr", "31", "--repo", "acme/console"], {}),
    "no-pr": (["--repo", "acme/console", "--out", "threads.json"], {}),
    "no-repo": (["--pr", "31", "--out", "threads.json"], {}),
    "a-pr-of-abc": (["--pr", "abc", *BASE_ARGV[2:]], {}),
    "a-pr-of-31a": (["--pr", "31a", *BASE_ARGV[2:]], {}),
    "an-empty-pr": (["--pr", "", *BASE_ARGV[2:]], {}),
    "a-negative-pr": (["--pr", "-1", *BASE_ARGV[2:]], {}),
    "a-pr-with-a-space": (["--pr", "3 1", *BASE_ARGV[2:]], {}),
    "a-decimal-pr": (["--pr", "31.0", *BASE_ARGV[2:]], {}),
    "a-single-page": (BASE_ARGV, {"script": [ok(page([thread("T_1"), thread("T_2")]))]}),
    "an-empty-thread-set": (BASE_ARGV, {"script": [ok(page([]))]}),
    "three-pages": (
        BASE_ARGV,
        {
            "script": [
                ok(page([thread("T_1")], has_next=True, cursor="CUR1")),
                ok(page([thread("T_2")], has_next=True, cursor="CUR2")),
                ok(page([thread("T_3")])),
            ]
        },
    ),
    "a-null-cursor-that-does-not-advance": (
        BASE_ARGV,
        {"script": [ok(page([thread("T_1")], has_next=True, cursor=None))]},
    ),
    "an-empty-cursor-that-does-not-advance": (
        BASE_ARGV,
        {"script": [ok(page([thread("T_1")], has_next=True, cursor=""))]},
    ),
    "the-page-limit": (BASE_ARGV, {"script": PAGE_LIMIT_SCRIPT}),
    "a-graphql-error": (BASE_ARGV, {"script": [ok(graphql_error("Resource not accessible"))]}),
    "a-graphql-error-with-no-message": (BASE_ARGV, {"script": [ok(graphql_error())]}),
    "a-graphql-error-on-page-two": (
        BASE_ARGV,
        {
            "script": [
                ok(page([thread("T_1")], has_next=True, cursor="CUR1")),
                ok(graphql_error("rate limited")),
            ]
        },
    ),
    "a-failing-gh": (BASE_ARGV, {"script": [{"rc": 1, "err": "HTTP 404\n"}] * 3}),
    "an-unparseable-body": (BASE_ARGV, {"script": [ok("not json")] * 3}),
    "a-null-body": (BASE_ARGV, {"script": [ok("null")] * 3}),
    "a-linked-submodule-pr": (
        [*BASE_ARGV, "--body", "body.md"],
        {
            "fixtures": {"body.md": LINKED_BODY},
            "script": [ok(page([thread("T_C")])), ok(page([thread("T_R")]))],
        },
    ),
    "a-linked-target-that-cannot-be-read": (
        [*BASE_ARGV, "--body", "body.md"],
        {
            "fixtures": {"body.md": LINKED_BODY},
            "script": [
                ok(page([thread("T_C")])),
                ok(graphql_error("Resource not accessible")),
            ],
        },
    ),
    "the-console-target-failing": (
        [*BASE_ARGV, "--body", "body.md"],
        {"fixtures": {"body.md": LINKED_BODY}, "script": [ok(graphql_error("nope"))]},
    ),
    "a-body-naming-an-unknown-repo": (
        [*BASE_ARGV, "--body", "body.md"],
        {"fixtures": {"body.md": "- attacker/evil#7\n"}, "script": [ok(page([thread("T_C")]))]},
    ),
    "a-body-with-no-links": (
        [*BASE_ARGV, "--body", "body.md"],
        {"fixtures": {"body.md": "just a description\n"}, "script": [ok(page([thread("T_C")]))]},
    ),
    "an-empty-body": (
        [*BASE_ARGV, "--body", "body.md"],
        {"fixtures": {"body.md": ""}, "script": [ok(page([thread("T_C")]))]},
    ),
    "a-mistyped-body-path": (
        [*BASE_ARGV, "--body", "nope.md"],
        {"fixtures": {"body.md": LINKED_BODY}, "script": [ok(page([thread("T_C")]))]},
    ),
    "three-failed-attempts": (
        BASE_ARGV,
        {"script": [{"rc": 4, "err": "gh: HTTP 401 Bad credentials\n"}] * 3},
    ),
    "a-transient-failure-that-recovers": (
        BASE_ARGV,
        {"script": [{"rc": 1, "err": "flake\n"}, ok(page([thread("T_1")]))]},
    ),
    "a-broken-accumulator": (BASE_ARGV, {"script": [ok(BROKEN_PAGE)]}),
}

CASES = tuple(CASE_KW)

# The one case whose two sleeps make it cost eighteen seconds.
SLOW = "three-failed-attempts"


def stub_bin(base: pathlib.Path) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def run(
    where: pathlib.Path, subject: pathlib.Path, name: str
) -> tuple[int, bytes, bytes, list[list[str]], bytes | None]:
    """One side, once, over its own copy of this case's fixture."""
    argv, kw = CASE_KW[name]
    base = where
    base.mkdir(parents=True, exist_ok=True)
    for rel, text in kw.get("fixtures", {}).items():
        (base / rel).write_text(text, encoding="utf-8")
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
        "FAKE_GH_SCRIPT": json.dumps(kw.get("script", [])),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(kw.get("env", {}))
    runner = BASH if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=180,
    )
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    out_file = base / "threads.json"
    written = out_file.read_bytes() if out_file.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, calls, written


def render(
    returncode: int,
    stdout: bytes,
    stderr: bytes,
    calls: list[list[str]],
    written: bytes | None,
) -> str:
    body = frozen.render(returncode, stdout.decode("utf-8"), stderr.decode("utf-8"))
    log = "".join(json.dumps(call) + "\n" for call in calls)
    out = NO_OUT + "\n" if written is None else written.decode("utf-8")
    return body + CALLS_MARKER + log + OUT_MARKER + out


def recorded(name: str) -> tuple[int, bytes, bytes, list[list[str]], bytes | None]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, tail = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    log, out = tail.split(OUT_MARKER, 1)
    calls = [json.loads(line) for line in log.splitlines() if line]
    written = None if out == NO_OUT + "\n" else out.encode("utf-8")
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout.encode("utf-8"),
        stderr.encode("utf-8"),
        calls,
        written,
    )


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT):
    return run(tmp_path / "run", subject, name)


def compare(tmp_path: pathlib.Path, name: str):
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d\nport stderr %r" % (
        name,
        want[0],
        got[0],
        got[2],
    )
    assert got[1] == want[1], "%s: stdout diverged:\nrecorded %r\nport %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged:\nrecorded %r\nport %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the gh calls diverged:\nrecorded %r\nport %r" % (
        name,
        want[3],
        got[3],
    )
    assert got[4] == want[4], "%s: --out diverged:\nrecorded %r\nport %r" % (name, want[4], got[4])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c != SLOW])
def test_port_matches_the_twins_recorded_behaviour(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Controls on the fake ---------------------------------------------------------------------------


def test_the_fake_gh_is_the_gh(tmp_path: pathlib.Path) -> None:
    """Nothing below means anything if the real `gh` wins the PATH race."""
    path = stub_bin(tmp_path)
    found = shutil.which("gh", path=path)
    assert found == str(tmp_path / "bin" / "gh"), "the fake gh is not first on PATH: %r" % found


def test_the_fake_gh_records_and_answers_in_order(tmp_path: pathlib.Path) -> None:
    """CONTROL for the call log. A fake that recorded nothing would make every `calls == [...]` assertion below vacuous."""
    path = stub_bin(tmp_path)
    log = tmp_path / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": path,
        "FAKE_GH_LOG": str(log),
        "FAKE_GH_SCRIPT": json.dumps([ok("first"), {"rc": 3, "err": "boom\n"}]),
    }
    one = subprocess.run(["gh", "api", "graphql"], capture_output=True, env=env, check=False)
    two = subprocess.run(["gh", "api", "x"], capture_output=True, env=env, check=False)
    three = subprocess.run(["gh", "api", "y"], capture_output=True, env=env, check=False)
    assert (one.returncode, one.stdout) == (0, b"first\n")
    assert (two.returncode, two.stderr) == (3, b"boom\n")
    assert three.returncode == 97, "an unscripted call must be loud"
    assert len(log.read_text(encoding="utf-8").splitlines()) == 3


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_three_required_flags() -> None:
    for name in ("no-flags-at-all", "only-the-pr", "no-out", "no-pr", "no-repo"):
        code, _out, err, calls, written = recorded(name)
        assert code == 2, name
        assert b"usage: fetch-review-threads.sh --pr <number> --repo <owner/name>" in err
        assert calls == [], "usage must be decided before any request: %r" % calls
        assert written is None


def test_the_pr_number_must_be_a_number() -> None:
    """The ONLY validated input, and it is validated because it travels as a TYPED GraphQL variable: a bad value would be a server error paid for after the request rather than a refusal before it."""
    for name, value in (
        ("a-pr-of-abc", "abc"),
        ("a-pr-of-31a", "31a"),
        ("an-empty-pr", ""),
        ("a-negative-pr", "-1"),
        ("a-pr-with-a-space", "3 1"),
        ("a-decimal-pr", "31.0"),
    ):
        code, _, err, calls, written = recorded(name)
        assert code == 2, name
        assert calls == [], name
        assert written is None, name
        if value == "":
            # An EMPTY value is caught by the usage check first, because `parse_args` stores nothing distinguishable from an absent flag.
            assert b"usage: fetch-review-threads.sh" in err
        else:
            assert b"--pr must be a number, got '%s'" % value.encode() in err, err


def test_a_single_page_of_threads() -> None:
    code, out, err, calls, written = recorded("a-single-page")
    assert code == 0
    assert out == b""
    assert b"fetched 2 review thread(s) across 1 pull request(s) -> threads.json" in err
    assert len(calls) == 1, calls
    argv = calls[0]
    assert argv[:2] == ["api", "graphql"]
    # THE REQUEST, field by field. `-F pr` is the typed form; `-f` the string form; the query travels whole, leading newline and all.
    assert argv[2] == "-f"
    assert argv[3].startswith("query=\nquery($owner: String!, $repo: String!, $pr: Int!")
    assert "comments(first: 20)" in argv[3], "the ONE way this query differs from its sibling"
    assert argv[4:] == ["-f", "owner=acme", "-f", "repo=console", "-F", "pr=31"]
    assert "after=" not in json.dumps(argv), "the first page must not send a cursor"
    # THE ARTIFACT. Every node tagged with the repo and PR it came from.
    nodes = json.loads(written)
    assert [n["id"] for n in nodes] == ["T_1", "T_2"]
    assert all(n["repo"] == "acme/console" and n["pr"] == 31 for n in nodes), nodes
    assert nodes[0]["comments"]["nodes"][0]["body"] == "finding", "the finding text survives"


def test_the_query_is_the_recorded_query() -> None:
    """The port's QUERY is a COPY, and the recorded request is what keeps the copy honest.

    Parsed out of the RECORDING rather than restated, so the port and this test cannot drift together away from the text the twin really sent.
    """
    sent = recorded("a-single-page")[3][0][3]
    assert sent.removeprefix("query=") == frt.QUERY, "the query text drifted from the recording"


def test_an_empty_thread_set_is_a_success_with_an_empty_array() -> None:
    """Zero threads is a legitimate answer and must be distinguishable from a failure: exit 0, `[]` on disk, and the count in the summary line."""
    code, _, err, _calls, written = recorded("an-empty-thread-set")
    assert code == 0
    assert written == b"[]\n"
    assert b"fetched 0 review thread(s) across 0 pull request(s)" in err


def test_pagination_follows_the_cursor() -> None:
    """The lesson `check-resolved-threads.sh` already paid for: without the cursor, thread 101 being unresolved reads as "all resolved"."""
    code, _, err, calls, written = recorded("three-pages")
    assert code == 0
    assert len(calls) == 3, calls
    assert "after=CUR1" in calls[1], calls[1]
    assert "after=CUR2" in calls[2], calls[2]
    assert [n["id"] for n in json.loads(written)] == ["T_1", "T_2", "T_3"]
    assert b"fetched 3 review thread(s)" in err


def test_a_cursor_that_does_not_advance_fails_closed() -> None:
    """`hasNextPage: true` with no cursor is a loop, and the twin refused it rather than spinning."""
    for name in ("a-null-cursor-that-does-not-advance", "an-empty-cursor-that-does-not-advance"):
        code, _, err, _calls, written = recorded(name)
        assert code == 1, name
        assert b"hasNextPage was true but the cursor was empty; failing closed" in err
        assert b"cannot fetch review threads for the console PR; failing closed" in err
        assert written is None, "nothing is written on a failure"


def test_the_page_limit_stops_a_runaway() -> None:
    """50 pages is 5000 threads; reaching it means the cursor stopped advancing in a way the emptiness check cannot see (a cursor that repeats)."""
    code, _, err, calls, written = recorded("the-page-limit")
    assert code == 1
    assert len(calls) == 50, "the 51st page is refused before it is requested"
    assert b"review-thread pagination did not terminate after 51 pages; failing closed" in err
    assert written is None


def test_a_graphql_error_object_is_not_an_empty_thread_set() -> None:
    """THE CHECK THAT MATTERS MOST HERE. A GraphQL error is valid JSON and exits 0, so `gh_json` is happy with it; without this per-page check a permission error would read as "this PR has no threads" and a review round would resolve everything it could not see."""
    code, _, err, _calls, written = recorded("a-graphql-error")
    assert code == 1
    assert b"GraphQL query failed: Resource not accessible" in err
    assert written is None
    # An error array with no message still names itself.
    code, _, err, _, _ = recorded("a-graphql-error-with-no-message")
    assert code == 1
    assert b"GraphQL query failed: unknown error" in err


def test_an_error_on_a_later_page_is_caught_too() -> None:
    """Per page, not only on the last one: page 1 succeeded and its threads are DISCARDED, because a partial array is not an answer."""
    code, _, err, calls, written = recorded("a-graphql-error-on-page-two")
    assert code == 1
    assert len(calls) == 2
    assert b"GraphQL query failed: rate limited" in err
    assert written is None, "the first page's thread must not be left behind"


def test_the_out_file_is_absent_after_every_failure() -> None:
    """One assertion, gathered: absence, not emptiness, on all four shapes."""
    for name in ("a-failing-gh", "an-unparseable-body", "a-null-body", "a-graphql-error"):
        code, _, err, _, written = recorded(name)
        assert code == 1, name
        assert written is None, name
        assert b"failing closed" in err, name


def test_a_body_that_exits_zero_but_is_not_usable_json() -> None:
    """`jq -e`'s rule, not `json.loads`': a body of `null` or `false` is UNUSABLE even though `gh` exited 0, and got the retry loop rather than being handed on as a page."""
    code, _, err, calls, _ = recorded("a-null-body")
    assert code == 1
    assert len(calls) == 3, "an unusable body is retried, not accepted: %r" % calls
    assert b"gh failed after 3 attempts (last exit 0)." in err, err


def test_linked_submodule_prs_are_fetched_and_tagged() -> None:
    """The whole reason `--body` exists: a round that answers every console finding and stays red on a complaint in another repository."""
    code, _out, err, calls, written = recorded("a-linked-submodule-pr")
    assert code == 0
    assert len(calls) == 2, calls
    assert calls[1][4:] == ["-f", "owner=rediacc", "-f", "repo=renet", "-F", "pr=7"], calls[1]
    assert b"also fetching review threads for the linked rediacc/renet#7" in err
    nodes = json.loads(written)
    assert [(n["id"], n["repo"], n["pr"]) for n in nodes] == [
        ("T_C", "acme/console", 31),
        ("T_R", "rediacc/renet", 7),
    ]
    assert b"across 2 pull request(s)" in err


def test_a_linked_target_that_cannot_be_read() -> None:
    """BEST EFFORT, AND LOUD. The gate holds no cross-repo token, so a private submodule's PR is simply unreadable from here; killing the round over it would take fix rounds down with it. The annotation is on STDOUT because an Actions workflow command has to be, and console's own threads survive."""
    code, out, err, _calls, written = recorded("a-linked-target-that-cannot-be-read")
    assert code == 0, "a linked failure does NOT fail the round"
    assert out == (
        b"::warning::autopilot gate: could not read review threads for rediacc/renet#7 "
        b"(the gate holds no cross-repo token); this round cannot answer them\n"
    ), out
    assert b"::warning::" not in err, "the annotation must be on stdout, not stderr"
    assert [n["id"] for n in json.loads(written)] == ["T_C"]


def test_the_console_target_is_not_best_effort() -> None:
    """The mirror of the case above, and the reason the two cannot be one code path: console failing kills the round."""
    code, out, _err, calls, written = recorded("the-console-target-failing")
    assert code == 1
    assert out == b"", "no annotation: this is not a degradation, it is a failure"
    assert len(calls) == 1, "the linked target is never reached"
    assert written is None


def test_a_body_naming_no_known_submodule() -> None:
    """The link reader recognises only the four known submodules, and that allowlist is the security boundary: this output decides which repositories the gate will fetch model-visible text from."""
    for name in ("a-body-naming-an-unknown-repo", "a-body-with-no-links", "an-empty-body"):
        code, _, err, calls, _written = recorded(name)
        assert code == 0, name
        assert len(calls) == 1, (name, calls)
        assert b"also fetching" not in err, name


def test_a_mistyped_body_path_is_silent() -> None:
    """`[[ -n && -s ]]`, never `require_file`. A typo reads as "no linked PRs", which is the same silence the LINKED SUBMODULE paragraph exists to prevent, reached by a typo rather than by a missing token. Preserved; fixing it changes a live workflow step's contract."""
    code, _, err, calls, _written = recorded("a-mistyped-body-path")
    assert code == 0
    assert len(calls) == 1
    assert b"also fetching" not in err
    assert b"nope.md" not in err, "and it never mentions the path it could not read"


def test_a_transient_failure_recovers_on_the_second_attempt() -> None:
    """The direction that proves the loop is a RETRY and not a counter: the first attempt fails, the second succeeds, and the run continues."""
    code, _, err, calls, written = recorded("a-transient-failure-that-recovers")
    assert code == 0
    assert len(calls) == 2
    assert b"retrying..." in err
    assert b"gh failed after 3 attempts" not in err
    assert [n["id"] for n in json.loads(written)] == ["T_1"]


def test_a_broken_accumulator_does_not_end_the_run() -> None:
    """HAZARD, PRESERVED AND PINNED.

    `fetch_target` is only ever called from an `||` list and an `if !`, and bash DISABLES `set -e` for the whole body of a function invoked that way. So a failing accumulator does not fail the run: the array becomes the empty string and the script writes a blank line to `--out` and reports `fetched review thread(s)` with the count missing.

    Reaching it needs a page whose `nodes` is not an array, which `gh_json` happily passes through because it IS valid JSON. Every real page comes from a schema that cannot produce it, so this is defence-in-depth failing quietly rather than a live bug -- and it is the one place in this script where a failure does not fail closed.
    """
    code, _out, err, _calls, written = recorded("a-broken-accumulator")
    assert code == 0, "it does NOT fail closed, which is the finding"
    assert written == b"\n", "a blank line where the array should be: %r" % written
    assert b"fetched  review thread(s) across  pull request(s)" in err, err
    assert b"Cannot iterate over string" in err, "jq's own diagnostic reaches stderr"


def test_slow_a_failing_fetch_retries_three_times_and_replays_its_stderr(
    tmp_path: pathlib.Path,
) -> None:
    """Eighteen seconds, and the only case that proves the `_gh_probe` loop: two warnings, the final error carrying the last exit code, and gh's captured stderr replayed indented four spaces."""
    code, _, err, calls, written = recorded(SLOW)
    assert code == 1
    assert len(calls) == 3, calls
    assert err.count(b"retrying...") == 2, err
    assert b"(page 1): gh failed after 3 attempts (last exit 4)." in err
    assert b"    gh: HTTP 401 Bad credentials\n" in err, "indented four spaces"
    assert written is None
    compare(tmp_path, SLOW)


# --------------------------------------------------------------------------- The pure helpers, driven directly ---------------------------------------------------------------------------


def test_page_args_omits_the_cursor_on_the_first_page() -> None:
    first = frt.page_args("Q", "acme", "console", "31", "")
    assert first == ["-f", "query=Q", "-f", "owner=acme", "-f", "repo=console", "-F", "pr=31"]
    later = frt.page_args("Q", "acme", "console", "31", "CUR")
    assert later == [*first, "-f", "after=CUR"]
    assert "-F" in first, "pr is the TYPED form; the GraphQL variable is Int!"


def test_json_usable_is_jq_dash_e_and_not_json_loads() -> None:
    assert frt._json_usable(b'{"data":{}}') is True
    assert frt._json_usable(b"[]") is True, "an empty array is usable; an empty answer is not null"
    assert frt._json_usable(b"null") is False
    assert frt._json_usable(b"false") is False
    assert frt._json_usable(b"") is False
    assert frt._json_usable(b"{oops") is False


def test_the_owner_and_name_split() -> None:
    """`${target%%/*}` and `${target##*/}`, which are NOT `split("/")` when a target carries more than one slash."""
    fetcher = frt.Fetcher()
    assert fetcher.all_nodes == "[]", "the accumulator starts as an empty JSON array"
    plain, nested = "acme/console", "a/b/c"
    assert plain.split("/", 1)[0] == "acme"
    assert nested.split("/", 1)[0] == "a", "%% takes the SHORTEST leading match"
    assert nested.rsplit("/", 1)[-1] == "c", "## takes the LONGEST leading match"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_acceptance_of_a_graphql_error_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Stop treating an `errors` array as a failure.

    That is the exact hole `test_a_graphql_error_object_is_not_an_empty_thread_set` exists for: a permission error is valid JSON and exits 0, so without the per-page check it reads as "this PR has no threads" and a review round resolves everything it could not see. The recorded verdict for `a-graphql-error` is 1 with no file written; a mutant that accepts it exits 0 and
    leaves an array on disk. The mutation runs from a throwaway copy of the package's module file; the tracked port is never touched.
    """
    with open(PORT, encoding="utf-8") as fh:
        original = fh.read()
    anchor = '            if _jq_quiet(["-e", ".errors"], page_json):\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "            if False:\n")

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "fetch_review_threads.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "a-graphql-error"
    code, _, _, _, written = run(tmp_path / "planted", mutant, name)
    want_exit, _, _, _, want_written = recorded(name)
    assert (want_exit, want_written) == (1, None), "the recorded verdict moved"
    assert code == 0, "the plant did not change the verdict"
    assert written is not None, "the plant left no artifact behind"

    compare(tmp_path / "good", name)
    with open(PORT, encoding="utf-8") as fh:
        assert fh.read() == original
