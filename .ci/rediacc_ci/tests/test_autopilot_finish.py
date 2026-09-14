"""Differential: `rediacc_ci.autopilot.finish` against its twin
`.ci/scripts/autopilot/finish.sh`.

A DECISION TREE, SO EVERY BRANCH GETS A CASE. This subject has three
subcommands, an unknown-subcommand arm, a usage refusal per subcommand, a
fail-closed write gate, two `gh` pipelines and jq's own exit codes leaking
through `set -e`. The cases below walk each of them, and the ones that pin the
EXIT CODE rather than the message are the load-bearing half: 0 and 1 out of
`check-done` are how the babysit loop decides whether to stop, and 5 out of a
broken pipeline is jq's, not this script's.

A RECORDING FAKE `gh` ON A STUB PATH, as in
`test_housekeeping_cleanup_github_deployments.py`. Nothing reaches the network,
and `test_the_stub_path_has_no_real_gh` is the control for that rather than a
comment claiming it. THE CALL LOG IS COMPARED, not just the streams: this
script's whole effect on the world is which requests it makes, and a port that
flipped the right PR in the wrong repository would print an identical summary.

THE WRITE GATE IS TESTED FROM BOTH SIDES, and the negative side is the one that
matters: `test_the_write_gate_is_closed_by_default` asserts that NO `gh` call
was recorded, because "it printed the refusal" is not the same claim as "it did
not write".

ONE CASE COSTS NINE SECONDS PER SIDE. `_gh_probe` sleeps 3 then 6 between its
three attempts, and it is the only way to prove the retry loop, the final
`gh failed after 3 attempts` line and the exit code agree.

K=5 LEDGER: `.ci/shadow/w7p6-finish.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout, since
`shadow-gate.ts --record` refuses a dirty tree and this checkout is never
clean.
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
from rediacc_ci.autopilot import finish as fin

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "finish.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "finish.py"
BASH = shutil.which("bash") or "/bin/bash"

# `tr` is here because `parse_args` shells out to `to_upper` once per flag, and
# `sleep` because `_gh_probe`'s backoff is an external command: without it the
# twin dies at 127 on every retry case while the port sails through.
# `mktemp` and `rm` are `_gh_probe`'s scratch file for gh's stderr, and their
# absence shows up as a 127 from the twin on every gh path.
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


def _stub_path(base: pathlib.Path, *, with_gh: bool = True) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
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


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], **extra: str):
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_path(base),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
    }
    env.update(extra)
    # `sys.executable`, not "python3": the stub PATH has no interpreter on it.
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def _sides(name: str, argv: list[str], *, fixtures: dict[str, bytes] | None = None, **extra: str):
    with tempfile.TemporaryDirectory() as td:
        results = []
        # "old"/"new", NOT `subject.stem`: both subjects are called `finish`
        # here (`finish.sh` and `finish.py` share a stem), so a stem-named
        # directory makes the second side collide with the first.
        for side, subject in (("old", TWIN), ("new", PORT)):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            for rel, data in (fixtures or {}).items():
                (base / rel).write_bytes(data)
            results.append(_run(subject, base, argv, **extra))
        old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\n twin stderr: %r\n port stderr: %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\nold %r\nnew %r" % (name, old[1], new[1])
    assert new[2] == old[2], "%s: stderr diverged:\nold %r\nnew %r" % (name, old[2], new[2])
    assert new[3] == old[3], "%s: gh calls diverged:\nold %r\nnew %r" % (name, old[3], new[3])
    return old


def _fixture(**fields: object) -> dict[str, bytes]:
    return {"pr.json": json.dumps(fields).encode("utf-8") + b"\n"}


DONE = {"ci_green": True, "draft": False, "reviewed": True, "unresolved_threads": 0}


def test_the_stub_path_has_no_real_gh() -> None:
    """CONTROL. Every write case's "no network" claim rests on this."""
    with tempfile.TemporaryDirectory() as td:
        without = _stub_path(pathlib.Path(td), with_gh=False)
        assert shutil.which("gh", path=without) is None, "gh leaked into the stub PATH"
        assert shutil.which("jq", path=without) is not None, "the stub PATH is not usable"


