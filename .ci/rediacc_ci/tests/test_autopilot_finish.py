"""`rediacc_ci.autopilot.finish`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/finish.sh` and the port over one stubbed PATH and compared four things per case: exit code, stdout, stderr and the `gh` CALL LOG.

The K=5 ledger `.ci/shadow/w7p6-finish.observations.jsonl` holds 11 rows of that comparison over distinct trees, recorded in a disposable scratch git repository outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout never is.

Every case now compares against `goldens/finish/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A DECISION TREE, SO EVERY BRANCH HAS ITS OWN GOLDEN. Three subcommands, an unknown-subcommand arm, a usage refusal per subcommand, a fail-closed write gate, two `gh` pipelines and jq's own exit codes leaking through `set -e`. The cases walk each of them, and the ones that pin the EXIT CODE rather than the message are the load-bearing half: 0 and 1 out of `check-done` are how the
babysit loop decides whether to stop, and 5 out of a broken pipeline is jq's, not this script's.

NOTHING HERE DIVERGES. Every case is compared byte for byte on all four channels, including the three refusals that carry text from `common.sh`, so this file has no shape-compared arm and no exemption to keep honest.

THE CALL LOG IS COMPARED, NOT JUST THE STREAMS, and it is carried in the recorded shape as its own `--- gh calls ---` section. This script's whole effect on the world is which requests it makes, and a port that flipped the right PR in the wrong repository, or reran every job instead of the failed ones, would print an identical summary. The control at the foot of this file plants
exactly that second mutation.

THE WRITE GATE IS RECORDED FROM BOTH SIDES, and the negative side is the one that matters: the closed-gate cases record an EMPTY call log, because "it printed the refusal" is not the same claim as "it did not write". Anything that is not exactly `true` is closed, and `1`, `TRUE` and `yes` each have their own recording.

A RECORDING FAKE `gh` ON A CURATED PATH is the seam, and `test_the_stub_path_has_no_real_gh` is the control for it rather than a comment claiming it. `jq` IS THE REAL `jq`, because the verdict program is the twin's own reasoning and a reimplementation would have to re-derive `//`'s falsy rule; the recorded stdout is therefore jq's compact spacing, its program key order and its
trailing newline.

ONE CASE COSTS NINE SECONDS. `_gh_probe` sleeps 3 then 6 between its three attempts, and it is the only way to prove the retry loop, the final `gh failed after 3 attempts` line and the exit code agree.

WHAT IS MASKED, and it is two paths. The case's own directory is its `HOME` and its working directory and is rebuilt under a different tempdir name every run, so it becomes `<work>`; the checkout root becomes `<repo>`, so that a bash diagnostic naming this worktree stays readable from any other. Nothing else is touched: every fixture path a message names is RELATIVE on purpose, so
the refusals and jq's parse errors are compared verbatim.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import finish as fin
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "finish.py"
SLUG = "finish"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

CALLS_MARKER = "--- gh calls ---\n"

# `tr` is here because `parse_args` shelled out to `to_upper` once per flag, and `sleep` because `_gh_probe`'s backoff is an external command: without it the twin died at 127 on every retry case while the port sailed through. `mktemp` and `rm` are `_gh_probe`'s scratch file for gh's stderr, and their absence showed up as a 127 from the twin on every gh path.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "sleep", "cat", "sed", "mktemp", "rm")

FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

if argv[:2] == ["pr", "ready"]:
    sys.stdout.write(os.environ.get("FAKE_READY_OUT", ""))
    sys.stderr.write(os.environ.get("FAKE_READY_ERR", ""))
    sys.exit(int(os.environ.get("FAKE_READY_RC", "0")))

if argv[0] == "api" and "/pulls/" in argv[1]:
    sys.stdout.write(os.environ.get("FAKE_HEAD", '{"sha":"deadbeef"}') + "\\n")
    sys.exit(int(os.environ.get("FAKE_HEAD_RC", "0")))

if argv[0] == "api" and "/actions/runs" in argv[1]:
    sys.stdout.write(os.environ.get("FAKE_RUN", '{"id":4242}') + "\\n")
    sys.exit(int(os.environ.get("FAKE_RUN_RC", "0")))

if argv[:2] == ["run", "rerun"]:
    sys.stdout.write(os.environ.get("FAKE_RERUN_OUT", ""))
    sys.exit(int(os.environ.get("FAKE_RERUN_RC", "0")))

sys.stderr.write("fake gh: unexpected call %r\\n" % (argv,))
sys.exit(9)
"""

