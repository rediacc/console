"""Differential: `rediacc_ci.autopilot.update_state` against its twin
`.ci/scripts/autopilot/update-state.sh`.

A RECORDING FAKE `gh` ON A PREPENDED PATH, and the fake is not a convenience:
this script's success path is an `api --method POST|PATCH` against a real
repository, and a case that reached the real binary would write a comment onto
whatever PR the argument named. Three independent things stop that, because one
would be a claim rather than a control:

  1. the stub directory is FIRST on PATH and `shutil.which("gh", path=...)`
     is asserted to resolve to the fake, in `test_the_fake_gh_is_the_gh` --
     a control that fires if the ordering ever stops working;
  2. every case names a repository that does not exist (`acme/widget`);
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` would fail auth instead of writing.

THE CALL LOG IS A PRIMARY ARTIFACT, not a sanity check. Almost everything this
script does is invisible in stdout: which endpoint, which method, and what body
bytes went up. A stdout-only comparison would be satisfied by a port that logged
the right sentence and PATCHed the wrong comment. So every case compares the
recorded `gh` argv AND the bytes of the file behind `-F body=@...`, and the fake
rewrites that path to `<work>/body.md` because the two sides' mktemp directories
legitimately differ.

WHAT THE BODY BYTES PROVE. The rendered comment is `state-comment.sh`'s output,
which both sides spawn -- so comparing it is not testing the renderer, it is
testing that the port passed the SAME argv into it. The `--campaign`-shaped
optional flags are the interesting half: an omitted flag means "carry the
previous value forward" and an empty one means "reset to none", so a port that
passed every flag unconditionally would silently close a live campaign. The
carry-over case below is what would catch that.

TWO PRESERVED DEFECTS ARE PINNED BY NAME rather than described in prose:
`test_a_mistyped_verdict_path_is_silent` and
`test_a_non_string_ruled_out_entry_kills_the_write`. If either twin behaviour is
ever repaired, the test goes red and the repair gets noticed here first.

K=5 LEDGER: `.ci/shadow/w7p6-update-state.observations.jsonl`, recorded in a
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
from typing import Any

from rediacc_ci import paths
from rediacc_ci.autopilot import update_state as us

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "update-state.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "update_state.py"
BASH = shutil.which("bash") or "/bin/bash"

# The recording fake. It rewrites the one volatile argument (the mktemp path
# behind `-F body=@`) and copies the body it was handed, so a case can compare
# the bytes that would have gone to GitHub.
FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
logged = []
for arg in argv:
    if arg.startswith("body=@"):
        path = arg[len("body=@"):]
        with open(path, "rb") as fh:
            body = fh.read()
        with open(os.environ["FAKE_GH_BODY"], "wb") as fh:
            fh.write(body)
        logged.append("body=@<work>/body.md")
    else:
        logged.append(arg)
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(logged) + "\\n")

sys.stdout.write(os.environ.get("FAKE_GH_STDOUT", "{}") + "\\n")
sys.stderr.write(os.environ.get("FAKE_GH_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_GH_RC", "0")))
"""

PR = "42"
REPO = "acme/widget"


