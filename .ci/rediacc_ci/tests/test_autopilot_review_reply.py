"""`rediacc_ci.autopilot.review_reply`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/review-reply.sh` and the port over the same fixtures and compared exit code, both streams, the whole `gh` call log and the bytes of the file `--out` writes. The K=5 ledger `.ci/shadow/w7p6-review-reply.observations.jsonl` recorded that comparison over five distinct trees.

Every case now compares against `goldens/review-reply/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE FAKE `gh` IS A SAFETY CONTROL, NOT A CONVENIENCE, and this subject is the one where that is literal: `apply`'s success path posts a comment into a review thread and marks that thread RESOLVED. GitHub undoes neither. The thread id comes out of a model-authored verdict, and a global GraphQL node id names a thread on any pull request in any repository the token can reach.

Four things stop a case from reaching the real binary, and the first is asserted rather than assumed: the stub directory is FIRST on PATH, and `test_the_fake_gh_is_the_gh` resolves `gh` through that PATH and fails if anything else wins; every fixture id is `T_acme...`, which names nothing; `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp tree, so a leaked
real `gh` fails auth rather than mutating; and the fake RECORDS every argv, so a case that somehow produced no call log fails rather than passing quietly.

THE RECORDED SHAPE THEREFORE CARRIES TWO SECTIONS BEYOND THE STREAMS. `--- calls ---` is the fake's argv log, and for `apply` it is THE artifact: everything this subcommand does to the world is two GraphQL mutations per entry, so which mutation, which thread id and the exact body bytes are the whole comparison, and a port that replied with the right text to the wrong thread would
print an identical summary line. `--- plan-file ---` is what `--out` wrote, because a plan that lands on disk is compared nowhere else.

WHAT IS MASKED: NOTHING. The differential compared raw bytes with no normalizer, and no absolute path reaches any recorded section. Every fixture path is relative and every diagnostic names it as the caller spelled it; `HOME` and `GH_CONFIG_DIR` are absolute and neither is ever printed. A golden that masked a value the differential compared would be weaker than the comparison it
replaced.

TWO DEFECTS ARE PINNED HERE RATHER THAN REPAIRED, and the recordings are what pin them: a multi-line disposition is dropped in SILENCE (jq's `s` flag is anchor mode, not dotall), and the bare-array `--threads` spelling the twin's own comment promises exits 5 with a jq diagnostic. Both read off the recording, and both go red when somebody repairs the port without recording a new
twin.
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
from rediacc_ci.autopilot import review_reply as rr
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SLUG = "review-reply"

TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "review-reply.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "review_reply.py"
BASH = shutil.which("bash") or "/bin/bash"

CALLS_MARKER = "--- calls ---\n"
PLAN_MARKER = "--- plan-file ---\n"

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

LONG_OK = "T" + "a" * 127
LONG_NO = "T" + "a" * 128

NASTY_BODY = '$(rm -rf /) `id` ; echo pwned | tee /tmp/x "quoted" \\backslash\n newline'

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
GH_OK = {"rc": 0, "out": '{"data":{}}'}


def one_reply(tid: str = "T_acme1", body: str = "a", repo: str = "acme/console") -> dict[str, str]:
    """A `--plan` file holding exactly one entry, which is the shape every write-path case starts from."""
    plan = {"replies": [{"thread_id": tid, "body": body, "repo": repo}]}
    return {"plan-in.json": json.dumps(plan) + "\n"}


def three_replies() -> dict[str, str]:
    plan = {
        "replies": [
            {"thread_id": "T_acme%d" % i, "body": "b%d" % i, "repo": "acme/console"}
            for i in (1, 2, 3)
        ]
    }
    return {"plan-in.json": json.dumps(plan) + "\n"}


def fixtures_with(**overrides: str) -> dict[str, str]:
    merged = dict(BASE_FIXTURES)
    merged.update(overrides)
    return merged


# name -> how the run is wired. `argv` is the command line, `fixtures` maps a filename in the scratch directory to its contents, `script` answers the fake `gh` in call order, and `env` adds to the base environment.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    # ------------------------------------------------- dispatch and usage
    "unknown-subcommand-frobnicate": {"argv": ["frobnicate"]},
    "unknown-subcommand-empty": {"argv": []},
    "unknown-subcommand-a-flag": {"argv": ["--plan", "plan.json"]},
    "unknown-subcommand-capitalised-plan": {"argv": ["Plan"]},
    "plan-with-no-flags": {"argv": ["plan"]},
    "plan-with-only-a-verdict": {"argv": ["plan", "--verdict", "verdict.json"]},
    "plan-with-only-threads": {"argv": ["plan", "--threads", "threads.json"]},
    "plan-with-a-missing-verdict-file": {
        "argv": ["plan", "--verdict", "nope.json", "--threads", "threads.json"]
    },
    "plan-with-a-missing-threads-file": {
        "argv": ["plan", "--verdict", "verdict.json", "--threads", "gone.json"]
    },
    "max-body-that-is-not-a-number": {"argv": [*PLAN_ARGV, "--max-body", "abc"]},
    "max-body-that-is-negative": {"argv": [*PLAN_ARGV, "--max-body", "-1"]},
    "max-body-of-seven-digits": {"argv": [*PLAN_ARGV, "--max-body", "1234567"]},
    "max-body-with-a-decimal-point": {"argv": [*PLAN_ARGV, "--max-body", "2000.0"]},
    "max-body-with-a-space": {"argv": [*PLAN_ARGV, "--max-body", "2 0"]},
    "max-body-is-checked-after-the-files": {
        "argv": ["plan", "--verdict", "nope.json", "--threads", "threads.json", "--max-body", "abc"]
    },
    # ------------------------------------------------- plan, the disposition parser
    "a-clean-plan": {"argv": PLAN_ARGV},
    "ordinary-decision-entries-are-not-thread-traffic": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(
            **{
                "verdict.json": verdict(
                    "ruled out bumping the pin, see the ledger",
                    "thread T_acme1: thanks, fixed",
                    "threadlike but not: no colon-space marker",
                    "thread-with-no-space: also not it",
                )
            }
        ),
    },
    "the-two-skip-reasons": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(
            **{
                "verdict.json": verdict(
                    "thread T_acme1: kept",
                    "thread has spaces: malformed",
                    "thread ../../etc/passwd: malformed",
                    "thread T_someoneElsesPR: well-shaped and unknown",
                )
            }
        ),
    },
    "the-id-length-boundary": {
        "argv": PLAN_ARGV,
        "fixtures": {
            "verdict.json": verdict("thread %s: ok" % LONG_OK, "thread %s: no" % LONG_NO),
            "threads.json": threads(entry(LONG_OK), entry(LONG_NO)),
        },
    },
    "the-body-cap-at-ten": {
        "argv": [*PLAN_ARGV, "--max-body", "10"],
        "fixtures": fixtures_with(**{"verdict.json": verdict("thread T_acme1: %s" % ("x" * 50))}),
    },
    "the-default-body-cap": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": verdict("thread T_acme1: %s" % ("x" * 50))}),
    },
    "the-body-cap-counts-codepoints": {
        "argv": [*PLAN_ARGV, "--max-body", "10"],
        "fixtures": fixtures_with(
            **{"verdict.json": verdict("thread T_acme1: %s" % ("\U0001f600" * 20))}
        ),
    },
    "a-multi-line-disposition": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(
            **{"verdict.json": verdict("thread T_acme1: first line\nsecond line\n\nthird")}
        ),
    },
    "a-multi-line-disposition-control": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": verdict("thread T_acme1: first line")}),
    },
    "threads-as-an-object": {"argv": PLAN_ARGV},
    "threads-as-an-empty-object": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"threads.json": '{"threads":[]}\n'}),
    },
    "threads-as-a-bare-array": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"threads.json": threads(entry("T_acme1"), wrapped=False)}),
    },
    "threads-as-an-empty-array": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"threads.json": "[]\n"}),
    },
    "the-repo-tag-is-carried-into-the-plan": {
        "argv": PLAN_ARGV,
        "fixtures": {
            "verdict.json": verdict("thread T_acme1: a", "thread T_acme2: b"),
            "threads.json": threads(entry("T_acme1", "rediacc/renet"), entry("T_acme2", repo=None)),
        },
    },
    "a-non-string-decision-entry": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(
            **{
                "verdict.json": verdict(
                    42, {"thread": "T_acme1"}, None, "thread T_acme1: thanks, fixed"
                )
            }
        ),
    },
    "a-verdict-with-no-decisions-key": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": "{}\n"}),
    },
    "a-verdict-with-a-null-decisions-key": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": '{"decisions":null}\n'}),
    },
    "a-verdict-with-an-empty-decisions-array": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": '{"decisions":[]}\n'}),
    },
    "a-verdict-jq-cannot-read": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"verdict.json": "not json\n"}),
    },
    "a-threads-file-jq-cannot-read": {
        "argv": PLAN_ARGV,
        "fixtures": fixtures_with(**{"threads.json": "{oops\n"}),
    },
    "out-writes-the-plan-to-a-file": {"argv": [*PLAN_ARGV, "--out", "plan.json"]},
    # ------------------------------------------------- apply, the writes
    "apply-with-no-plan-flag": {"argv": ["apply"], "fixtures": APPLY_FIXTURES},
    "apply-with-a-missing-plan-file": {
        "argv": ["apply", "--plan", "nope.json"],
        "fixtures": APPLY_FIXTURES,
    },
    "the-write-gate-is-closed-by-default": {"argv": APPLY_ARGV, "fixtures": APPLY_FIXTURES},
    "the-write-gate-with-an-empty-flag": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "the-write-gate-with-a-one": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": {"AUTOPILOT_ALLOW_PUSH": "1"},
    },
    "the-write-gate-with-an-upper-case-true": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": {"AUTOPILOT_ALLOW_PUSH": "TRUE"},
    },
    "the-write-gate-with-yes": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": {"AUTOPILOT_ALLOW_PUSH": "yes"},
    },
    "the-write-gate-with-a-trailing-space": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": {"AUTOPILOT_ALLOW_PUSH": "true "},
    },
    "the-file-check-comes-before-the-write-gate": {
        "argv": ["apply", "--plan", "nope.json"],
        "fixtures": APPLY_FIXTURES,
    },
    "nothing-planned-with-an-empty-replies-array": {
        "argv": APPLY_ARGV,
        "fixtures": {"plan-in.json": '{"replies":[],"skipped":[],"flagged":false}\n'},
        "env": PUSH_ON,
    },
    "nothing-planned-with-no-replies-key": {
        "argv": APPLY_ARGV,
        "fixtures": {"plan-in.json": "{}\n"},
        "env": PUSH_ON,
    },
    "nothing-planned-with-a-null-replies-key": {
        "argv": APPLY_ARGV,
        "fixtures": {"plan-in.json": '{"replies":null}\n'},
        "env": PUSH_ON,
    },
    "apply-replies-then-resolves-in-order": {
        "argv": APPLY_ARGV,
        "fixtures": APPLY_FIXTURES,
        "env": PUSH_ON,
    },
    "model-text-travels-as-an-argv-value": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply(body=NASTY_BODY),
        "env": PUSH_ON,
    },
    "apply-refuses-an-id-with-a-space": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply("T_acme1 T_acme2", "x"),
        "env": PUSH_ON,
    },
    "apply-refuses-a-path-shaped-id": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply("../../x", "x"),
        "env": PUSH_ON,
    },
    "apply-refuses-a-shell-shaped-id": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply("T_acme1;id", "x"),
        "env": PUSH_ON,
    },
    "apply-refuses-an-over-long-id": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply(LONG_NO, "x"),
        "env": PUSH_ON,
    },
    "apply-refuses-an-empty-id": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply("", "x"),
        "env": PUSH_ON,
    },
    "apply-refuses-the-second-id-after-writing-the-first": {
        "argv": APPLY_ARGV,
        "fixtures": {
            "plan-in.json": json.dumps(
                {
                    "replies": [
                        {"thread_id": "T_acme1", "body": "a", "repo": "acme/console"},
                        {"thread_id": "bad id", "body": "b", "repo": "acme/console"},
                    ]
                }
            )
            + "\n"
        },
        "env": PUSH_ON,
    },
    "a-mutation-failure-stops-the-run-mid-plan": {
        "argv": APPLY_ARGV,
        "fixtures": three_replies(),
        "script": [GH_OK, GH_OK] + [{"rc": 1, "err": "HTTP 403\n"}] * 3,
        "env": PUSH_ON,
    },
    "a-resolve-failure-leaves-the-reply-posted": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply(),
        "script": [GH_OK] + [{"rc": 1, "err": "HTTP 422\n"}] * 3,
        "env": PUSH_ON,
    },
    "a-mutation-answering-null-with-exit-zero-is-retried": {
        "argv": APPLY_ARGV,
        "fixtures": one_reply(),
        "script": [{"rc": 0, "out": "null"}] * 3,
        "env": PUSH_ON,
    },
    "a-plan-jq-cannot-read": {
        "argv": APPLY_ARGV,
        "fixtures": {"plan-in.json": "{oops\n"},
        "env": PUSH_ON,
    },
}

CASES = tuple(CASE_KW)


def stub_bin(base: pathlib.Path) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def run(
    tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT
) -> tuple[int, str, str, list[list[str]], str | None]:
    """One subject, once, over this case's own scratch directory. Returns the recorded shape's five parts.

    THE STREAMS ARE DECODED AS UTF-8 and a case that ever printed a byte outside it would fail the recording rather than be silently mangled. One case plans an astral emoji on purpose, so the encoding is exercised rather than assumed.
    """
    kw = CASE_KW[name]
    base = tmp_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    for rel, text in (kw.get("fixtures") or BASE_FIXTURES).items():
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
        "FAKE_GH_SCRIPT": json.dumps(kw.get("script") or []),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(kw.get("env") or {})
    runner = BASH if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [str(runner), str(subject), *kw["argv"]],
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
        proc.stdout.decode("utf-8"),
        proc.stderr.decode("utf-8"),
        calls,
        written.read_text(encoding="utf-8") if written.exists() else None,
    )


def render(code: int, stdout: str, stderr: str, calls: list[list[str]], plan: str | None) -> str:
    return "%s%s%s\n%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        json.dumps(calls, indent=2),
        PLAN_MARKER,
        json.dumps(plan, indent=2),
    )


def recorded(name: str) -> tuple[int, str, str, list[list[str]], str | None]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, plan = rest.split(PLAN_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        json.loads(calls),
        json.loads(plan),
    )


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[list[str]], str | None]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the gh calls diverged: %r vs %r" % (name, want[3], got[3])
    assert got[4] == want[4], "%s: the written plan diverged: %r vs %r" % (name, want[4], got[4])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Controls on the harness itself ---------------------------------------------------------------------------


def test_the_fake_gh_is_the_gh(tmp_path: pathlib.Path) -> None:
    """The whole "nothing was mutated" claim rests on this one resolution."""
    found = shutil.which("gh", path=stub_bin(tmp_path))
    assert found == str(tmp_path / "bin" / "gh"), "the fake gh is not first on PATH: %r" % found


def test_the_fake_gh_records_every_call(tmp_path: pathlib.Path) -> None:
    """CONTROL for every `--- calls ---` section below: a fake that logged nothing would make each of them an empty list that compares equal for the wrong reason."""
    path = stub_bin(tmp_path)
    log = tmp_path / "gh-calls.log"
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
    """Byte for byte, read off the RECORDED ARGV rather than off the twin's source, which is gone.

    The two mutations travelled as request arguments, so the recording of `apply-replies-then-resolves-in-order` carries them verbatim; `check-resolved-threads.sh` advertises the same two to humans, and the automated and manual paths must not drift.
    """
    calls = recorded("apply-replies-then-resolves-in-order")[3]
    assert calls[0][3] == "query=%s" % rr.REPLY_MUTATION
    assert calls[1][3] == "query=%s" % rr.RESOLVE_MUTATION


# --------------------------------------------------------------------------- Dispatch and usage ---------------------------------------------------------------------------


def test_unknown_subcommands_including_the_empty_one() -> None:
    for name, shown in (
        ("unknown-subcommand-frobnicate", "unknown subcommand 'frobnicate' (plan|apply)"),
        ("unknown-subcommand-empty", "unknown subcommand '' (plan|apply)"),
        ("unknown-subcommand-a-flag", "unknown subcommand '--plan' (plan|apply)"),
        ("unknown-subcommand-capitalised-plan", "unknown subcommand 'Plan' (plan|apply)"),
    ):
        code, stdout, stderr, calls, _ = recorded(name)
        assert code == 2, name
        assert stdout == "", name
        assert shown in stderr, (name, stderr)
        assert calls == [], name


def test_plan_usage_and_its_two_required_flags() -> None:
    """Both flags are required, and neither alone is enough."""
    for name in ("plan-with-no-flags", "plan-with-only-a-verdict", "plan-with-only-threads"):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 2, name
        assert "usage: review-reply.sh plan --verdict <file> --threads <file>" in stderr, name
        assert calls == [], name


def test_plan_requires_both_files_to_exist() -> None:
    """`require_file`, in the twin's order: verdict first."""
    code, _, stderr, _, _ = recorded("plan-with-a-missing-verdict-file")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr
    code, _, stderr, _, _ = recorded("plan-with-a-missing-threads-file")
    assert code == 1
    assert "Required file 'gone.json' does not exist" in stderr


