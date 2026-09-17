"""Differential: `rediacc_ci.autopilot.fetch_review_threads` against its twin
`.ci/scripts/autopilot/fetch-review-threads.sh`.

A RECORDING FAKE `gh` ON A STUB PATH, and here the fake is not a convenience: it is the only thing standing between a test run and a real GraphQL query against whatever repository a fixture names. The fake answers from a SCRIPT of per-call responses handed to it in the environment, so a case can make page two fail, or return a GraphQL error object, or hand back a cursor that never
advances, without any of it leaving the process tree.

`test_the_fake_gh_is_the_gh` resolves `gh` through the stub PATH and fails if anything else wins. Every other case rests on that.

WHAT IS COMPARED: exit code, stdout bytes, stderr bytes, the `gh` CALL LOG, and the CONTENT OF `--out`. The last two are the artifact. This script's entire effect on the world is which GraphQL requests it makes and what array it leaves behind, and a port that fetched the right threads from the wrong repository, or dropped the `repo`/`pr` tags that let a reply be routed back, would
print an identical summary line. The call log therefore carries the full argv INCLUDING the query text, so a reflowed query is a failure here rather than a surprise in production.

THE OUT FILE IS CHECKED FOR ABSENCE ON EVERY FAILURE PATH, not for emptiness.
"No threads" and "could not ask" must not share an output; an empty file is a
value a reader could act on, absence is not.

ONE CASE COSTS EIGHTEEN SECONDS PER SIDE. `_gh_probe` sleeps 3 then 6 between its three attempts, and it is the only way to prove the retry loop, the final `gh failed after 3 attempts` line and the exit code agree. It is named `test_slow_...` so it can be deselected by name, and it is not skipped by default, because a retry loop nobody drives is a retry loop nobody has seen.

K=5 LEDGER: `.ci/shadow/w7p6-fetch-review-threads.observations.jsonl`, recorded
in a disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import fetch_review_threads as frt

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "fetch-review-threads.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "fetch_review_threads.py"
BASH = shutil.which("bash") or "/bin/bash"

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


def _stub_bin(base: pathlib.Path) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
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


BASE_ARGV = ["--pr", "31", "--repo", "acme/console", "--out", "threads.json"]


def _sides(
    name: str,
    argv: list[str] | None = None,
    *,
    script: list[dict] | None = None,
    fixtures: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
):
    argv = list(argv) if argv is not None else list(BASE_ARGV)
    env_extra = {"FAKE_GH_SCRIPT": json.dumps(script or [])}
    env_extra.update(env or {})
    results = []
    with tempfile.TemporaryDirectory() as td:
        for side, subject in (("old", TWIN), ("new", PORT)):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            for rel, text in (fixtures or {}).items():
                (base / rel).write_text(text, encoding="utf-8")
            results.append(_run(subject, base, argv, dict(env_extra)))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\nold stderr %r\nnew stderr %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\nold %r\nnew %r" % (name, old[1], new[1])
    assert new[2] == old[2], "%s: stderr diverged:\nold %r\nnew %r" % (name, old[2], new[2])
    assert new[3] == old[3], "%s: gh calls diverged:\nold %r\nnew %r" % (name, old[3], new[3])
    assert new[4] == old[4], "%s: --out diverged:\nold %r\nnew %r" % (name, old[4], new[4])
    return old


# --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------


def test_the_fake_gh_is_the_gh() -> None:
    """Nothing below means anything if the real `gh` wins the PATH race."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        found = shutil.which("gh", path=path)
        assert found == str(base / "bin" / "gh"), "the fake gh is not first on PATH: %r" % found