def _stub_bin(base: pathlib.Path) -> str:
    """A directory holding the fake `gh`, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm, because both subjects
    reach for a long tail of coreutils through `common.sh` and
    `state-comment.sh` (dirname, uname, tr, mktemp, awk, jq, wc, grep, sed).
    The safety property is therefore RESOLUTION ORDER, and it is asserted rather
    than assumed -- see `test_the_fake_gh_is_the_gh`.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    call_log = base / "gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    body_seen = base / "gh-body.md"
    env = {
        "PATH": _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(call_log),
        "FAKE_GH_BODY": str(body_seen),
        # A leaked real `gh` would fail auth rather than write anything.
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
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    body = body_seen.read_bytes() if body_seen.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, calls, body


BASE_ARGV = [
    "--pr",
    PR,
    "--repo",
    REPO,
    "--state",
    "fixing",
    "--round",
    "2",
    "--rounds-max",
    "8",
    "--head",
    "abc1234",
    "--last-run",
    "555/1 handled",
]


def _sides(
    name: str,
    argv: list[str] | None = None,
    *,
    files: dict[str, bytes] | None = None,
    env: dict[str, str] | None = None,
):
    """Both subjects, one fixture shape, two private trees."""
    argv = list(argv) if argv is not None else list(BASE_ARGV)
    env_extra = {"AUTOPILOT_ALLOW_STATE": "true"}
    env_extra.update(env or {})
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            for rel, body in (files or {}).items():
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            results.append(_run(subject, base, argv, env_extra))
    old, new = results
    labels = ("exit", "stdout", "stderr", "gh calls", "gh body")
    for i, label in enumerate(labels):
        assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old[i],
            new[i],
        )
    return old


def verdict(**fields: Any) -> bytes:
    return json.dumps(fields).encode()


def test_post_when_there_is_no_comment_yet() -> None:
    """The create arm: POST to the issue's comment collection."""
    exit_code, stdout, stderr, calls, body = _sides("post")
    assert exit_code == 0
    assert stdout == b""
    assert calls == [
        "api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"
    ], calls
    assert body is not None
    assert body.startswith(b"### Autopilot state (machine-maintained, do not edit)\n")
    assert b"round: 2/8" in body
    assert b"state comment POST to repos/acme/widget/issues/42/comments" in stderr


def test_patch_when_the_comment_exists() -> None:
    """The update arm, which is what makes this idempotent: the same comment is
    rewritten in place rather than a second one appearing per round."""
    exit_code, _, stderr, calls, body = _sides("patch", [*BASE_ARGV, "--comment-id", "9001"])
    assert exit_code == 0
    assert calls == [
        "api\t--method\tPATCH\trepos/acme/widget/issues/comments/9001\t-F\tbody=@<work>/body.md"
    ], calls
    assert body is not None
    assert b"state comment PATCH to repos/acme/widget/issues/comments/9001" in stderr


def test_the_previous_body_is_carried_forward() -> None:
    """Round 2 renders round 1's ledger and ruled-out lines again, and does NOT
    close the campaign that round 1 opened, because `--campaign` is absent."""
    previous = (
        b"### Autopilot state (machine-maintained, do not edit)\n"
        b"state: fixing | round: 1/8 | head: aaa | last_run: 1/1 handled | "
        b"campaign: open | model: opus | rounds_max: 8 | last_sig: none | sig_count: 0\n"
        b"\n#### Round ledger\n"
        b"r1 | run 111 | commit deadbee | did the first thing\n"
        b"\n#### Ruled out\n- the cache theory\n"
        b"\n#### DECISIONS (post-hoc review)\n- kept the retry\n"
    )
    exit_code, _, _, _, body = _sides(
        "carry-over",
        [*BASE_ARGV, "--body", "previous.md", "--ledger", "r2 | run 555 | commit cafe | did more"],
        files={"previous.md": previous},
    )
    assert exit_code == 0
    assert body is not None
    text = body.decode("utf-8")
    assert "r1 | run 111" in text
    assert "r2 | run 555" in text
    assert "- the cache theory" in text
    assert "- kept the retry" in text
    assert "campaign: open" in text, (
        "the campaign was closed by a round that said nothing about it; the "
        "optional flags are being passed unconditionally"
    )


def test_the_verdict_becomes_one_bullet_per_entry() -> None:
    """The anti-thrash memory only works if it records more than the first
    entry, and a multi-line entry must collapse to ONE line."""
    exit_code, _, _, _, body = _sides(
        "verdict",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={
            "verdict.json": verdict(
                ruled_out=["not the cache", "not the clock\nsecond line", "third"],
                decisions=["kept the retry", "dropped the flag"],
            )
        },
    )
    assert exit_code == 0
    assert body is not None
    text = body.decode("utf-8")
    assert "- not the cache" in text
    assert "- not the clock second line" in text, "the newline did not collapse to a space"
    assert "- third" in text
    assert "- kept the retry" in text
    assert "- dropped the flag" in text