def test_max_body_must_be_a_number_and_is_checked_after_the_files() -> None:
    for name, value in (
        ("max-body-that-is-not-a-number", "abc"),
        ("max-body-that-is-negative", "-1"),
        ("max-body-of-seven-digits", "1234567"),
        ("max-body-with-a-decimal-point", "2000.0"),
        ("max-body-with-a-space", "2 0"),
    ):
        code, _, stderr, _, _ = recorded(name)
        assert code == 2, name
        assert "--max-body must be a number, got '%s'" % value in stderr, (name, stderr)
    # ORDER: a bad --max-body with a missing verdict is the FILE error, because require_file runs first.
    code, _, stderr, _, _ = recorded("max-body-is-checked-after-the-files")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr


# --------------------------------------------------------------------------- plan: the disposition parser ---------------------------------------------------------------------------


def test_a_clean_plan() -> None:
    code, stdout, stderr, calls, _ = recorded("a-clean-plan")
    assert code == 0
    assert json.loads(stdout) == {
        "replies": [{"thread_id": "T_acme1", "body": "thanks, fixed", "repo": "acme/console"}],
        "skipped": [],
        "flagged": False,
    }, stdout
    assert "review-reply plan: 1 reply/resolve pair(s) planned" in stderr
    assert "disposition(s) name no thread" not in stderr
    assert calls == [], "plan is PURE: it must not call gh"