DONE = {"ci_green": True, "draft": False, "reviewed": True, "unresolved_threads": 0}


def fixture(**fields: object) -> dict[str, bytes]:
    return {"pr.json": json.dumps(fields).encode("utf-8") + b"\n"}


def _without(field: str) -> dict[str, bytes]:
    shrunk = dict(DONE)
    del shrunk[field]
    return fixture(**shrunk)


def _broken(field: str, value: object) -> dict[str, bytes]:
    broken = dict(DONE)
    broken[field] = value
    return fixture(**broken)


OPEN_GATE = {"AUTOPILOT_ALLOW_PUSH": "true"}
FLIP = ["ready-flip", "--pr", "5", "--repo", "rediacc/console"]
RERUN = ["rerun-review", "--pr", "5", "--repo", "rediacc/console"]

# name -> argv, the files written into the case's own directory, and the environment the fake `gh` reads its behaviour from
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "check-done-when-everything-is-met": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": fixture(**DONE),
    },
    "check-done-with-nothing-met": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": fixture(),
    },
    "check-done-without-ci-green": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _broken("ci_green", False),
    },
    "check-done-on-a-draft": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _broken("draft", True),
    },
    "check-done-without-a-review": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _broken("reviewed", False),
    },
    "check-done-with-unresolved-threads": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _broken("unresolved_threads", 2),
    },
    "check-done-with-no-draft-field": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _without("draft"),
    },
    "check-done-with-no-threads-field": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": _without("unresolved_threads"),
    },
    "check-done-on-unreadable-json": {
        "argv": ["check-done", "--pr", "pr.json"],
        "files": {"pr.json": b"not json\n"},
    },
    "check-done-with-a-missing-fixture": {"argv": ["check-done", "--pr", "nope.json"]},
    "check-done-with-no-flag": {"argv": ["check-done"]},
    "check-done-with-an-empty-flag": {"argv": ["check-done", "--pr="]},
    "an-unknown-subcommand": {"argv": ["frobnicate"]},
    "no-arguments-at-all": {"argv": []},
    "a-flag-in-the-subcommand-slot": {
        "argv": ["--pr", "pr.json"],
        "files": fixture(**DONE),
    },
    "ready-flip-with-the-gate-closed": {"argv": FLIP},
    "rerun-review-with-the-gate-closed": {"argv": RERUN},
    "the-gate-with-an-empty-value": {"argv": FLIP, "env": {"AUTOPILOT_ALLOW_PUSH": ""}},
    "the-gate-with-one": {"argv": FLIP, "env": {"AUTOPILOT_ALLOW_PUSH": "1"}},
    "the-gate-with-uppercase-true": {"argv": FLIP, "env": {"AUTOPILOT_ALLOW_PUSH": "TRUE"}},
    "the-gate-with-yes": {"argv": FLIP, "env": {"AUTOPILOT_ALLOW_PUSH": "yes"}},
    "ready-flip-without-a-repo": {"argv": ["ready-flip", "--pr", "5"]},
    "ready-flip-without-a-pr": {"argv": ["ready-flip", "--repo", "r/c"]},
    "rerun-review-without-a-repo": {"argv": ["rerun-review", "--pr", "5"]},
    "rerun-review-without-a-pr": {"argv": ["rerun-review", "--repo", "r/c"]},
    "a-ready-flip": {
        "argv": FLIP,
        "env": {
            **OPEN_GATE,
            "FAKE_READY_OUT": "marked ready\n",
            "FAKE_READY_ERR": "gh: some progress chatter\n",
        },
    },
    "a-rerun-review": {"argv": RERUN, "env": OPEN_GATE},
    "a-rerun-with-a-null-run-id": {
        "argv": ["rerun-review", "--pr", "5", "--repo", "r/c"],
        "env": {**OPEN_GATE, "FAKE_RUN": '{"id":null}'},
    },
    "a-rerun-with-an-empty-run-id": {
        "argv": ["rerun-review", "--pr", "5", "--repo", "r/c"],
        "env": {**OPEN_GATE, "FAKE_RUN": '{"id":""}'},
    },
    "a-head-body-that-cannot-be-indexed": {
        "argv": ["rerun-review", "--pr", "5", "--repo", "r/c"],
        "env": {**OPEN_GATE, "FAKE_HEAD": "[]"},
    },
    "a-failing-flip-retried-three-times": {
        "argv": ["ready-flip", "--pr", "5", "--repo", "r/c"],
        "env": {
            **OPEN_GATE,
            "FAKE_READY_RC": "4",
            "FAKE_READY_ERR": "gh: HTTP 401 Bad credentials\n",
        },
    },
}

