"""Differential: `rediacc_ci.autopilot.review_reply` against its twin `.ci/scripts/autopilot/review-reply.sh`.

THE FAKE `gh` IS A SAFETY CONTROL, NOT A CONVENIENCE, and this subject is the one where that is literal: `apply`'s success path posts a comment into a review thread and marks that thread RESOLVED. GitHub undoes neither. The thread id comes out of a model-authored verdict, and a global GraphQL node id names a thread on any pull request in any repository the token can reach. So a
case that reached the real binary could post fixture text onto somebody's PR.

Four things stop that, and the first is asserted rather than assumed:

  1. the stub directory is FIRST on PATH, and `test_the_fake_gh_is_the_gh`
     resolves `gh` through that PATH and fails if anything else wins;
  2. every fixture id is `T_acme...`, which names nothing;
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` fails auth rather than mutating;
  4. the fake RECORDS every argv, so a case that somehow produced no call log
     fails rather than passing quietly.

THE CALL LOG IS THE ARTIFACT FOR `apply`, and it is compared whole. Everything this subcommand does to the world is two GraphQL mutations per entry: which mutation, which thread id, and the exact body bytes. A port that replied with the right text to the wrong thread would print an identical summary line. `test_model_text_travels_as_an_argv_value_not_as_shell` is the case that
reads the recorded argv back and checks a `$(...)` in a reply body arrived literal.

FOR `plan` THE ARTIFACT IS STDOUT (or `--out`), and the two skip reasons are driven SEPARATELY. `malformed-id` and `unknown-thread` fail for different reasons -- the first is a shape check, the second is "the payload is the round's whole world" -- and a port that collapsed them would still pass a test that only ever fed it garbage.

K=5 LEDGER: `.ci/shadow/w7p6-review-reply.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
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
from rediacc_ci.autopilot import review_reply as rr

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "review-reply.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "review_reply.py"
BASH = shutil.which("bash") or "/bin/bash"

# A recording fake `gh`. Answers from FAKE_GH_SCRIPT in call order; records every argv BEFORE deciding anything.
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
step = script[index] if index < len(script) else {"rc": 0, "out": '{"data":{}}'}
sys.stdout.write(step.get("out", '{"data":{}}'))
sys.stderr.write(step.get("err", ""))
sys.exit(int(step.get("rc", 0)))
"""


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
    written = base / "plan.json"
    return (
        proc.returncode,
        proc.stdout,
        proc.stderr,
        calls,
        written.read_bytes() if written.exists() else None,
    )


def _sides(
    name: str,
    argv: list[str],
    *,
    fixtures: dict[str, str] | None = None,
    script: list[dict] | None = None,
    env: dict[str, str] | None = None,
):
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
    assert new[4] == old[4], "%s: plan.json diverged:\nold %r\nnew %r" % (name, old[4], new[4])
    return old


def verdict(*decisions: object, **extra: object) -> str:
    payload: dict = {"decisions": list(decisions)}
    payload.update(extra)
    return json.dumps(payload) + "\n"


def threads(*entries: dict, wrapped: bool = True) -> str:
    return json.dumps({"threads": list(entries)} if wrapped else list(entries)) + "\n"


def entry(tid: str, repo: str | None = "acme/console") -> dict:
    node: dict = {"id": tid, "isResolved": False, "path": "a.ts"}
    if repo is not None:
        node["repo"] = repo
    return node


PLAN_ARGV = ["plan", "--verdict", "verdict.json", "--threads", "threads.json"]
BASE_FIXTURES = {
    "verdict.json": verdict("thread T_acme1: thanks, fixed"),
    "threads.json": threads(entry("T_acme1")),
}


# --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------