def test_an_ordinary_decision_entry_is_not_thread_traffic() -> None:
    """Dropped SILENTLY, not skipped loudly. A round whose decisions are mostly prose must not be `flagged`, or the warning stops meaning anything."""
    plan = json.loads(recorded("ordinary-decision-entries-are-not-thread-traffic")[1])
    assert plan["flagged"] is False, plan
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    assert plan["skipped"] == []


def test_the_two_skip_reasons_are_different_reasons() -> None:
    """A malformed id and a well-formed id nobody showed the model are separate findings. The second is the security one: the payload is the round's whole world, so an id outside it is not addressable."""
    _, stdout, stderr, _, _ = recorded("the-two-skip-reasons")
    plan = json.loads(stdout)
    assert plan["flagged"] is True
    assert plan["skipped"] == [
        {"entry": "has spaces", "reason": "malformed-id"},
        {"entry": "../../etc/passwd", "reason": "malformed-id"},
        {"entry": "T_someoneElsesPR", "reason": "unknown-thread"},
    ], plan["skipped"]
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    # LOUD, on stderr, one line per skip, and the count in the header.
    assert "review-reply plan: 3 disposition(s) name no thread in this round's payload" in stderr
    assert "    - malformed-id: has spaces\n" in stderr
    assert "    - unknown-thread: T_someoneElsesPR\n" in stderr