CASES = tuple(CASE_KW)


def stub_path(base: pathlib.Path, *, with_gh: bool = True) -> str:
    stub = base / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, over this case's own files and its own stub PATH."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    for rel, data in (kw.get("files") or {}).items():
        (base / rel).write_bytes(data)
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_path(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
    }
    env.update(kw.get("env") or {})
    # `sys.executable`, not "python3": the stub PATH has no interpreter on it.
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *kw["argv"]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )

    def mask(text: str) -> str:
        return text.replace(str(base), "<work>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(log.read_text(encoding="utf-8")),
    )


def render(code: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(code, stdout, stderr), CALLS_MARKER, calls)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(PORT, tmp_path / name, name)


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the gh CALL LOG")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_stub_path_has_no_real_gh(tmp_path: pathlib.Path) -> None:
    """CONTROL. Every write case's "no network" claim rests on this."""
    without = stub_path(tmp_path, with_gh=False)
    assert shutil.which("gh", path=without) is None, "gh leaked into the stub PATH"
    assert shutil.which("jq", path=without) is not None, "the stub PATH is not usable"


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_check_done_when_everything_is_met() -> None:
    code, stdout, stderr, calls = recorded("check-done-when-everything-is-met")
    assert code == 0
    assert stdout == '{"done":true,"missing":[]}\n', stdout
    assert stderr == ""
    assert calls == "", "check-done is PURE: it must not call gh"


def test_check_done_names_every_unmet_condition() -> None:
    """`missing` is the diagnosis, so its CONTENT and ORDER are the contract, and one condition at a time is what stops a port collapsing them into a single flag."""
    code, stdout, _, _ = recorded("check-done-with-nothing-met")
    assert code == 1
    assert (
        stdout
        == '{"done":false,"missing":["ci_green","not_draft","reviewed","threads_resolved"]}\n'
    ), stdout
    for name, missing in (
        ("check-done-without-ci-green", '["ci_green"]'),
        ("check-done-on-a-draft", '["not_draft"]'),
        ("check-done-without-a-review", '["reviewed"]'),
        ("check-done-with-unresolved-threads", '["threads_resolved"]'),
    ):
        code, stdout, _, _ = recorded(name)
        assert code == 1, name
        assert stdout == '{"done":false,"missing":%s}\n' % missing, (name, stdout)


def test_check_done_fails_closed_on_an_absent_draft_field() -> None:
    """The twin's own comment: NOT `.draft // true | not`. A PR whose fixture never mentions `draft` is NOT done, and a non-draft PR (`draft: false`) is not read as a draft. Both directions, because only one of them catches the `//` bug the comment describes."""
    code, stdout, _, _ = recorded("check-done-with-no-draft-field")
    assert (code, stdout) == (1, '{"done":false,"missing":["not_draft"]}\n'), stdout
    code, stdout, _, _ = recorded("check-done-when-everything-is-met")
    assert (code, stdout) == (0, '{"done":true,"missing":[]}\n'), stdout


def test_check_done_unresolved_threads_defaults_to_one() -> None:
    """`(.unresolved_threads // 1) == 0`: silence means UNRESOLVED, not zero."""
    code, stdout, _, _ = recorded("check-done-with-no-threads-field")
    assert (code, stdout) == (1, '{"done":false,"missing":["threads_resolved"]}\n'), stdout