def test_the_fake_gh_is_the_gh() -> None:
    """The whole "nothing was mutated" claim rests on this one resolution."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        found = shutil.which("gh", path=_stub_bin(base))
        assert found == str(base / "bin" / "gh"), "the fake gh is not first on PATH: %r" % found


def test_the_fake_gh_records_every_call() -> None:
    """CONTROL for every `calls == [...]` assertion below."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        log = base / "gh-calls.log"
        log.write_text("", encoding="utf-8")
        env = {"PATH": path, "FAKE_GH_LOG": str(log), "FAKE_GH_SCRIPT": "[]"}
        proc = subprocess.run(
            ["gh", "api", "graphql", "-f", "query=x"], capture_output=True, env=env, check=False
        )
        assert proc.returncode == 0
        assert json.loads(log.read_text(encoding="utf-8").strip()) == [
            "api",
            "graphql",
            "-f",
            "query=x",
        ]


def test_the_mutations_are_the_twins_mutations() -> None:
    """Byte for byte, because they travel as request arguments and because `check-resolved-threads.sh` advertises the same two to humans -- the automated and manual paths must not drift."""
    twin = TWIN.read_text(encoding="utf-8")
    for name, value in (
        ("REPLY_MUTATION", rr.REPLY_MUTATION),
        ("RESOLVE_MUTATION", rr.RESOLVE_MUTATION),
    ):
        start = twin.index("%s='" % name) + len("%s='" % name)
        end = twin.index("'", start)
        assert value == twin[start:end], "%s drifted from the twin" % name
    start = twin.index("ID_SHAPE='") + len("ID_SHAPE='")
    assert twin[start : twin.index("'", start)] == rr.ID_SHAPE


# --------------------------------------------------------------------------- Dispatch and usage ---------------------------------------------------------------------------


def test_unknown_subcommands_including_the_empty_one() -> None:
    for argv, shown in (
        (["frobnicate"], b"unknown subcommand 'frobnicate' (plan|apply)"),
        ([], b"unknown subcommand '' (plan|apply)"),
        (["--plan", "plan.json"], b"unknown subcommand '--plan' (plan|apply)"),
        (["Plan"], b"unknown subcommand 'Plan' (plan|apply)"),
    ):
        code, out, err, calls, _ = _sides("unknown-%r" % argv, argv, fixtures=BASE_FIXTURES)
        assert code == 2, argv
        assert out == b""
        assert shown in err, err
        assert calls == []


def test_plan_usage_and_its_two_required_flags() -> None:
    for argv in (
        ["plan"],
        ["plan", "--verdict", "verdict.json"],
        ["plan", "--threads", "threads.json"],
    ):
        code, _out, err, calls, _ = _sides(
            "plan-usage-%d" % len(argv), argv, fixtures=BASE_FIXTURES
        )
        assert code == 2, argv
        assert b"usage: review-reply.sh plan --verdict <file> --threads <file>" in err
        assert calls == []


def test_plan_requires_both_files_to_exist() -> None:
    """`require_file`, in the twin's order: verdict first."""
    code, _, err, _, _ = _sides(
        "plan-no-verdict",
        ["plan", "--verdict", "nope.json", "--threads", "threads.json"],
        fixtures=BASE_FIXTURES,
    )
    assert code == 1
    assert b"Required file 'nope.json' does not exist" in err
    code, _, err, _, _ = _sides(
        "plan-no-threads",
        ["plan", "--verdict", "verdict.json", "--threads", "gone.json"],
        fixtures=BASE_FIXTURES,
    )
    assert code == 1
    assert b"Required file 'gone.json' does not exist" in err


def test_max_body_must_be_a_number_and_is_checked_after_the_files() -> None:
    for value in ("abc", "-1", "1234567", "2000.0", "2 0"):
        code, _, err, _, _ = _sides(
            "maxbody-%r" % value,
            [*PLAN_ARGV, "--max-body", value],
            fixtures=BASE_FIXTURES,
        )
        assert code == 2, value
        assert b"--max-body must be a number, got '%s'" % value.encode() in err, err
    # ORDER: a bad --max-body with a missing verdict is the FILE error, because require_file runs first.
    code, _, err, _, _ = _sides(
        "maxbody-order",
        ["plan", "--verdict", "nope.json", "--threads", "threads.json", "--max-body", "abc"],
        fixtures=BASE_FIXTURES,
    )
    assert code == 1
    assert b"Required file 'nope.json' does not exist" in err