def test_an_id_of_exactly_the_boundary_lengths() -> None:
    """`{1,128}`: 128 characters pass, 129 do not, and the bound is what stops a mutation variable growing without limit."""
    plan = json.loads(recorded("the-id-length-boundary")[1])
    assert [r["thread_id"] for r in plan["replies"]] == [LONG_OK]
    assert plan["skipped"] == [{"entry": LONG_NO, "reason": "malformed-id"}]


def test_the_body_is_capped_and_the_cap_is_configurable() -> None:
    """`.body[0:$max]` is a jq string slice over CODEPOINTS, so ten astral characters are ten and not forty, and the default of 2000 leaves a fifty-character body untouched."""
    assert json.loads(recorded("the-body-cap-at-ten")[1])["replies"][0]["body"] == "x" * 10
    assert json.loads(recorded("the-default-body-cap")[1])["replies"][0]["body"] == "x" * 50
    astral = json.loads(recorded("the-body-cap-counts-codepoints")[1])
    assert astral["replies"][0]["body"] == "\U0001f600" * 10


def test_a_multi_line_disposition_is_silently_dropped() -> None:
    """DEFECT 1, LIVE, PRESERVED AND PINNED. See the port's docstring.

    jq's `s` flag is single-line ANCHOR mode (`^` to `\\A`, `$` to `\\Z`), not dotall: the dotall flag is `m`. So `.*` still stopped at the first newline, the anchored `$` could not match, and `capture` yielded NOTHING, which dropped the entry from the stream entirely: not replied, not skipped, `flagged` false, and no warning on stderr.

    THAT CONTRADICTS THE TWIN'S OWN HEADER ("Anything else lands in skipped[] with a reason and raises flagged -- never silently"). A model writing a two-line answer got exactly the silence that sentence promises cannot happen. Recorded as the twin BEHAVED rather than as it was documented, and this is what goes red when somebody repairs it.
    """
    code, stdout, stderr, _, _ = recorded("a-multi-line-disposition")
    assert code == 0
    assert json.loads(stdout) == {"replies": [], "skipped": [], "flagged": False}, stdout
    assert "review-reply plan: 0 reply/resolve pair(s) planned" in stderr
    assert "disposition(s) name no thread" not in stderr, "the silence is the defect"
    # CONTROL, so the case is not simply "this fixture never plans anything": the SAME disposition on ONE line plans a reply.
    control = json.loads(recorded("a-multi-line-disposition-control")[1])
    assert control["replies"][0]["body"] == "first line"