def test_check_done_when_everything_is_met() -> None:
    exit_code, stdout, stderr, calls = _sides(
        "done", ["check-done", "--pr", "pr.json"], fixtures=_fixture(**DONE)
    )
    assert exit_code == 0
    assert stdout == b'{"done":true,"missing":[]}\n', stdout
    assert stderr == b""
    assert calls == [], "check-done is PURE: it must not call gh"


def test_check_done_names_every_unmet_condition() -> None:
    """`missing` is the diagnosis, so its CONTENT and ORDER are the contract."""
    exit_code, stdout, _, _ = _sides(
        "none-met", ["check-done", "--pr", "pr.json"], fixtures=_fixture()
    )
    assert exit_code == 1
    assert stdout == (
        b'{"done":false,"missing":["ci_green","not_draft","reviewed","threads_resolved"]}\n'
    ), stdout
    # One condition at a time, so a port that collapsed them all into one flag
    # would fail here rather than on the all-or-nothing cases.
    for field, missing in (
        ("ci_green", b'["ci_green"]'),
        ("draft", b'["not_draft"]'),
        ("reviewed", b'["reviewed"]'),
        ("unresolved_threads", b'["threads_resolved"]'),
    ):
        broken = dict(DONE)
        broken[field] = (
            True if field == "draft" else (2 if field == "unresolved_threads" else False)
        )
        code, out, _, _ = _sides(
            "missing-%s" % field, ["check-done", "--pr", "pr.json"], fixtures=_fixture(**broken)
        )
        assert code == 1, field
        assert out == b'{"done":false,"missing":%s}\n' % missing, (field, out)


def test_check_done_fails_closed_on_an_absent_draft_field() -> None:
    """The twin's own comment: NOT `.draft // true | not`. A PR whose fixture
    never mentions `draft` is NOT done, and a non-draft PR (`draft: false`) is
    not read as a draft. Both directions, because only one of them catches the
    `//` bug the comment describes."""
    absent = dict(DONE)
    del absent["draft"]
    code, out, _, _ = _sides(
        "draft-absent", ["check-done", "--pr", "pr.json"], fixtures=_fixture(**absent)
    )
    assert (code, out) == (1, b'{"done":false,"missing":["not_draft"]}\n'), out
    code, out, _, _ = _sides(
        "draft-false", ["check-done", "--pr", "pr.json"], fixtures=_fixture(**DONE)
    )
    assert (code, out) == (0, b'{"done":true,"missing":[]}\n'), out


def test_check_done_unresolved_threads_defaults_to_one() -> None:
    """`(.unresolved_threads // 1) == 0`: silence means UNRESOLVED, not zero."""
    absent = dict(DONE)
    del absent["unresolved_threads"]
    code, out, _, _ = _sides(
        "threads-absent", ["check-done", "--pr", "pr.json"], fixtures=_fixture(**absent)
    )
    assert (code, out) == (1, b'{"done":false,"missing":["threads_resolved"]}\n'), out


def test_check_done_on_a_fixture_jq_cannot_read() -> None:
    """jq's exit code, not this script's: `set -e` ends the run at 5 and
    nothing is printed to stdout."""
    exit_code, stdout, stderr, _ = _sides(
        "bad-json", ["check-done", "--pr", "pr.json"], fixtures={"pr.json": b"not json\n"}
    )
    assert exit_code == 5, exit_code
    assert stdout == b""
    assert b"jq: parse error: Invalid numeric literal" in stderr, stderr


def test_check_done_refusals() -> None:
    exit_code, _, stderr, _ = _sides("no-fixture", ["check-done", "--pr", "nope.json"])
    assert exit_code == 1
    assert b"Required file 'nope.json' does not exist" in stderr
    exit_code, _, stderr, _ = _sides("no-flag", ["check-done"])
    assert exit_code == 2
    assert b"usage: finish.sh check-done --pr <fixture.json>" in stderr
    assert _sides("empty-flag", ["check-done", "--pr="])[0] == 2