def test_check_done_on_a_fixture_jq_cannot_read() -> None:
    """jq's exit code, not this script's: `set -e` ended the run at 5 and nothing was printed to stdout."""
    code, stdout, stderr, _ = recorded("check-done-on-unreadable-json")
    assert code == 5, code
    assert stdout == ""
    assert "jq: parse error: Invalid numeric literal" in stderr, stderr


def test_check_done_refusals() -> None:
    code, _, stderr, _ = recorded("check-done-with-a-missing-fixture")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr
    code, _, stderr, _ = recorded("check-done-with-no-flag")
    assert code == 2
    assert "usage: finish.sh check-done --pr <fixture.json>" in stderr
    assert recorded("check-done-with-an-empty-flag")[0] == 2


def test_unknown_subcommands() -> None:
    """Including the empty one, which is what NO arguments produces."""
    code, _, stderr, calls = recorded("an-unknown-subcommand")
    assert code == 2
    assert "unknown subcommand 'frobnicate' (check-done|ready-flip|rerun-review)" in stderr
    assert calls == ""
    code, _, stderr, _ = recorded("no-arguments-at-all")
    assert code == 2
    assert "unknown subcommand '' (check-done|ready-flip|rerun-review)" in stderr
    # A FLAG in the subcommand slot is a subcommand, not a flag: `parse_args` never saw `$1`.
    code, _, stderr, _ = recorded("a-flag-in-the-subcommand-slot")
    assert code == 2
    assert "unknown subcommand '--pr'" in stderr


def test_the_write_gate_is_closed_by_default() -> None:
    """FAIL CLOSED, and the assertion that matters is the EMPTY call log: the refusal message is not evidence that nothing was written. Anything that is not exactly `true` is closed, including `TRUE` and `1`."""
    for name in ("ready-flip-with-the-gate-closed", "rerun-review-with-the-gate-closed"):
        code, _, stderr, calls = recorded(name)
        assert code == 1, name
        assert "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'" in stderr
        assert calls == "", "the write gate let a gh call through: %r" % calls
    for name in (
        "the-gate-with-an-empty-value",
        "the-gate-with-one",
        "the-gate-with-uppercase-true",
        "the-gate-with-yes",
    ):
        code, _, _, calls = recorded(name)
        assert (code, calls) == (1, ""), name


def test_the_usage_refusal_comes_before_the_write_gate() -> None:
    """ORDER, not just outcome: a missing `--repo` is exit 2 even with the stage flag off, so a caller cannot mistake a typo for a closed stage."""
    for name in ("ready-flip-without-a-repo", "ready-flip-without-a-pr"):
        code, _, stderr, calls = recorded(name)
        assert code == 2, name
        assert "usage: finish.sh ready-flip --pr <number> --repo <owner/name>" in stderr
        assert calls == ""
    for name in ("rerun-review-without-a-repo", "rerun-review-without-a-pr"):
        code, _, stderr, _ = recorded(name)
        assert code == 2, name
        assert "usage: finish.sh rerun-review --pr <number> --repo <owner/name>" in stderr


def test_ready_flip_when_the_gate_is_open() -> None:
    code, stdout, stderr, calls = recorded("a-ready-flip")
    assert code == 0
    # `gh_retry`'s `printf '%s'`: gh's stdout with its trailing newline STRIPPED by the command substitution and none added back.
    assert stdout == "marked ready", stdout
    assert "PR #5 flipped ready for review" in stderr
    # gh's own stderr is CAPTURED by the probe and dropped on success.
    assert "some progress chatter" not in stderr, stderr
    assert lines(calls) == ["pr\tready\t5\t--repo\trediacc/console"], calls


def test_rerun_review_walks_head_then_run_then_rerun() -> None:
    code, stdout, stderr, calls = recorded("a-rerun-review")
    assert code == 0
    assert stdout == ""
    assert "review run 4242 rerun requested for PR #5" in stderr
    recorded_calls = lines(calls)
    assert len(recorded_calls) == 3, recorded_calls
    assert recorded_calls[0].startswith(
        "api\trepos/rediacc/console/pulls/5\t--jq\t{sha: .head.sha}"
    )
    # The head sha from call 1 is what call 2 queries with. A port that dropped it would still make three calls.
    assert "head_sha=deadbeef&event=pull_request" in recorded_calls[1], recorded_calls[1]
    assert recorded_calls[2] == "run\trerun\t4242\t--repo\trediacc/console\t--failed"