def test_the_threads_fixture_is_accepted_as_an_object() -> None:
    """`(.threads // .) // []`: the payload OBJECT is the spelling every caller uses, and an empty one names no thread, so every disposition becomes unknown."""
    assert json.loads(recorded("threads-as-an-object")[1])["replies"][0]["thread_id"] == "T_acme1"
    plan = json.loads(recorded("threads-as-an-empty-object")[1])
    assert plan["replies"] == []
    assert plan["skipped"] == [{"entry": "T_acme1", "reason": "unknown-thread"}]


def test_a_bare_array_threads_fixture_is_refused_by_jq() -> None:
    """DEFECT 2, LATENT, PRESERVED AND PINNED. See the port's docstring.

    `.threads` on an ARRAY is an ERROR in jq, not `null`, so `(.threads // .)` never fell through and the bare-array spelling the twin's comment promises exited 5 with a jq diagnostic and no plan. Latent because the only caller (`.github/workflows/autopilot.yml:817`) passes `review-payload.sh`'s object, so this is documentation of a capability that was never there.
    """
    for name in ("threads-as-a-bare-array", "threads-as-an-empty-array"):
        code, stdout, stderr, _, _ = recorded(name)
        assert code == 5, name
        assert stdout == "", name
        assert 'Cannot index array with string "threads"' in stderr, (name, stderr)