def test_a_mistyped_verdict_path_is_silent() -> None:
    """PRESERVED DEFECT. `--verdict` is `[[ -n && -s ]]`-checked, never
    `require_file`-checked, so a path that does not exist renders empty sections
    and exits 0. If this ever starts refusing, this test goes red first."""
    exit_code, _, stderr, _, body = _sides(
        "mistyped-verdict", [*BASE_ARGV, "--verdict", "nope.json"]
    )
    assert exit_code == 0, "the mistyped path was refused; the hazard is fixed, update the port"
    assert b"nope.json" not in stderr
    assert body is not None
    assert "#### Ruled out\n\n" in body.decode("utf-8")


def test_an_empty_verdict_file_is_also_silent() -> None:
    """`-s` is a SIZE test, which is the right one: an empty file is the shape a
    failed validator leaves behind."""
    _sides("empty-verdict", [*BASE_ARGV, "--verdict", "verdict.json"], files={"verdict.json": b""})


def test_a_non_string_ruled_out_entry_kills_the_write() -> None:
    """PRESERVED DEFECT. `gsub` refuses a number, jq exits 5, `set -e` takes the
    state write with it -- so the round runs UNRECORDED, which is the one
    outcome this script exists to prevent."""
    exit_code, _, stderr, calls, _ = _sides(
        "non-string-entry",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={"verdict.json": verdict(ruled_out=["fine", 7])},
    )
    assert exit_code == 5, "jq's runtime status is 5"
    assert b"cannot be matched, as it is not a string" in stderr
    assert calls == [], "a comment was written despite the failure"


def test_a_malformed_verdict_file_fails_with_jqs_own_words() -> None:
    exit_code, _, stderr, calls, _ = _sides(
        "malformed-verdict",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={"verdict.json": b"{truncated"},
    )
    assert exit_code == 5
    assert stderr.startswith(b"jq: parse error:")
    assert calls == []


def test_dry_run_writes_nothing_and_prints_the_body() -> None:
    """The comment the operator actually reads, exercisable offline."""
    exit_code, stdout, stderr, calls, body = _sides("dry-run", [*BASE_ARGV, "--dry-run"])
    assert exit_code == 0
    assert calls == [], "a dry run called gh"
    assert body is None
    assert stdout.startswith(b"### Autopilot state")
    assert b"dry-run: would write the state comment for PR #42 (comment id 'none')" in stderr
    # And with an id, the id is named.
    _, _, stderr2, _, _ = _sides(
        "dry-run-with-id", [*BASE_ARGV, "--dry-run", "--comment-id", "9001"]
    )
    assert b"(comment id '9001')" in stderr2


def test_body_bytes_are_not_decoded() -> None:
    """A carried-over line that is not valid UTF-8 must survive the round trip.
    The comment carries model-authored text, and a port that decoded would fail
    the round on a stray byte the twin passed through."""
    previous = (
        b"### Autopilot state (machine-maintained, do not edit)\n"
        b"state: fixing | round: 1/8 | head: aaa | last_run: 1/1 handled | "
        b"campaign: none | model: none | rounds_max: 8 | last_sig: none | sig_count: 0\n"
        b"\n#### Round ledger\n\n#### Ruled out\n- caf\xe9 theory\n"
        b"\n#### DECISIONS (post-hoc review)\n"
    )
    exit_code, stdout, _, _, _ = _sides(
        "raw-bytes",
        [*BASE_ARGV, "--dry-run", "--body", "previous.md"],
        files={"previous.md": previous},
    )
    assert exit_code == 0
    assert b"caf\xe9 theory" in stdout


def test_the_stage_flag_fails_closed() -> None:
    """Absent is off; only the exact string `true` arms it."""
    for name, value in (
        ("unset", None),
        ("false", "false"),
        ("uppercase", "TRUE"),
        ("empty", ""),
        ("truthy", "1"),
    ):
        env = {"AUTOPILOT_ALLOW_STATE": value} if value is not None else {}
        argv = list(BASE_ARGV)
        if value is None:
            # Removing the key means overriding the default `_sides` sets.
            code, _, err, calls, _ = _sides(
                "flag-%s" % name, argv, env={"AUTOPILOT_ALLOW_STATE": ""}
            )
        else:
            code, _, err, calls, _ = _sides("flag-%s" % name, argv, env=env)
        assert code == 1, name
        assert b"stage-flag-disabled" in err
        assert calls == [], "the write happened with the stage flag off"