# --------------------------------------------------------------------------- plan: the disposition parser ---------------------------------------------------------------------------


def test_a_clean_plan() -> None:
    code, out, err, calls, _written = _sides("plan-clean", PLAN_ARGV, fixtures=BASE_FIXTURES)
    assert code == 0
    assert json.loads(out) == {
        "replies": [{"thread_id": "T_acme1", "body": "thanks, fixed", "repo": "acme/console"}],
        "skipped": [],
        "flagged": False,
    }, out
    assert b"review-reply plan: 1 reply/resolve pair(s) planned" in err
    assert b"disposition(s) name no thread" not in err
    assert calls == [], "plan is PURE: it must not call gh"


def test_an_ordinary_decision_entry_is_not_thread_traffic() -> None:
    """Dropped SILENTLY, not skipped loudly. A round whose decisions are mostly prose must not be `flagged`, or the warning stops meaning anything."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["verdict.json"] = verdict(
        "ruled out bumping the pin, see the ledger",
        "thread T_acme1: thanks, fixed",
        "threadlike but not: no colon-space marker",
        "thread-with-no-space: also not it",
    )
    _code, out, _err, _, _ = _sides("plan-prose", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert plan["flagged"] is False, plan
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    assert plan["skipped"] == []


def test_the_two_skip_reasons_are_different_reasons() -> None:
    """A malformed id and a well-formed id nobody showed the model are separate findings. The second is the security one: the payload is the round's whole world, so an id outside it is not addressable."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["verdict.json"] = verdict(
        "thread T_acme1: kept",
        "thread has spaces: malformed",
        "thread ../../etc/passwd: malformed",
        "thread T_someoneElsesPR: well-shaped and unknown",
    )
    _code, out, err, _, _ = _sides("plan-skips", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert plan["flagged"] is True
    assert plan["skipped"] == [
        {"entry": "has spaces", "reason": "malformed-id"},
        {"entry": "../../etc/passwd", "reason": "malformed-id"},
        {"entry": "T_someoneElsesPR", "reason": "unknown-thread"},
    ], plan["skipped"]
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    # LOUD, on stderr, one line per skip, and the count in the header.
    assert b"review-reply plan: 3 disposition(s) name no thread in this round's payload" in err
    assert b"    - malformed-id: has spaces\n" in err
    assert b"    - unknown-thread: T_someoneElsesPR\n" in err


def test_an_id_of_exactly_the_boundary_lengths() -> None:
    """`{1,128}`: 128 characters pass, 129 do not, and the bound is what stops
    a mutation variable growing without limit."""
    long_ok = "T" + "a" * 127
    long_no = "T" + "a" * 128
    fixtures = {
        "verdict.json": verdict("thread %s: ok" % long_ok, "thread %s: no" % long_no),
        "threads.json": threads(entry(long_ok), entry(long_no)),
    }
    _code, out, _, _, _ = _sides("plan-bounds", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert [r["thread_id"] for r in plan["replies"]] == [long_ok]
    assert plan["skipped"] == [{"entry": long_no, "reason": "malformed-id"}]


def test_the_body_is_capped_and_the_cap_is_configurable() -> None:
    """`.body[0:$max]` is a jq string slice over CODEPOINTS."""
    fixtures = {
        "verdict.json": verdict("thread T_acme1: %s" % ("x" * 50)),
        "threads.json": threads(entry("T_acme1")),
    }
    _, out, _, _, _ = _sides("plan-cap", [*PLAN_ARGV, "--max-body", "10"], fixtures=fixtures)
    assert json.loads(out)["replies"][0]["body"] == "x" * 10
    # The default is 2000, so 50 characters survive untouched.
    _, out, _, _, _ = _sides("plan-cap-default", PLAN_ARGV, fixtures=fixtures)
    assert json.loads(out)["replies"][0]["body"] == "x" * 50
    # Codepoints, not bytes: ten astral characters are ten, not forty.
    fixtures["verdict.json"] = verdict("thread T_acme1: %s" % ("\U0001f600" * 20))
    _code, out, _, _, _ = _sides(
        "plan-cap-astral", [*PLAN_ARGV, "--max-body", "10"], fixtures=fixtures
    )
    assert json.loads(out)["replies"][0]["body"] == "\U0001f600" * 10


def test_a_multi_line_disposition_is_silently_dropped() -> None:
    """DEFECT 1, LIVE, PRESERVED AND PINNED. See the port's docstring.

    jq's `s` flag is single-line ANCHOR mode (`^` -> `\\A`, `$` -> `\\Z`), not dotall -- the dotall flag is `m`. So `.*` still stops at the first newline, the anchored `$` cannot match, and `capture` yields NOTHING, which drops the entry from the stream entirely: not replied, not skipped, `flagged` false, and no warning on stderr.

    THAT CONTRADICTS THE TWIN'S OWN HEADER ("Anything else lands in skipped[]
    with a reason and raises flagged -- never silently"). A model writing a
    two-line answer gets exactly the silence that sentence promises cannot happen. Asserted as the twin BEHAVES rather than as it is documented, and this test is what will go red when somebody repairs it."""
    fixtures = {
        "verdict.json": verdict("thread T_acme1: first line\nsecond line\n\nthird"),
        "threads.json": threads(entry("T_acme1")),
    }
    code, out, err, _, _ = _sides("plan-multiline", PLAN_ARGV, fixtures=fixtures)
    assert code == 0
    plan = json.loads(out)
    assert plan == {"replies": [], "skipped": [], "flagged": False}, plan
    assert b"review-reply plan: 0 reply/resolve pair(s) planned" in err
    assert b"disposition(s) name no thread" not in err, "the silence is the defect"
    # CONTROL, so the case is not simply "this fixture never plans anything": the SAME disposition on ONE line plans a reply.
    fixtures["verdict.json"] = verdict("thread T_acme1: first line")
    code, out, _, _, _ = _sides("plan-multiline-control", PLAN_ARGV, fixtures=fixtures)
    assert json.loads(out)["replies"][0]["body"] == "first line"


def test_the_threads_fixture_is_accepted_in_both_spellings() -> None:
    """`(.threads // .) // []`: the payload object OR a bare array, because requiring one spelling breaks the moment the payload gains a field."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["threads.json"] = threads(entry("T_acme1"))
    _, out, _, _, _ = _sides("plan-shape-object", PLAN_ARGV, fixtures=fixtures)
    assert json.loads(out)["replies"][0]["thread_id"] == "T_acme1"
    # An empty OBJECT payload names no thread, so every disposition is unknown.
    fixtures["threads.json"] = '{"threads":[]}\n'
    _code, out, _, _, _ = _sides("plan-empty-object", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert plan["replies"] == []
    assert plan["skipped"] == [{"entry": "T_acme1", "reason": "unknown-thread"}]


def test_a_bare_array_threads_fixture_is_refused_by_jq() -> None:
    """DEFECT 2, LATENT, PRESERVED AND PINNED. See the port's docstring.

    `.threads` on an ARRAY is an ERROR in jq, not `null`, so `(.threads // .)` never falls through and the bare-array spelling the comment promises exits 5
    with a jq diagnostic and no plan. Latent because the only caller
    (`.github/workflows/autopilot.yml:817`) passes `review-payload.sh`'s object, so this is documentation of a capability that was never there."""
    for label, text in (
        ("array-of-threads", threads(entry("T_acme1"), wrapped=False)),
        ("empty-array", "[]\n"),
    ):
        fixtures = dict(BASE_FIXTURES)
        fixtures["threads.json"] = text
        code, out, err, _, _ = _sides("plan-array-%s" % label, PLAN_ARGV, fixtures=fixtures)
        assert code == 5, label
        assert out == b"", label
        assert b'Cannot index array with string "threads"' in err, err


def test_the_repo_tag_is_carried_into_the_plan() -> None:
    """The plan is an audit record: "resolved a thread" is not a useful sentence without naming where. An untagged thread falls back to `console`."""
    fixtures = {
        "verdict.json": verdict("thread T_acme1: a", "thread T_acme2: b"),
        "threads.json": threads(entry("T_acme1", "rediacc/renet"), entry("T_acme2", repo=None)),
    }
    _code, out, _, _, _ = _sides("plan-repo", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert [(r["thread_id"], r["repo"]) for r in plan["replies"]] == [
        ("T_acme1", "rediacc/renet"),
        ("T_acme2", "console"),
    ]


def test_a_non_string_decision_entry_is_ignored() -> None:
    """`select(type == "string")`: a number or an object in `decisions[]` is not
    a disposition and must not crash the plan."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["verdict.json"] = verdict(
        42, {"thread": "T_acme1"}, None, "thread T_acme1: thanks, fixed"
    )
    _code, out, _, _, _ = _sides("plan-nonstring", PLAN_ARGV, fixtures=fixtures)
    plan = json.loads(out)
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    assert plan["flagged"] is False


def test_a_verdict_with_no_decisions_at_all() -> None:
    for label, text in (
        ("absent", "{}\n"),
        ("null", '{"decisions":null}\n'),
        ("empty", '{"decisions":[]}\n'),
    ):
        fixtures = dict(BASE_FIXTURES)
        fixtures["verdict.json"] = text
        code, out, err, _, _ = _sides("plan-nodecisions-%s" % label, PLAN_ARGV, fixtures=fixtures)
        assert code == 0, label
        assert json.loads(out) == {"replies": [], "skipped": [], "flagged": False}, label
        assert b"review-reply plan: 0 reply/resolve pair(s) planned" in err


def test_a_verdict_jq_cannot_read() -> None:
    """jq's own exit code through `set -e`, not a refusal of this script's."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["verdict.json"] = "not json\n"
    code, out, err, _, _ = _sides("plan-badjson", PLAN_ARGV, fixtures=fixtures)
    assert code == 5, code
    assert out == b""
    assert b"parse error" in err
    # And a THREADS file jq cannot read fails earlier, at `known`.
    fixtures = dict(BASE_FIXTURES)
    fixtures["threads.json"] = "{oops\n"
    code, out, err, _, _ = _sides("plan-badthreads", PLAN_ARGV, fixtures=fixtures)
    assert code == 5
    assert out == b""


def test_out_writes_the_plan_to_a_file_instead_of_stdout() -> None:
    code, out, err, _, written = _sides(
        "plan-out", [*PLAN_ARGV, "--out", "plan.json"], fixtures=BASE_FIXTURES
    )
    assert code == 0
    assert out == b"", "with --out, stdout carries nothing"
    assert written is not None
    assert json.loads(written)["replies"][0]["thread_id"] == "T_acme1"
    assert written.endswith(b"}\n"), "one line, newline-terminated"
    assert b"1 reply/resolve pair(s) planned" in err


# --------------------------------------------------------------------------- apply: the writes ---------------------------------------------------------------------------

PLAN_FILE = (
    json.dumps(
        {
            "replies": [
                {"thread_id": "T_acme1", "body": "thanks, fixed", "repo": "acme/console"},
                {"thread_id": "T_acme2", "body": "answered", "repo": "rediacc/renet"},
            ],
            "skipped": [],
            "flagged": False,
        }
    )
    + "\n"
)

APPLY_ARGV = ["apply", "--plan", "plan-in.json"]
APPLY_FIXTURES = {"plan-in.json": PLAN_FILE}
PUSH_ON = {"AUTOPILOT_ALLOW_PUSH": "true"}


def test_apply_usage_and_the_missing_plan_file() -> None:
    code, _, err, calls, _ = _sides("apply-usage", ["apply"], fixtures=APPLY_FIXTURES)
    assert code == 2
    assert b"usage: review-reply.sh apply --plan <file>" in err
    assert calls == []
    code, _, err, calls, _ = _sides(
        "apply-nofile", ["apply", "--plan", "nope.json"], fixtures=APPLY_FIXTURES
    )
    assert code == 1
    assert b"Required file 'nope.json' does not exist" in err
    assert calls == []


def test_the_write_gate_is_closed_by_default() -> None:
    """FAIL CLOSED, and the assertion that matters is `calls == []`: printing
    the refusal is not the same claim as not having written."""
    code, _, err, calls, _ = _sides("apply-closed", APPLY_ARGV, fixtures=APPLY_FIXTURES)
    assert code == 1
    assert (
        b"stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing to reply or "
        b"resolve (fail closed)" in err
    )
    assert calls == [], "the write gate let a gh call through: %r" % calls
    for value in ("", "1", "TRUE", "yes", "true "):
        code, _, _, calls, _ = _sides(
            "apply-closed-%r" % value,
            APPLY_ARGV,
            fixtures=APPLY_FIXTURES,
            env={"AUTOPILOT_ALLOW_PUSH": value},
        )
        assert (code, calls) == (1, []), value


def test_the_file_check_comes_before_the_write_gate() -> None:
    """ORDER: a typo'd `--plan` with the stage OFF is still the FILE error, so a mistyped path cannot be mistaken for a closed stage."""
    code, _, err, _, _ = _sides(
        "apply-order", ["apply", "--plan", "nope.json"], fixtures=APPLY_FIXTURES
    )
    assert code == 1
    assert b"Required file 'nope.json' does not exist" in err
    assert b"stage-flag-disabled" not in err


def test_nothing_planned_touches_nothing() -> None:
    for label, text in (
        ("empty", '{"replies":[],"skipped":[],"flagged":false}\n'),
        ("absent", "{}\n"),
        ("null", '{"replies":null}\n'),
    ):
        code, _, err, calls, _ = _sides(
            "apply-empty-%s" % label,
            APPLY_ARGV,
            fixtures={"plan-in.json": text},
            env=PUSH_ON,
        )
        assert code == 0, label
        assert b"review-reply apply: nothing planned; no thread touched" in err
        assert calls == [], label


def test_apply_replies_then_resolves_each_thread_in_order() -> None:
    """TWO mutations per entry, reply FIRST. Resolving first would leave a resolved thread with no answer in it if the reply failed, which is exactly the state `check-resolved-threads.sh` cannot tell from a human having dealt
    with it."""
    code, _out, err, calls, _ = _sides(
        "apply-two", APPLY_ARGV, fixtures=APPLY_FIXTURES, env=PUSH_ON
    )
    assert code == 0
    assert len(calls) == 4, calls
    for index, (tid, body) in enumerate((("T_acme1", "thanks, fixed"), ("T_acme2", "answered"))):
        reply, resolve = calls[index * 2], calls[index * 2 + 1]
        assert reply[:2] == ["api", "graphql"]
        assert "addPullRequestReviewThreadReply" in reply[3], reply[3]
        assert reply[4:] == ["-f", "threadId=%s" % tid, "-f", "body=%s" % body], reply
        assert "resolveReviewThread" in resolve[3], resolve[3]
        assert resolve[4:] == ["-f", "threadId=%s" % tid], resolve
    assert b"replied and resolved thread T_acme1 in acme/console" in err
    assert b"replied and resolved thread T_acme2 in rediacc/renet" in err
    assert b"review-reply apply: 2 thread(s) answered and resolved" in err


def test_model_text_travels_as_an_argv_value_not_as_shell() -> None:
    """`-f k=v` puts the bytes in ONE argv slot with no re-parse. The recorded
    argv is read back and compared literally, so a body that looks like a command substitution arrives as text."""
    nasty = '$(rm -rf /) `id` ; echo pwned | tee /tmp/x "quoted" \\backslash\n newline'
    plan = json.dumps(
        {"replies": [{"thread_id": "T_acme1", "body": nasty, "repo": "acme/console"}]}
    )
    code, _, _err, calls, _ = _sides(
        "apply-nasty", APPLY_ARGV, fixtures={"plan-in.json": plan + "\n"}, env=PUSH_ON
    )
    assert code == 0
    # argv is ["api","graphql","-f","query=...","-f","threadId=...","-f","body=..."],
    # so the body is slot 7 and it is ONE slot, whatever is in it.
    assert calls[0][7] == "body=%s" % nasty, calls[0][7]
    assert len(calls) == 2


def test_the_id_shape_is_rechecked_at_the_write() -> None:
    """`apply` is a SEPARATE INVOCATION whose input is a file on disk. `plan` having been careful is not a property of the bytes `apply` reads."""
    for bad in ("T_acme1 T_acme2", "../../x", "T_acme1;id", "T" + "a" * 128, ""):
        plan = json.dumps({"replies": [{"thread_id": bad, "body": "x", "repo": "acme/console"}]})
        code, _, err, calls, _ = _sides(
            "apply-badid-%r" % bad,
            APPLY_ARGV,
            fixtures={"plan-in.json": plan + "\n"},
            env=PUSH_ON,
        )
        assert code == 1, bad
        assert b"does not match the id shape; refusing" in err, bad
        assert calls == [], "a refused id must not reach gh: %r" % calls
    # And a REFUSED id in position 2 stops the run AFTER position 1 was written, which is the non-transactional shape named in the port's docstring.
    plan = json.dumps(
        {
            "replies": [
                {"thread_id": "T_acme1", "body": "a", "repo": "acme/console"},
                {"thread_id": "bad id", "body": "b", "repo": "acme/console"},
            ]
        }
    )
    code, _, err, calls, _ = _sides(
        "apply-badid-second", APPLY_ARGV, fixtures={"plan-in.json": plan + "\n"}, env=PUSH_ON
    )
    assert code == 1
    assert len(calls) == 2, "thread 1 was replied AND resolved before the refusal: %r" % calls


def test_a_mutation_failure_stops_the_run_mid_plan() -> None:
    """NOT TRANSACTIONAL, and pinned as a finding rather than repaired.

    The reply on entry 2 fails; entry 1 is already replied-and-resolved and entry 3 is never touched, with no record of where it stopped beyond the per-thread log lines. Rerunning would re-reply to entry 1."""
    plan = json.dumps(
        {
            "replies": [
                {"thread_id": "T_acme%d" % i, "body": "b%d" % i, "repo": "acme/console"}
                for i in (1, 2, 3)
            ]
        }
    )
    ok = {"rc": 0, "out": '{"data":{}}'}
    script = [ok, ok] + [{"rc": 1, "err": "HTTP 403\n"}] * 3
    code, _, err, calls, _ = _sides(
        "apply-midfail",
        APPLY_ARGV,
        fixtures={"plan-in.json": plan + "\n"},
        script=script,
        env=PUSH_ON,
    )
    assert code == 1
    assert len(calls) == 5, "two for entry 1, three attempts for entry 2's reply: %r" % calls
    assert b"replied and resolved thread T_acme1 in acme/console" in err
    assert b"replied and resolved thread T_acme2" not in err
    assert b"T_acme3" not in err, "entry 3 was never reached"
    assert b"review-reply apply: 3 thread(s) answered and resolved" not in err
    assert b"    HTTP 403\n" in err, "gh's stderr, indented four spaces"


def test_a_resolve_failure_leaves_the_reply_posted() -> None:
    """The other half of the same finding: the reply succeeded and the thread is NOT resolved, so the round looks answered and the gate stays red."""
    plan = json.dumps({"replies": [{"thread_id": "T_acme1", "body": "a", "repo": "acme/console"}]})
    ok = {"rc": 0, "out": '{"data":{}}'}
    code, _, err, calls, _ = _sides(
        "apply-resolvefail",
        APPLY_ARGV,
        fixtures={"plan-in.json": plan + "\n"},
        script=[ok] + [{"rc": 1, "err": "HTTP 422\n"}] * 3,
        env=PUSH_ON,
    )
    assert code == 1
    assert len(calls) == 4, calls
    assert b"resolve thread T_acme1: gh failed after 3 attempts (last exit 1)." in err
    assert b"replied and resolved thread T_acme1" not in err


def test_a_mutation_that_exits_zero_with_an_unusable_body_is_retried() -> None:
    """`gh_json` is `_gh_probe true`: the body must PARSE and must not be `null` or `false`. A GraphQL endpoint answering `null` with exit 0 is exactly the swallowed failure `_gh_probe` was written for."""
    plan = json.dumps({"replies": [{"thread_id": "T_acme1", "body": "a", "repo": "acme/console"}]})
    code, _, err, calls, _ = _sides(
        "apply-nullbody",
        APPLY_ARGV,
        fixtures={"plan-in.json": plan + "\n"},
        script=[{"rc": 0, "out": "null"}] * 3,
        env=PUSH_ON,
    )
    assert code == 1
    assert len(calls) == 3
    assert b"gh failed after 3 attempts (last exit 0)." in err


def test_a_plan_jq_cannot_read() -> None:
    code, _, _err, calls, _ = _sides(
        "apply-badjson",
        APPLY_ARGV,
        fixtures={"plan-in.json": "{oops\n"},
        env=PUSH_ON,
    )
    assert code == 5, code
    assert calls == []


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_matches_id_shape_both_directions() -> None:
    assert rr.matches_id_shape("T_kwDOAbc-123_=") is True
    assert rr.matches_id_shape("a") is True
    assert rr.matches_id_shape("T" + "a" * 127) is True, "128 is the bound, inclusive"
    assert rr.matches_id_shape("T" + "a" * 128) is False
    assert rr.matches_id_shape("") is False
    assert rr.matches_id_shape("has space") is False
    assert rr.matches_id_shape("../etc/passwd") is False
    assert rr.matches_id_shape("T_abc;id") is False
    assert rr.matches_id_shape("T_abc\n") is False, "bash's $ is end-of-STRING, not end-of-line"
    assert rr.matches_id_shape("T_abc\nbad") is False


def test_plan_max_body_both_directions() -> None:
    assert rr.plan_max_body("2000") is True
    assert rr.plan_max_body("0") is True
    assert rr.plan_max_body("999999") is True
    assert rr.plan_max_body("1000000") is False, "seven digits is out of shape"
    assert rr.plan_max_body("") is False
    assert rr.plan_max_body("-1") is False
    assert rr.plan_max_body("2e3") is False


def test_json_usable_is_jq_dash_e_and_not_json_loads() -> None:
    assert rr._json_usable(b'{"data":{}}') is True
    assert rr._json_usable(b"null") is False
    assert rr._json_usable(b"false") is False
    assert rr._json_usable(b"0") is True, "jq -e only rejects null and false"
    assert rr._json_usable(b"") is False


def test_the_plan_program_keeps_the_twins_reasoning() -> None:
    """The jq program is the twin's, so the comment inside it is too: it is the sentence that says an ordinary decisions entry is not an error."""
    assert "an ordinary decisions entry is not a reply and is" in rr.PLAN_PROGRAM
    assert "not an error either." in rr.PLAN_PROGRAM
    assert 'capture("^thread (?<id>[^:]+): (?<body>.*)$"; "s")' in rr.PLAN_PROGRAM
    assert ".body[0:$max]" in rr.PLAN_PROGRAM