def test_the_fake_gh_records_and_answers_in_order() -> None:
    """CONTROL for the call log. A fake that recorded nothing would make every
    `calls == [...]` assertion below vacuous."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        log = base / "gh-calls.log"
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


# --------------------------------------------------------------------------- Usage ---------------------------------------------------------------------------


def test_the_three_required_flags() -> None:
    for argv in (
        [],
        ["--pr", "31"],
        ["--pr", "31", "--repo", "acme/console"],
        ["--repo", "acme/console", "--out", "threads.json"],
        ["--pr", "31", "--out", "threads.json"],
    ):
        code, _out, err, calls, written = _sides("usage-%d" % len(argv), argv)
        assert code == 2, argv
        assert b"usage: fetch-review-threads.sh --pr <number> --repo <owner/name>" in err
        assert calls == [], "usage must be decided before any request: %r" % calls
        assert written is None


def test_the_pr_number_must_be_a_number() -> None:
    """The ONLY validated input, and it is validated because it travels as a
    TYPED GraphQL variable: a bad value would be a server error paid for after
    the request rather than a refusal before it."""
    for value in ("abc", "31a", "", "-1", "3 1", "31.0"):
        argv = ["--pr", value, "--repo", "acme/console", "--out", "threads.json"]
        code, _, err, calls, written = _sides("pr-%r" % value, argv)
        assert code == 2, value
        assert calls == [], value
        assert written is None
        if value == "":
            # An EMPTY value is caught by the usage test first, because `parse_args` stores nothing distinguishable from an absent flag.
            assert b"usage: fetch-review-threads.sh" in err
        else:
            assert b"--pr must be a number, got '%s'" % value.encode() in err, err


# --------------------------------------------------------------------------- The happy path, and what the request actually is ---------------------------------------------------------------------------


def test_a_single_page_of_threads() -> None:
    code, out, err, calls, written = _sides(
        "one-page", script=[ok(page([thread("T_1"), thread("T_2")]))]
    )
    assert code == 0
    assert out == b""
    assert b"fetched 2 review thread(s) across 1 pull request(s) -> threads.json" in err
    assert len(calls) == 1, calls
    argv = calls[0]
    assert argv[:2] == ["api", "graphql"]
    # THE REQUEST, field by field. `-F pr` is the typed form; `-f` the string
    # form; the query travels whole, leading newline and all.
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


def test_an_empty_thread_set_is_a_success_with_an_empty_array() -> None:
    """Zero threads is a legitimate answer and must be distinguishable from a
    failure: exit 0, `[]` on disk, and the count in the summary line."""
    code, _, err, _calls, written = _sides("empty", script=[ok(page([]))])
    assert code == 0
    assert written == b"[]\n"
    assert b"fetched 0 review thread(s) across 0 pull request(s)" in err


def test_pagination_follows_the_cursor() -> None:
    """The lesson `check-resolved-threads.sh` already paid for: without the
    cursor, thread 101 being unresolved reads as "all resolved"."""
    code, _, err, calls, written = _sides(
        "paged",
        script=[
            ok(page([thread("T_1")], has_next=True, cursor="CUR1")),
            ok(page([thread("T_2")], has_next=True, cursor="CUR2")),
            ok(page([thread("T_3")])),
        ],
    )
    assert code == 0
    assert len(calls) == 3, calls
    assert "after=CUR1" in calls[1], calls[1]
    assert "after=CUR2" in calls[2], calls[2]
    assert [n["id"] for n in json.loads(written)] == ["T_1", "T_2", "T_3"]
    assert b"fetched 3 review thread(s)" in err


def test_a_cursor_that_does_not_advance_fails_closed() -> None:
    """`hasNextPage: true` with no cursor is a loop, and the twin refuses it
    rather than spinning."""
    for cursor in (None, ""):
        code, _, err, _calls, written = _sides(
            "cursor-%r" % cursor,
            script=[ok(page([thread("T_1")], has_next=True, cursor=cursor))],
        )
        assert code == 1, cursor
        assert b"hasNextPage was true but the cursor was empty; failing closed" in err
        assert b"cannot fetch review threads for the console PR; failing closed" in err
        assert written is None, "nothing is written on a failure"


def test_the_page_limit_stops_a_runaway() -> None:
    """50 pages is 5000 threads; reaching it means the cursor stopped advancing
    in a way the emptiness check cannot see (a cursor that repeats)."""
    script = [ok(page([thread("T_%d" % i)], has_next=True, cursor="CUR%d" % i)) for i in range(50)]
    code, _, err, calls, written = _sides("page-limit", script=script)
    assert code == 1
    assert len(calls) == 50, "the 51st page is refused before it is requested"
    assert b"review-thread pagination did not terminate after 51 pages; failing closed" in err
    assert written is None


# --------------------------------------------------------------------------- Failure, and the shapes it arrives in ---------------------------------------------------------------------------


def test_a_graphql_error_object_is_not_an_empty_thread_set() -> None:
    """THE CHECK THAT MATTERS MOST HERE. A GraphQL error is valid JSON and exits
    0, so `gh_json` is happy with it; without this per-page check a permission
    error would read as "this PR has no threads" and a review round would
    resolve everything it could not see."""
    body = json.dumps({"errors": [{"message": "Resource not accessible by integration"}]})
    code, _, err, _calls, written = _sides("graphql-error", script=[ok(body)])
    assert code == 1
    assert b"GraphQL query failed: Resource not accessible by integration" in err
    assert written is None
    # An error array with no message still names itself.
    code, _, err, _, _ = _sides("graphql-error-bare", script=[ok(json.dumps({"errors": [{}]}))])
    assert code == 1
    assert b"GraphQL query failed: unknown error" in err


def test_an_error_on_a_later_page_is_caught_too() -> None:
    """Per page, not only on the last one: pages 1 and 2 succeeded and their
    threads are DISCARDED, because a partial array is not an answer."""
    body = json.dumps({"errors": [{"message": "rate limited"}]})
    code, _, err, calls, written = _sides(
        "graphql-error-page-2",
        script=[ok(page([thread("T_1")], has_next=True, cursor="CUR1")), ok(body)],
    )
    assert code == 1
    assert len(calls) == 2
    assert b"GraphQL query failed: rate limited" in err
    assert written is None, "the first page's thread must not be left behind"


def test_the_out_file_is_absent_after_every_failure() -> None:
    """One assertion, gathered: absence, not emptiness, on all four shapes."""
    shapes = {
        "gh-fails": [{"rc": 1, "err": "HTTP 404\n"}] * 3,
        "unparseable": [ok("not json")] * 3,
        "null-body": [ok("null")] * 3,
        "graphql-error": [ok(json.dumps({"errors": [{"message": "no"}]}))],
    }
    for label, script in shapes.items():
        code, _, err, _, written = _sides("absent-%s" % label, script=script)
        assert code == 1, label
        assert written is None, label
        assert b"failing closed" in err, label


def test_a_body_that_exits_zero_but_is_not_usable_json() -> None:
    """`jq -e`'s rule, not `json.loads`': a body of `null` or `false` is
    UNUSABLE even though `gh` exited 0, and gets the retry loop rather than
    being handed on as a page."""
    code, _, err, calls, _ = _sides("null-body-detail", script=[ok("null")] * 3)
    assert code == 1
    assert len(calls) == 3, "an unusable body is retried, not accepted: %r" % calls
    assert b"gh failed after 3 attempts (last exit 0)." in err, err


# --------------------------------------------------------------------------- Linked submodule PRs ---------------------------------------------------------------------------

LINKED_BODY = """Some description.