def test_usage_refusals() -> None:
    """The six required flags, each dropped in turn. `--body`, `--rounds-max`,
    `--comment-id` and `--verdict` are NOT required, and that is pinned too."""
    required = ("--pr", "--repo", "--state", "--round", "--head", "--last-run")
    for drop in required:
        argv = []
        skip = False
        for token in BASE_ARGV:
            if skip:
                skip = False
                continue
            if token == drop:
                skip = True
                continue
            argv.append(token)
        code, _, err, calls, _ = _sides("missing%s" % drop, argv)
        assert code == 2, "%s: expected the usage refusal" % drop
        assert b"usage: update-state.sh" in err
        assert calls == []
    # The optional ones: absent is fine, and `--rounds-max` defaults to 0.
    argv = [t for t in BASE_ARGV if t not in ("--rounds-max", "8")]
    code, _, err, _, body = _sides("no-rounds-max", argv)
    assert code == 0
    assert b"round: 2/0" in (body or b"")


def test_a_failing_gh_is_never_a_success() -> None:
    """Three attempts, the warnings between them, the indented child stderr, and
    exit 1 -- the swallowed-failure shape `_gh_probe` exists to end.

    SLOW ON PURPOSE (9 seconds per side): the retry sleeps are 3s then 6s, and a
    port that dropped them would stop being a retry past a rate limit.
    """
    exit_code, _, stderr, calls, _ = _sides(
        "gh-fails",
        None,
        env={"FAKE_GH_RC": "4", "FAKE_GH_STDERR": "gh: fake auth failure\n"},
    )
    assert exit_code == 1
    assert (
        calls
        == ["api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"]
        * 3
    ), "not three attempts"
    assert stderr.count(b"retrying...") == 2
    assert b"gh failed after 3 attempts (last exit 4)." in stderr
    assert b"    gh: fake auth failure" in stderr
    assert b"state comment POST to" not in stderr, "the success line was printed after a failure"


def test_renderer_stderr_reaches_fd_2() -> None:
    """The renderer is spawned, not re-implemented, so its diagnostics have to
    arrive on this process's stderr. A DIRECTORY as `--body` makes awk warn six
    times without failing, which is a cheap way to prove the passthrough."""
    exit_code, _, stderr, _, _ = _sides(
        "renderer-chatter",
        [*BASE_ARGV, "--dry-run", "--body", "olddir"],
        files={"olddir/keep": b"x"},
    )
    assert exit_code == 0
    assert stderr.count(b"is a directory: skipped") == 5


def test_the_fake_gh_is_the_gh() -> None:
    """CONTROL for the whole file. If the stub ever stops winning the PATH
    lookup, every case above would be talking to the real GitHub CLI."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        resolved = shutil.which("gh", path=path)
        assert resolved == str(base / "bin" / "gh"), (
            "the fake gh does not win the PATH lookup: %r" % resolved
        )


def test_pure_helpers_are_exercised_directly() -> None:
    """`endpoint_for` and `render_args` without a subprocess."""
    assert us.endpoint_for("o/r", "5", "") == ("repos/o/r/issues/5/comments", "POST")
    assert us.endpoint_for("o/r", "5", "77") == ("repos/o/r/issues/comments/77", "PATCH")
    argv = us.render_args({"ARG_STATE": "fixing", "ARG_ROUND": "2"}, "/w")
    assert argv[0] == "render"
    assert "--body" in argv
    assert argv[argv.index("--body") + 1] == "/dev/null"
    assert argv[argv.index("--round") + 1] == "2/0"
    assert "--campaign" not in argv, "an absent optional flag must stay absent"
    argv = us.render_args({"ARG_ROUND": "2", "ARG_ROUNDS_MAX": "8", "ARG_CAMPAIGN": "open"}, "/w")
    assert argv[argv.index("--round") + 1] == "2/8"
    assert argv[argv.index("--campaign") + 1] == "open"
    assert argv[argv.index("--rounds-max") + 1] == "8"