def test_the_repo_tag_is_carried_into_the_plan() -> None:
    """The plan is an audit record: "resolved a thread" is not a useful sentence without naming where. An untagged thread falls back to `console`."""
    plan = json.loads(recorded("the-repo-tag-is-carried-into-the-plan")[1])
    assert [(r["thread_id"], r["repo"]) for r in plan["replies"]] == [
        ("T_acme1", "rediacc/renet"),
        ("T_acme2", "console"),
    ]


def test_a_non_string_decision_entry_is_ignored() -> None:
    """`select(type == "string")`: a number or an object in `decisions[]` is not a disposition and must not crash the plan."""
    plan = json.loads(recorded("a-non-string-decision-entry")[1])
    assert [r["thread_id"] for r in plan["replies"]] == ["T_acme1"]
    assert plan["flagged"] is False


def test_a_verdict_with_no_decisions_at_all() -> None:
    for name in (
        "a-verdict-with-no-decisions-key",
        "a-verdict-with-a-null-decisions-key",
        "a-verdict-with-an-empty-decisions-array",
    ):
        code, stdout, stderr, _, _ = recorded(name)
        assert code == 0, name
        assert json.loads(stdout) == {"replies": [], "skipped": [], "flagged": False}, name
        assert "review-reply plan: 0 reply/resolve pair(s) planned" in stderr, name


def test_a_file_jq_cannot_read() -> None:
    """jq's own exit code through `set -e`, not a refusal of this script's, and a THREADS file jq cannot read fails earlier, at `known`."""
    code, stdout, stderr, _, _ = recorded("a-verdict-jq-cannot-read")
    assert code == 5, code
    assert stdout == ""
    assert "parse error" in stderr
    code, stdout, _, _, _ = recorded("a-threads-file-jq-cannot-read")
    assert code == 5
    assert stdout == ""