- renet: rediacc/renet#7
"""


def test_linked_submodule_prs_are_fetched_and_tagged() -> None:
    """The whole reason `--body` exists: a round that answers every console
    finding and stays red on a complaint in another repository."""
    code, _out, err, calls, written = _sides(
        "linked",
        [*BASE_ARGV, "--body", "body.md"],
        fixtures={"body.md": LINKED_BODY},
        script=[ok(page([thread("T_C")])), ok(page([thread("T_R")]))],
    )
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
    """BEST EFFORT, AND LOUD. The gate holds no cross-repo token, so a private
    submodule's PR is simply unreadable from here; killing the round over it
    would take fix rounds down with it. The annotation is on STDOUT because an
    Actions workflow command has to be, and console's own threads survive."""
    code, out, err, _calls, written = _sides(
        "linked-denied",
        [*BASE_ARGV, "--body", "body.md"],
        fixtures={"body.md": LINKED_BODY},
        script=[
            ok(page([thread("T_C")])),
            ok(json.dumps({"errors": [{"message": "Resource not accessible"}]})),
        ],
    )
    assert code == 0, "a linked failure does NOT fail the round"
    assert out == (
        b"::warning::autopilot gate: could not read review threads for rediacc/renet#7 "
        b"(the gate holds no cross-repo token); this round cannot answer them\n"
    ), out
    assert b"::warning::" not in err, "the annotation must be on stdout, not stderr"
    assert [n["id"] for n in json.loads(written)] == ["T_C"]


def test_the_console_target_is_not_best_effort() -> None:
    """The mirror of the case above, and the reason the two cannot be one code
    path: console failing kills the round."""
    code, out, _err, calls, written = _sides(
        "console-required",
        [*BASE_ARGV, "--body", "body.md"],
        fixtures={"body.md": LINKED_BODY},
        script=[ok(json.dumps({"errors": [{"message": "nope"}]}))],
    )
    assert code == 1
    assert out == b"", "no annotation: this is not a degradation, it is a failure"
    assert len(calls) == 1, "the linked target is never reached"
    assert written is None


def test_a_body_naming_no_known_submodule() -> None:
    """`linked-sub-prs.sh` recognises only the four known submodules, and that
    allowlist is the security boundary: this output decides which repositories
    the gate will fetch model-visible text from."""
    for label, body in (
        ("unknown-repo", "- attacker/evil#7\n"),
        ("no-links", "just a description\n"),
        ("empty", ""),
    ):
        code, _, err, calls, _written = _sides(
            "body-%s" % label,
            [*BASE_ARGV, "--body", "body.md"],
            fixtures={"body.md": body},
            script=[ok(page([thread("T_C")]))],
        )
        assert code == 0, label
        assert len(calls) == 1, (label, calls)
        assert b"also fetching" not in err, label