def test_rerun_review_when_no_review_run_exists() -> None:
    """`first` over an empty list is `null`, which jq prints as the STRING `null`. Both spellings of "nothing" are refused."""
    for name in ("a-rerun-with-a-null-run-id", "a-rerun-with-an-empty-run-id"):
        code, _, stderr, calls = recorded(name)
        assert code == 1, name
        assert "rerun-review: no review-pipeline run found for head deadbeef" in stderr
        assert len(lines(calls)) == 2, "it must not rerun anything: %r" % calls


def test_rerun_review_when_the_body_cannot_be_indexed() -> None:
    """jq's 5 through `pipefail`, not a refusal of this script's own."""
    code, _, stderr, calls = recorded("a-head-body-that-cannot-be-indexed")
    assert code == 5, code
    assert "Cannot index array with" in stderr, stderr
    assert len(lines(calls)) == 1, calls


def test_a_failing_flip_retries_three_times_and_replays_its_stderr() -> None:
    """The only case that proves the `_gh_probe` loop: three identical calls, two warnings, the final error carrying the last exit code, and gh's captured stderr replayed indented four spaces."""
    code, stdout, stderr, calls = recorded("a-failing-flip-retried-three-times")
    assert code == 1
    assert stdout == ""
    assert lines(calls) == ["pr\tready\t5\t--repo\tr/c"] * 3, calls
    assert "ready-flip: gh failed after 3 attempts (last exit 4)." in stderr
    assert stderr.endswith("    gh: HTTP 401 Bad credentials\n"), stderr
    assert "flipped ready" not in stderr


def test_pure_helpers_are_exercised_directly(tmp_path: pathlib.Path) -> None:
    """The helpers, without a subprocess, in BOTH directions."""
    assert fin.require_write_flag({"AUTOPILOT_ALLOW_PUSH": "true"}) is True
    assert fin.require_write_flag({"AUTOPILOT_ALLOW_PUSH": "TRUE"}) is False
    assert fin.require_write_flag({}) is False

    assert fin._json_usable(b'{"sha":"x"}') is True
    assert fin._json_usable(b"null") is False, "jq -e's rule, not json.loads'"
    assert fin._json_usable(b"") is False

    fixture_path = tmp_path / "pr.json"
    fixture_path.write_text(json.dumps(DONE), encoding="utf-8")
    assert fin.check_done(str(fixture_path)) == (0, b'{"done":true,"missing":[]}\n')
    fixture_path.write_text("{}", encoding="utf-8")
    code, line = fin.check_done(str(fixture_path))
    assert code == 1
    assert json.loads(line)["missing"] == [
        "ci_green",
        "not_draft",
        "reviewed",
        "threads_resolved",
    ]

    # The jq program is the twin's, so the comment inside it is too.
    assert "NOT `.draft // true | not`" in fin.DONE_PROGRAM


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_rerun_of_every_job_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `gh run rerun <id> --failed` reruns the failed jobs of a run; without `--failed` it reruns EVERY job, which on the review pipeline means paying for the whole matrix again and re-reporting jobs that already passed. The fake answers the same bytes either way, so the exit code, the empty stdout and the "rerun requested" line are identical and only the `--- gh calls ---` section
    sees the change. The mutation runs from a throwaway copy of the module, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '            ["run", "rerun", run_id, "--repo", repo, "--failed"],\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant_source = original.replace(
        anchor, '            ["run", "rerun", run_id, "--repo", repo],\n'
    )

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutant_source, encoding="utf-8")

    name = "a-rerun-review"
    want = recorded(name)
    assert want[3].endswith("--failed\n"), "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert planted[3] != want[3], "the plant did not change the call log"
    assert not planted[3].endswith("--failed\n")
    for index in (0, 1, 2):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