def test_out_writes_the_plan_to_a_file_instead_of_stdout() -> None:
    code, stdout, stderr, _, written = recorded("out-writes-the-plan-to-a-file")
    assert code == 0
    assert stdout == "", "with --out, stdout carries nothing"
    assert written is not None
    assert json.loads(written)["replies"][0]["thread_id"] == "T_acme1"
    assert written.endswith("}\n"), "one line, newline-terminated"
    assert "1 reply/resolve pair(s) planned" in stderr


# --------------------------------------------------------------------------- apply: the writes ---------------------------------------------------------------------------


def test_apply_usage_and_the_missing_plan_file() -> None:
    code, _, stderr, calls, _ = recorded("apply-with-no-plan-flag")
    assert code == 2
    assert "usage: review-reply.sh apply --plan <file>" in stderr
    assert calls == []
    code, _, stderr, calls, _ = recorded("apply-with-a-missing-plan-file")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr
    assert calls == []


def test_the_write_gate_is_closed_by_default() -> None:
    """FAIL CLOSED, and the assertion that matters is `calls == []`: printing the refusal is not the same claim as not having written. Five near-miss spellings of the flag are recorded beside the absent one, because only the literal `true` opens the gate."""
    code, _, stderr, calls, _ = recorded("the-write-gate-is-closed-by-default")
    assert code == 1
    assert (
        "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing to reply or "
        "resolve (fail closed)" in stderr
    )
    assert calls == [], "the write gate let a gh call through: %r" % calls
    for name in (
        "the-write-gate-with-an-empty-flag",
        "the-write-gate-with-a-one",
        "the-write-gate-with-an-upper-case-true",
        "the-write-gate-with-yes",
        "the-write-gate-with-a-trailing-space",
    ):
        code, _, _, calls, _ = recorded(name)
        assert (code, calls) == (1, []), name


def test_the_file_check_comes_before_the_write_gate() -> None:
    """ORDER: a typo'd `--plan` with the stage OFF is still the FILE error, so a mistyped path cannot be mistaken for a closed stage."""
    code, _, stderr, _, _ = recorded("the-file-check-comes-before-the-write-gate")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr
    assert "stage-flag-disabled" not in stderr


def test_nothing_planned_touches_nothing() -> None:
    for name in (
        "nothing-planned-with-an-empty-replies-array",
        "nothing-planned-with-no-replies-key",
        "nothing-planned-with-a-null-replies-key",
    ):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 0, name
        assert "review-reply apply: nothing planned; no thread touched" in stderr, name
        assert calls == [], name


def test_apply_replies_then_resolves_each_thread_in_order() -> None:
    """TWO mutations per entry, reply FIRST. Resolving first would leave a resolved thread with no answer in it if the reply failed, which is exactly the state `check-resolved-threads.sh` cannot tell from a human having dealt with it."""
    code, _, stderr, calls, _ = recorded("apply-replies-then-resolves-in-order")
    assert code == 0
    assert len(calls) == 4, calls
    for index, (tid, body) in enumerate((("T_acme1", "thanks, fixed"), ("T_acme2", "answered"))):
        reply, resolve = calls[index * 2], calls[index * 2 + 1]
        assert reply[:2] == ["api", "graphql"]
        assert "addPullRequestReviewThreadReply" in reply[3], reply[3]
        assert reply[4:] == ["-f", "threadId=%s" % tid, "-f", "body=%s" % body], reply
        assert "resolveReviewThread" in resolve[3], resolve[3]
        assert resolve[4:] == ["-f", "threadId=%s" % tid], resolve
    assert "replied and resolved thread T_acme1 in acme/console" in stderr
    assert "replied and resolved thread T_acme2 in rediacc/renet" in stderr
    assert "review-reply apply: 2 thread(s) answered and resolved" in stderr


def test_model_text_travels_as_an_argv_value_not_as_shell() -> None:
    """`-f k=v` puts the bytes in ONE argv slot with no re-parse. The recorded argv is read back and compared literally, so a body that looks like a command substitution arrived as text."""
    code, _, _, calls, _ = recorded("model-text-travels-as-an-argv-value")
    assert code == 0
    # argv is ["api","graphql","-f","query=...","-f","threadId=...","-f","body=..."], so the body is slot 7 and it is ONE slot, whatever is in it.
    assert calls[0][7] == "body=%s" % NASTY_BODY, calls[0][7]
    assert len(calls) == 2