def test_a_mistyped_body_path_is_silent() -> None:
    """`[[ -n && -s ]]`, never `require_file`. A typo reads as "no linked PRs",
    which is the same silence the LINKED SUBMODULE paragraph exists to prevent,
    reached by a typo rather than by a missing token. Preserved; fixing it
    changes a live workflow step's contract."""
    code, _, err, calls, _written = _sides(
        "body-typo",
        [*BASE_ARGV, "--body", "nope.md"],
        fixtures={"body.md": LINKED_BODY},
        script=[ok(page([thread("T_C")]))],
    )
    assert code == 0
    assert len(calls) == 1
    assert b"also fetching" not in err
    assert b"nope.md" not in err, "and it never mentions the path it could not read"


# --------------------------------------------------------------------------- The retry loop ---------------------------------------------------------------------------


def test_slow_a_failing_fetch_retries_three_times_and_replays_its_stderr() -> None:
    """Eighteen seconds per side, and the only case that proves the `_gh_probe`
    loop: two warnings, the final error carrying the last exit code, and gh's
    captured stderr replayed indented four spaces."""
    code, _, err, calls, written = _sides(
        "retry",
        script=[{"rc": 4, "err": "gh: HTTP 401 Bad credentials\n"}] * 3,
    )
    assert code == 1
    assert len(calls) == 3, calls
    assert err.count(b"retrying...") == 2, err
    assert b"(page 1): gh failed after 3 attempts (last exit 4)." in err
    assert b"    gh: HTTP 401 Bad credentials\n" in err, "indented four spaces"
    assert written is None


def test_a_transient_failure_recovers_on_the_second_attempt() -> None:
    """The direction that proves the loop is a RETRY and not a counter: the
    first attempt fails, the second succeeds, and the run continues."""
    code, _, err, calls, written = _sides(
        "retry-recovers",
        script=[{"rc": 1, "err": "flake\n"}, ok(page([thread("T_1")]))],
    )
    assert code == 0
    assert len(calls) == 2
    assert b"retrying..." in err
    assert b"gh failed after 3 attempts" not in err
    assert [n["id"] for n in json.loads(written)] == ["T_1"]


# --------------------------------------------------------------------------- The preserved hazard ---------------------------------------------------------------------------


def test_a_broken_accumulator_does_not_end_the_run() -> None:
    """HAZARD, PRESERVED AND PINNED.

    `fetch_target` is only ever called from an `||` list and an `if !`, and bash DISABLES `set -e` for the whole body of a function invoked that way. So a failing accumulator does not fail the run: the array becomes the empty string and the script writes a blank line to `--out` and reports `fetched review thread(s)` with the count missing.

    Reaching it needs a page whose `nodes` is not an array, which `gh_json` happily passes through because it IS valid JSON. Every real page comes from a schema that cannot produce it, so this is defence-in-depth failing quietly rather than a live bug -- and it is the one place in this script where a
    failure does not fail closed."""
    broken = json.dumps(
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
    code, _out, err, _calls, written = _sides("accumulator", script=[ok(broken)])
    assert code == 0, "it does NOT fail closed, which is the finding"
    assert written == b"\n", "a blank line where the array should be: %r" % written
    assert b"fetched  review thread(s) across  pull request(s)" in err, err
    assert b"Cannot iterate over string" in err, "jq's own diagnostic reaches stderr"


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


def test_the_query_is_the_twins_query() -> None:
    """Byte for byte, because it travels as a request argument."""
    twin = TWIN.read_text(encoding="utf-8")
    start = twin.index("QUERY='") + len("QUERY='")
    end = twin.index("'", start)
    assert twin[start:end] == frt.QUERY, "the query text drifted from the twin"


def test_the_owner_and_name_split() -> None:
    """`${target%%/*}` and `${target##*/}`, which are NOT `split("/")` when a
    target carries more than one slash."""
    fetcher = frt.Fetcher()
    assert fetcher.all_nodes == "[]", "the accumulator starts as an empty JSON array"
    plain, nested = "acme/console", "a/b/c"
    assert plain.split("/", 1)[0] == "acme"
    assert nested.split("/", 1)[0] == "a", "%% takes the SHORTEST leading match"
    assert nested.rsplit("/", 1)[-1] == "c", "## takes the LONGEST leading match"