def test_unknown_subcommands() -> None:
    """Including the empty one, which is what NO arguments produces."""
    exit_code, _, stderr, calls = _sides("frobnicate", ["frobnicate"])
    assert exit_code == 2
    assert b"unknown subcommand 'frobnicate' (check-done|ready-flip|rerun-review)" in stderr
    assert calls == []
    exit_code, _, stderr, _ = _sides("no-args", [])
    assert exit_code == 2
    assert b"unknown subcommand '' (check-done|ready-flip|rerun-review)" in stderr
    # A FLAG in the subcommand slot is a subcommand, not a flag: `parse_args`
    # never sees `$1`.
    exit_code, _, stderr, _ = _sides("flag-first", ["--pr", "pr.json"], fixtures=_fixture(**DONE))
    assert exit_code == 2
    assert b"unknown subcommand '--pr'" in stderr


def test_the_write_gate_is_closed_by_default() -> None:
    """FAIL CLOSED, and the assertion that matters is `calls == []`: the
    refusal message is not evidence that nothing was written."""
    for argv in (
        ["ready-flip", "--pr", "5", "--repo", "r/c"],
        ["rerun-review", "--pr", "5", "--repo", "r/c"],
    ):
        exit_code, _, stderr, calls = _sides("closed-%s" % argv[0], argv)
        assert exit_code == 1, argv
        assert b"stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'" in stderr
        assert calls == [], "the write gate let a gh call through: %r" % calls
    # Anything that is not exactly `true` is closed, including `TRUE` and `1`.
    for value in ("", "1", "TRUE", "yes"):
        code, _, _, calls = _sides(
            "closed-%r" % value,
            ["ready-flip", "--pr", "5", "--repo", "r/c"],
            AUTOPILOT_ALLOW_PUSH=value,
        )
        assert (code, calls) == (1, []), value


def test_the_usage_refusal_comes_before_the_write_gate() -> None:
    """ORDER, not just outcome: a missing `--repo` is exit 2 even with the
    stage flag off, so a caller cannot mistake a typo for a closed stage."""
    for argv in (["ready-flip", "--pr", "5"], ["ready-flip", "--repo", "r/c"]):
        exit_code, _, stderr, calls = _sides("usage-%s" % len(argv), argv)
        assert exit_code == 2, argv
        assert b"usage: finish.sh ready-flip --pr <number> --repo <owner/name>" in stderr
        assert calls == []
    for argv in (["rerun-review", "--pr", "5"], ["rerun-review", "--repo", "r/c"]):
        exit_code, _, stderr, _ = _sides("usage-rerun-%s" % len(argv), argv)
        assert exit_code == 2, argv
        assert b"usage: finish.sh rerun-review --pr <number> --repo <owner/name>" in stderr


def test_ready_flip_when_the_gate_is_open() -> None:
    exit_code, stdout, stderr, calls = _sides(
        "ready",
        ["ready-flip", "--pr", "5", "--repo", "rediacc/console"],
        AUTOPILOT_ALLOW_PUSH="true",
        FAKE_READY_OUT="marked ready\n",
        FAKE_READY_ERR="gh: some progress chatter\n",
    )
    assert exit_code == 0
    # `gh_retry`'s `printf '%s'`: gh's stdout with its trailing newline
    # STRIPPED by the command substitution and none added back.
    assert stdout == b"marked ready", stdout
    assert b"PR #5 flipped ready for review" in stderr
    # gh's own stderr is CAPTURED by the probe and dropped on success.
    assert b"some progress chatter" not in stderr, stderr
    assert calls == ["pr\tready\t5\t--repo\trediacc/console"], calls