def test_the_id_shape_is_rechecked_at_the_write() -> None:
    """`apply` is a SEPARATE INVOCATION whose input is a file on disk. `plan` having been careful is not a property of the bytes `apply` reads."""
    for name in (
        "apply-refuses-an-id-with-a-space",
        "apply-refuses-a-path-shaped-id",
        "apply-refuses-a-shell-shaped-id",
        "apply-refuses-an-over-long-id",
        "apply-refuses-an-empty-id",
    ):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 1, name
        assert "does not match the id shape; refusing" in stderr, name
        assert calls == [], "a refused id must not reach gh: %r" % calls
    # And a REFUSED id in position 2 stops the run AFTER position 1 was written, which is the non-transactional shape named in the port's docstring.
    code, _, _, calls, _ = recorded("apply-refuses-the-second-id-after-writing-the-first")
    assert code == 1
    assert len(calls) == 2, "thread 1 was replied AND resolved before the refusal: %r" % calls


def test_a_mutation_failure_stops_the_run_mid_plan() -> None:
    """NOT TRANSACTIONAL, and pinned as a finding rather than repaired.

    The reply on entry 2 failed; entry 1 was already replied-and-resolved and entry 3 was never touched, with no record of where it stopped beyond the per-thread log lines. Rerunning would re-reply to entry 1.
    """
    code, _, stderr, calls, _ = recorded("a-mutation-failure-stops-the-run-mid-plan")
    assert code == 1
    assert len(calls) == 5, "two for entry 1, three attempts for entry 2's reply: %r" % calls
    assert "replied and resolved thread T_acme1 in acme/console" in stderr
    assert "replied and resolved thread T_acme2" not in stderr
    assert "T_acme3" not in stderr, "entry 3 was never reached"
    assert "review-reply apply: 3 thread(s) answered and resolved" not in stderr
    assert "    HTTP 403\n" in stderr, "gh's stderr, indented four spaces"


def test_a_resolve_failure_leaves_the_reply_posted() -> None:
    """The other half of the same finding: the reply succeeded and the thread is NOT resolved, so the round looks answered and the gate stays red."""
    code, _, stderr, calls, _ = recorded("a-resolve-failure-leaves-the-reply-posted")
    assert code == 1
    assert len(calls) == 4, calls
    assert "resolve thread T_acme1: gh failed after 3 attempts (last exit 1)." in stderr
    assert "replied and resolved thread T_acme1" not in stderr


def test_a_mutation_that_exits_zero_with_an_unusable_body_is_retried() -> None:
    """`gh_json` is `_gh_probe true`: the body must PARSE and must not be `null` or `false`. A GraphQL endpoint answering `null` with exit 0 is exactly the swallowed failure `_gh_probe` was written for."""
    code, _, stderr, calls, _ = recorded("a-mutation-answering-null-with-exit-zero-is-retried")
    assert code == 1
    assert len(calls) == 3
    assert "gh failed after 3 attempts (last exit 0)." in stderr


def test_a_plan_jq_cannot_read() -> None:
    code, _, _, calls, _ = recorded("a-plan-jq-cannot-read")
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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_swap_of_the_two_mutations_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Send the model's reply under the RESOLVE mutation.

    The two log lines name the thread and the repository, never the mutation, so a run that resolved a thread without ever posting the answer into it prints exactly what a correct run prints: same exit, same stdout, same stderr, same number of calls. `--- calls ---` is the only section that sees it, and seeing it is the entire reason the argv is recorded rather than summarised.

    The mutation runs from a throwaway copy placed outside the fixture and resolving `rediacc_ci` through the same `PYTHONPATH`; the tracked port is never touched, and the real port is compared again afterwards so a mutant that failed for some unrelated reason cannot pass for a caught one.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '"query=%s" % REPLY_MUTATION,'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, '"query=%s" % RESOLVE_MUTATION,')

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "apply-replies-then-resolves-in-order"
    want = recorded(name)
    got = run(tmp_path / "planted", name, subject=mutant)
    assert "addPullRequestReviewThreadReply" in want[3][0][3], "the recorded corpus moved"
    assert "addPullRequestReviewThreadReply" not in got[3][0][3], (
        "the plant did not change the argv"
    )
    assert got[:3] == want[:3], "only the recorded argv may differ, and it is what catches this"
    assert len(got[3]) == len(want[3])

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