def test_rerun_review_walks_head_then_run_then_rerun() -> None:
    exit_code, stdout, stderr, calls = _sides(
        "rerun",
        ["rerun-review", "--pr", "5", "--repo", "rediacc/console"],
        AUTOPILOT_ALLOW_PUSH="true",
    )
    assert exit_code == 0
    assert stdout == b""
    assert b"review run 4242 rerun requested for PR #5" in stderr
    assert len(calls) == 3, calls
    assert calls[0].startswith("api\trepos/rediacc/console/pulls/5\t--jq\t{sha: .head.sha}")
    # The head sha from call 1 is what call 2 queries with. A port that dropped
    # it would still make three calls.
    assert "head_sha=deadbeef&event=pull_request" in calls[1], calls[1]
    assert calls[2] == "run\trerun\t4242\t--repo\trediacc/console\t--failed"


def test_rerun_review_when_no_review_run_exists() -> None:
    """`first` over an empty list is `null`, which jq prints as the STRING
    `null`. Both spellings of "nothing" are refused."""
    for label, body in (("null-id", '{"id":null}'), ("empty-id", '{"id":""}')):
        exit_code, _, stderr, calls = _sides(
            label,
            ["rerun-review", "--pr", "5", "--repo", "r/c"],
            AUTOPILOT_ALLOW_PUSH="true",
            FAKE_RUN=body,
        )
        assert exit_code == 1, label
        assert b"rerun-review: no review-pipeline run found for head deadbeef" in stderr
        assert len(calls) == 2, "it must not rerun anything: %r" % calls


def test_rerun_review_when_the_body_cannot_be_indexed() -> None:
    """jq's 5 through `pipefail`, not a refusal of this script's own."""
    exit_code, _, stderr, calls = _sides(
        "head-array",
        ["rerun-review", "--pr", "5", "--repo", "r/c"],
        AUTOPILOT_ALLOW_PUSH="true",
        FAKE_HEAD="[]",
    )
    assert exit_code == 5, exit_code
    assert b"Cannot index array with" in stderr, stderr
    assert len(calls) == 1, calls


def test_slow_a_failing_flip_retries_three_times_and_replays_its_stderr() -> None:
    """18 seconds, and the only case that proves the `_gh_probe` loop: two
    warnings, the final error carrying the last exit code, and gh's captured
    stderr replayed indented four spaces."""
    exit_code, stdout, stderr, calls = _sides(
        "flip-fails",
        ["ready-flip", "--pr", "5", "--repo", "r/c"],
        AUTOPILOT_ALLOW_PUSH="true",
        FAKE_READY_RC="4",
        FAKE_READY_ERR="gh: HTTP 401 Bad credentials\n",
    )
    assert exit_code == 1
    assert stdout == b""
    assert calls == ["pr\tready\t5\t--repo\tr/c"] * 3, calls
    assert b"ready-flip: gh failed after 3 attempts (last exit 4)." in stderr
    assert stderr.endswith(b"    gh: HTTP 401 Bad credentials\n"), stderr
    assert b"flipped ready" not in stderr


def test_pure_helpers_are_exercised_directly() -> None:
    """The helpers, without a subprocess, in BOTH directions."""
    assert fin.require_write_flag({"AUTOPILOT_ALLOW_PUSH": "true"}) is True
    assert fin.require_write_flag({"AUTOPILOT_ALLOW_PUSH": "TRUE"}) is False
    assert fin.require_write_flag({}) is False

    assert fin._json_usable(b'{"sha":"x"}') is True
    assert fin._json_usable(b"null") is False, "jq -e's rule, not json.loads'"
    assert fin._json_usable(b"") is False

    with tempfile.TemporaryDirectory() as td:
        fixture = pathlib.Path(td) / "pr.json"
        fixture.write_text(json.dumps(DONE), encoding="utf-8")
        assert fin.check_done(str(fixture)) == (0, b'{"done":true,"missing":[]}\n')
        fixture.write_text("{}", encoding="utf-8")
        code, line = fin.check_done(str(fixture))
        assert code == 1
        assert json.loads(line)["missing"] == [
            "ci_green",
            "not_draft",
            "reviewed",
            "threads_resolved",
        ]

    # The jq program is the twin's, so the comment inside it is too.
    assert "NOT `.draft // true | not`" in fin.DONE_PROGRAM
